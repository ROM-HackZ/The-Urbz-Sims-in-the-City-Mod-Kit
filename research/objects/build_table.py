"""Build objects.json + objects.md: object number -> actions -> motive effect rows.
Inputs: analysis.json (analyze.py), dispatch.json (emu_dispatch.py), area data (../areas/area_parse.py)."""
import json, sys, collections
from common import *
import analyze as AN
sys.path.insert(0, '/root/urbz/agentwork/areas')
import area_parse as AP

A = json.load(open('analysis.json'))
D = json.load(open('dispatch.json'))
QMULT = [s32(0x020EA998 + 4 * i) / 16777216 for i in range(6)]
PAGES = {0: 'Appliances', 1: 'Decorative', 2: 'Electronics', 3: 'Furniture', 4: 'Hobbies', 5: 'Utilities', 6: 'page 6', 7: 'not sold'}

# How long each effect runs (read from the decompile; 'until X full' = FUN_020691d0(state, needs, X, timer):
# keeps going while need X < 100, then counts the timer at sim+0x108 down).
ENDS = {
    '02015b24': 'fixed 150 ticks (sim+0x10e=0x96), after a 150-tick grill phase',
    '0204f5fc': 'meals (Breakfast/Lunch/Dinner): row 19 for 150 ticks; snacks (Snack/Late-Night Snack): row 20 for 60 ticks',
    '0207a5ac': 'fixed 60 ticks (sim+0x10e=0x3c)',
    '0209ec20': 'fixed ticks (sim+0x10e countdown)',
    '02036f00': 'fixed ticks (sim+0x10e countdown)',
    '02077c44': 'fixed ticks (sim+0x10e countdown)',
    '0208a4fc': 'fixed ticks (sim+0x10e countdown)',
    '0208a1ec': 'fixed ticks (sim+0x10e countdown)',
    '020ad5c4': 'while the eat animation plays',
    '020ad854': 'while the drink animation plays',
    '02031534': 'while the drink animation plays',
    '02030a44': 'while the drink animation plays',
    '02082da0': 'until hygiene is 100, then 150 more ticks',
    '020abd88': 'until bladder is 100, then 90 more ticks',
    '02086fb0': 'fixed ticks (sim+0x108 countdown)',
    '020a60cc': 'until fun is 100 (then timer)',
    '0206b90c': 'until energy is 100, then 90 ticks; between 23:00 and 04:59 it does not stop on its own; the player\'s sleep fast-forwards the clock (FUN_020840f4(1))',
    '0206b6d0': 'until energy is 100 (then timer); player nap fast-forwards the clock',
    '0206bba4': 'until comfort is 100 (then timer)',
    '0206be3c': 'until comfort is 100, then 90 ticks',
    '0202afbc': 'until fun is 100 (then timer)',
    '020330e8': 'fixed ticks (sim+0x108 countdown)',
    '02023398': 'fixed ticks (sim+0x10e countdown)',
    '02035e68': 'until fun is 100, then 150 ticks',
    '020887a8': 'until fun is 100 (then timer)',
    '020892c0': 'fixed ticks (sim+0x10e countdown)',
    '0202c154': 'fixed ticks (sim+0x108 countdown)',
    '0202e9cc': 'until fun is 100 (then timer)',
    '02061d0c': 'fixed ticks (sim+0x10e countdown)',
    '020ac82c': 'until fun is 100 (then timer)',
    '020ad058': 'until fun is 100 (then timer)',
    '02082904': 'until bladder is 100 (row 58 raises every need)',
    '0206ab4c': 'until fun is 100 (then timer)',
    '0206a6a0': 'while cleaning (until the object is clean)',
    '0206b42c': 'while repairing (until the repair meter is done)',
    '0206c1d0': 'skill practice: ticks until the skill point / stop',
    '0206c2b8': 'skill practice: ticks until the skill point / stop',
    '0206a3f4': 'while admiring/viewing',
    '020128f0': 'while cleaning', '020793f4': 'while cleaning', '02041ee0': 'fixed ticks (sim+0x10e countdown)',
}

def row_entry(row, quality, site, func, via):
    v = effect_row(row)
    m = QMULT[quality] if quality is not None and quality < 6 else 1.0
    return dict(row=row, per_tick={NEEDS[i]: round(x, 4) for i, x in enumerate(v) if x},
                per_tick_scaled={NEEDS[i]: round(x * m, 4) for i, x in enumerate(v) if x},
                site=site, func=func, via=via, ends=ENDS.get(func) or ENDS.get(via[7:15] if via.startswith('helper') else '', ''))

def expand(e, q):
    rows = e['row'] if isinstance(e['row'], list) else [e['row']]
    return [row_entry(r, q, e['site'], e['func'], e['via']) for r in rows if r is not None]

