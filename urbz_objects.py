#!/usr/bin/env python3
"""New catalog objects (and changes to the game's own), from objects.json in a mod.

The game keeps seven tables indexed by object number: text (model, description, name, catalog
page) and info (price, flags, shop masks) for objects 0-385, and class (behaviour), shape, model,
variant and anim tables for the 253 placeable ones (0-252). They are packed in the game's data, so
they can't grow in place. When a mod has an objects.json, the builder makes a hidden code mod
(build/new-objects/) holding copies of all seven with room for the new rows, points every reference
in the game's code at the copies, and adds code/objects, which makes the game's number checks ask
about the object a new one copies (docs/systems.md "Buyable objects").

objects.json:
  {"objects": [
     {"id": 389, "like": 225, "name": "Puppy", "description": "A playful pup.",
      "price": 60, "page": 7, "sell": {"9": "common"}},
     {"id": 200, "price": 99}
  ]}
  id        the object number. 0-385 are the game's (change them), 386 and 389-511 are new
            (387 and 388 mean "random pick" and "empty" to the game; the save keeps 9 bits).
  like      (new objects) the object to copy: its art, behaviour and every field not given.
  name, description   text, or a string number. Text gets new string numbers automatically.
  price     Simoleons.   page   catalog page (0 Appliances ... 5 Utilities, 7 = not in the catalog).
  model     the art (model) number; default: like's.
  sell      {"shop list": "common" | "uncommon" | "rare"}: shops that may stock it each day.

  python urbz_objects.py show 225 [389 ...]     print rows (with the project's game data)
"""
import json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
ARM9_BASE = 0x02000000
MAIN_END = 0x02121AC0                      # end of the main code+data (BSS follows)
SHAPE = 0x020E6954                         # u32 per placeable object: footprint data
TEXT = 0x020E6D48                          # {model, description, name, page, ?}
INFO = 0x020E8B70                          # {price, shop masks: common, uncommon, rare; flags?}
CLASS = 0x020EAF84                         # 0x24 bytes: behaviour functions; rows 0-252
MODEL = 0x020F1D28                         # u32 per placeable object: its art (model data)
VARIANT = 0x020F211C                       # 5 x u32 per placeable object (per colour variant)
ANIM = 0x020F34E0                          # 0x1C per placeable object (art per look: default, variants)
N_GAME, N_PLACE = 386, 253                 # objects; placeable ones (tables of 253 rows)
TABLES = [('text', TEXT, 0x14, N_GAME), ('info', INFO, 0x14, N_GAME), ('class', CLASS, 0x24, N_PLACE),
          ('shape', SHAPE, 4, N_PLACE), ('model', MODEL, 4, N_PLACE), ('variant', VARIANT, 0x14, N_PLACE),
          ('anim', ANIM, 0x1C, N_PLACE)]
RANDOM, EMPTY = 0x183, 0x184               # object numbers the game uses as markers
FIRST_NEW, LAST = 386, 511
UI_SPRITES, UI_ROWS = 0x020CB134, 632      # icon records by model number; model 632 = "not sold"
UI_SPRITE_REFS = (0x0204E7B0, 0x0204ED20)  # the only two words in the game that hold its address
SHOP_PICK_COUNT = 0x0203C6AC               # literal: objects shop_pick looks at (386)
SHOP_DEFS, N_SHOPS = 0x020C76E8, 21        # {u8 capacity, u8 n, u8 keep, pad, u16 *items} per shop list
PICK_RANDOM = 387                          # a shop_defs item: "pick one at random" (by the sell masks)
# shop_pick: once every rarity tier has nothing left that isn't already on the shelf, the game adds its last
# try anyway (a second copy). This branch goes to the end instead, so that slot stays empty.
SHOP_PICK_GIVE_UP = 0x0203C5A8, 0x0A000034, 0x0A00003C   # beq 0x0203C680 (add it) -> beq 0x0203C6A0 (return)
CATALOG_LOOPS = (0x0201C6E8, 0x0201C920)   # "cmp rN, #0x118": the Catalog only looks at objects 0-279
RARITY = {'common': 1, 'uncommon': 2, 'rare': 3}        # info word (shop_pick reads +4, +8, +0xC)
# Activities: {u16 need, u16 menu text} per activity number (0-119). New actions (objects.json "actions") get
# numbers 120+ in a moved copy; these three words in the game point at it (+0, +0, +2).
ACTIVITY_TABLE, N_ACTIVITIES = 0x020EA9B0, 120
ACTIVITY_REFS = ((0x02008BEC, 0), (0x02067A48, 0), (0x02067A4C, 2))
NEEDS = ['hunger', 'hygiene', 'energy', 'social', 'comfort', 'bladder', 'fun', 'room']
FIELDS = {'model': ('t', 0), 'description': ('t', 1), 'name': ('t', 2), 'page': ('t', 3),
          'price': ('i', 0)}


