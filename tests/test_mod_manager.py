#!/usr/bin/env python3
"""Unit tests for mod_manager.py (no ROM, no window): mod zips and the enabled list.
Run: python tests/test_mod_manager.py"""
import io, json, os, sys, tempfile, zipfile
KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT)
import mod_manager as M
import urbz_mod


def make_zip(files):
    p = os.path.join(tempfile.mkdtemp(), 'mod.zip')
    with zipfile.ZipFile(p, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return p


def sandbox():
    d = tempfile.mkdtemp()
    M.MODS = urbz_mod.MODS = os.path.join(d, 'mods')
    urbz_mod.CFG = os.path.join(d, 'mods.json')
    os.makedirs(M.MODS)
    return d


def refused(files, words):
    try:
        M.install_zip(make_zip(files))
    except M.ManagerError as e:
        assert words in str(e), str(e)
        return
    raise AssertionError('installed a bad zip: %s' % list(files))


def test_install_folder_and_root_zips():
    sandbox()
    meta = json.dumps({'name': 'hello', 'version': '1.2', 'toggle': True})
    assert M.install_zip(make_zip({'hello/mod.json': meta, 'hello/text/strings.tsv': 'x'})) == 'hello'
    assert os.path.exists(os.path.join(M.MODS, 'hello', 'text', 'strings.tsv'))
    assert M.install_zip(make_zip({'mod.json': json.dumps({'name': 'flat'}), 'code/hooks.txt': ''})) == 'flat'
    assert os.path.exists(os.path.join(M.MODS, 'flat', 'code', 'hooks.txt'))
    refused({'hello/mod.json': meta}, 'already installed')
    assert M.install_zip(make_zip({'hello/mod.json': meta}), replace=True) == 'hello'


def test_refuses_game_files_and_bad_paths():
    sandbox()
    meta = json.dumps({'name': 'x'})
    refused({'x/mod.json': meta, 'x/game.nds': b'rom'}, 'must not include')
    refused({'x/mod.json': meta, 'x/save.sav': b'.'}, 'must not include')
    refused({'x/mod.json': meta, 'project/assets/00000.bin': b'.'}, 'must not include')
    refused({'x/mod.json': meta, 'x/../../evil.txt': b'.'}, 'unsafe path')
    refused({'readme.txt': b'.'}, 'no mod.json')
    refused({'x/mod.json': '{bad json'}, 'not valid JSON')


def test_enabled_order_and_conflicts():
    sandbox()
    for n, extra in (('a', {}), ('b', {'conflicts': ['a']}), ('c', {})):
        os.makedirs(os.path.join(M.MODS, n))
        json.dump(dict(name=n, **extra), open(os.path.join(M.MODS, n, 'mod.json'), 'w'))
    M.save_enabled(['c', 'a'])
    assert [m['name'] for m in M.list_mods()] == ['c', 'a', 'b']
    assert [m['enabled'] for m in M.list_mods()] == [True, True, False]
    assert M.check(['c', 'a']) == ([], [])
    errs, _ = M.check(['a', 'b'])
    assert errs and 'conflicts' in errs[0], errs


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok  ' + name)