def effects_for(fns, q):
    cl = AN.closure([int(f, 16) for f in fns])
    out = []
    for e in AN.effects_in(cl, q):
        # skip the duplicate "direct" entry for a call inside a helper we already expanded
        if e['via'] == 'direct' and int(e['func'], 16) in AN.HELPERS and any(x['via'].startswith('helper ' + e['func']) for x in AN.effects_in(cl, q)):
            continue
        out += expand(e, q)
    return out

objects = []
for o in A:
    n = o['object']
    rec = dict(object=n, name=o['name'], name_string=o['name_string'], desc_string=o['desc_string'], model=o['model'],
               catalog_page=o['catalog_page'], catalog=PAGES.get(o['catalog_page'], str(o['catalog_page'])), price=o['price'])
    if 'descriptor' in o:
        q = o['quality_index']
        rec.update(descriptor=o['descriptor'], slots=o['slots'], quality_index=q, quality_mult=QMULT[q] if q < 6 else None)
        dd = D.get(str(n))
        acts = []
        import emu_dispatch as ED
        ids = list(dd['actions']) if dd else []
        for a in o.get('actions', []):
            if a['id'] not in ids: ids.append(a['id'])
        for a in ids:
            act = AN.action(a)
            hs = (dd or {}).get('handlers', {}).get(str(a))
            if hs is None:
                hs = ['%08x' % c for c in ED.handlers(int(o['slots']['update'], 16), a)]
            act['handlers'] = hs
            effs = []
            for h in hs:
                if int(h, 16) in AN.HELPERS:
                    effs += [x for e in o.get('effects', []) if e['via'].startswith('helper ' + h) for x in expand(e, q)]
                else:
                    effs += effects_for([h], q)
            SITE_ACTS = {'0204f840': (30, 32, 34), '0204f898': (33, 35)}   # microwave: meals vs snacks (decompile 0x0204F6xx)
            effs = [e for e in effs if e['site'] not in SITE_ACTS or a in SITE_ACTS[e['site']]]
            act['effects'] = effs
            acts.append(act)
        if n in (117, 118):   # arcade: list fn reads table 0x020C5F7C {u32 object, u32 action, .., +0x10 row}
            k = n - 117
            a = u32(0x020C5F84 + 0x20 * k)
            act = AN.action(a); act['handlers'] = ['02035e68']
            act['effects'] = [row_entry(u32(0x020C5F8C + 0x20 * k), q, '02035fe0', '02035e68', 'arcade table 0x020C5F7C')]
            acts.append(act)
        rec['actions'] = acts
        rec['all_effects_reachable'] = [x for e in o.get('effects', []) for x in expand(e, q)]
    else:
        # inventory item: consumable table 0x020C1CC8
        for i in range(0x34):
            e = AN.INV_TAB + 12 * i
            if u32(e) == n:
                ticks = u16(e + 4); anim, act, row, q = ARM9[e + 6 - 0x02000000:e + 10 - 0x02000000]
                rec['consumable'] = dict(table_row=i, table_addr='%08x' % e, ticks=ticks, anim=anim, entity_action=act,
                                         quality_index=q, quality_mult=QMULT[q],
                                         effect=row_entry(row, q, '020092e4/02009320', '02009214', 'inventory consumable table 0x020C1CC8'))
                rec['consumable']['ends'] = ('%d ticks' % ticks) if ticks else 'while the drink animation plays'
    objects.append(rec)

# where each object is placed by area records (type 5: {u16 5, u16, s16 x, s16 y, u16 object, u8 facing, ...})
placed = collections.defaultdict(list)
for ar in AP.area_table():
    try:
        p = AP.parse_area(ar['data_gid'])
    except Exception:
        continue
    for si, s in enumerate(p['sections']):
        for gi, g in enumerate(s['groups']):
            for r in g:
                if r['type'] == 5:
                    raw = bytes.fromhex(r['raw'])
                    x, y, obj = struct.unpack_from('<hhH', raw, 4)
                    placed[obj].append(dict(area=ar['id'], area_name=text(ar['name_string']), section=si, group=gi, x=x, y=y))
for rec in objects:
    if placed.get(rec['object']):
        rec['placed_in_areas'] = placed[rec['object']]

OTHER = [
    dict(func='02009214', rows='table 0x020C1CC8 (+8 row, +9 quality)', what='eating/drinking an inventory item (food, drinks, smoothies)', sites='020092e4, 02009320'),
    dict(func='0200a71c', rows='3 (room +0.02), 64 (bladder accident), 65 (passing out)', what='player/sim state actions inside entity_common_update: motive failures and one Room tick', sites='0200add0, 0200b024, 0200b0a4'),
    dict(func='02007a44', rows='54', what='entity actions B..E (row 54: hygiene +0.03, fun +0.1, hunger/energy -) inside entity_common_update; looks like swimming/splashing (inferred)', sites='02007c70, 02007d50'),
    dict(func='0200c294', rows='42', what='fun +0.05 while moving fast (skateboard/run speed above 0x68000), from entity_common_update (inferred)', sites='0200c34c, 0200c378'),
    dict(func='0200edd8', rows='42', what='fun +0.05 when speed passes 0x80000 (inferred: riding)', sites='0200ee34'),
    dict(func='0200dad0', rows='26', what='pets (record type 6 / objects 225 Chicken, 236, 237): being petted (comfort +0.02, fun +0.018) applied to the sim at pet+0x120', sites='0200dc00'),
    dict(func='0200e9c4', rows='27', what='pets: play with pet (fun +0.04)', sites='0200ecb8'),
    dict(func='02083cb8', rows='39 / 41', what='room_motive_tick: Room drifts toward the area score', sites='02083d64, 02083d90'),
    dict(func='0208e2f4', rows='52', what='one-shot when a screen/state ends (data table 0x020CD944; social +2.4, others down): inferred to be a date/party wrap-up', sites='0208e308'),
]

