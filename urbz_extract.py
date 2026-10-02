#!/usr/bin/env python3
"""Unpack The Urbz DS ROM into an editable project folder.

Usage: python3 urbz_extract.py "Urbz.nds" project_dir

Layout written:
  project_dir/
    base.nds                 untouched original (header, code, banner are reused from it)
    sound/SoundData.rom
    assets/00000.bin ...     one file per rom.bin entry, raw bytes (the "container")
    unpacked/NNNNN/HHHHHH.bin  every compressed chunk inside asset NNNNN, decompressed;
                               HHHHHH is the chunk header's byte offset (hex) in the asset
    manifest.json            entry order, hashes and chunk table used by urbz_build.py

    unpacked/NNNNN/HHHHHH.tiles.bin  decompressed tile stream embedded at the end of that
                               chunk (screens), when it has one
    sprite_refs.json         which sprite layouts point at which chunk offsets

Don't edit project/ directly: put changes in a mod (see urbz_mod.py), then run
urbz_build.py. Untouched chunks are reused byte-for-byte.

Upgrade an older project (adds tiles files + sprite_refs.json, keeps everything else):
  python3 urbz_extract.py --upgrade project
"""
import hashlib, json, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ndspy.rom
from scan_chunks import asset_chunks, find_trailing_nested
from urbzcomp import unpack_chunk


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def split_rombin(data):
    first = struct.unpack_from('<I', data, 0)[0]
    count = first // 4                      # includes trailing EOF sentinel
    offs = struct.unpack_from('<%dI' % count, data, 0)
    if offs[-1] != len(data):
        raise ValueError('rom.bin table does not end with EOF sentinel')
    return [data[offs[i]:offs[i + 1]] for i in range(count - 1)]


