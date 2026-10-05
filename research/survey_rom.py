#!/usr/bin/env python3
"""Survey a DS ROM (read-only): what kinds of files it holds, and whether its art uses the formats of
The Urbz DS (Griptonite: rom.bin + EA-compressed chunks + composite sprite layouts) or Nintendo's
standard ones (NARC archives, NCGR/NCLR/NCER/NANR sprites, NSBMD 3D models).

  python3 research/survey_rom.py <game.nds> [report.txt]

Used to judge what can be brought over from other Sims DS games (docs/other-games.md). Nothing is
written into the kit; the report only lists names, sizes and counts.
"""
import collections, hashlib, os, struct, sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT)

MAGICS = {b'NARC': 'NARC archive', b'RGCN': 'NCGR graphics', b'RLCN': 'NCLR palette', b'RECN': 'NCER cells',
          b'RNAN': 'NANR animation', b'RCSN': 'NSCR screen', b'BMD0': 'NSBMD 3D model',
          b'BTX0': 'NSBTX 3D texture', b'BCA0': 'NSBCA 3D animation', b'SDAT': 'SDAT sound',
          b'BMG1': 'BMG text', b'MESG': 'BMG text'}


def kind_of(data):
    if len(data) < 4:
        return 'tiny'
    m = bytes(data[:4])
    if m in MAGICS:
        return MAGICS[m]
    if m[::-1] in MAGICS:
        return MAGICS[m[::-1]]
    if data[0] in (0x10, 0x11) and len(data) > 8:
        return 'LZ77-compressed (%02x)' % data[0]
    if urbz_table(data):
        return 'Urbz-style rom.bin table'
    return 'other'


def urbz_table(data):
    """An Urbz rom.bin: u32 offsets (first = table size) ending with the file size."""
    if len(data) < 16:
        return False
    first = struct.unpack_from('<I', data, 0)[0]
    if first % 4 or first < 8 or first > len(data) or first > 0x100000:
        return False
    offs = struct.unpack_from('<%dI' % (first // 4), data, 0)
    return offs[-1] == len(data) and all(a <= b for a, b in zip(offs, offs[1:]))


def survey(path):
    import ndspy.rom, ndspy.narc
    raw = open(path, 'rb').read()
    rom = ndspy.rom.NintendoDSRom(raw)
    out = ['%s' % os.path.basename(path),
           '  title %r, code %r, %d bytes, SHA1 %s' % (rom.name.decode('latin-1').strip('\0'),
                                                       rom.idCode.decode('latin-1'), len(raw),
                                                       hashlib.sha1(raw).hexdigest()),
           '  arm9 %d bytes, %d overlays, %d files' % (len(rom.arm9), len(rom.loadArm9Overlays()), len(rom.files))]
    names = {}
    for i in range(len(rom.files)):
        try:
            names[i] = rom.filenames.filenameOf(i) or '#%d' % i
        except Exception:
            names[i] = '#%d' % i
    kinds, sizes, inner = collections.Counter(), collections.Counter(), collections.Counter()
    for i, f in enumerate(rom.files):
        k = kind_of(f)
        kinds[k] += 1
        sizes[k] += len(f)
        if k == 'NARC archive':
            try:
                for sub in ndspy.narc.NARC(f).files:
                    inner[kind_of(sub)] += 1
            except Exception:
                inner['(unreadable NARC)'] += 1
    out.append('  file kinds (count, total KB):')
    for k, n in kinds.most_common():
        out.append('    %-28s %5d  %8d KB' % (k, n, sizes[k] // 1024))
    if inner:
        out.append('  inside NARC archives:')
        for k, n in inner.most_common():
            out.append('    %-28s %5d' % (k, n))
    big = sorted(range(len(rom.files)), key=lambda i: -len(rom.files[i]))[:12]
    out.append('  largest files:')
    for i in big:
        out.append('    %-40s %8d KB  %s' % (names[i][:40], len(rom.files[i]) // 1024, kind_of(rom.files[i])))
    for i, f in enumerate(rom.files):
        if kind_of(f) == 'Urbz-style rom.bin table':
            out += urbz_check(names[i], f)
    exts = collections.Counter(os.path.splitext(n)[1].lower() or '(none)' for n in names.values())
    out.append('  file name extensions: ' + ', '.join('%s %d' % kv for kv in exts.most_common(15)))
    return '\n'.join(out)


def urbz_check(name, data):
    """How much of an Urbz-style container parses like The Urbz's assets (EA chunks, sprite layouts)."""
    from scan_chunks import asset_chunks
    first = struct.unpack_from('<I', data, 0)[0]
    offs = struct.unpack_from('<%dI' % (first // 4), data, 0)
    n = len(offs) - 1
    step = max(1, n // 400)
    sample = range(0, n, step)
    with_chunks = 0
    for k in sample:
        try:
            if asset_chunks(data[offs[k]:offs[k + 1]]):
                with_chunks += 1
        except Exception:
            pass
    return ['  %s: Urbz-style container, %d entries; %d of %d sampled entries hold EA-compressed chunks '
            '(The Urbz DS itself: about 45%%)' % (name, n, with_chunks, len(sample))]


def main(argv):
    if not argv:
        sys.exit(__doc__)
    text = survey(argv[0])
    print(text)
    if len(argv) > 1:
        open(argv[1], 'w').write(text + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
