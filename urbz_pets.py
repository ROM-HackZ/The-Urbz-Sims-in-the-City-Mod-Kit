#!/usr/bin/env python3
"""Pets from pets.json in a mod: new animals you buy, place at home and pick up, like the Chicken.

pets.json:
  {"pets": [
     {"name": "Puppy", "object": 386, "from": "rooster", "price": 60, "sell": {"9": "common"},
      "description": "A playful pup.", "art": "art/puppy"}
  ]}
  name, description   the object's name and text (new strings).
  object    its object number (386 or 389-511; the pets mod keeps 386 and 389-429).
  from      the animal it starts from: chicken, rooster or nutria (how it moves, and its art until
            you draw your own).
  price, sell, page   as in objects.json (page defaults to 4, Recreation).
  art       a folder of drawings (urbz_art.py template makes one); missing = the starting animal's art.
  import    instead of drawings: an animal from another Sims game (urbz_import.py), e.g.
            {"from": "aptpets", "model": "dog", "coat": "beagle"}; options: coat (dog breeds / cat coats),
            height (pixels standing), anims, hop. Missing source game = the drawings / starting art.
  speed     walking speed as a multiple of the starting animal's (0.5 = half; default 1).
  bed       the object number of its bed or cage (an objects.json entry): it sleeps there at night.
  bed_spot  [dx, dy]: where on the bed it lies, in pixels from the bed's position (default [30, 10]: the
            front half of a bed drawn on one floor tile; further back it would be drawn behind the bed).
  stray     true: one of the two strays of the Urbania Park quest (code/pets-kit/strays.inc).

A top-level "text" object may change the messages code/pets-kit shows (the strays quest, docs/plan-phase10.md):
keys TEXT_KEYS (defaults DEFAULT_TEXT); @1 / @2 are filled in by the game (a pet's or a person's name).

The builder (urbz_build.py) calls pets_mod(): each pet gets a critter kind (7, 8, ...). The game's three
critter tables (behaviour, art, palette) are copied with room for the new kinds into a hidden generated
mod (build/new-pets/) and every reference to them is pointed at the copies; the pets' objects go to
urbz_objects.py (copies of the Chicken, object 225); code/pets-kit (precompiled) turns a placed pet object
into its critter and gives the object back when the critter is picked up. Before the copied behaviour
table sits the list {object, kind} that code/pets-kit reads (magic 'PETM'). docs/systems.md "Pets".
"""
import json, os, struct

KIT = os.path.dirname(os.path.abspath(__file__))
ARM9_BASE = 0x02000000
MAIN_END = 0x02121AC0
CRIT_TABLE, CRIT_ANIMS, CRIT_PALETTES = 0x020C3400, 0x020C348C, 0x020C2FD4
N_KINDS = 7                                # the game's critter kinds (0-6)
ROW, ANIM_ROW = 0x14, 0x28
FROM = {'chicken': 1, 'rooster': 2, 'nutria': 5}
PET_OBJECT_LIKE = 225                      # pet objects copy the Chicken's (placing, picking up)
MAX_PETS = 24
# The messages code/pets-kit shows, in its order (enum T_* in code/pets-kit/pets.c).
TEXT_KEYS = ['strays_intro', 'stray_wary', 'stray_friendly', 'no_treats', 'fed_first', 'fed_today', 'trusts',
             'take_home', 'adopted', 'other_adopted', 'leave', 'ok']
NAME_LEN = 12
DEFAULT_TEXT = {'strays_intro': 'A stray puppy and a stray kitten are hiding in the park. They look hungry and scared.',
                'stray_wary': 'The stray @1 watches you nervously.',
                'stray_friendly': 'The stray @1 wags up to you.',
                'no_treats': 'It sniffs your hand. Pet Treats would win it over: Drifter Woods sells them, by the Brownstones.',
                'fed_first': 'The @1 gobbles up the treat. Come back tomorrow!',
                'fed_today': 'The @1 is full for today. Come back tomorrow.',
                'trusts': 'The @1 trusts you now! You can take it home.',
                'take_home': 'Take Home',
                'adopted': "You adopted the @1! It's in your Pockets: let it loose at home.",
                'other_adopted': '@1 adopted the stray @2. It found a home too!',
                'leave': 'Leave',
                'ok': 'OK'}


