#!/usr/bin/env python3
"""Rebuild The Urbz DS ROM from a project folder made by urbz_extract.py.

Usage: python3 urbz_build.py project_dir out.nds

The original cartridge image (base.nds) is patched in place: rom.bin and
SoundData.rom are rewritten, the file allocation table, used-ROM-size field
and header CRC are updated, and everything else (code, banner, secure area)
is left byte-for-byte untouched. With no edits the output is identical to
the original dump.

Asset order comes from manifest.json. To ADD an asset, append an entry at
the end so existing asset IDs never shift. The ROM grows into the free
space after SoundData; past 32 MB the cartridge capacity is raised.
"""
import hashlib, json, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from urbzcomp import pack_chunk, compress

ROMBIN_ID, SOUND_ID = 0, 1          # FAT indices (see notes.md)
ALIGN = 0x200


def pad4(b):
    return b + b'\0' * (-len(b) % 4)


def join_rombin(entries):
    count = len(entries) + 1                # + EOF sentinel
    pos = count * 4
    offs = []
    for e in entries:
        offs.append(pos)
        pos += len(e)
    offs.append(pos)
    return struct.pack('<%dI' % count, *offs) + b''.join(entries)


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def align(x):
    return (x + ALIGN - 1) & ~(ALIGN - 1)


class BuildError(Exception):
    pass


class Overlay:
    """Resolves project-relative paths through enabled mods (later mods win)."""

    def __init__(self, proj, mod_dirs=()):
        self.proj = proj
        self.mod_dirs = list(mod_dirs)
        self.files = {}                       # 'assets/00001.bin' -> (mod_name, abs path)
        for md in self.mod_dirs:
            name = os.path.basename(os.path.normpath(md))
            for root, dirs, files in os.walk(md):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if f.startswith('.') or f in ('mod.json', 'README.md', 'README.txt'):
                        continue
                    p = os.path.join(root, f)
                    rel = os.path.relpath(p, md).replace(os.sep, '/')
                    self.files[rel] = (name, p)

    def path(self, rel):
        hit = self.files.get(rel)
        return hit[1] if hit else os.path.join(self.proj, *rel.split('/'))

    def overridden(self, rel):
        return rel in self.files

    def chunk_overrides(self, idx):
        prefix = 'unpacked/%05d/' % idx
        return [r for r in self.files if r.startswith(prefix)]

    def new_asset_ids(self, n_existing):
        ids = sorted(int(r[7:12]) for r in self.files
                     if r.startswith('assets/') and r.endswith('.bin') and len(r) == 16
                     and r[7:12].isdigit() and int(r[7:12]) >= n_existing)
        return ids


class AssetResult:
    """What assemble_asset produced for one asset."""

    def __init__(self, data, changed=0, moved=None, grown=0):
        self.data = data            # final bytes (padded to 4)
        self.changed = changed      # number of chunks (or whole-asset replacements) changed
        self.moved = moved or {}    # {old chunk offset: new offset} for chunks that moved
        self.grown = grown          # chunks that no longer fit their original slot


def _chunk_content(ov, idx, ch, png=None):
    """Final decoded content of one chunk: a converted PNG from a mod if there is
    one, else the chunk file with an edited .tiles.bin spliced back in."""
    if png and (idx, ch['file']) in png:
        return png[(idx, ch['file'])]
    content = open(ov.path('unpacked/%05d/%s' % (idx, ch['file'])), 'rb').read()
    nest = ch.get('nested')
    if nest:
        trel = 'unpacked/%05d/%s' % (idx, nest['file'])
        tpath = ov.path(trel)
        if os.path.exists(tpath):
            tiles = open(tpath, 'rb').read()
            if hashlib.sha1(tiles).hexdigest() != nest['sha1']:
                if len(content) < nest['pos'] + 2:
                    raise BuildError('asset %05d chunk %s is too short to hold its tile stream '
                                     '(was it truncated?)' % (idx, ch['file']))
                stream = compress(tiles)
                if len(stream) > 0xFFFF:
                    raise BuildError('asset %05d %s: compressed tiles are %d bytes; the format '
                                     'allows 65535' % (idx, nest['file'], len(stream)))
                content = content[:nest['pos']] + struct.pack('<H', len(stream)) + stream
    return content


