#!/usr/bin/env python3
"""Composite sprite frames of The Urbz DS: parse, render, and split back.

Format (from FUN_020ae17c, FUN_02001abc, FUN_02005534, FUN_0206e774 in arm9):

Layout asset (no chunks)
  +0  u8  frame w, u8 frame h            (max over entries)
  +6  u16 entry count
  +10 u8  X = number of u16 extras per entry
  +11 u8  Y = number of 6-byte extras per entry
  +12 u16 entry offset table (offsets relative to +12)
  (files are padded to a multiple of 4 bytes)

Entry (one per animation frame)
  +0  u8  bits 0-4 cell count, bits 5-7 flags (0x80 seen; ignored by the draw code)
  +1  u8  0
  +2  u8  w, +3 u8 h                     bounding box of the cells (pixels)
  +4  u16 byte offset of the frame's tile chunk in the paired gfx asset
  +6  s16 x, +8 s16 y                    bounding-box origin = min cell x / y
  +10 X*2 + Y*6 bytes of extra data      (not used for drawing; kept verbatim)
  then count x u32 cell words:
      bits  0-8   x  (signed 9-bit, relative to the sprite origin)
      bits  9-17  y  (signed 9-bit)
      bits 18-19  OBJ size   -> OAM attr1 bits 14-15
      bits 20-21  OBJ shape  -> OAM attr0 bits 14-15
      bits 22-31  first tile of this cell inside the chunk (32-byte units)
                  (always = running sum of previous cells' tile counts)

Chunk = the cells' 4bpp tiles back to back, each cell's tiles row-major
(1D OBJ mapping). On load the game re-spaces them in VRAM so every cell
starts on a 64-byte boundary (an 8x8 cell gets one pad tile); the OAM tile
number advances by (tiles+1)//2 per cell. Flips are per sprite, not per cell:
with H-flip the game mirrors each cell (x' = -(x + w)), likewise V-flip.
Cells never overlap in the shipped data; earlier cells get lower OAM indices
(drawn on top), which compose_frame honours.

API
  parse_layout(layout_bytes)              -> Layout (header, entries[] with cells[])
  compose_frame(entry, chunk, palette16)  -> PIL RGBA image, entry.w x entry.h
                                             (pixel (0,0) = sprite origin + (entry.x, entry.y))
  split_frame(image, entry, palette16, orig_chunk=None) -> new chunk bytes
  build_layout(layout)                    -> bytes (inverse of parse_layout)
  frames(gfx, layout, proj=KIT_PROJECT)   -> [(entry, chunk_bytes)] from the unpacked project
"""
import os, struct, sys
from dataclasses import dataclass, field

KIT = os.path.dirname(os.path.abspath(__file__))
KIT_PROJECT = os.path.join(KIT, 'project')

# FUN_020ae17c's table at 0x020c22bc: tiles per [shape*4 + size]
TILES = [1, 4, 16, 64, 2, 4, 8, 32, 2, 4, 8, 32]
DIMS = {(0, 0): (8, 8), (0, 1): (16, 16), (0, 2): (32, 32), (0, 3): (64, 64),
        (1, 0): (16, 8), (1, 1): (32, 8), (1, 2): (32, 16), (1, 3): (64, 32),
        (2, 0): (8, 16), (2, 1): (8, 32), (2, 2): (16, 32), (2, 3): (32, 64)}


def _s9(v):
    return v - 512 if v & 256 else v


@dataclass
class Cell:
    x: int
    y: int
    shape: int
    size: int
    tile: int            # first tile (32-byte units) inside the chunk
    raw: int

    @property
    def legal(self):
        return (self.shape, self.size) in DIMS

    @property
    def dims(self):
        return DIMS[(self.shape, self.size)]

    @property
    def tiles(self):
        return TILES[self.shape * 4 + self.size]


@dataclass
class Entry:
    index: int
    flags: int           # byte0 bits 5-7
    w: int
    h: int
    chunk_off: int
    x: int
    y: int
    extra: bytes
    cells: list = field(default_factory=list)
    byte1: int = 0

    @property
    def tiles(self):
        return sum(c.tiles for c in self.cells)


@dataclass
class Layout:
    head: bytes          # first 12 bytes verbatim
    entries: list
    n_u16: int
    n_6: int