class PetsError(Exception):
    pass


def game_arm9(proj):
    img = open(os.path.join(proj, 'base.nds'), 'rb').read()
    off, _, _, size = struct.unpack_from('<4I', img, 0x20)
    return img[off:off + size]


def table_refs(arm9):
    """[(address, symbol, offset)] of every word pointing into the three critter tables."""
    spans = [('crit_table', CRIT_TABLE, ROW * N_KINDS), ('crit_anims', CRIT_ANIMS, ANIM_ROW * N_KINDS),
             ('crit_palettes', CRIT_PALETTES, 4 * N_KINDS)]
    out = []
    for o in range(0, MAIN_END - ARM9_BASE, 4):
        v = struct.unpack_from('<I', arm9, o)[0]
        for name, a, size in spans:
            if a <= v < a + size:
                out.append((ARM9_BASE + o, name, v - a))
    return out


def mod_pets(mod_dirs):
    """[(mod name, mod dir, pet)] from every mod's pets.json, checked."""
    out, objs = [], {}
    for md in mod_dirs:
        p = os.path.join(md, 'pets.json')
        if not os.path.exists(p):
            continue
        name = os.path.basename(os.path.normpath(md))
        try:
            pets = json.load(open(p, encoding='utf-8'))['pets']
        except (ValueError, KeyError) as e:
            raise PetsError('mod "%s": pets.json: %s' % (name, e))
        for pet in pets:
            what = 'mod "%s": pet %r' % (name, pet.get('name'))
            if not isinstance(pet.get('name'), str) or not pet['name']:
                raise PetsError('%s: needs a "name"' % what)
            if pet.get('from') not in FROM:
                raise PetsError('%s: "from" must be one of %s' % (what, ', '.join(FROM)))
            o = pet.get('object')
            if not isinstance(o, int):
                raise PetsError('%s: needs an "object" number' % what)
            if o in objs:
                raise PetsError('object %d is used by two pets (%s)' % (o, what))
            objs[o] = name
            out.append((name, md, pet))
    if len(out) > MAX_PETS:
        raise PetsError('%d pets; at most %d' % (len(out), MAX_PETS))
    return out


def mod_text(mod_dirs):
    """{key: text} from the "text" of every pets.json (later mods win) over DEFAULT_TEXT."""
    text = dict(DEFAULT_TEXT)
    for md in mod_dirs:
        p = os.path.join(md, 'pets.json')
        if os.path.exists(p):
            t = json.load(open(p, encoding='utf-8')).get('text', {})
            unknown = sorted(set(t) - set(TEXT_KEYS))
            if unknown:
                raise PetsError('mod "%s": pets.json text: unknown key(s) %s (known: %s)' % (
                    os.path.basename(os.path.normpath(md)), ', '.join(unknown), ', '.join(TEXT_KEYS)))
            text.update(t)
    missing = [k for k in TEXT_KEYS if not text.get(k)]
    if missing:
        raise PetsError('pets.json "text" needs: %s' % ', '.join(missing))
    return text


