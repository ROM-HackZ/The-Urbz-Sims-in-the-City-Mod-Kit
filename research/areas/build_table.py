"""Build areas.json: every area id the game knows, from the arm9 tables + area data assets."""
import json, struct, sys, collections
import area_parse as P
sys.path.insert(0, '/root/urbz/kit9')
import urbz_text as T

def get_strings():
    import os
    st = T.project_strings('/root/urbz/kit9/project')
    return {i: (x.decode('latin-1') if isinstance(x, bytes) else x) for i, x in enumerate(st)}

S = get_strings()
import os
HEAP = json.load(open('heap_sweep.json')) if os.path.exists('heap_sweep.json') else {}
ARM9 = P.ARM9
def u32(a): return struct.unpack_from('<I', ARM9, a - 0x02000000)[0]

def char_name(c):
    if 31 <= c <= 85:
        return S.get(481 + c, '?')
    return None

def sched(cid):
    p = u32(0x020E4FD8 + 4 * (cid - 31))
    if not p: return None
    o = p - 0x02000000
    return [[ARM9[o + h * 7 + d] for d in range(7)] for h in range(24)]

TYPE_NAMES = {3: 'door', 7: 'person', 20: 'door(variant)', 25: 'elevator', 29: 'link?', 30: 'edge?'}

areas = []
tab = P.area_table()
for a in tab:
    p = P.parse_area(a['data_gid'])
    i = a['id']
    rec = dict(id=i, name=S.get(a['name_string']), name_string=a['name_string'],
               phone_phrase=S.get(1057 + i), data_asset_gid=a['data_gid'],
               data_asset_file='%05d.bin' % (a['data_gid'] - 1), data_size=p['size'],
               gfx_asset_gids=a['gfx_assets'], table_ptr='%08x' % a['ptr'], misc=a['misc'], misc2=a['misc2'],
               entry_points=p['entries'], variant_to_section=p['variant_to_section'], sections=[])
    people = collections.defaultdict(list)
    exits = set()
    for si, s in enumerate(p['sections']):
        merged = ([('base', 0)] if (si and s['include_base']) else []) 
        sec = dict(index=si, flags=s['flags'], n_listA=s['n_listA'], n_listB=s['n_listB'], groups=[])
        for gi, g in enumerate(s['groups']):
            grp = dict(index=gi, type_counts=dict(collections.Counter(r['type'] for r in g)), people=[], doors=[])
            for r in g:
                raw = bytes.fromhex(r['raw'])
                if r['type'] == 7:
                    grp['people'].append(dict(char=r['char'], name=char_name(r['char']), x=r['x'], y=r['y'], facing=r['facing']))
                    people[r['char']].append('s%d.g%d' % (si, gi))
                elif r['type'] in (3, 20):
                    x, y = struct.unpack_from('<hh', raw, 4)
                    grp['doors'].append(dict(kind=TYPE_NAMES[r['type']], x=x, y=y, to_area=raw[11], entry=raw[10]))
                    exits.add(raw[11])
                elif r['type'] == 25:
                    x, y = struct.unpack_from('<hh', raw, 4)
                    tg = [(raw[10 + 2 * k], raw[11 + 2 * k]) for k in range(5)]
                    tg = [t for k, t in enumerate(tg) if k == 0 or t != (0, 0)]
                    grp['doors'].append(dict(kind='elevator', x=x, y=y, to=[dict(area=t[0], entry=t[1]) for t in tg]))
                    exits.update(t[0] for t in tg)
                elif r['type'] == 29:
                    x, y = struct.unpack_from('<hh', raw, 4)
                    grp['doors'].append(dict(kind='link29', x=x, y=y, to_area=raw[8], entry=raw[9]))
            sec['groups'].append(grp)
        rec['sections'].append(sec)
    rec['people'] = {str(c): dict(name=char_name(c), where=sorted(set(v)),
                                  at_load=any(w.endswith('.g0') for w in v)) for c, v in sorted(people.items())}
    rec['heap'] = HEAP.get(str(i))
    rec['exits_to'] = sorted(exits)
    areas.append(rec)

# schedules
sch = {}
for cid in range(31, 80):
    t = sched(cid)
    used = collections.Counter(v for row in t for v in row) if t else {}
    sch[cid] = dict(name=char_name(cid), table_ptr='%08x' % u32(0x020E4FD8 + 4 * (cid - 31)),
                    areas_used={str(k): n for k, n in sorted(used.items())}, table=t)

xref = {}
for cid in range(31, 80):
    used = [int(k) for k in sch[cid]['areas_used']]
    has = [a['id'] for a in areas if str(cid) in a['people']]
    at_load = [a['id'] for a in areas if str(cid) in a['people'] and a['people'][str(cid)]['at_load']]
    xref[cid] = dict(name=char_name(cid), schedule_areas=used, record_areas=has, record_areas_at_load=at_load,
                     schedule_only_scripted_record=[x for x in used if x in has and x not in at_load],
                     schedule_without_record=[x for x in used if x not in has],
                     record_without_schedule=[x for x in has if x not in used])
json.dump(dict(areas=areas, schedules=sch, xref=xref), open('areas.json', 'w'), indent=1)
for a in areas:
    print('%2d %-30s gid %5d exits %s people %s' % (a['id'], a['name'], a['data_asset_gid'], a['exits_to'],
          ','.join(a['people'].keys())))
print()
for c, x in xref.items():
    print(c, x['name'], 'sched', x['schedule_areas'], 'MISSING', x['schedule_without_record'], 'SCRIPTED-ONLY', x['schedule_only_scripted_record'], 'EXTRA', x['record_without_schedule'])