json.dump(dict(objects=objects, other_effect_sources=OTHER,
               tables=dict(object_descriptor_table='0x020EAF84 (0x24 bytes x 253): {init, list_actions(obj,u8 out[7]), test(obj,sim,action), begin(obj,sim,action), update(obj), end, ?, in_range, u8 flags[3], u8 quality_index}',
                           action_table='0x020EA9B0: u32 per action {u16 advertised need (8 = none), u16 name string}',
                           effect_table='0x020CEED4 s32[8] per row per tick', quality_mult='0x020EA998',
                           sit_table='0x020F5584 12 bytes per sit type, +8 = row', arcade_table='0x020C5F80 0x20 bytes per game, +0xC = row',
                           inventory_consumables='0x020C1CC8 12 bytes x 52 {u32 object, u16 ticks, u8 anim, u8 action, u8 row, u8 quality}')),
          open('objects.json', 'w'), indent=1)

# ---------------- markdown
def fx(e, scaled=False):
    d = e['per_tick_scaled'] if scaled else e['per_tick']
    return ', '.join('%s %+.3f' % (k, v) for k, v in d.items()) or '(none)'
L = ['# Objects -> needs', '',
     'Generated by build_table.py from the vanilla ROM. Per-tick values are the row in `0x020CEED4`; the game multiplies them by the',
     'object\'s quality (`descriptor+0x23` -> `0x020EA998`: 1.0, 1.0, 1.2, 1.4, 1.6, 2.0). 30 ticks = 1 real second; at normal speed',
     'a game minute is 20 ticks. To change what an object does to the needs, edit the row (shared by every object that uses it), or',
     'patch the `mov r1,#row` at the call site, or change the object\'s quality byte.', '',
     '## Catalog and placed objects (have a descriptor at 0x020EAF84 + n*0x24)', '',
     '| # | name | sold | q | action | row | per tick (x quality) | applied at (func) | runs |', '|---|---|---|---|---|---|---|---|---|']
for r in objects:
    if 'descriptor' not in r: continue
    first = True
    any_row = False
    for a in r['actions']:
        for e in a['effects']:
            any_row = True
            L.append('| %d | %s | %s | %d (x%.1f) | %s (%d) | %d | %s | %s (%s) | %s |' % (
                r['object'], r['name'], ('$%d %s' % (r['price'], r['catalog'])) if r['catalog_page'] != 7 else 'no',
                r['quality_index'], r['quality_mult'] or 0, a['name'], a['id'], e['row'], fx(e), e['site'], e['func'], e['ends']))
    if not any_row:
        acts = ', '.join('%s (%d)' % (a['name'], a['id']) for a in r['actions']) or '-'
        L.append('| %d | %s | %s | %d | %s | - | no need change | | |' % (r['object'], r['name'],
                 ('$%d %s' % (r['price'], r['catalog'])) if r['catalog_page'] != 7 else 'no', r['quality_index'], acts))
L += ['', '## Inventory items eaten/drunk from the pocket (table 0x020C1CC8, applied in 0x02009214)', '',
      '| # | name | row | per tick | quality | ticks |', '|---|---|---|---|---|---|']
for r in objects:
    c = r.get('consumable')
    if c:
        L.append('| %d | %s | %d | %s | %d (x%.1f) | %s |' % (r['object'], r['name'], c['effect']['row'], fx(c['effect']), c['quality_index'], c['quality_mult'], c['ends']))
L += ['', '## Other effect sources (not objects)', '', '| function | rows | what | call sites |', '|---|---|---|---|']
for o in OTHER:
    L.append('| %s | %s | %s | %s |' % (o['func'], o['rows'], o['what'], o['sites']))
L += ['', '## Objects placed by area records (record type 5)', '', '| # | name | areas (id) |', '|---|---|---|']
for r in objects:
    if r.get('placed_in_areas'):
        ar = sorted(set((p['area'], p['area_name']) for p in r['placed_in_areas']))
        L.append('| %d | %s | %s |' % (r['object'], r['name'], ', '.join('%s (%d)' % (b, a) for a, b in ar)))
open('objects.md', 'w').write('\n'.join(L) + '\n')
print('objects', len(objects), 'md lines', len(L))