def assemble_asset(proj, idx, ent, overlay=None, refs=None, png=None):
    """Build one asset. Edited chunks are recompressed; if any no longer fits its
    slot, the chunks are laid out again and AssetResult.moved says which chunk
    offsets changed (the caller re-points sprite layouts using sprite_refs)."""
    ov = overlay or Overlay(proj)
    raw_rel = 'assets/' + ent['file']
    data = bytes(open(ov.path(raw_rel), 'rb').read())
    if ov.overridden(raw_rel):
        # A mod replaced the whole container: use it verbatim. Mixing that with
        # per-chunk edits would apply chunk offsets to a different layout.
        if ov.chunk_overrides(idx):
            raise BuildError(
                'asset %05d: a mod replaces assets/%s AND edits chunks in unpacked/%05d/. '
                'Edit one or the other.' % (idx, ent['file'], idx))
        return AssetResult(pad4(data), 1)
    chunks = sorted(ent.get('chunks', []), key=lambda c: c['off'])
    if not chunks:
        return AssetResult(pad4(data))

    blocks = []                    # (chunk, bytes or None if untouched, fits_slot)
    changed = 0
    for ch in chunks:
        content = _chunk_content(ov, idx, ch, png)
        if hashlib.sha1(content).hexdigest() == ch['sha1']:
            blocks.append((ch, None, True))
            continue
        changed += 1
        packed = pack_chunk(ch['flags'], content)
        blocks.append((ch, packed, len(packed) <= ch['slot']))
    if not changed:
        return AssetResult(pad4(data))

    if all(fits for _, _, fits in blocks):
        out = bytearray(data)                       # everything fits: patch in place
        for ch, packed, _ in blocks:
            if packed is not None:
                out[ch['off']:ch['off'] + ch['slot']] = packed + b'\0' * (ch['slot'] - len(packed))
        return AssetResult(pad4(bytes(out)), changed)

    # Some chunk outgrew its slot: lay the asset out again, chunk after chunk,
    # keeping any bytes between chunks and after the last one.
    out = bytearray()
    moved = {}
    pos = 0
    for ch, packed, _ in blocks:
        out += data[pos:ch['off']]                  # gap before this chunk (usually none)
        if len(out) != ch['off']:
            moved[ch['off']] = len(out)
        out += data[ch['off']:ch['off'] + ch['slot']] if packed is None else pad4(packed)
        pos = ch['off'] + ch['slot']
    tail = data[pos:]
    tail_moved = len(tail) > 3 and len(out) != pos
    out += tail
    grown = sum(1 for _, p, fits in blocks if p is not None and not fits)

    if moved or tail_moved:
        info = (refs or {}).get('%05d' % idx)
        known = set(info['referenced_offsets']) if info else set()
        unknown = sorted(o for o in moved if o not in known)
        if tail_moved:
            raise BuildError(
                'asset %05d: an edited chunk grew and the asset has %d bytes of other data after '
                'its last chunk that would move. Nothing tells the game where that data is, so '
                'keep the edit small enough to fit (%s).' % (idx, len(tail), _slot_hint(blocks)))
        if not info or unknown:
            raise BuildError(
                'asset %05d: an edited chunk grew, which moves the chunk(s) at offset(s) %s, but '
                'no known sprite layout points at %s. Keep the edit small enough to fit its slot '
                '(%s), or find what references this asset first.'
                % (idx, ', '.join(map(str, unknown or sorted(moved))),
                   'them' if (unknown or moved) else 'it', _slot_hint(blocks)))
        if max(moved.values()) > 0xFFFF:
            raise BuildError('asset %05d would grow past 64 KB; sprite layouts can only point '
                             'at the first 65,535 bytes. Shrink the edit.' % idx)
    return AssetResult(pad4(bytes(out)), changed, moved, grown)


def _slot_hint(blocks):
    worst = [(ch['file'], len(p), ch['slot']) for ch, p, fits in blocks if p is not None and not fits]
    return '; '.join('%s packs to %d bytes, slot is %d' % w for w in worst)


def repoint_layout(layout_bytes, moved, idx):
    """Patch a sprite layout's chunk offsets (u16 at entry+4) using {old: new}."""
    from urbz_sprites import layout_offsets
    b = bytearray(layout_bytes)
    lo = layout_offsets(b)
    if lo is None:
        raise BuildError('asset %05d is listed as a sprite layout but does not parse as one '
                         '(was it replaced by a mod?)' % idx)
    n = 0
    for field, off in lo:
        if off in moved:
            struct.pack_into('<H', b, field, moved[off])
            n += 1
    return bytes(b), n