def parse_layout(a):
    a = bytes(a)
    n = struct.unpack_from('<H', a, 6)[0]
    nx, ny = a[10], a[11]
    ex = nx * 2 + ny * 6
    entries = []
    for k in range(n):
        eo = 0xC + struct.unpack_from('<H', a, 0xC + 2 * k)[0]
        b0, b1, w, h, off, x, y = struct.unpack_from('<BBBBHhh', a, eo)
        cells = []
        p = eo + 10 + ex
        for i in range(b0 & 0x1F):
            v = struct.unpack_from('<I', a, p + 4 * i)[0]
            cells.append(Cell(_s9(v & 511), _s9((v >> 9) & 511), (v >> 20) & 3, (v >> 18) & 3, v >> 22, v))
        entries.append(Entry(k, b0 >> 5, w, h, off, x, y, a[eo + 10:eo + 10 + ex], cells, b1))
    return Layout(a[:12], entries, nx, ny)


def build_layout(lay):
    """Serialise a Layout (inverse of parse_layout; offsets/tile fields recomputed)."""
    body, table = bytearray(), []
    base = 0xC + 2 * len(lay.entries)
    for e in lay.entries:
        table.append(base + len(body) - 0xC)
        body += struct.pack('<BBBBHhh', (e.flags << 5) | len(e.cells), e.byte1, e.w, e.h,
                            e.chunk_off, e.x, e.y) + e.extra
        t = 0
        for c in e.cells:
            body += struct.pack('<I', (c.x & 511) | ((c.y & 511) << 9) | (c.size << 18)
                                | (c.shape << 20) | (t << 22))
            t += c.tiles
    out = bytearray(lay.head) + b''.join(struct.pack('<H', o) for o in table) + body
    struct.pack_into('<H', out, 6, len(lay.entries))
    while len(out) % 4:
        out += b'\0'
    return bytes(out)


def check_entry(entry, chunk_len=None):
    """List of problems (empty = valid): illegal shapes, wrong tile fields, chunk too small."""
    errs, t = [], 0
    for i, c in enumerate(entry.cells):
        if not c.legal:
            errs.append('cell %d: illegal shape/size %d/%d' % (i, c.shape, c.size))
            continue
        if c.tile != t:
            errs.append('cell %d: tile field %d, expected %d' % (i, c.tile, t))
        t += c.tiles
    if chunk_len is not None and t * 32 > chunk_len:
        errs.append('needs %d tile bytes, chunk has %d' % (t * 32, chunk_len))
    return errs


