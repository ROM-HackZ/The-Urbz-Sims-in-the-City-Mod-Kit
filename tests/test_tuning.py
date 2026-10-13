#!/usr/bin/env python3
"""Unit tests for urbz_tuning.py (no ROM): your Tune-window settings reach what the builder reads, bad values are
refused, Reset forgets them, and NPC Life's places table is rewritten in its compiled code.
Run: python tests/test_tuning.py"""
import json, os, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT); sys.path.insert(0, os.path.join(KIT, 'kit'))
import urbz_tuning as T
import urbz_objects, urbz_pets


def sandbox():
    T.TUNING = tempfile.mkdtemp()


def test_objects_and_pets_read_tuned():
    sandbox()
    md = os.path.join(KIT, 'mods', 'more-furniture')
    own = {e['id']: e for e in json.load(open(os.path.join(md, 'objects.json')))['objects']}
    T.set_value('more-furniture', 'objects.json', 434, 'price', 999, own[434]['price'])
    T.set_value('more-furniture', 'objects.json', 434, 'sell', {'10': 'rare'}, own[434]['sell'])
    T.set_value('more-furniture', 'objects.json', 434, 'name', 'Big Green Sofa', own[434]['name'])
    got = {e['id']: e for _m, e in urbz_objects.mod_objects([md])}
    assert got[434]['price'] == 999 and got[434]['sell'] == {'10': 'rare'} and got[434]['name'] == 'Big Green Sofa'
    assert got[430]['price'] == own[430]['price']                 # the others untouched
    pd = os.path.join(KIT, 'mods', 'pets')
    T.set_value('pets', 'pets.json', 'Puppy', 'price', 5, 60)
    pets = {p['name']: p for _m, _d, p in urbz_pets.mod_pets([pd])}
    assert pets['Puppy']['price'] == 5, pets['Puppy']['price']


def test_same_as_own_forgets():
    sandbox()
    T.set_value('more-furniture', 'objects.json', 430, 'price', 200, 180)
    T.set_value('more-furniture', 'objects.json', 430, 'price', 180, 180)   # back to the mod's own
    assert T.overrides('more-furniture') == {}


def test_bad_values_refused():
    sandbox()
    for field, value in (('price', 0), ('price', 'lots'), ('quality', 9), ('name', ''), ('name', 'x' * 31),
                         ('sell', {'4': 'often'}), ('like', 5)):
        try:
            T.set_value('m', 'objects.json', 430, field, value)
        except T.TuningError:
            continue
        raise AssertionError('accepted %s = %r' % (field, value))
    assert T.overrides('m') == {}


def test_reset():
    sandbox()
    T.set_value('m', 'objects.json', 1, 'price', 10)
    T.set_value('m', 'objects.json', 2, 'price', 20)
    T.set_value('m', 'places.json', '42', 'kinds', ['food'])
    T.reset('m', 'objects.json', 1)
    assert set(T.overrides('m')['objects.json']) == {'2'}
    T.reset('m', 'objects.json')
    assert list(T.overrides('m')) == ['places.json']
    T.reset('m')
    assert T.overrides('m') == {} and not os.path.exists(T.path('m'))


def test_places_in_compiled_code():
    sandbox()
    md = os.path.join(KIT, 'mods', 'npc-life')
    info = json.load(open(os.path.join(md, 'code', 'build', 'patch.json')))
    blob = open(os.path.join(md, 'code', 'build', 'patch.bin'), 'rb').read()
    off = info['symbols']['sim_places']
    own = T.places_table(json.load(open(os.path.join(md, 'places.json')))['places'])
    assert blob[off:off + len(own)] == own, 'npc-life is compiled from an older places.json: run make_data.py'
    T.set_value('npc-life', 'places.json', '42', 'kinds', ['gym', 'food'])
    new = T.patch_blob(md, blob, info['symbols'])
    row = next(k for k in range(0, len(own), 3) if new[off + k] == 42)
    assert new[off + row + 1] == 1 | 16 and len(new) == len(blob)
    assert new[:off] == blob[:off] and new[off + len(own):] == blob[off + len(own):]


if __name__ == '__main__':
    n = 0
    for name, f in sorted(globals().items()):
        if name.startswith('test_'):
            f()
            print('ok ', name)
            n += 1
    print('%d passed' % n)