def load_mod_list(kit_dir, config=None):
    """Read mods.json -> list of enabled mod folders (in priority order)."""
    cfg_path = config or os.path.join(kit_dir, 'mods.json')
    if not os.path.exists(cfg_path):
        return []
    cfg = json.load(open(cfg_path))
    mods_root = os.path.join(kit_dir, 'mods')
    out = []
    for name in cfg.get('enabled', []):
        d = os.path.join(mods_root, name)
        if not os.path.isdir(d):
            raise BuildError('mods.json enables "%s" but %s does not exist' % (name, d))
        out.append(d)
    return out


# The game's asset manager keeps 3 tables sized for exactly the original assets (docs/systems.md
# "Assets"): where each one is in rom.bin (read from rom.bin's own index at boot), where it is
# loaded, and a use count. When mods add assets, a generated code mod moves the tables into the
# code region, sized for the build, and patches the 5 counts, the read size and 13 table addresses.
ASSET_OFFSETS_LITS = (0x02032B00, 0x02032C94)            # -> offsets; 0x02032C98 -> offsets + 4
ASSET_PTRS_LITS = (0x02032CA0, 0x02032DE0, 0x02032E84, 0x02032F58, 0x020330DC)
ASSET_REFS_LITS = (0x02032DDC, 0x02032E80, 0x02032F5C, 0x020330D8)
ASSET_COUNT_LITS = (0x02032C90, 0x02032DD8, 0x02032E88, 0x02032F54, 0x020330E0)   # entries (0x344A)
ASSET_READ_SIZE_LIT = 0x02032B04                         # bytes of rom.bin's index read at boot


def asset_tables_mod(proj, n_entries):
    """Write build/new-assets/ (a code mod of zeroed tables + hooks) for n_entries index entries."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build', 'new-assets')
    cdir = os.path.join(d, 'code')
    os.makedirs(os.path.join(cdir, 'build'), exist_ok=True)
    words = n_entries * 4
    refs_size = (n_entries + 3) & ~3
    lines = ['# Generated by urbz_build.py: the asset tables, sized for %d index entries' % n_entries]
    lines += ['u32 0x%08X @asset_offsets' % a for a in ASSET_OFFSETS_LITS]
    lines += ['u32 0x02032C98 @asset_offsets+4']
    lines += ['u32 0x%08X @asset_ptrs' % a for a in ASSET_PTRS_LITS]
    lines += ['u32 0x%08X @asset_refs' % a for a in ASSET_REFS_LITS]
    lines += ['u32 0x%08X %d' % (a, n_entries) for a in ASSET_COUNT_LITS]
    lines += ['u32 0x%08X %d' % (ASSET_READ_SIZE_LIT, words)]
    open(os.path.join(cdir, 'hooks.txt'), 'w').write('\n'.join(lines) + '\n')
    open(os.path.join(cdir, 'build', 'patch.bin'), 'wb').write(b'NEWA')      # gives the mod a place
    json.dump({'relocs': [], 'symbols': {'asset_offsets': 4, 'asset_ptrs': 4 + words, 'asset_refs': 4 + 2 * words},
               'bss': 2 * words + refs_size, 'sources': {}}, open(os.path.join(cdir, 'build', 'patch.json'), 'w'))
    json.dump({'name': 'new-assets', 'description': 'Kit: room for the assets mods add', 'toggle': False,
               'hidden': True},
              open(os.path.join(d, 'mod.json'), 'w'))
    return d


def _first_free_string(proj, mod_dirs):
    """The first string number after the game's and after any new ones mods add."""
    from urbz_text import project_strings, read_tsv
    n = len(project_strings(proj))
    for md in mod_dirs:
        p = os.path.join(md, 'text', 'strings.tsv')
        if os.path.exists(p) and os.path.basename(os.path.normpath(md)) != 'new-objects':
            n = max([n] + [k + 1 for k in read_tsv(p)])
    return n