def _cell_pixels(chunk, cell):
    """Yield (px, py, colour index) for a cell, px/py relative to the cell's top-left."""
    cw, ch = cell.dims
    tw = cw // 8
    base = cell.tile * 32
    for t in range(cell.tiles):
        ox, oy = (t % tw) * 8, (t // tw) * 8
        for i in range(32):
            b = chunk[base + t * 32 + i]
            yy, xx = divmod(i, 4)
            yield ox + xx * 2, oy + yy, b & 15
            yield ox + xx * 2 + 1, oy + yy, b >> 4


def compose_indices(entry, chunk):
    """2-D list [h][w] of colour indices (0 = transparent) for the assembled frame."""
    img = [[0] * entry.w for _ in range(entry.h)]
    for cell in reversed(entry.cells):          # lower OAM index ends up on top
        bx, by = cell.x - entry.x, cell.y - entry.y
        for px, py, v in _cell_pixels(chunk, cell):
            if v:
                X, Y = bx + px, by + py
                if 0 <= X < entry.w and 0 <= Y < entry.h:
                    img[Y][X] = v
    return img


def compose_frame(entry, chunk, palette16):
    """Assembled frame as a PIL RGBA image (entry.w x entry.h). palette16: 16 (r,g,b)."""
    from PIL import Image
    im = Image.new('RGBA', (max(1, entry.w), max(1, entry.h)), (0, 0, 0, 0))
    px = im.load()
    for y, row in enumerate(compose_indices(entry, chunk)):
        for x, v in enumerate(row):
            if v:
                r, g, b = palette16[v][:3]
                px[x, y] = (r, g, b, 255)
    return im


def _image_indices(image, palette16, orig_idx):
    """Colour index per pixel of `image`. RGBA/RGB: alpha<128 -> 0, else the palette entry
    (1..15) of exactly that colour (preferring the original pixel's index when it has the
    same colour, so unedited frames round-trip byte for byte), else the nearest colour."""
    w, h = image.size
    if image.mode == 'P':
        pal = image.getpalette() or []
        same = all(tuple(pal[3 * i:3 * i + 3]) == tuple(palette16[i][:3]) for i in range(16))
        if same:
            get = image.load()
            return [[get[x, y] & 15 for x in range(w)] for y in range(h)]
    rgba = image.convert('RGBA').load()
    pal = [tuple(c[:3]) for c in palette16]
    cache = {}

    def nearest(c):
        if c not in cache:
            cache[c] = min(range(1, 16), key=lambda i: sum((a - b) ** 2 for a, b in zip(c, pal[i])))
        return cache[c]

    out = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = rgba[x, y]
            if a < 128:
                row.append(0)
                continue
            o = orig_idx[y][x] if orig_idx else 0
            row.append(o if o and pal[o] == (r, g, b) else nearest((r, g, b)))
        out.append(row)
    return out


def split_frame(image, entry, palette16, orig_chunk=None):
    """Turn an edited assembled frame back into chunk tile bytes with the same cell layout.
    `image` must be entry.w x entry.h (as from compose_frame). Pixels outside every cell are
    dropped. Where cells overlap, the topmost (first) cell takes the pixel; the hidden part
    of lower cells keeps `orig_chunk`'s data (or 0). Bytes past the cells' tiles in
    orig_chunk are kept."""
    if image.size != (entry.w, entry.h):
        raise ValueError('frame %d must be %dx%d, got %dx%d'
                         % (entry.index, entry.w, entry.h, image.size[0], image.size[1]))
    ntiles = entry.tiles
    orig = bytes(orig_chunk) if orig_chunk is not None else bytes(ntiles * 32)
    orig_idx = compose_indices(entry, orig) if orig_chunk is not None else None
    idx = _image_indices(image, palette16, orig_idx)
    out = bytearray(orig[:ntiles * 32].ljust(ntiles * 32, b'\0'))
    owner = {}                                   # pixel -> first cell covering it
    for ci, cell in enumerate(entry.cells):
        cw, ch = cell.dims
        bx, by = cell.x - entry.x, cell.y - entry.y
        for yy in range(ch):
            for xx in range(cw):
                owner.setdefault((bx + xx, by + yy), ci)
    for ci, cell in enumerate(entry.cells):
        cw, ch = cell.dims
        tw = cw // 8
        bx, by = cell.x - entry.x, cell.y - entry.y
        for yy in range(ch):
            for xx in range(cw):
                X, Y = bx + xx, by + yy
                if owner.get((X, Y)) != ci or not (0 <= X < entry.w and 0 <= Y < entry.h):
                    continue
                v = idx[Y][X]
                pos = (cell.tile + (yy // 8) * tw + xx // 8) * 32 + (yy % 8) * 4 + (xx % 8) // 2
                if xx & 1:
                    out[pos] = (out[pos] & 0x0F) | (v << 4)
                else:
                    out[pos] = (out[pos] & 0xF0) | v
    return bytes(out) + orig[ntiles * 32:]


# ------------------------------------------------------------------ project glue

_CACHE = {}


def _manifest(proj):
    import json
    if ('m', proj) not in _CACHE:
        _CACHE[('m', proj)] = json.load(open(os.path.join(proj, 'manifest.json')))
    return _CACHE[('m', proj)]


def frames(gfx, layout, proj=KIT_PROJECT):
    """[(entry, chunk_bytes)] for a gfx/layout pair given as file numbers (game id - 1)."""
    m = _manifest(proj)
    lay = parse_layout(open(os.path.join(proj, 'assets', m['entries'][int(layout)]['file']), 'rb').read())
    out = []
    for e in lay.entries:
        p = os.path.join(proj, 'unpacked', '%05d' % int(gfx), '%06X.bin' % e.chunk_off)
        out.append((e, open(p, 'rb').read()))
    return out


def palette_for(gfx, proj=KIT_PROJECT):
    """16 RGB colours for a gfx asset via kit9/urbz_png.sprite_palette (greyscale fallback)."""
    import json
    key = ('pal', proj, int(gfx))
    if key not in _CACHE:
        sys.path.insert(0, KIT)
        from urbz_png import sprite_palette
        m = _manifest(proj)
        refs = json.load(open(os.path.join(proj, 'sprite_refs.json')))['gfx']
        _CACHE[key] = sprite_palette(proj, int(gfx), m, refs)[0]
    return _CACHE[key]


def validate_all(proj=KIT_PROJECT):
    """Static check over every (gfx, layout) pair in sprite_refs.json."""
    import json, collections
    m = _manifest(proj)
    refs = json.load(open(os.path.join(proj, 'sprite_refs.json')))['gfx']
    st = collections.Counter()
    bad_pairs = []
    for g, info in sorted(refs.items()):
        for l in info['layouts']:
            lay = parse_layout(open(os.path.join(proj, 'assets', m['entries'][int(l)]['file']), 'rb').read())
            pair_ok = True
            for e in lay.entries:
                st['entries'] += 1
                st['cells'] += len(e.cells)
                st['composite_entries'] += len(e.cells) > 1
                st['illegal_cells'] += sum(not c.legal for c in e.cells)
                st['bad_tile_field'] += sum(1 for x in check_entry(e) if 'tile field' in x)
                n = os.path.getsize(os.path.join(proj, 'unpacked', g, '%06X.bin' % e.chunk_off))
                st['fits' if e.tiles * 32 <= n else 'overflows'] += 1
                st['exact_size' if e.tiles * 32 == n else 'size_differs'] += 1
                pair_ok &= e.tiles * 32 == n
            st['pairs'] += 1
            st['pairs_exact'] += pair_ok
            if not pair_ok:
                bad_pairs.append((g, l, len(lay.entries)))
    return st, bad_pairs


def self_test(n=200, seed=1, proj=KIT_PROJECT):
    """compose -> split must give identical tile bytes for n random composite frames."""
    import json, random
    m = _manifest(proj)
    refs = json.load(open(os.path.join(proj, 'sprite_refs.json')))['gfx']
    pool = []
    for g, info in sorted(refs.items()):
        for l in info['layouts']:
            lay = parse_layout(open(os.path.join(proj, 'assets', m['entries'][int(l)]['file']), 'rb').read())
            for e in lay.entries:
                size = os.path.getsize(os.path.join(proj, 'unpacked', g, '%06X.bin' % e.chunk_off))
                if len(e.cells) > 1 and e.tiles * 32 == size:
                    pool.append((g, l, e.index))
    rnd = random.Random(seed)
    sample = rnd.sample(pool, n)
    fails = blind_ok = blind_dup = 0
    for g, l, k in sample:
        e, ch = frames(g, l, proj)[k]
        pal = palette_for(g, proj)
        im = compose_frame(e, ch, pal)
        if split_frame(im, e, pal, ch) != ch:     # the editing path: original chunk known
            fails += 1
            print('FAIL', g, l, k)
        # Without the original, colours shared by two palette slots are ambiguous.
        if split_frame(im, e, pal) == ch:
            blind_ok += 1
        elif len(set(map(tuple, pal[1:]))) < 15:
            blind_dup += 1
        else:
            fails += 1
            print('FAIL (no orig, distinct palette)', g, l, k)
    # serialisation round trip on every layout touched
    for l in sorted({l for _, l, _ in sample}):
        a = open(os.path.join(proj, 'assets', m['entries'][int(l)]['file']), 'rb').read()
        if build_layout(parse_layout(a)) != a:
            fails += 1
            print('FAIL build_layout', l)
    print('round trip: %d/%d composite frames identical with split_frame(..., orig_chunk); '
          'without orig_chunk %d identical, %d differ only because their palette repeats a colour '
          '(pool %d composite frames; %d failures)' % (n - fails, n, blind_ok, blind_dup, len(pool), fails))
    return fails == 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'validate':
        st, bad = validate_all()
        print(dict(st))
        print('pairs with size mismatch:', len(bad), bad[:10])
    elif len(sys.argv) > 1 and sys.argv[1] == 'render':
        # render <gfx> <layout> <outdir>
        g, l, outd = sys.argv[2:5]
        os.makedirs(outd, exist_ok=True)
        pal = palette_for(g)
        for e, ch in frames(g, l):
            compose_frame(e, ch, pal).save(os.path.join(outd, '%s_%s_%03d.png' % (g, l, e.index)))
    else:
        sys.exit(0 if self_test() else 1)
