#!/usr/bin/env python3
"""Export / import The Urbz DS text fonts as PNG sheets.

Font assets (raw, not chunked): project/assets/NNNNN.bin, loaded at boot by FUN_02034924 ->
FUN_02033a48(slot) from the table at arm9 0x020C5CEC {u32 game id, u32 colour base} x 8.

Format (all fonts):
  +0  u16  first code (0x20)
  +2  u16  last code  (0xB9; 0xBA in 11555)
  +4  u8   glyph height in pixels      (+5 unused, 0)
  +6  u8,u8  BIG-endian u16: offset of the glyph offset table   (always 0x0010)
  +A  u8,u8  BIG-endian u16: offset of the width table           (+8,+9 unused, 0)
  +E  u8,u8  BIG-endian u16: offset of the bitmap data           (+C,+D unused, 0)
  offset table: u16 per code (first..last), byte offset into bitmap data, padded to 4
  width table : u8 per code, padded with 0 to a multiple of 4
  bitmap      : per glyph, width*height 4-bit pixels, COLUMN-major (x outer, y inner),
                low nibble first, glyph starts on a byte boundary; file padded to 4.
Pixel value 0 = transparent; v>0 is drawn as palette colour (colour base + v).
The advance is the glyph width (spacing is baked into the glyph's blank columns).
Codes outside first..last draw glyph index 1 ('!'). 0x00 ends a string, '@' (0x40)
starts a name/clock substitution, 0xF0-0xFF are 2-byte lead bytes (no 2-byte font loaded),
so usable codes are 0x20..0xEF minus 0x40.

Sheet: 16 glyphs per row, row r = codes (0x20 + 16r) .. ; each cell holds the glyph at
its top-left, then one row below it a WIDTH BAR (palette index 17) of length = width.
The bar is authoritative on import (so you can add/resize glyphs in the image alone).
PNG is indexed: 0..15 = pixel values, 16 = cell grid/background, 17 = width bar.
"""
import json, os, struct, sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = HERE
PROJECT = os.path.join(KIT, 'project')
# slot -> asset file number (game id - 1), colour base; from arm9 table 0x020C5CEC
SLOTS = [(0, 11547, 8), (1, 11546, 8), (2, 11549, 16), (3, 11548, 16),
         (4, 11550, 16), (5, 11552, 16), (6, 11551, 16), (7, 11555, 16)]
FONT_ASSETS = sorted(a for _, a, _ in SLOTS)
SHEET_LAST = 0xEF            # highest code a sheet offers (0xF0+ are lead bytes)
COLS = 16
GRID, BAR = 16, 17

# display colours for the indexed PNG
_PAL = [(255, 255, 255), (0, 0, 0), (150, 150, 150), (230, 160, 0)] + \
       [(40 + i * 15, 0, 120) for i in range(12)] + [(200, 225, 255), (230, 40, 40)]