def build(proj, out_path, mod_dirs=(), quiet=False):
    manifest = json.load(open(os.path.join(proj, 'manifest.json')))
    from urbz_code import check_mod_set, CodeError
    try:
        for w in check_mod_set(mod_dirs):
            print(w)
    except CodeError as e:
        raise BuildError(str(e))
    # Objects: mods with objects.json get the object tables moved (a generated, hidden mod).
    from urbz_objects import objects_mod, ObjectsError
    try:
        odir, objects_line = objects_mod(proj, mod_dirs, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build', 'new-objects'),
                                         lambda: _first_free_string(proj, mod_dirs))
    except ObjectsError as e:
        raise BuildError(str(e))
    if odir:
        mod_dirs = list(mod_dirs) + odir
        if not quiet:
            print(objects_line)
    ov = Overlay(proj, mod_dirs)
    n_existing = len(manifest['entries'])

    # Catch chunk files in mods that don't correspond to a real chunk.
    for rel in ov.files:
        if rel.startswith('unpacked/'):
            parts = rel.split('/')
            ok = len(parts) == 3 and parts[1].isdigit() and int(parts[1]) < n_existing and \
                any(parts[2] in (c['file'], c.get('nested', {}).get('file'))
                    for c in manifest['entries'][int(parts[1])].get('chunks', []))
            if not ok:
                raise BuildError('mod file %s (in mod "%s") does not match any chunk in the '
                                 'manifest. Check the asset number and chunk filename.'
                                 % (rel, ov.files[rel][0]))

    refs_path = os.path.join(proj, 'sprite_refs.json')
    refs = json.load(open(refs_path))['gfx'] if os.path.exists(refs_path) else {}

    # PNG edits in mods -> decoded chunk content.
    from urbz_png import png_overrides
    try:
        png, png_warnings = png_overrides(proj, ov, manifest, refs)
    except ValueError as e:
        raise BuildError(str(e))
    for w in png_warnings:
        print('warning: ' + w)

    entries, changed, grown = [], 0, 0
    repoint = {}                                   # layout index -> {old: new}
    for idx, ent in enumerate(manifest['entries']):
        r = assemble_asset(proj, idx, ent, ov, refs, png)
        if r.changed or hashlib.sha1(r.data).hexdigest() != ent.get('sha1'):
            changed += 1
        grown += r.grown
        if r.moved:
            for l in refs['%05d' % idx]['layouts']:
                li = int(l)
                if li in repoint and repoint[li] != r.moved:
                    raise BuildError('sprite layout %s is shared by two grown assets' % l)
                repoint[li] = r.moved
        entries.append(r.data)

    # Text: if a mod edits strings, re-encode the text bank (asset 00054).
    from urbz_text import build_text_asset, TEXT_ASSET
    try:
        bank = build_text_asset(proj, ov)
    except ValueError as e:
        raise BuildError(str(e))
    text_changed = 0
    if bank is not None:
        if ov.overridden('assets/' + manifest['entries'][TEXT_ASSET]['file']):
            raise BuildError('a mod edits text/strings.tsv AND replaces assets/%s (the text bank). '
                             'Use one or the other.' % manifest['entries'][TEXT_ASSET]['file'])
        entries[TEXT_ASSET] = pad4(bank)
        changed += 1
        text_changed = 1

    # Fonts: edited PNG sheets in mods/*/font/ -> font assets.
    from urbz_font import font_overrides
    try:
        fonts = font_overrides(proj, ov)
    except ValueError as e:
        raise BuildError(str(e))
    for idx, data in fonts.items():
        entries[idx] = pad4(data)
        changed += 1

    # Palettes: edited swatch sheets in mods/*/palette/ -> palette assets.
    from urbz_palette import palette_overrides
    try:
        pals = palette_overrides(proj, ov)
    except ValueError as e:
        raise BuildError(str(e))
    for idx, data in pals.items():
        entries[idx] = pad4(data)
        changed += 1

    # Second pass: re-point sprite layouts at the chunks' new offsets.
    layouts_patched = 0
    for li, moved in repoint.items():
        new, n = repoint_layout(entries[li], moved, li)
        if n:
            entries[li] = pad4(new)
            layouts_patched += 1
            changed += 1

    # New assets: IDs must continue the sequence with no gaps.
    new_ids = ov.new_asset_ids(n_existing)
    if new_ids and new_ids != list(range(n_existing, n_existing + len(new_ids))):
        raise BuildError('new assets must be numbered %05d, %05d, ... with no gaps; found %s'
                         % (n_existing, n_existing + 1, ', '.join('%05d' % i for i in new_ids)))
    for i in new_ids:
        entries.append(pad4(open(ov.path('assets/%05d.bin' % i), 'rb').read()))
        changed += 1

    rombin = join_rombin(entries)
    sound = open(ov.path('sound/SoundData.rom'), 'rb').read()
    if new_ids:                          # the game's asset tables only fit the original assets
        mod_dirs = list(mod_dirs) + [asset_tables_mod(proj, len(entries) + 1)]

    img = bytearray(open(os.path.join(proj, 'base.nds'), 'rb').read())
    fat_off = struct.unpack_from('<I', img, 0x48)[0]
    rb_start, old_rb_end = struct.unpack_from('<II', img, fat_off + 8 * ROMBIN_ID)
    old_snd_start, old_snd_end = struct.unpack_from('<II', img, fat_off + 8 * SOUND_ID)

    rb_end = rb_start + len(rombin)
    # Keep SoundData where it was if rom.bin still fits before it.
    snd_start = old_snd_start if rb_end <= old_snd_start else align(rb_end)
    snd_end = snd_start + len(sound)

    # Grow the image if needed (DS carts are power-of-two sizes from 128 KB).
    cap = img[0x14]
    while (0x20000 << cap) < snd_end:
        cap += 1
    if (0x20000 << cap) > len(img):
        img += b'\xff' * ((0x20000 << cap) - len(img))
        img[0x14] = cap

    # Blank any region the old files occupied that the new layout no longer
    # covers (the original gap bytes are kept when nothing moves).
    if rb_end < old_rb_end:
        img[rb_end:old_rb_end] = b'\xff' * (old_rb_end - rb_end)
    if snd_start != old_snd_start:
        img[old_snd_start:old_snd_end] = b'\xff' * (old_snd_end - old_snd_start)
        img[rb_end:snd_start] = b'\xff' * (snd_start - rb_end)
    elif snd_end < old_snd_end:
        img[snd_end:old_snd_end] = b'\xff' * (old_snd_end - snd_end)

    img[rb_start:rb_end] = rombin
    img[snd_start:snd_end] = sound

    struct.pack_into('<II', img, fat_off + 8 * ROMBIN_ID, rb_start, rb_end)
    struct.pack_into('<II', img, fat_off + 8 * SOUND_ID, snd_start, snd_end)
    struct.pack_into('<I', img, 0x80, snd_end)          # total used ROM size

    # Code mods: compiled blobs + hooks into the game's code (urbz_code.py).
    from urbz_code import apply_to_image, CodeError
    try:
        code_report = apply_to_image(img, mod_dirs)
    except CodeError as e:
        raise BuildError(str(e))
    struct.pack_into('<H', img, 0x15E, crc16(img[:0x15E]))

    open(out_path, 'wb').write(img)
    sha = hashlib.sha1(img).hexdigest()
    if not quiet:
        for line in code_report:
            print(line)
        mods = ', '.join(os.path.basename(os.path.normpath(m)) for m in mod_dirs) or 'none'
        grow = ('; %d chunk(s) grew, %d sprite layout(s) re-pointed' % (grown, layouts_patched)
                if grown or layouts_patched else '')
        grow += '; text bank re-encoded' if text_changed else ''
        grow += ('; %d font(s) rebuilt' % len(fonts)) if fonts else ''
        grow += ('; %d palette(s) changed' % len(pals)) if pals else ''
        print('built %s  (mods: %s; %d assets, %d changed, %d new%s)  sha1=%s%s' % (
            out_path, mods, len(entries), changed, len(new_ids), grow, sha,
            '  [IDENTICAL to original]' if sha == manifest['source_sha1'] else ''))
    return sha