def main(nds_path, out_dir):
    raw_nds = open(nds_path, 'rb').read()
    rom = ndspy.rom.NintendoDSRom(raw_nds)
    names = {rom.filenames.filenameOf(i): i for i in range(len(rom.files))}
    rombin = rom.files[names['rom.bin']]
    sound = rom.files[names['SoundData.rom']]

    for sub in ('assets', 'sound', 'unpacked'):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)

    entries = split_rombin(rombin)
    manifest = {'source_sha1': sha1(raw_nds), 'format': 4, 'entries': []}
    n_chunks = 0
    for i, e in enumerate(entries):
        name = '%05d.bin' % i
        with open(os.path.join(out_dir, 'assets', name), 'wb') as f:
            f.write(e)
        rec = {'file': name, 'size': len(e), 'sha1': sha1(e)}
        chunks = asset_chunks(e)
        if chunks:
            cdir = os.path.join(out_dir, 'unpacked', '%05d' % i)
            os.makedirs(cdir, exist_ok=True)
            rec['chunks'] = []
            for off, flags, size, slot, out in chunks:
                cname = '%06X.bin' % off
                out = unpack_chunk(flags, out)       # 0xE0 chunks: undo delta
                with open(os.path.join(cdir, cname), 'wb') as f:
                    f.write(out)
                crec = {'off': off, 'slot': slot,
                        'flags': flags, 'file': cname, 'sha1': sha1(out)}
                add_nested(cdir, cname, out, crec)
                rec['chunks'].append(crec)
                n_chunks += 1
        manifest['entries'].append(rec)
        if i % 1000 == 0:
            print('  %d / %d assets' % (i, len(entries)), flush=True)

    with open(os.path.join(out_dir, 'sound', 'SoundData.rom'), 'wb') as f:
        f.write(sound)
    with open(os.path.join(out_dir, 'base.nds'), 'wb') as f:
        f.write(raw_nds)
    with open(os.path.join(out_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=0)
    from urbz_sprites import build_refs
    build_refs(out_dir)
    from urbz_text import export as export_text
    export_text(out_dir, os.path.join(out_dir, 'text', 'strings.tsv'))
    print('extracted %d assets (%d compressed chunks unpacked) to %s'
          % (len(entries), n_chunks, out_dir))


def add_nested(cdir, cname, content, crec):
    """If a decoded chunk ends with an embedded [u16 len][stream] (e.g. a screen's
    tiles), also write the decompressed stream as <chunk>.tiles.bin."""
    nest = find_trailing_nested(content)
    if not nest:
        return False
    pos, L, tiles = nest
    tname = cname[:-4] + '.tiles.bin'
    with open(os.path.join(cdir, tname), 'wb') as f:
        f.write(tiles)
    crec['nested'] = {'pos': pos, 'len': L, 'file': tname, 'sha1': sha1(tiles)}
    return True


def upgrade(proj):
    """Bring an existing project up to format 4 without re-extracting everything:
      - format 3: <chunk>.tiles.bin files for embedded tile streams
      - format 4: chunks in every codec (raw, LZ77 and EA), not just EA ones
    and (re)write sprite_refs.json. Untouched files and records are kept as is."""
    mpath = os.path.join(proj, 'manifest.json')
    manifest = json.load(open(mpath))
    fmt = manifest.get('format', 2)
    added_tiles = added_chunks = 0
    if fmt < 4:
        for i, rec in enumerate(manifest['entries']):
            raw = open(os.path.join(proj, 'assets', rec['file']), 'rb').read()
            if sha1(raw) != rec['sha1']:
                sys.exit('error: assets/%s was edited inside project/. Run '
                         '"python urbz_mod.py rescue <mod>" first, then upgrade.' % rec['file'])
            cdir = os.path.join(proj, 'unpacked', '%05d' % i)
            old = {c['off']: c for c in rec.get('chunks', [])}
            new_list = []
            for off, flags, size, slot, dec in asset_chunks(raw):
                content = unpack_chunk(flags, dec)
                c = old.get(off)
                if c is not None:
                    path = os.path.join(cdir, c['file'])
                    if sha1(open(path, 'rb').read()) != c['sha1']:
                        sys.exit('error: %s was edited inside project/. Run "python urbz_mod.py '
                                 'rescue <mod>" first, then upgrade.' % path)
                    if c['slot'] != slot or c['sha1'] != sha1(content):
                        sys.exit('error: asset %05d chunk %s does not match a fresh scan; '
                                 're-extract the project instead' % (i, c['file']))
                else:
                    os.makedirs(cdir, exist_ok=True)
                    c = {'off': off, 'slot': slot, 'flags': flags, 'file': '%06X.bin' % off,
                         'sha1': sha1(content)}
                    with open(os.path.join(cdir, c['file']), 'wb') as f:
                        f.write(content)
                    added_chunks += 1
                if 'nested' not in c:
                    added_tiles += add_nested(cdir, c['file'], content, c)
                new_list.append(c)
            if new_list:
                rec['chunks'] = new_list
            if i % 2000 == 0:
                print('  %d / %d assets' % (i, len(manifest['entries'])), flush=True)
        manifest['format'] = 4
        tmp = mpath + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(manifest, f, indent=0)
        os.replace(tmp, mpath)
        print('upgraded to format 4: added %d chunk files and %d tile files'
              % (added_chunks, added_tiles))
    else:
        print('project is already format %d' % fmt)
    from urbz_sprites import build_refs
    path, n, covered, multi = build_refs(proj)
    print('sprite_refs.json: %d of %d multi-chunk assets can grow' % (covered, multi))
    from urbz_text import export as export_text
    tpath = os.path.join(proj, 'text', 'strings.tsv')
    if not os.path.exists(tpath):
        print('text/strings.tsv: %d strings' % export_text(proj, tpath))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--upgrade':
        upgrade(sys.argv[2])
    elif len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    else:
        sys.exit('usage: urbz_extract.py <rom.nds> <project_dir>\n'
                 '       urbz_extract.py --upgrade <project_dir>')
