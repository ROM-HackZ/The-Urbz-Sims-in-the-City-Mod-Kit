#!/usr/bin/env python3
"""Manage mods for the Urbz DS Mod Kit.

A mod is a folder under mods/ that holds ONLY the files you changed or added,
at the same relative paths as in project/ (assets/NNNNN.bin,
unpacked/NNNNN/HHHHHH.bin). project/ stays pristine. mods.json lists the
enabled mods; later mods win when two change the same file.

  python urbz_mod.py list                      show mods and which are enabled
  python urbz_mod.py new <mod> ["description"] create a mod and enable it
  python urbz_mod.py edit <mod> <asset> [chunk|--raw]
                                               copy pristine file(s) into the mod to edit
  python urbz_mod.py status [<mod>]            what each mod changes, adds or leaves identical
  python urbz_mod.py enable|disable <mod>      toggle a mod in mods.json
  python urbz_mod.py rescue <mod>              move accidental edits made inside project/
                                               into <mod> and restore project/ to pristine
"""
import hashlib, json, os, shutil, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
PROJ = os.path.join(KIT, 'project')
MODS = os.path.join(KIT, 'mods')
CFG = os.path.join(KIT, 'mods.json')


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def manifest():
    return json.load(open(os.path.join(PROJ, 'manifest.json')))


def load_cfg():
    return json.load(open(CFG)) if os.path.exists(CFG) else {'enabled': []}


def save_cfg(cfg):
    with open(CFG, 'w') as f:
        json.dump(cfg, f, indent=2)


def die(msg):
    sys.exit('error: ' + msg)


def mod_dir(name, must_exist=True):
    d = os.path.join(MODS, name)
    if must_exist and not os.path.isdir(d):
        die('no mod named "%s" (expected folder %s)' % (name, d))
    return d


def cmd_list(_):
    from urbz_code import mod_info
    cfg = load_cfg()
    names = sorted(n for n in os.listdir(MODS)) if os.path.isdir(MODS) else []
    if not names:
        print('no mods yet. Create one with: python urbz_mod.py new my-first-mod')
    for n in names:
        info = mod_info(os.path.join(MODS, n))
        order = cfg['enabled'].index(n) + 1 if n in cfg['enabled'] else None
        print('%-4s %-24s %-8s %s' % ('#%d' % order if order else 'off', n, info['version'],
                                      info['description']))
        extra = []
        if info['author']:
            extra.append('by ' + info['author'])
        if info['toggle']:
            extra.append('in-game switch, starts %s' % ('on' if info['default'] else 'off'))
        if info['save_bytes']:
            extra.append('saves up to %d bytes' % info['save_bytes'])
        if info['conflicts']:
            extra.append('conflicts with ' + ', '.join(info['conflicts']))
        if extra:
            print('     %s' % '; '.join(extra))


def cmd_new(args):
    if not args:
        die('usage: urbz_mod.py new <mod> ["description"]')
    name = args[0]
    if not name.replace('-', '').replace('_', '').isalnum():
        die('mod names may use letters, digits, - and _ only')
    d = mod_dir(name, must_exist=False)
    if os.path.exists(d):
        die('mod "%s" already exists' % name)
    os.makedirs(d)
    with open(os.path.join(d, 'mod.json'), 'w') as f:
        json.dump({'name': name, 'description': args[1] if len(args) > 1 else ''}, f, indent=2)
    cfg = load_cfg()
    cfg['enabled'].append(name)
    save_cfg(cfg)
    print('created and enabled mods/%s' % name)


def cmd_edit(args):
    if len(args) < 2:
        die('usage: urbz_mod.py edit <mod> <asset> [chunk|--raw]')
    d = mod_dir(args[0])
    m = manifest()
    try:
        idx = int(args[1])
        ent = m['entries'][idx]
    except (ValueError, IndexError):
        die('asset must be a number from 0 to %d' % (len(m['entries']) - 1))
    chunks = ent.get('chunks', [])
    if len(args) > 2 and args[2] == '--raw' or not chunks:
        rels = ['assets/' + ent['file']]
    elif len(args) > 2:
        want = args[2] if args[2].endswith('.bin') else args[2] + '.bin'
        nested = {c['nested']['file']: c for c in chunks if 'nested' in c}
        if want in nested:
            rels = ['unpacked/%05d/%s' % (idx, want)]
        elif not any(c['file'] == want for c in chunks):
            die('asset %05d has no chunk %s. Its chunks: %s'
                % (idx, want, ', '.join(c['file'] for c in chunks)))
        else:
            rels = ['unpacked/%05d/%s' % (idx, want)]
    else:
        rels = ['unpacked/%05d/%s' % (idx, c['file']) for c in chunks]
    # Chunks with an embedded tile stream: copy its .tiles.bin too (edit either file).
    for c in chunks:
        if 'nested' in c and 'unpacked/%05d/%s' % (idx, c['file']) in rels:
            rels.append('unpacked/%05d/%s' % (idx, c['nested']['file']))
    for rel in rels:
        dst = os.path.join(d, *rel.split('/'))
        if os.path.exists(dst):
            print('already in mod (left as is): ' + dst)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(PROJ, *rel.split('/')), dst)
        print('copied to edit: ' + dst)