class ObjectsError(Exception):
    pass


def game_arm9(proj):
    img = open(os.path.join(proj, 'base.nds'), 'rb').read()
    off, _, _, size = struct.unpack_from('<4I', img, 0x20)
    return img[off:off + size]


def table_refs(arm9):
    """Every word in the game's code/data that points into one of the three tables:
    [(address, table, offset)]. (They all point at a table start or start + 0x1000.)"""
    out = []
    for o in range(0, MAIN_END - ARM9_BASE, 4):
        v = struct.unpack_from('<I', arm9, o)[0]
        for name, a, stride, count in TABLES:
            if a <= v < a + stride * count:
                out.append((ARM9_BASE + o, name, v - a))
    return out


def mod_objects(mod_dirs, extra=()):
    """[(mod name, entry)] from every mod's objects.json and `extra` [(mod name, [entries])] (objects
    other kit stages add, e.g. pets from pets.json), checked."""
    out, seen, sources = [], {}, []
    for md in mod_dirs:
        p = os.path.join(md, 'objects.json')
        if not os.path.exists(p):
            continue
        name = os.path.basename(os.path.normpath(md))
        try:
            ents = json.load(open(p, encoding='utf-8'))['objects']
            for e in ents:
                e['_dir'] = md
            sources.append((name, ents))
        except (ValueError, KeyError) as e:
            raise ObjectsError('mod "%s": objects.json: %s' % (name, e))
    for name, entries in list(sources) + list(extra):
        for e in entries:
            i = e.get('id')
            if not isinstance(i, int) or not 0 <= i <= LAST or i in (RANDOM, EMPTY):
                raise ObjectsError('mod "%s": object id %r: use 0-%d (the game\'s) or 386 and %d-%d (new; '
                                   '387 and 388 are markers to the game)' % (name, i, N_GAME - 1, EMPTY + 1, LAST))
            if i in seen:
                raise ObjectsError('object %d is set by both "%s" and "%s"' % (i, seen[i], name))
            seen[i] = name
            if i >= N_GAME and not isinstance(e.get('like'), int):
                raise ObjectsError('mod "%s": new object %d needs "like" (an object to copy)' % (name, i))
            if i >= N_GAME and not 0 <= e['like'] < N_GAME:
                raise ObjectsError('mod "%s": object %d: "like" must be one of the game\'s objects' % (name, i))
            out.append((name, e))
    return out


def activity_names(arm9, by_number=False):
    """{lower-case menu text: activity number} of the game's activities (the first one with each name), or
    with by_number [lower-case menu text per activity number]."""
    from urbz_text import project_strings
    texts = project_strings(os.path.join(KIT, 'project'))
    out, each = {}, []
    for k in range(N_ACTIVITIES):
        sid = struct.unpack_from('<H', arm9, ACTIVITY_TABLE - ARM9_BASE + 4 * k + 2)[0]
        t = texts[sid] if sid < len(texts) else None
        t = (t.decode('latin-1') if isinstance(t, bytes) else t or '').strip().lower()
        each.append(t)
        if t:
            out.setdefault(t, k)
    return each if by_number else out


