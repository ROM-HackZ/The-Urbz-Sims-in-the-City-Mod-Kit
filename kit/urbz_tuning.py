"""Your own settings for the mods, kept apart from the mods themselves.

The mod manager's Tune window writes them (tuning/<mod>.json in the kit folder, never committed); the builder
applies them on top of each mod's own files when it reads them. Updating a mod never loses them, and Reset
deletes them. What can be tuned:

  pets.json     each pet's name, price, description, and which shops sell it (and how often)
  objects.json  each object's name, price, description, quality (1-5, how fast it fills needs), shops
  places.json   NPC Life: what each place offers the townspeople (food, fun, social, park, gym)

  python urbz.py tuning show [mod]      what you've changed
  python urbz.py tuning reset mod       back to the mod's own settings
"""
import copy
import json
import os
import struct
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUNING = os.path.join(KIT, 'tuning')

# Shop lists people can pick in the Tune window (docs/systems.md "Shops"); others keep their list number.
SHOPS = {4: 'Furniture shop', 9: "Bayou Bazaar (Farmer's Market)", 10: 'Second Looks Thrift Emporium',
         18: "Drifter Woods' stall (Urbania Park)"}
RARITY = ('common', 'uncommon', 'rare')
KINDS = ('food', 'fun', 'social', 'park', 'gym')

# file -> (list or dict key in the file, what identifies an entry, the fields you may change)
FILES = {
    'pets.json': ('pets', 'name', ('name', 'price', 'description', 'sell')),
    'objects.json': ('objects', 'id', ('name', 'price', 'description', 'sell', 'quality')),
    'places.json': ('places', None, ('kinds',)),
}


class TuningError(Exception):
    pass


def path(mod):
    return os.path.join(TUNING, mod + '.json')


def overrides(mod):
    """{file: {entry key (text): {field: value}}} for a mod (empty if you changed nothing)."""
    try:
        return json.load(open(path(mod), encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _save(mod, data):
    data = {f: {k: v for k, v in ents.items() if v} for f, ents in data.items()}
    data = {f: ents for f, ents in data.items() if ents}
    if not data:
        if os.path.exists(path(mod)):
            os.remove(path(mod))
        return
    os.makedirs(TUNING, exist_ok=True)
    tmp = path(mod) + '.part'
    json.dump(data, open(tmp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    os.replace(tmp, path(mod))


def entries(data, fname):
    """[(key text, entry)] of a mod file's data."""
    where, ident, _ = FILES[fname]
    items = data.get(where, {} if ident is None else [])
    if ident is None:
        return [(str(k), v) for k, v in items.items()]
    return [(str(e.get(ident)), e) for e in items]


def check(fname, field, value):
    """A tuned value, checked -> the value to store (raises TuningError)."""
    if fname not in FILES or field not in FILES[fname][2]:
        raise TuningError('%s: "%s" can\'t be tuned' % (fname, field))
    if field == 'name':
        value = str(value).strip()
        if not 1 <= len(value) <= 30:
            raise TuningError('a name is 1-30 letters')
    elif field == 'price':
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise TuningError('a price is a whole number of Simoleons')
        if not 1 <= value <= 99999:
            raise TuningError('a price is $1-99,999')
    elif field == 'description':
        value = ' '.join(str(value).split())
        if len(value) > 120:
            raise TuningError('a description is at most 120 letters')
    elif field == 'quality':
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise TuningError('quality is 1-5')
        if not 1 <= value <= 5:
            raise TuningError('quality is 1-5')
    elif field == 'sell':
        if not isinstance(value, dict) or any(r not in RARITY for r in value.values()):
            raise TuningError('shops: {list number: common/uncommon/rare}')
        value = {str(int(k)): r for k, r in value.items()}
    elif field == 'kinds':
        if not isinstance(value, (list, tuple)) or any(k not in KINDS for k in value):
            raise TuningError('a place offers some of: ' + ', '.join(KINDS))
        value = [k for k in KINDS if k in value]
    return value


def set_value(mod, fname, key, field, value, original=None):
    """Remember one tuned value (the same as the mod's own one = forget it)."""
    value = check(fname, field, value)
    data = overrides(mod)
    ent = data.setdefault(fname, {}).setdefault(str(key), {})
    if original is not None and value == original:
        ent.pop(field, None)
    else:
        ent[field] = value
    _save(mod, data)


def reset(mod, fname=None, key=None):
    """Forget what you tuned: all of a mod, one file of it, or one entry."""
    if fname is None:
        _save(mod, {})
        return
    data = overrides(mod)
    if key is None:
        data.pop(fname, None)
    else:
        data.get(fname, {}).pop(str(key), None)
    _save(mod, data)


def apply(mod, fname, data):
    """The mod file's data with your tuning on top (a copy; unknown entries and fields are ignored)."""
    tuned = overrides(mod).get(fname)
    if not tuned or fname not in FILES:
        return data
    data = copy.deepcopy(data)
    allowed = FILES[fname][2]
    for key, ent in entries(data, fname):
        for field, value in tuned.get(key, {}).items():
            if field in allowed:
                try:
                    ent[field] = check(fname, field, value)
                except TuningError:
                    pass                                  # a hand-edited bad value: keep the mod's own
    return data


def load(mod_dir, fname):
    """Read a mod's pets.json / objects.json / places.json with your tuning applied."""
    mod = os.path.basename(os.path.normpath(mod_dir))
    data = json.load(open(os.path.join(mod_dir, fname), encoding='utf-8'))
    return apply(mod, fname, data)


# ---------------------------------------------------------------- tables in compiled code

PLACES_MAX = 80                      # NPC Life's sim_places: one {area, kinds, cost} row per area (255 = none)
KIND_BITS = {'food': 1, 'fun': 2, 'social': 4, 'park': 8, 'gym': 16}


def places_table(places):
    """places.json's "places" -> the bytes of NPC Life's sim_places table (mods/npc-life/make_data.py)."""
    rows = []
    for a in sorted(places, key=int):
        p = places[a]
        k = 0
        for kind in p['kinds']:
            k |= KIND_BITS[kind]
        rows.append(struct.pack('<BBB', int(a), k, int(p.get('cost', 0))))
    if len(rows) > PLACES_MAX:
        raise TuningError('places.json: at most %d places' % PLACES_MAX)
    return b''.join(rows) + b'\xff\x00\x00' * (PLACES_MAX - len(rows))


def patch_blob(mod_dir, blob, symbols):
    """A code mod's compiled blob with its data tables rewritten from its (tuned) files, so changes need no
    compiler. Today: NPC Life's places (symbol sim_places, from places.json)."""
    if 'sim_places' in symbols and os.path.exists(os.path.join(mod_dir, 'places.json')):
        table = places_table(load(mod_dir, 'places.json')['places'])
        off = symbols['sim_places']
        blob = bytearray(blob)
        if off + len(table) > len(blob):
            raise TuningError('%s: sim_places is not the size the kit expects (rebuild the mod\'s code)' % mod_dir)
        blob[off:off + len(table)] = table
        blob = bytes(blob)
    return blob


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    if argv[0] == 'show':
        mods = argv[1:] or sorted(os.path.splitext(f)[0] for f in os.listdir(TUNING) if f.endswith('.json')) \
            if os.path.isdir(TUNING) else argv[1:]
        for m in mods:
            print('%s: %s' % (m, json.dumps(overrides(m), ensure_ascii=False) if overrides(m) else 'nothing changed'))
    elif argv[0] == 'reset' and len(argv) == 2:
        reset(argv[1])
        print('%s: back to its own settings' % argv[1])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