def classify(rel, path, m):
    """'changed' / 'identical' / 'new' / 'unknown' for one mod file."""
    n = len(m['entries'])
    data = open(path, 'rb').read()
    parts = rel.split('/')
    if parts[0] == 'assets' and parts[-1][:5].isdigit():
        i = int(parts[-1][:5])
        if i >= n:
            return 'new'
        return 'identical' if sha1(data) == m['entries'][i]['sha1'] else 'changed'
    if parts[0] == 'unpacked' and len(parts) == 3 and parts[1].isdigit() and int(parts[1]) < n:
        for c in m['entries'][int(parts[1])].get('chunks', []):
            if c['file'] == parts[2]:
                return 'identical' if sha1(data) == c['sha1'] else 'changed'
            if c.get('nested', {}).get('file') == parts[2]:
                return 'identical' if sha1(data) == c['nested']['sha1'] else 'changed'
    if rel == 'sound/SoundData.rom':
        return 'changed'
    if rel == 'text/strings.tsv':
        return 'text'
    if parts[0] == 'png' and rel.endswith('.png'):
        return 'png'
    if parts[0] == 'code':
        return 'code'
    if parts[0] == 'font':
        return 'font'
    if parts[0] == 'palette':
        return 'palette'
    return 'unknown'


def cmd_status(args):
    m = manifest()
    cfg = load_cfg()
    names = [args[0]] if args else sorted(os.listdir(MODS)) if os.path.isdir(MODS) else []
    for n in names:
        d = mod_dir(n)
        state = 'enabled #%d' % (cfg['enabled'].index(n) + 1) if n in cfg['enabled'] else 'disabled'
        print('== %s (%s)' % (n, state))
        rows = []
        for root, dirs, files in os.walk(d):
            for f in files:
                if f in ('mod.json', 'README.md', 'README.txt') or f.startswith('.'):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, d).replace(os.sep, '/')
                rows.append((rel, classify(rel, p, m)))
        if not rows:
            print('   (empty)')
        for rel, st in sorted(rows):
            print('   %-9s %s' % (st, rel))
        for rel, st in rows:
            if st == 'text':
                try:
                    from urbz_text import read_tsv
                    print('             (%d string edit(s))' % len(read_tsv(os.path.join(d, 'text', 'strings.tsv'))))
                except ValueError as e:
                    print('             ! ' + str(e))
        if any(st == 'unknown' for _, st in rows):
            print('   ! "unknown" files do not match anything in the project and will make the build fail')


def pristine_bytes(rel, m, base_entries):
    from urbzcomp import decompress, unpack_chunk
    parts = rel.split('/')
    if parts[0] == 'assets':
        return base_entries[int(parts[-1][:5])]
    i = int(parts[1])
    raw = base_entries[i]
    for c in m['entries'][i]['chunks']:
        if c['file'] == parts[2]:
            return unpack_chunk(c['flags'], decompress(raw, c['off'] + 4))
        if c.get('nested', {}).get('file') == parts[2]:
            content = unpack_chunk(c['flags'], decompress(raw, c['off'] + 4))
            return decompress(content, c['nested']['pos'] + 2)
    raise KeyError(rel)


def cmd_rescue(args):
    if not args:
        die('usage: urbz_mod.py rescue <mod>')
    d = mod_dir(args[0])
    import ndspy.rom
    from urbz_extract import split_rombin
    m = manifest()
    print('checking every file in project/ against the manifest (takes a minute)...')
    edited = []
    for i, ent in enumerate(m['entries']):
        rel = 'assets/' + ent['file']
        if sha1(open(os.path.join(PROJ, *rel.split('/')), 'rb').read()) != ent['sha1']:
            edited.append(rel)
        for c in ent.get('chunks', []):
            rel = 'unpacked/%05d/%s' % (i, c['file'])
            if sha1(open(os.path.join(PROJ, *rel.split('/')), 'rb').read()) != c['sha1']:
                edited.append(rel)
            if 'nested' in c:
                rel = 'unpacked/%05d/%s' % (i, c['nested']['file'])
                p = os.path.join(PROJ, *rel.split('/'))
                if os.path.exists(p) and sha1(open(p, 'rb').read()) != c['nested']['sha1']:
                    edited.append(rel)
    if not edited:
        print('project/ is pristine. Nothing to rescue.')
        return
    rom = ndspy.rom.NintendoDSRom.fromFile(os.path.join(PROJ, 'base.nds'))
    base_entries = split_rombin(rom.files[0])
    for rel in edited:
        src = os.path.join(PROJ, *rel.split('/'))
        dst = os.path.join(d, *rel.split('/'))
        if os.path.exists(dst):
            die('%s already exists in mod "%s"; resolve it by hand first' % (rel, args[0]))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        with open(src, 'wb') as f:
            f.write(pristine_bytes(rel, m, base_entries))
        print('rescued %s -> mods/%s/' % (rel, args[0]))
    print('%d file(s) moved into the mod; project/ restored to pristine.' % len(edited))


def cmd_toggle(args, on):
    if not args:
        die('usage: urbz_mod.py %s <mod>' % ('enable' if on else 'disable'))
    mod_dir(args[0])
    cfg = load_cfg()
    if on and args[0] not in cfg['enabled']:
        cfg['enabled'].append(args[0])
    if not on and args[0] in cfg['enabled']:
        cfg['enabled'].remove(args[0])
    save_cfg(cfg)
    print('%s %s' % ('enabled' if on else 'disabled', args[0]))


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    os.makedirs(MODS, exist_ok=True)
    table = {'list': cmd_list, 'new': cmd_new, 'edit': cmd_edit, 'status': cmd_status,
             'rescue': cmd_rescue, 'enable': lambda a: cmd_toggle(a, True),
             'disable': lambda a: cmd_toggle(a, False)}
    if cmd not in table:
        die('unknown command "%s". Run: python urbz_mod.py help' % cmd)
    table[cmd](args)


if __name__ == '__main__':
    main(sys.argv[1:])