def parse(data):
    first, last, height = struct.unpack_from('<HHB', data, 0)
    ot = data[6] << 8 | data[7]
    wt = data[10] << 8 | data[11]
    bt = data[14] << 8 | data[15]
    n = last - first + 1
    offs = struct.unpack_from('<%dH' % n, data, ot)
    glyphs = {}
    for i in range(n):
        w = data[wt + i]
        p = bt + offs[i]
        cols = []
        for x in range(w):
            col = []
            for y in range(height):
                k = x * height + y
                b = data[p + k // 2]
                col.append((b >> 4) if k & 1 else (b & 15))
            cols.append(col)
        glyphs[first + i] = (w, cols)
    return {'first': first, 'last': last, 'height': height, 'glyphs': glyphs}


def build(font):
    """font dict (as from parse) -> asset bytes, same container layout."""
    first, last, h = font['first'], font['last'], font['height']
    n = last - first + 1
    ot = 0x10
    wt = (ot + 2 * n + 3) & ~3
    bt = wt + ((n + 3) & ~3)
    if bt > 0xFFFF:
        raise ValueError('tables too big')
    offs, widths, bitmap = [], bytearray(), bytearray()
    for c in range(first, last + 1):
        w, cols = font['glyphs'].get(c, (0, []))
        if w > 255:
            raise ValueError('glyph 0x%02X wider than 255' % c)
        offs.append(len(bitmap))
        widths.append(w)
        nib = [cols[x][y] for x in range(w) for y in range(h)]
        if len(nib) & 1:
            nib.append(0)
        bitmap += bytes(nib[i] | nib[i + 1] << 4 for i in range(0, len(nib), 2))
    if offs[-1] > 0xFFFF:
        raise ValueError('bitmap data over 64 KB (u16 offsets)')
    hdr = struct.pack('<HHBB', first, last, h, 0) + bytes([ot >> 8, ot & 255, 0, 0,
                                                           wt >> 8, wt & 255, 0, 0, bt >> 8, bt & 255])
    out = hdr + struct.pack('<%dH' % n, *offs) + bytes(wt - ot - 2 * n) + widths + bytes(bt - wt - n) + bitmap
    out += bytes(-len(out) % 4)
    return bytes(out)


def _cell(font):
    maxw = max(w for w, _ in font['glyphs'].values())
    return maxw + 4, font['height'] + 3          # room to widen glyphs; +bar row +gap


def export_font(data, png_path, json_path, meta=None):
    font = parse(data)
    cw, ch = _cell(font)
    rows = (SHEET_LAST - 0x20 + COLS) // COLS
    img = Image.new('P', (COLS * cw, rows * ch), GRID)
    flat = [v for c in _PAL for v in c]
    img.putpalette(flat + [0] * (768 - len(flat)))
    px = img.load()
    h = font['height']
    for c, (w, cols) in font['glyphs'].items():
        r, k = divmod(c - 0x20, COLS)
        x0, y0 = k * cw, r * ch
        for x in range(cw - 1):
            for y in range(h + 2):
                px[x0 + x, y0 + y] = 0
        for x in range(w):
            for y in range(h):
                px[x0 + x, y0 + y] = cols[x][y]
            px[x0 + x, y0 + h + 1] = BAR
    # empty (free) cells after `last`: transparent area, no bar
    for c in range(font['last'] + 1, SHEET_LAST + 1):
        r, k = divmod(c - 0x20, COLS)
        for x in range(cw - 1):
            for y in range(h + 2):
                px[k * cw + x, r * ch + y] = 0
    img.save(png_path)
    info = dict(meta or {})
    info.update({'first': font['first'], 'last': font['last'], 'height': h,
                 'cell': [cw, ch], 'cols': COLS, 'sheet_first': 0x20, 'sheet_last': SHEET_LAST,
                 'pixel_values': 'palette index 0..15 = 4-bit pixel (0 transparent); 16 grid; 17 width bar',
                 'glyphs': {'%02X' % c: font['glyphs'][c][0] for c in sorted(font['glyphs'])}})
    with open(json_path, 'w') as f:
        json.dump(info, f, indent=1)
    return font


def _to_index(img):
    if img.mode == 'P':
        return img
    # RGB edit: map to nearest of the sheet palette
    rgb = img.convert('RGB')
    out = Image.new('P', rgb.size)
    src, dst = rgb.load(), out.load()
    cache = {}
    for y in range(rgb.size[1]):
        for x in range(rgb.size[0]):
            c = src[x, y]
            if c not in cache:
                cache[c] = min(range(len(_PAL)), key=lambda i: sum((a - b) ** 2 for a, b in zip(_PAL[i], c)))
            dst[x, y] = cache[c]
    return out


def import_sheet(sheet, json_path):
    """Edited sheet (PNG path or Image) + its JSON -> new font asset bytes."""
    info = json.load(open(json_path))
    img = _to_index(sheet if isinstance(sheet, Image.Image) else Image.open(sheet))
    px = img.load()
    cw, ch = info['cell']
    h = info['height']
    first = info['first']
    glyphs, last = {}, info['last']
    for c in range(first, SHEET_LAST + 1):
        r, k = divmod(c - 0x20, COLS)
        x0, y0 = k * cw, r * ch
        w = 0
        while w < cw - 1 and px[x0 + w, y0 + h + 1] == BAR:
            w += 1
        cols = [[px[x0 + x, y0 + y] & 15 if px[x0 + x, y0 + y] < 16 else 0 for y in range(h)]
                for x in range(w)]
        glyphs[c] = (w, cols)
        if w and c > last:
            last = c
    for c in range(first, last + 1):
        if c >= 0xF0:
            raise ValueError('codes 0xF0..0xFF are 2-byte lead bytes')
    glyphs = {c: g for c, g in glyphs.items() if c <= last}
    return build({'first': first, 'last': last, 'height': h, 'glyphs': glyphs})


def _name(slot, asset):
    return 'font%d_%05d' % (slot, asset)


def cmd_export(outdir, project=PROJECT):
    os.makedirs(outdir, exist_ok=True)
    for slot, asset, base in SLOTS:
        data = open(os.path.join(project, 'assets', '%05d.bin' % asset), 'rb').read()
        nm = _name(slot, asset)
        f = export_font(data, os.path.join(outdir, nm + '.png'), os.path.join(outdir, nm + '.json'),
                        {'slot': slot, 'asset': asset, 'game_id': asset + 1, 'colour_base': base})
        print('%s: %d glyphs 0x%02X-0x%02X, height %d' % (nm, len(f['glyphs']), f['first'], f['last'], f['height']))


def cmd_roundtrip(project=PROJECT):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as d:
        cmd_export(d, project)
        for slot, asset, _ in SLOTS:
            orig = open(os.path.join(project, 'assets', '%05d.bin' % asset), 'rb').read()
            nm = _name(slot, asset)
            new = import_sheet(os.path.join(d, nm + '.png'), os.path.join(d, nm + '.json'))
            same = new == orig
            ok &= same
            print('%05d: %s (%d bytes)' % (asset, 'identical' if same else 'DIFFERENT', len(new)))
    return ok


# ---------------------------------------------------------------- mods / builder

def cmd_edit(mod, slots=None):
    """Copy font sheets into mods/<mod>/font/ for editing."""
    md = os.path.join(KIT, 'mods', mod)
    if not os.path.isdir(md):
        sys.exit('error: no mod named "%s" (create it: python urbz_mod.py new %s)' % (mod, mod))
    out = os.path.join(md, 'font')
    os.makedirs(out, exist_ok=True)
    for slot, asset, base in SLOTS:
        if slots and slot not in slots:
            continue
        nm = _name(slot, asset)
        if os.path.exists(os.path.join(out, nm + '.png')):
            print('kept existing ' + nm + '.png')
            continue
        data = open(os.path.join(PROJECT, 'assets', '%05d.bin' % asset), 'rb').read()
        export_font(data, os.path.join(out, nm + '.png'), os.path.join(out, nm + '.json'),
                    {'slot': slot, 'asset': asset, 'game_id': asset + 1, 'colour_base': base})
        print('wrote ' + os.path.join(out, nm + '.png'))
    print('edit the PNGs (glyph pixels 1-15, width = red bar under each glyph), then build')


def font_overrides(proj, overlay):
    """Builder hook: {asset file number: new font bytes} from mods/*/font/fontN_NNNNN.png."""
    out = {}
    for rel, (mod, path) in sorted(overlay.files.items()):
        parts = rel.split('/')
        if parts[0] != 'font' or not rel.endswith('.png'):
            continue
        name = parts[-1][:-4]
        match = [a for s_, a, _ in SLOTS if _name(s_, a) == name]
        if not match:
            raise ValueError('mod "%s": %s is not a font sheet name (fontN_NNNNN.png)' % (mod, rel))
        jp = path[:-4] + '.json'
        if not os.path.exists(jp):
            raise ValueError('mod "%s": %s needs its .json next to it' % (mod, rel))
        asset = match[0]
        if overlay.overridden('assets/%05d.bin' % asset):
            raise ValueError('mod "%s" edits font %s as a PNG and assets/%05d.bin; keep one'
                             % (mod, name, asset))
        new = import_sheet(path, jp)
        orig = open(os.path.join(proj, 'assets', '%05d.bin' % asset), 'rb').read()
        if new != orig:
            out[asset] = new
    return out


def main(argv):
    if len(argv) >= 2 and argv[0] == 'edit':
        cmd_edit(argv[1], {int(x) for x in argv[2:]} or None)
        return
    if len(argv) >= 2 and argv[0] == 'export':
        cmd_export(argv[1], argv[2] if len(argv) > 2 else PROJECT)
    elif len(argv) >= 4 and argv[0] == 'import':
        # import sheet.png sheet.json out.bin   (out may be mods/<name>/assets/NNNNN.bin)
        data = import_sheet(argv[1], argv[2])
        os.makedirs(os.path.dirname(os.path.abspath(argv[3])), exist_ok=True)
        open(argv[3], 'wb').write(data)
        print('wrote %s (%d bytes)' % (argv[3], len(data)))
    elif argv and argv[0] == 'roundtrip':
        sys.exit(0 if cmd_roundtrip(argv[1] if len(argv) > 1 else PROJECT) else 1)
    else:
        print(__doc__)
        print('usage: urbz_font.py edit <mod> [slot ...]   copy font sheets into a mod\n'
              '       urbz_font.py export <outdir> [project]\n'
              '       urbz_font.py import <sheet.png> <sheet.json> <out.bin>\n'
              '       urbz_font.py roundtrip [project]')
        sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