def pets_mod(proj, mod_dirs, out_dir, first_asset, first_string=None):
    """Write the generated mod. New art files (from the pets' art folders) are numbered from first_asset
    (the builder's next free number). Returns (mod dirs to add, object entries for urbz_objects, report
    line), or ([], [], None) when no mod has pets.json."""
    pets = mod_pets(mod_dirs)
    tsv = os.path.join(out_dir, 'text', 'strings.tsv')
    if os.path.exists(tsv):
        os.remove(tsv)
    adir = os.path.join(out_dir, 'assets')
    if os.path.isdir(adir):
        for f in os.listdir(adir):
            os.remove(os.path.join(adir, f))
    if not pets:
        return [], [], None
    os.makedirs(adir, exist_ok=True)
    nxt = [first_asset]

    def new_asset(data):
        open(os.path.join(adir, '%05d.bin' % nxt[0]), 'wb').write(data)
        nxt[0] += 1
        return nxt[0]                                  # game id = file number + 1
    arm9 = game_arm9(proj)
    rd = lambda a, n: arm9[a - ARM9_BASE:a - ARM9_BASE + n]
    k_total = N_KINDS + len(pets)
    table = [bytearray(rd(CRIT_TABLE + ROW * k, ROW)) for k in range(N_KINDS)]
    anims = [bytearray(rd(CRIT_ANIMS + ANIM_ROW * k, ANIM_ROW)) for k in range(N_KINDS)]
    pals = [bytearray(rd(CRIT_PALETTES + 4 * k, 4)) for k in range(N_KINDS)]
    pairs, objects, names, art = [], [], [], {}
    for i, (mod, md, pet) in enumerate(pets):
        kind, src = N_KINDS + i, FROM[pet['from']]
        table.append(bytearray(table[src]))
        if 'speed' in pet:                             # walking speed, x the starting animal's (16.16 px/tick)
            sp = struct.unpack_from('<I', table[src], 0xC)[0]
            struct.pack_into('<I', table[kind], 0xC, int(sp * float(pet['speed'])))
        anims.append(bytearray(anims[src]))
        pals.append(bytearray(pals[src]))
        folder = os.path.join(md, pet.get('art', 'art/' + pet['name'].lower()))
        if 'import' in pet:                            # rendered from another Sims game (urbz_import.py)
            import urbz_import
            try:
                folder = urbz_import.pet_art(pet['import'], src, os.path.join(
                    os.path.dirname(out_dir), 'imports', '%s-%s' % (mod, pet['name'].lower())))
            except urbz_import.SourceMissing as sm:            # build anyway, with the starting animal's art
                print('warning: mod "%s": %s keeps the %s\'s art: %s' % (mod, pet['name'], pet['from'], sm))
            except (OSError, ValueError, KeyError) as e:
                raise PetsError('mod "%s": pet %s: import: %s' % (mod, pet['name'], e))
        if os.path.exists(os.path.join(folder, 'timing.json')):
            from urbz_art import build_pet_art
            try:
                art[kind] = build_pet_art(folder, src, new_asset, tuple(pet.get('bed_spot', [30, 10])))
            except (OSError, ValueError, KeyError) as e:
                raise PetsError('mod "%s": pet %s: art: %s' % (mod, pet['name'], e))
            struct.pack_into('<I', pals[kind], 0, art[kind]['palette'])
        bed = pet.get('bed', 0)
        if not isinstance(bed, int) or bed < 0:
            raise PetsError('mod "%s": pet %s: "bed" must be an object number' % (mod, pet['name']))
        spot = pet.get('bed_spot', [30, 10])
        if not (isinstance(spot, list) and len(spot) == 2 and all(isinstance(v, int) and -128 <= v < 128 for v in spot)):
            raise PetsError('mod "%s": pet %s: "bed_spot" must be [dx, dy] (pixels)' % (mod, pet['name']))
        pairs.append((pet['object'], kind, bed, pet['name'], 1 if pet.get('stray') else 0, spot))
        e = {'id': pet['object'], 'like': PET_OBJECT_LIKE, 'name': pet['name'], 'page': pet.get('page', 4)}
        if os.path.exists(os.path.join(folder, 'icon.png')):
            e['_icon'] = folder                        # its own Pockets / Catalog icon (urbz_objects)
        for k in ('description', 'price', 'sell'):
            if k in pet:
                e[k] = pet[k]
        objects.append(e)
        names.append('%s (kind %d, from %s%s)' % (pet['name'], kind, pet['from'],
                                                  ', own art' if kind in art else ''))

    # What code/pets-kit reads just before crit_table:
    #   'PETT', u16 text[len(TEXT_KEYS)] (string numbers, padded to 4), u32 len(TEXT_KEYS),
    #   'PETB', {u16 object, u16 kind, u32 actions, u16 bed, u8 flags (1 = a stray), u8 0, char name[12],
    #            s8 bed_spot x, y, u16 0} x n, u32 n.
    # actions -> N_ACTIONS x {u32 records (5 x 16 bytes), u32 frame script} (0 = no actions: drawn pets).
    text, strings = mod_text(mod_dirs), []
    sid = first_string() if first_string else 8311
    for k in TEXT_KEYS:
        strings.append((sid, text[k]))
        sid += 1
    blob = bytearray(b'PETT')
    for n, _ in strings:
        blob += struct.pack('<H', n)
    while len(blob) % 4:
        blob.append(0)
    blob += struct.pack('<I', len(strings)) + b'PETB'
    act_refs = []
    for o, k, bed, name, flags, spot in pairs:
        act_refs.append(len(blob) + 4)
        blob += struct.pack('<HHIHBB', o, k, 0, bed, flags, 0) + \
            name.encode('latin-1', 'replace')[:NAME_LEN - 1].ljust(NAME_LEN, b'\0') + struct.pack('<bbH', spot[0], spot[1], 0)
    blob += struct.pack('<I', len(pairs))
    syms = {'crit_table': len(blob)}
    blob += b''.join(table)
    syms['crit_anims'] = len(blob)
    blob += b''.join(anims)
    syms['crit_palettes'] = len(blob)
    blob += b''.join(pals)
    relocs = []
    for kind, a in sorted(art.items()):                # the new records; the anims rows point at them
        for slot, (records, script) in enumerate(a['slots']):
            row = syms['crit_anims'] + ANIM_ROW * kind + 8 * slot
            if records is not None:
                struct.pack_into('<II', blob, row, len(blob), script)
                relocs.append(row)
                blob += records
    for (o, k, _, _, _, _), ref in zip(pairs, act_refs):   # the action tables (Phase 9)
        acts = art.get(k, {}).get('actions')
        if not acts:
            continue
        while len(blob) % 4:
            blob.append(0)
        tab = len(blob)
        struct.pack_into('<I', blob, ref, tab)
        relocs.append(ref)
        blob += bytes(8 * len(acts))
        for j, (records, script) in enumerate(acts):
            struct.pack_into('<II', blob, tab + 8 * j, len(blob), script)
            relocs.append(tab + 8 * j)
            blob += records
    lines = ['# Generated by urbz_pets.py: the critter tables, %d kinds' % k_total]
    lines += ['u32 0x%08X @%s+0x%X' % (a, name, off) for a, name, off in table_refs(arm9)]
    cdir = os.path.join(out_dir, 'code')
    os.makedirs(os.path.join(cdir, 'build'), exist_ok=True)
    open(os.path.join(cdir, 'hooks.txt'), 'w').write('\n'.join(lines) + '\n')
    os.makedirs(os.path.dirname(tsv), exist_ok=True)
    esc = lambda t: t.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')
    open(tsv, 'w', encoding='utf-8').write(''.join('%d\t%s\n' % (n, esc(t)) for n, t in strings))
    open(os.path.join(cdir, 'build', 'patch.bin'), 'wb').write(bytes(blob))
    json.dump({'relocs': relocs, 'symbols': syms, 'bss': 0, 'sources': {}},
              open(os.path.join(cdir, 'build', 'patch.json'), 'w'))
    json.dump({'name': 'new-pets', 'description': 'Kit: the critter tables with room for new pets',
               'toggle': False, 'hidden': True}, open(os.path.join(out_dir, 'mod.json'), 'w'))
    extra = [('pets', objects)]
    line = 'pets: %s; %d new art file(s)' % (', '.join(names), nxt[0] - first_asset)
    return [out_dir, os.path.join(KIT, 'code', 'pets-kit')], extra, line
