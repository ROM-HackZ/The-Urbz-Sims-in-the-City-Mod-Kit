#!/usr/bin/env python3
"""Recolour things by editing the game's palette files as PNG swatch sheets.

Sprites on the DS use 16-colour palettes. Most of the game's sprites don't carry their
own colours: the game loads separate palette files at runtime (docs/systems.md,
"Sprite palettes"). Edit the right file and everything drawn with it changes colour.

  python urbz_palette.py list                      the palette files we know, and what uses them
  python urbz_palette.py who <character>           a person's palette file (name or id 31-75)
  python urbz_palette.py edit <mod> <asset>        copy a palette into mods/<mod>/palette/NNNNN.png
  python urbz_palette.py export <asset> <out.png>

The PNG is a grid of 16x16-pixel swatches, 16 per row (one row per 16-colour palette).
Paint a swatch with a new colour and build. The first colour of each row is see-through
in sprites. Colours are stored as 15-bit (5 bits per channel), so close colours merge.
"""
import json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
SW = 16                                          # swatch size in pixels

# What we know uses which palette file (file number = game id - 1). See docs/systems.md.
KNOWN = {
    11543: 'player: skin tones (rows 0-5 colours 1-5; rows 8-13 3-shade), hair colours '
           '(colours 6-10), shoes (colours 11-14) - 16 rows',
    11542: 'player: the 32 clothing colours (3-shade and 4-shade versions) - 16 rows',
    0: 'city streets: object palette row 2',
    1: 'city streets: object palette row 3 (puddles, ...)',
    2: 'city streets: object palette row 4',
    4: 'city streets: object palette row 5',
    5: 'city streets: object palette row 6',
    6: 'city streets: object palette row 7',
    7: 'city streets: object palette row 8',
    10361: 'bottom-screen HUD sprites, rows 0-7',
}
NPC_PALETTE_TABLE = 0x020D0054                 # u32 palette game id per character id


def bgr555(v):
    return ((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31)


def to555(c):
    return (c[0] * 31 + 127) // 255 | ((c[1] * 31 + 127) // 255) << 5 | ((c[2] * 31 + 127) // 255) << 10


def _proj():
    return os.path.join(KIT, 'project')


def _asset(idx, proj=None):
    return open(os.path.join(proj or _proj(), 'assets', '%05d.bin' % idx), 'rb').read()


def export_palette(data, path):
    from PIL import Image
    n = len(data) // 2
    rows = (n + 15) // 16
    img = Image.new('RGB', (16 * SW, rows * SW), (0, 0, 0))
    px = img.load()
    for i in range(n):
        c = bgr555(struct.unpack_from('<H', data, 2 * i)[0])
        x0, y0 = (i % 16) * SW, (i // 16) * SW
        for y in range(SW):
            for x in range(SW):
                px[x0 + x, y0 + y] = c
    img.save(path)


def import_palette(orig, path):
    """Edited swatch sheet -> palette bytes. Unchanged swatches keep their exact original
    value (including bit 15), so an untouched sheet gives identical bytes."""
    from PIL import Image
    img = Image.open(path).convert('RGB')
    n = len(orig) // 2
    if img.size != (16 * SW, ((n + 15) // 16) * SW):
        raise ValueError('%s must stay %dx%d' % (path, 16 * SW, ((n + 15) // 16) * SW))
    px = img.load()
    out = bytearray(orig)
    for i in range(n):
        x0, y0 = (i % 16) * SW, (i // 16) * SW
        c = px[x0 + SW // 2, y0 + SW // 2]
        old = struct.unpack_from('<H', orig, 2 * i)[0]
        if bgr555(old) != c:
            struct.pack_into('<H', out, 2 * i, to555(c) | (old & 0x8000))
    return bytes(out)


def palette_overrides(proj, overlay):
    """Builder hook: {asset file number: new bytes} from mods/*/palette/NNNNN.png."""
    out = {}
    for rel, (mod, path) in sorted(overlay.files.items()):
        parts = rel.split('/')
        if parts[0] != 'palette' or not rel.endswith('.png'):
            continue
        if len(parts) != 2 or not parts[1][:5].isdigit():
            raise ValueError('mod "%s": %s should be palette/NNNNN.png' % (mod, rel))
        idx = int(parts[1][:5])
        if overlay.overridden('assets/%05d.bin' % idx):
            raise ValueError('mod "%s" edits palette %05d as a PNG and as assets/%05d.bin; keep one'
                             % (mod, idx, idx))
        orig = _asset(idx, proj)
        new = import_palette(orig, path)
        if new != orig:
            out[idx] = new
    return out


def npc_palettes(proj=None):
    """{character id: palette file number} from the game's table."""
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(os.path.join(proj or _proj(), 'base.nds'))
    a9 = bytes(rom.arm9)
    o = NPC_PALETTE_TABLE - 0x02000000
    return {cid: struct.unpack_from('<I', a9, o + 4 * cid)[0] - 1 for cid in range(31, 67)}


def _names():
    sys.path.insert(0, KIT)
    from urbz_text import project_strings
    s = project_strings(_proj())
    return {cid: s[481 + cid].decode('latin-1') for cid in range(31, 67)}


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == 'list':
        for idx, what in sorted(KNOWN.items()):
            print('%05d  %s' % (idx, what))
        names = _names()
        for cid, idx in sorted(npc_palettes().items()):
            print('%05d  person %d: %s' % (idx, cid, names[cid]))
    elif cmd == 'who' and args:
        names = _names()
        q = args[0].lower()
        hits = [c for c, n in names.items() if q == str(c) or q in n.lower()]
        pals = npc_palettes()
        for c in hits:
            print('%s (id %d): palette file %05d' % (names[c], c, pals[c]))
        if not hits:
            sys.exit('no person matches "%s"' % args[0])
    elif cmd == 'export' and len(args) == 2:
        export_palette(_asset(int(args[0])), args[1])
        print('wrote ' + args[1])
    elif cmd == 'edit' and len(args) == 2:
        md = os.path.join(KIT, 'mods', args[0])
        if not os.path.isdir(md):
            sys.exit('error: no mod named "%s" (create it: python urbz_mod.py new %s)' % (args[0], args[0]))
        idx = int(args[1])
        data = _asset(idx)
        if len(data) % 32:
            sys.exit('error: asset %05d is %d bytes, not a palette (a multiple of 32)' % (idx, len(data)))
        out = os.path.join(md, 'palette', '%05d.png' % idx)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        export_palette(data, out)
        print('wrote %s (%d colours); repaint swatches, then build' % (out, len(data) // 2))
    else:
        sys.exit('usage: urbz_palette.py list | who <name> | edit <mod> <asset> | export <asset> <png>')


if __name__ == '__main__':
    main(sys.argv[1:])