def action_rows(new_actions, rows, arm9, string):
    """objects.json "actions" -> (rows for code/objects, rows for the moved activity table).
    An action: {"name": menu text, "as": one of the object's own activities ("Sit", "Sleep", ... or a number),
    the needs it changes per tick (e.g. "fun": 0.3; the game's chairs give comfort 0.2-0.3), "until": the
    need that ends it when full (default: the one it fills most), "minutes": or after this many game minutes}.
    It plays exactly like "as" (walk there, animation, the object's own effects) plus these effects, and ends
    when "until" is full or the time is up. code/objects reads {u16 object, u8 activity, u8 until, u8 quality,
    u8 0, u16 ticks, u8 as[4] (the game's activities with that menu text: several are called "Sit"; code/objects
    takes the one the object offers; 0 = none), s32 effects[8]} rows."""
    if not new_actions:
        return b'', []
    names = activity_names(arm9)
    names_of = activity_names(arm9, by_number=True)
    code_rows, table_rows = [], []
    for k, (mod, obj, a) in enumerate(new_actions):
        what = 'mod "%s": object %d: action %d' % (mod, obj, k + 1)
        aid = N_ACTIVITIES + k
        if aid > 255:
            raise ObjectsError('%s: too many new actions (at most %d)' % (what, 256 - N_ACTIVITIES))
        if not isinstance(a, dict) or not a.get('name') or 'as' not in a:
            raise ObjectsError('%s: needs "name" and "as" (e.g. {"name": "Read a Book", "as": "Sit", "fun": 0.3})' % what)
        base = a['as'] if isinstance(a['as'], int) else names.get(str(a['as']).strip().lower())
        if base is None or not 0 <= base < N_ACTIVITIES:
            raise ObjectsError('%s: "as": "%s" is not one of the game\'s activities (Sit, Sleep, ...)' % (what, a['as']))
        eff = [0] * 8
        for n, v in a.items():
            if n in NEEDS:
                if not isinstance(v, (int, float)) or not -2 <= v <= 2:
                    raise ObjectsError('%s: "%s" is the change per tick, -2 to 2 (a chair: comfort 0.2)' % (what, n))
                eff[NEEDS.index(n)] = int(round(v * (1 << 24)))
            elif n not in ('name', 'as', 'until', 'minutes'):
                raise ObjectsError('%s: unknown field "%s" (needs: %s)' % (what, n, ', '.join(NEEDS)))
        until = a.get('until')
        if until is None and 'minutes' not in a:
            best = max(range(8), key=lambda j: eff[j])
            until = NEEDS[best] if eff[best] > 0 else None
        if until is not None and until not in NEEDS:
            raise ObjectsError('%s: "until" is a need (%s)' % (what, ', '.join(NEEDS)))
        if until is None and 'minutes' not in a:
            raise ObjectsError('%s: give "until" (a need) or "minutes"' % what)
        ticks = int(a.get('minutes', 0)) * 20                # 20 ticks a game minute at normal speed
        if not 0 <= ticks <= 0xFFFF:
            raise ObjectsError('%s: "minutes" is 1-3000' % what)
        u = NEEDS.index(until) if until else 8
        q = rows['class'][obj][0x23] if obj < len(rows['class']) else 1
        same = [k for k in range(1, N_ACTIVITIES) if names_of[k] == names_of[base]][:4] or [base]
        code_rows.append(struct.pack('<HBBBBH4B8i', obj, aid, u, q, 0, ticks, *(same + [0] * (4 - len(same))), *eff))
        need = struct.unpack_from('<H', arm9, ACTIVITY_TABLE - ARM9_BASE + 4 * base)[0]
        table_rows.append(struct.pack('<HH', need if u == 8 else u, string(a['name'], what + ' name')))
    return b''.join(code_rows), table_rows


