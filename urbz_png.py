#!/usr/bin/env python3
"""Edit screens and sprite frames as PNG images.

  python urbz_png.py edit <mod> <asset>     write PNGs for an asset into mods/<mod>/png/
  python urbz_png.py export <asset> <dir>   write PNGs anywhere (just to look)

Then paint on the PNGs in any editor and build. The builder converts every
mods/<mod>/png/NNNNN/HHHHHH.png back into chunk HHHHHH of asset NNNNN.

Screens (full 256x192 backgrounds): an indexed PNG with the screen's own 256
colours. Keep using those colours for a pixel-perfect result; other colours are
matched to the nearest colour in the best 16-colour palette row for each 8x8
tile. Tiles are re-cut and de-duplicated (flipped copies too) on import.

Sprite frames: one PNG per frame (chunk), in real colours when the sprite's
palette is known (a palette chunk inside the asset, or the palette named in the
game's sprite table), otherwise in greyscale. Fully transparent pixels and colour
index 0 are see-through. Frames built from several pieces (composite sprites, like
the player's body) export as the assembled picture and are cut back into their pieces
on import. Chunks that no layout describes are
exported as a plain 16-tile-wide strip of their tiles; edit the tiles in place.
"""
import json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from urbz_gfx import bgr555, find_screen
from urbzcomp import decompress, compress


# ---------------------------------------------------------------- helpers

