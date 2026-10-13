"""Decoders for Urbz DS graphics formats (screen containers, 4bpp tiles, palettes)."""
import struct
from urbzcomp import decompress


def bgr555(c):
    r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


def find_screen(d):
    """Return (pal_off, n_colors, map_off, w, h, tiles_len_off) if d is a screen
    container ([u16 ?][palette][u16 w][u16 h][map w*h u16][u16 len][tiles stream]
    with the tiles stream as the last block), else None."""
    n = len(d)
    for w, h in ((32, 24), (32, 32), (64, 32), (32, 64), (64, 64), (32, 48), (64, 24)):
        mh = 2 + 512                        # common case: 256 colours after a u16
        for pal_end in (mh, 2 + 32 * 2, 2 + 16 * 2, 2 + 128 * 2):
            if pal_end + 4 + 2 * w * h + 2 > n:
                continue
            if struct.unpack_from('<HH', d, pal_end) != (w, h):
                continue
            p = pal_end + 4 + 2 * w * h
            L = struct.unpack_from('<H', d, p)[0]
            if p + 2 + L > n or n - (p + 2 + L) > 3:
                continue
            try:                                # the tiles stream must really decode
                _, used = decompress(d, p + 2, return_consumed=True)
            except Exception:
                continue
            if used > L:
                continue
            return (2, (pal_end - 2) // 2, pal_end, w, h, p)
    return None


def render_screen(d, info=None):
    from PIL import Image
    info = info or find_screen(d)
    if not info:
        raise ValueError('not a screen container')
    pal_off, ncol, mh, w, h, p = info
    pal = [bgr555(c) for c in struct.unpack_from('<%dH' % ncol, d, pal_off)]
    pal += [(255, 0, 255)] * (256 - len(pal))
    mp = struct.unpack_from('<%dH' % (w * h), d, mh + 4)
    tiles = decompress(d, p + 2)
    img = Image.new('RGB', (w * 8, h * 8))
    px = img.load()
    for ty in range(h):
        for tx in range(w):
            e = mp[ty * w + tx]
            t, hf, vf, pl = e & 0x3FF, (e >> 10) & 1, (e >> 11) & 1, e >> 12
            base = t * 32
            if base + 32 > len(tiles):
                continue
            for y in range(8):
                for x in range(8):
                    b = tiles[base + y * 4 + x // 2]
                    v = (b >> 4) if x & 1 else (b & 15)
                    sx = 7 - x if hf else x
                    sy = 7 - y if vf else y
                    px[tx * 8 + sx, ty * 8 + sy] = pal[pl * 16 + v]
    return img


def render_tiles(data, pal=None, cols=16, max_tiles=512):
    """Preview raw 4bpp tile data (greyscale unless a 16-colour palette is given)."""
    from PIL import Image
    n = min(len(data) // 32, max_tiles)
    if n == 0:
        return None
    pal = pal or [(v * 17, v * 17, v * 17) for v in range(16)]
    rows = (n + cols - 1) // cols
    img = Image.new('RGB', (cols * 8, rows * 8))
    px = img.load()
    for t in range(n):
        ox, oy = (t % cols) * 8, (t // cols) * 8
        for y in range(8):
            for x in range(8):
                b = data[t * 32 + y * 4 + x // 2]
                px[ox + x, oy + y] = pal[(b >> 4) if x & 1 else (b & 15)]
    return img


def render_palette(data, sw=8):
    from PIL import Image
    n = len(data) // 2
    cols = [bgr555(c) for c in struct.unpack_from('<%dH' % n, data)]
    img = Image.new('RGB', (16 * sw, ((n + 15) // 16) * sw))
    for i, c in enumerate(cols):
        x, y = (i % 16) * sw, (i // 16) * sw
        for yy in range(sw):
            for xx in range(sw):
                img.putpixel((x + xx, y + yy), c)
    return img


def tiles_to_array(data, cols=16, max_tiles=256):
    """4bpp tiles -> 2D numpy array of colour indices (fast)."""
    import numpy as np
    n = min(len(data) // 32, max_tiles)
    if n == 0:
        return None
    raw = np.frombuffer(bytes(data[:n * 32]), dtype=np.uint8).reshape(n, 8, 4)
    px = np.empty((n, 8, 8), dtype=np.uint8)
    px[:, :, 0::2] = raw & 15
    px[:, :, 1::2] = raw >> 4
    rows = (n + cols - 1) // cols
    pad = rows * cols - n
    if pad:
        px = np.concatenate([px, np.zeros((pad, 8, 8), np.uint8)])
    return px.reshape(rows, cols, 8, 8).transpose(0, 2, 1, 3).reshape(rows * 8, cols * 8)


def tiles_preview(data, pal=None, cols=16, max_tiles=256):
    """Fast PIL preview of 4bpp tile data (greyscale ramp unless pal given)."""
    from PIL import Image
    arr = tiles_to_array(data, cols, max_tiles)
    if arr is None:
        return None
    img = Image.fromarray(arr, mode='P')
    pal = pal or [(v * 17, v * 17, v * 17) for v in range(16)]
    flat = [c for rgb in pal for c in rgb]
    img.putpalette(flat + [0] * (768 - len(flat)))
    return img.convert('RGB')