def objects_mod(proj, mod_dirs, out_dir, first_string, extra=(), first_asset=None):
    """first_string() gives the first free string number for new text; first_asset() the first free
    asset number for new art. Write the generated mod (code/build/patch.bin+json, hooks.txt, text/strings.tsv,
    assets/ for objects with "art" or "import").
    Returns ([the generated mod, code/objects], report line) or (None, None) if no mod has objects.json."""
    entries = mod_objects(mod_dirs, extra)
    adir = os.path.join(out_dir, 'assets')
    if os.path.isdir(adir):
        for f in os.listdir(adir):
            os.remove(os.path.join(adir, f))
    if not entries:
        return None, None
    from urbz_code import game_symbols, _address, CodeError
    syms = game_symbols(KIT)
    for md in mod_dirs:                         # edits to the old tables would be silently lost
        hp = os.path.join(md, 'code', 'hooks.txt')
        for line in (open(hp).read().splitlines() if os.path.exists(hp) else ()):
            p = line.split('#', 1)[0].split()
            if len(p) < 2 or p[0].lower() not in ('data', 'u8', 'u16', 'u32'):
                continue
            try:
                a = _address(p[1], syms, hp)
            except CodeError:
                continue
            for name, addr, stride, count in TABLES:
                if a is not None and addr <= a < addr + stride * count:
                    raise ObjectsError('mod "%s" writes to the object %s table at 0x%08X, but another mod adds '
                                       'objects, which moves the tables: change object %d in an objects.json '
                                       'instead' % (os.path.basename(os.path.normpath(md)), name, a,
                                                    (a - addr) // stride))
    arm9 = game_arm9(proj)
    n = max([N_GAME] + [e['id'] + 1 for _, e in entries])
    n = (n + 3) & ~3                            # (the catalog loops need a multiple of 4)
    rows = {}
    for name, addr, stride, count in TABLES:
        rows[name] = [bytearray(arm9[addr - ARM9_BASE + stride * i:addr - ARM9_BASE + stride * (i + 1)])
                      for i in range(count)]
        while len(rows[name]) < n:              # markers and gaps
            rows[name].append(bytearray(rows[name][1]) if count == N_GAME else bytearray(stride))
    for i in range(N_GAME, n):                  # gaps: an unused, unsold row
        rows['info'][i] = bytearray(struct.pack('<5I', 1, 0, 0, 0, 0))
    strings, sid = [], None
    new_actions = []

    def string(v, what):
        nonlocal sid
        if isinstance(v, int):
            return v
        if not isinstance(v, str) or not v:
            raise ObjectsError('%s must be text or a string number' % what)
        if sid is None:
            sid = first_string()
        strings.append((sid, v))
        sid += 1
        return sid - 1

    for mod, e in entries:
        i = e['id']
        if i >= N_GAME:
            b = e['like']
            for name, addr, stride, count in TABLES:
                if b < count:
                    rows[name][i] = bytearray(rows[name][b])
            struct.pack_into('<3I', rows['info'][i], 4, 0, 0, 0)   # sold where "sell" says
        for k, (t, f) in FIELDS.items():
            if k in e:
                v = string(e[k], 'object %d %s' % (i, k)) if k in ('name', 'description') else e[k]
                struct.pack_into('<I', rows['text' if t == 't' else 'info'][i], 4 * f, v & 0xFFFFFFFF)
        if 'quality' in e:                      # how fast it fills needs: the class row's byte 0x23 indexes
            q = e['quality']                    # motive_effect_scale (x1.0, 1.0, 1.2, 1.4, 1.6, 2.0)
            if not isinstance(q, int) or not 1 <= q <= 5:
                raise ObjectsError('mod "%s": object %d: "quality" is 1 (x1.0) to 5 (x2.0)' % (mod, i))
            rows['class'][i][0x23] = q
        for a in e.get('actions', []):
            new_actions.append((mod, i, a))
        for shop, rarity in e.get('sell', {}).items():
            if rarity not in RARITY or not str(shop).isdigit() or not 0 <= int(shop) <= 20:
                raise ObjectsError('mod "%s": object %d: sell {"0-20": "common|uncommon|rare"}' % (mod, i))
            w = struct.unpack_from('<I', rows['info'][i], 4 * RARITY[rarity])[0] | 1 << int(shop)
            struct.pack_into('<I', rows['info'][i], 4 * RARITY[rarity], w)

    # Art: objects with "art" (a folder of PNGs, urbz_art.py) or "import" (a model from another Sims game,
    # urbz_import.py) get new art files, their own palette (variants 0xFD: drawn in a palette of their own,
    # like the game's Personal Painting) and, with an icon, a new row in the moved icon table.
    art = {}
    nxt = [first_asset() if first_asset else None]

    def new_asset(data):
        os.makedirs(adir, exist_ok=True)
        open(os.path.join(adir, '%05d.bin' % nxt[0]), 'wb').write(data)
        nxt[0] += 1
        return nxt[0]                           # game id = file number + 1
    for mod, e in entries:
        if 'art' not in e and 'import' not in e:
            continue
        i = e['id']
        if i < N_GAME:
            raise ObjectsError('mod "%s": object %d: new art is for new objects (386, 389-%d)' % (mod, i, LAST))
        if nxt[0] is None:
            raise ObjectsError('object %d has art, but the builder gave no asset numbers' % i)
        try:
            if 'import' in e:
                import urbz_import
                try:
                    folder = urbz_import.object_art(e['import'], e['like'], os.path.join(
                        os.path.dirname(out_dir), 'imports', '%s-%d' % (mod, i)))
                except urbz_import.SourceMissing as sm:     # build anyway: it keeps its like's art
                    print('warning: mod "%s": object %d keeps object %d\'s art: %s' % (mod, i, e['like'], sm))
                    continue
            else:
                folder = os.path.join(e.get('_dir', ''), e['art'])
            from urbz_art import build_object_art
            art[i] = build_object_art(folder, e['like'], new_asset)
        except (OSError, ValueError, KeyError, SystemExit) as ex:
            raise ObjectsError('mod "%s": object %d: art: %s' % (mod, i, ex))
        rows['variant'][i] = bytearray(struct.pack('<5I', *[0xFD] * 5))

    icon_only = {}                              # entries with just an icon ("_icon": an art folder): pets
    for mod, e in entries:
        if e.get('_icon') and e['id'] not in art:
            if nxt[0] is None:
                raise ObjectsError('object %d has an icon, but the builder gave no asset numbers' % e['id'])
            from urbz_art import build_icon
            try:
                icon_only[e['id']] = build_icon(e['_icon'], e['like'], new_asset)
            except (OSError, ValueError, KeyError) as ex:
                raise ObjectsError('mod "%s": object %d: icon: %s' % (mod, e['id'], ex))

    like = list(range(LAST + 1))                # what each object counts as for the game's checks
    for _, e in entries:
        if e['id'] >= N_GAME:
            like[e['id']] = e['like']
    # Own palettes for code/objects: {u16 object, u16 0, u32 palette id x 4} ..., u32 count, 'OPAL', then 'NEWO'.
    acts, act_rows = action_rows(new_actions, rows, arm9, string)
    opal = b''.join(struct.pack('<HH4I', i, 0, *[a['palette']] * 4) for i, a in sorted(art.items()))
    blob = bytearray(acts + struct.pack('<I', len(act_rows)) + b'ACTS' +
                     opal + struct.pack('<I', len(art)) + b'OPAL')
    shelves = []
    blob += b'NEWO' + struct.pack('<%dH' % (LAST + 1), *like)  # code/objects finds it before obj_text
    syms = {}
    relocs = []
    for name, addr, stride, count in TABLES:    # text first: the like list sits right before it
        while len(blob) % 4:
            blob.append(0)
        syms['obj_' + name] = len(blob)
        blob += b''.join(rows[name])
    for i, a in sorted(art.items()):            # the art records; the model rows point at them
        while len(blob) % 4:
            blob.append(0)
        row = syms['obj_model'] + 4 * i
        struct.pack_into('<I', blob, row, len(blob))
        relocs.append(row)
        blob += a['records']
    icons = sorted([(i, a['icon']) for i, a in art.items() if a['icon']] +
                   [(i, rec) for i, rec in icon_only.items() if rec])
    if icons:                                   # the icon table moves and grows: new model numbers 633+
        base = UI_SPRITES - ARM9_BASE
        while len(blob) % 4:
            blob.append(0)
        syms['ui_sprites'] = len(blob)
        blob += arm9[base:base + 16 * UI_ROWS] + bytes(16)        # row 632 means "not sold": never drawn
        for k, (i, rec) in enumerate(icons):
            blob += rec
            struct.pack_into('<I', blob, syms['obj_text'] + 0x14 * i, UI_ROWS + 1 + k)
    lines = ['# Generated by urbz_objects.py: the object tables, %d rows' % n]
    if icons:
        lines += ['u32 0x%08X @ui_sprites' % a for a in UI_SPRITE_REFS]
    for addr, name, off in table_refs(arm9):
        lines.append('u32 0x%08X @obj_%s+0x%X' % (addr, name, off))
    lines.append('u32 0x%08X %d' % (SHOP_PICK_COUNT, n))
    # Shelves: a shop that sells new objects stocks more each day (up to double, at most its capacity),
    # so the game's own goods turn up about as often as before instead of being crowded out.
    new_sellers = {}
    for mod, e in entries:
        if e['id'] >= N_GAME:
            for shop in e.get('sell', {}):
                new_sellers[int(shop)] = new_sellers.get(int(shop), 0) + 1
    for shop, k in sorted(new_sellers.items()):
        cap, n0, keep, _, ptr = struct.unpack_from('<BBBBI', arm9, SHOP_DEFS + 8 * shop - ARM9_BASE)
        n1 = min(cap, n0 + min(k, n0))
        if n1 <= n0:
            continue
        items = list(struct.unpack_from('<%dH' % n0, arm9, ptr - ARM9_BASE)) + [PICK_RANDOM] * (n1 - n0)
        while len(blob) % 4:
            blob.append(0)
        syms['shop_items_%d' % shop] = len(blob)
        blob += struct.pack('<%dH' % n1, *items)
        lines.append('u8 0x%08X %d' % (SHOP_DEFS + 8 * shop + 1, n1))
        lines.append('u32 0x%08X @shop_items_%d' % (SHOP_DEFS + 8 * shop + 4, shop))
        shelves.append('list %d: %d -> %d a day' % (shop, n0, n1))
    if shelves:                                 # more slots than goods: no doubles, an empty slot instead
        a, old, new = SHOP_PICK_GIVE_UP
        assert struct.unpack_from('<I', arm9, a - ARM9_BASE)[0] == old, 'unexpected shop_pick at %08x' % a
        lines.append('u32 0x%08X 0x%08X' % (a, new))
    if act_rows:                                # the activity table moves: room for the new actions
        while len(blob) % 4:
            blob.append(0)
        syms['activities'] = len(blob)
        base = ACTIVITY_TABLE - ARM9_BASE
        blob += arm9[base:base + 4 * N_ACTIVITIES] + b''.join(act_rows)
        for a, off in ACTIVITY_REFS:
            assert struct.unpack_from('<I', arm9, a - ARM9_BASE)[0] == ACTIVITY_TABLE + off, 'activity ref %08x' % a
            lines.append('u32 0x%08X @activities+%d' % (a, off))
    n4 = (n + 3) & ~3                           # an ARM immediate (rows past n are never on a page)
    for a in CATALOG_LOOPS:
        w = struct.unpack_from('<I', arm9, a - ARM9_BASE)[0]
        assert w & 0xFFF0FFFF == 0xE3500F46, 'unexpected catalog loop at %08x' % a
        lines.append('u32 0x%08X 0x%08X' % (a, (w & 0xFFFFF000) | 0xF00 | (n4 >> 2)))
    cdir = os.path.join(out_dir, 'code')
    os.makedirs(os.path.join(cdir, 'build'), exist_ok=True)
    open(os.path.join(cdir, 'hooks.txt'), 'w').write('\n'.join(lines) + '\n')
    open(os.path.join(cdir, 'build', 'patch.bin'), 'wb').write(bytes(blob))
    json.dump({'relocs': relocs, 'symbols': syms, 'bss': 0, 'sources': {}},
              open(os.path.join(cdir, 'build', 'patch.json'), 'w'))
    tdir = os.path.join(out_dir, 'text')
    if strings:
        os.makedirs(tdir, exist_ok=True)
        tsv = lambda s: s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')
        open(os.path.join(tdir, 'strings.tsv'), 'w', encoding='utf-8').write(
            ''.join('%d\t%s\n' % (k, tsv(s)) for k, s in strings))
    elif os.path.exists(os.path.join(tdir, 'strings.tsv')):
        os.remove(os.path.join(tdir, 'strings.tsv'))
    json.dump({'name': 'new-objects', 'description': 'Kit: room for the objects mods add', 'toggle': False,
               'hidden': True}, open(os.path.join(out_dir, 'mod.json'), 'w'))
    new = sorted(e['id'] for _, e in entries if e['id'] >= N_GAME)
    return [out_dir, os.path.join(KIT, 'code', 'objects')], 'objects: %d new (%s), %d changed; tables moved (%d rows)%s' % (
        len(new), ', '.join(map(str, new)) or '-', len(entries) - len(new), n,
        ('; own art: %s' % ', '.join(map(str, sorted(art))) if art else '') +
        ('; bigger shelves: %s, no doubles' % ', '.join(shelves) if shelves else ''))


def main(argv):
    if len(argv) >= 2 and argv[0] == 'show':
        arm9 = game_arm9(os.path.join(KIT, 'project'))
        for a in argv[1:]:
            i = int(a, 0)
            t = struct.unpack_from('<5I', arm9, TEXT - ARM9_BASE + 0x14 * i)
            f = struct.unpack_from('<5I', arm9, INFO - ARM9_BASE + 0x14 * i)
            print('%d: model %d, description %d, name %d, page %d; price %d, shop lists: common 0x%x '
                  'uncommon 0x%x rare 0x%x; +0x10 0x%x' % ((i,) + t[:4] + f))
        return
    print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