def main(argv):
    import argparse
    kit = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description='Build The Urbz DS ROM from project/ plus enabled mods.')
    ap.add_argument('out', nargs='?', default=os.path.join(kit, 'build', 'Urbz Mod.nds'),
                    help='output .nds (default: build/Urbz Mod.nds)')
    ap.add_argument('--project', default=os.path.join(kit, 'project'))
    ap.add_argument('--config', help='mods list (default: mods.json next to this script)')
    ap.add_argument('--mod', action='append', default=[],
                    help='build with only these mods (repeatable; a name in mods/ or a folder path), ignoring mods.json')
    ap.add_argument('--vanilla', action='store_true', help='ignore all mods')
    a = ap.parse_args(argv)
    try:
        if a.vanilla:
            mods = []
        elif a.mod:
            mods = [os.path.abspath(m) if os.sep in m and os.path.isdir(m) else os.path.join(kit, 'mods', m)
                    for m in a.mod]
            for m in mods:
                if not os.path.isdir(m):
                    raise BuildError('no such mod folder: %s' % m)
        else:
            mods = load_mod_list(kit, a.config)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        build(a.project, a.out, mods)
    except BuildError as e:
        sys.exit('BUILD FAILED: %s' % e)


if __name__ == '__main__':
    # Backward compatible: urbz_build.py project_dir out.nds
    if len(sys.argv) == 3 and os.path.isdir(sys.argv[1]) and sys.argv[2].endswith('.nds'):
        try:
            build(sys.argv[1], sys.argv[2])
        except BuildError as e:
            sys.exit('BUILD FAILED: %s' % e)
    else:
        main(sys.argv[1:])