def rgb_to_bgr555(c):
    r, g, b = c[:3]
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def decode_tiles(data):
    n = len(data) // 32
    tiles = []
    for t in range(n):
        px = []
        for y in range(8):
            for x in range(8):
                b = data[t * 32 + y * 4 + x // 2]
                px.append((b >> 4) if x & 1 else (b & 15))
        tiles.append(px)
    return tiles


def encode_tile(px):
    out = bytearray(32)
    for i, v in enumerate(px):
        y, x = divmod(i, 8)
        if x & 1:
            out[y * 4 + x // 2] |= (v & 15) << 4
        else:
            out[y * 4 + x // 2] |= v & 15
    return bytes(out)


def flip_tile(px, h, v):
    return [px[(7 - y if v else y) * 8 + (7 - x if h else x)] for y in range(8) for x in range(8)]


def _nearest(c, pal):
    best, bi = None, 0
    for i, p in enumerate(pal):
        d = (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 + (c[2] - p[2]) ** 2
        if best is None or d < best:
            best, bi = d, i
            if d == 0:
                break
    return bi, best


def _load_png(path):
    from PIL import Image
    return Image.open(path)


# ---------------------------------------------------------------- screens

def screen_to_png(content, path):
    from PIL import Image
    info = find_screen(content)
    if not info:
        raise ValueError('not a screen container')
    pal_off, ncol, mh, w, h, p = info
    cols = [bgr555(c) for c in struct.unpack_from('<%dH' % ncol, content, pal_off)]
    cols += [(0, 0, 0)] * (256 - len(cols))
    mp = struct.unpack_from('<%dH' % (w * h), content, mh + 4)
    tiles = decode_tiles(decompress(content, p + 2))
    img = Image.new('P', (w * 8, h * 8))
    img.putpalette([c for rgb in cols for c in rgb])
    px = img.load()
    for ty in range(h):
        for tx in range(w):
            e = mp[ty * w + tx]
            t, hf, vf, bank = e & 0x3FF, (e >> 10) & 1, (e >> 11) & 1, e >> 12
            if t >= len(tiles):
                continue
            tp = flip_tile(tiles[t], hf, vf)
            for i, v in enumerate(tp):
                px[tx * 8 + i % 8, ty * 8 + i // 8] = bank * 16 + v
    img.save(path, format='PNG', optimize=True)


NEW_COLOUR_ERR = 3 * 32 * 32      # if any pixel is further than this (squared RGB) from the
                                  # best existing row, the tile gets new colours


def _free_banks(pal, used):
    """Palette rows the screen's map never uses and that hold only filler.
    Row 0 is never free: the game loads its text-layer colours there at runtime."""
    out = []
    for b in range(15, 0, -1):
        if b in used or b * 16 + 16 > len(pal):
            continue
        row = pal[b * 16 + 1:b * 16 + 16]
        if len(set(row)) == 1:
            out.append(b)
    return out


def png_to_screen(content, path):
    """Rebuild a screen chunk's decoded content from an edited PNG.
    Unchanged tiles keep their exact data; edited tiles use the best existing
    16-colour row, or (if their colours aren't there) a new row built in a
    spare palette slot."""
    info = find_screen(content)
    pal_off, ncol, mh, w, h, p = info
    pal_raw = list(struct.unpack_from('<%dH' % ncol, content, pal_off))
    pal = [bgr555(c) for c in pal_raw]
    orig_map = struct.unpack_from('<%dH' % (w * h), content, mh + 4)
    orig_tiles = decode_tiles(decompress(content, p + 2))
    used_banks = sorted({e >> 12 for e in orig_map})
    img = _load_png(path)
    if img.size != (w * 8, h * 8):
        raise ValueError('%s is %dx%d; this screen must stay %dx%d'
                         % (path, img.size[0], img.size[1], w * 8, h * 8))
    rgb = img.convert('RGB').load()
    q = lambda c: bgr555(rgb_to_bgr555(c))          # what the DS can actually show

    cells = []                                       # per map cell: (bank, px) or ('new', colours)
    needs_new = []
    for ty in range(h):
        for tx in range(w):
            e = orig_map[ty * w + tx]
            t, hf, vf, bank = e & 0x3FF, (e >> 10) & 1, (e >> 11) & 1, e >> 12
            cols = [q(rgb[tx * 8 + i % 8, ty * 8 + i // 8]) for i in range(64)]
            if t < len(orig_tiles):
                opx = flip_tile(orig_tiles[t], hf, vf)
                if cols == [pal[bank * 16 + v] for v in opx]:
                    cells.append((bank, opx))          # untouched tile: keep exactly
                    continue
            best = None
            for b in used_banks:
                # colour 0 is transparent on the DS: never use it for a painted pixel
                sub = [(-999, -999, -999)] + pal[b * 16 + 1:b * 16 + 16]
                picks = [_nearest(c, sub) for c in cols]
                err = sum(x for _, x in picks)
                worst = max(x for _, x in picks)
                if best is None or err < best[0]:
                    best = (err, b, [i for i, _ in picks], worst)
            if best is None or best[3] > NEW_COLOUR_ERR:
                cells.append(('new', cols))
                needs_new.append(len(cells) - 1)
            else:
                cells.append((best[1], best[2]))

    warn = []
    if needs_new:
        free = _free_banks(pal_raw, set(used_banks))
        if not free:
            warn.append('%s: %d edited tile(s) use colours this screen has no room for; they were '
                        'matched to the nearest existing colours' % (path, len(needs_new)))
            for k in needs_new:
                cols = cells[k][1]
                rows = {b: [(-999, -999, -999)] + pal[b * 16 + 1:b * 16 + 16] for b in used_banks}
                best = min(((sum(_nearest(c, rows[b])[1] for c in cols), b) for b in used_banks))
                cells[k] = (best[1], [_nearest(c, rows[best[1]])[0] for c in cols])
        else:
            groups = _split_tiles([cells[k][1] for k in needs_new], len(free))
            for g, bank in zip(groups, free):
                colours = _quantize([c for k in g for c in cells[needs_new[k]][1]], 15)
                for i, c in enumerate(colours):
                    pal_raw[bank * 16 + 1 + i] = rgb_to_bgr555(c)
                    pal[bank * 16 + 1 + i] = bgr555(rgb_to_bgr555(c))
                sub = [(-999, -999, -999)] + pal[bank * 16 + 1:bank * 16 + 16]   # never pick 0
                for k in g:
                    cols = cells[needs_new[k]][1]
                    cells[needs_new[k]] = (bank, [_nearest(c, sub)[0] for c in cols])
            used_banks = sorted(set(used_banks) | set(free[:len(groups)]))

    tiles, tile_index, mp = [], {}, []
    for bank, px in cells:
        hit = None
        for hf in (0, 1):
            for vf in (0, 1):
                key = bytes(flip_tile(px, hf, vf))
                if key in tile_index:
                    hit = (tile_index[key], hf, vf)
                    break
            if hit:
                break
        if not hit:
            tile_index[bytes(px)] = len(tiles)
            tiles.append(px)
            hit = (len(tiles) - 1, 0, 0)
        t, hf, vf = hit
        mp.append(t | hf << 10 | vf << 11 | bank << 12)
    if len(tiles) > 1024:
        raise ValueError('%s needs %d unique 8x8 tiles; the map can address 1024. Simplify the '
                         'image (fewer unique tiles).' % (path, len(tiles)))
    if len(tiles) > len(orig_tiles):
        warn.append('%s uses %d unique tiles (the original used %d). Extra tiles take more video '
                    'memory; if the screen shows garbage in-game, simplify the image.'
                    % (path, len(tiles), len(orig_tiles)))
    stream = compress(b''.join(encode_tile(t) for t in tiles))
    head = bytearray(content[:mh + 4])
    struct.pack_into('<%dH' % ncol, head, pal_off, *pal_raw)
    new = bytes(head) + struct.pack('<%dH' % len(mp), *mp) + struct.pack('<H', len(stream)) + stream
    return new, ('; '.join(warn) or None)


def _quantize(colours, n):
    """Up to n representative RGB colours (median cut via Pillow)."""
    from PIL import Image
    img = Image.new('RGB', (len(colours), 1))
    img.putdata(colours)
    qimg = img.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    p = qimg.getpalette()[:n * 3]
    out = [tuple(p[i:i + 3]) for i in range(0, len(p), 3)]
    return (out + [out[-1]] * n)[:n]


def _split_tiles(tile_cols, k):
    """Group tiles into up to k groups by average colour (tiny k-means)."""
    if k <= 1 or len(tile_cols) <= 1:
        return [list(range(len(tile_cols)))]
    means = [tuple(sum(c[j] for c in cols) / 64 for j in range(3)) for cols in tile_cols]
    cent = [means[0], max(means, key=lambda m: sum((m[j] - means[0][j]) ** 2 for j in range(3)))][:k]
    for _ in range(8):
        groups = [[] for _ in cent]
        for i, m in enumerate(means):
            gi = min(range(len(cent)), key=lambda c: sum((m[j] - cent[c][j]) ** 2 for j in range(3)))
            groups[gi].append(i)
        cent = [tuple(sum(means[i][j] for i in g) / len(g) for j in range(3)) if g else cent[n]
                for n, g in enumerate(groups)]
    return [g for g in groups if g]


def _same_screen_pixels(content, path):
    import io
    buf = io.BytesIO()
    screen_to_png(content, buf)
    from PIL import Image
    a = Image.open(io.BytesIO(buf.getvalue()))
    b = _load_png(path)
    if b.mode == 'P' and b.size == a.size and a.tobytes() == b.tobytes():
        return True
    return b.size == a.size and a.convert('RGB').tobytes() == b.convert('RGB').tobytes()


def _png_palette_matches(img, pal):
    p = img.getpalette() or []
    cols = [tuple(p[i * 3:i * 3 + 3]) for i in range(min(len(p) // 3, len(pal)))]
    return len(cols) >= len(pal) and all(
        rgb_to_bgr555(a) == rgb_to_bgr555(b) for a, b in zip(cols, pal))


# ---------------------------------------------------------------- sprites

_CAPTURED = None


def captured_palettes():
    """{asset number: [16 BGR555]} from verify/palettes/*.json (urbz_verify.py trace)."""
    global _CAPTURED
    if _CAPTURED is None:
        _CAPTURED = {}
        pdir = os.path.join(KIT, 'verify', 'palettes')
        if os.path.isdir(pdir):
            for f in sorted(os.listdir(pdir)):
                if f.endswith('.json'):
                    for k, v in json.load(open(os.path.join(pdir, f))).items():
                        _CAPTURED.setdefault(int(k), v)
    return _CAPTURED


def sprite_palette(proj, idx, manifest, refs):
    """16 RGB colours for sprite asset idx, and where they came from."""
    cap = captured_palettes().get(idx)
    if cap:
        return [bgr555(v) for v in cap], 'captured in-game (verify/palettes)'
    e = manifest['entries'][idx]
    for c in e.get('chunks', []):
        if (c['flags'] >> 4) & 7 in (0, 1):
            d = open(os.path.join(proj, 'unpacked', '%05d' % idx, c['file']), 'rb').read()
            if len(d) in (32, 512):
                return [bgr555(v) for v in struct.unpack_from('<16H', d)], 'palette chunk %s' % c['file']
    info = (refs or {}).get('%05d' % idx)
    for p in (info or {}).get('palettes', []):
        a = open(os.path.join(proj, 'assets', manifest['entries'][int(p)]['file']), 'rb').read()
        if len(a) >= 32:
            return [bgr555(v) for v in struct.unpack_from('<16H', a)], 'palette asset %s' % p
    return [(v * 17, v * 17, v * 17) for v in range(16)], 'greyscale (palette not known yet)'


def frame_shape(proj, idx, manifest, refs, chunk):
    """(w_tiles, h_tiles) if this chunk is one simple w*h frame, else None."""
    info = (refs or {}).get('%05d' % idx)
    if not info:
        return None
    for l in info['layouts']:
        a = open(os.path.join(proj, 'assets', manifest['entries'][int(l)]['file']), 'rb').read()
        w, h = a[0], a[1]
        if w and h and w % 8 == 0 and h % 8 == 0:
            size = os.path.getsize(os.path.join(proj, 'unpacked', '%05d' % idx, chunk))
            if size == (w // 8) * (h // 8) * 32:
                return w // 8, h // 8
    return None


def composite_entry(proj, idx, manifest, refs, chunk):
    """The layout entry that assembles this chunk from several cells (composite sprite),
    or None. Uses the decoded cell format in urbz_composite.py."""
    from urbz_composite import parse_layout, check_entry
    info = (refs or {}).get('%05d' % idx)
    if not info:
        return None
    off = int(chunk[:6], 16)
    size = os.path.getsize(os.path.join(proj, 'unpacked', '%05d' % idx, chunk))
    for l in info['layouts']:
        a = open(os.path.join(proj, 'assets', manifest['entries'][int(l)]['file']), 'rb').read()
        try:
            lay = parse_layout(a)
        except Exception:
            continue
        for e in lay.entries:
            if e.chunk_off == off and len(e.cells) > 1 and e.tiles * 32 == size and \
                    not check_entry(e, size):
                return e
    return None


def composite_to_png(entry, data, pal, path):
    from PIL import Image
    from urbz_composite import compose_indices
    rows = compose_indices(entry, data)
    img = Image.new('P', (max(1, entry.w), max(1, entry.h)))
    img.putpalette([c for rgb in pal for c in rgb])
    px = img.load()
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            px[x, y] = v
    img.save(path, transparency=0, optimize=True)


def png_to_composite(orig, entry, pal, path):
    from urbz_composite import split_frame
    img = _load_png(path)
    if img.size != (entry.w, entry.h):
        raise ValueError('%s is %dx%d; this frame must stay %dx%d'
                         % (path, img.size[0], img.size[1], entry.w, entry.h))
    new = split_frame(img, entry, pal, orig)
    return new, None


def sprite_to_png(data, pal, shape, path):
    from PIL import Image
    tiles = decode_tiles(data)
    wt, ht = shape if shape else (16, (len(tiles) + 15) // 16)
    img = Image.new('P', (wt * 8, max(1, ht) * 8))
    img.putpalette([c for rgb in pal for c in rgb])
    img.info['transparency'] = 0
    px = img.load()
    for t, tp in enumerate(tiles):
        ox, oy = (t % wt) * 8, (t // wt) * 8
        for i, v in enumerate(tp):
            px[ox + i % 8, oy + i // 8] = v
    img.save(path, transparency=0, optimize=True)


def png_to_sprite(orig, pal, shape, path):
    tiles = decode_tiles(orig)
    wt, ht = shape if shape else (16, (len(tiles) + 15) // 16)
    img = _load_png(path)
    if img.size != (wt * 8, max(1, ht) * 8):
        raise ValueError('%s is %dx%d; this frame must stay %dx%d'
                         % (path, img.size[0], img.size[1], wt * 8, max(1, ht) * 8))
    far = [0]
    if img.mode == 'P' and _png_palette_matches(img, pal):
        get = img.load()
        val = lambda x, y: get[x, y] & 15
    else:
        rgba = img.convert('RGBA').load()
        cache = {}

        def val(x, y):
            c = rgba[x, y]
            if c[3] < 128:
                return 0
            if c not in cache:
                cache[c] = _nearest(c, pal[1:])                 # index 0 is see-through
            i, err = cache[c]
            if err > 3 * 32 * 32:
                far[0] += 1
            return i + 1
    out = bytearray()
    for t in range(len(tiles)):
        ox, oy = (t % wt) * 8, (t // wt) * 8
        out += encode_tile([val(ox + i % 8, oy + i // 8) for i in range(64)])
    warn = None
    if far[0]:
        warn = ('%s: %d pixel(s) use colours that are not in this sprite\'s 16-colour palette; '
                'they were changed to the nearest palette colour. Sprites can only use the colours '
                'in their exported PNG.' % (path, far[0]))
    return bytes(out) + bytes(orig[len(out):]), warn


# ---------------------------------------------------------------- project glue

def _project():
    proj = os.path.join(KIT, 'project')
    m = json.load(open(os.path.join(proj, 'manifest.json')))
    rp = os.path.join(proj, 'sprite_refs.json')
    refs = json.load(open(rp))['gfx'] if os.path.exists(rp) else {}
    return proj, m, refs


def export_asset(idx, outdir):
    proj, m, refs = _project()
    e = m['entries'][idx]
    if not e.get('chunks'):
        raise ValueError('asset %05d has no image chunks' % idx)
    os.makedirs(outdir, exist_ok=True)
    written = []
    pal, pal_src = None, None
    for c in e['chunks']:
        d = open(os.path.join(proj, 'unpacked', '%05d' % idx, c['file']), 'rb').read()
        out = os.path.join(outdir, c['file'][:-4] + '.png')
        if find_screen(d):
            screen_to_png(d, out)
            written.append((out, 'screen'))
        elif '%05d' % idx in refs and len(d) >= 32 and len(d) % 32 == 0:
            if pal is None:
                pal, pal_src = sprite_palette(proj, idx, m, refs)
            comp = composite_entry(proj, idx, m, refs, c['file'])
            shape = None if comp else frame_shape(proj, idx, m, refs, c['file'])
            if comp:
                composite_to_png(comp, d, pal, out)
                written.append((out, 'sprite frame (%d pieces)' % len(comp.cells)))
            else:
                sprite_to_png(d, pal, shape, out)
                written.append((out, 'sprite frame' if shape else 'tile strip'))
    if not written:
        raise ValueError('asset %05d has no screens or sprite frames to export' % idx)
    return written, pal_src


def png_overrides(proj, overlay, manifest, refs):
    """Builder hook: {('unpacked', idx, chunkfile): new decoded content} for every
    mods/*/png/NNNNN/HHHHHH.png, plus a list of warnings."""
    out, warnings = {}, []
    for rel, (mod, path) in sorted(overlay.files.items()):
        parts = rel.split('/')
        if parts[0] != 'png':
            continue
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].endswith('.png'):
            raise ValueError('mod "%s": %s should be png/NNNNN/HHHHHH.png' % (mod, rel))
        idx, chunk = int(parts[1]), parts[2][:-4] + '.bin'
        e = manifest['entries'][idx] if idx < len(manifest['entries']) else None
        ch = next((c for c in (e or {}).get('chunks', []) if c['file'] == chunk), None)
        if ch is None:
            raise ValueError('mod "%s": %s does not match a chunk of asset %05d' % (mod, rel, idx))
        crel = 'unpacked/%05d/%s' % (idx, chunk)
        if overlay.overridden(crel) or overlay.overridden('unpacked/%05d/%s' % (idx, ch.get('nested', {}).get('file', '-'))):
            raise ValueError('asset %05d chunk %s is edited both as a PNG and as a .bin; keep one'
                             % (idx, chunk))
        orig = open(overlay.path(crel), 'rb').read()
        if find_screen(orig):
            if _same_screen_pixels(orig, path):
                continue                      # PNG unchanged: keep the original chunk
            new, warn = png_to_screen(orig, path)
            if warn:
                warnings.append(warn)
        else:
            pal, _ = sprite_palette(proj, idx, manifest, refs)
            comp = composite_entry(proj, idx, manifest, refs, chunk)
            shape = None if comp else frame_shape(proj, idx, manifest, refs, chunk)
            if comp:
                new, warn = png_to_composite(orig, comp, pal, path)
            else:
                new, warn = png_to_sprite(orig, pal, shape, path)
            if warn:
                warnings.append(warn)
        out[(idx, chunk)] = new
    return out, warnings


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd = argv[0]
    if cmd == 'export' and len(argv) == 3:
        written, src = export_asset(int(argv[1]), argv[2])
    elif cmd == 'edit' and len(argv) == 3:
        md = os.path.join(KIT, 'mods', argv[1])
        if not os.path.isdir(md):
            sys.exit('error: no mod named "%s" (create it: python urbz_mod.py new %s)' % (argv[1], argv[1]))
        written, src = export_asset(int(argv[2]), os.path.join(md, 'png', '%05d' % int(argv[2])))
    else:
        sys.exit('usage: urbz_png.py edit <mod> <asset>  |  urbz_png.py export <asset> <dir>')
    for p, kind in written:
        print('%-12s %s' % (kind, p))
    if src:
        print('sprite colours: ' + src)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except ValueError as e:
        sys.exit('error: %s' % e)
