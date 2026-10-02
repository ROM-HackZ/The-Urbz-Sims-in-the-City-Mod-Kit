"""Static asset classification for the catalog."""
import struct
from urbz_gfx import find_screen


def parse_sprite_layout(a):
    """Sprite layout (metadata) asset -> list of chunk offsets it references, or None."""
    if len(a) < 0x10:
        return None
    n = struct.unpack_from('<H', a, 6)[0]
    if not 1 <= n <= 512 or 0xC + 2 * n > len(a):
        return None
    refs = []
    for k in range(n):
        eo = 0xC + struct.unpack_from('<H', a, 0xC + 2 * k)[0]
        if eo + 6 > len(a):
            return None
        refs.append(struct.unpack_from('<H', a, eo + 4)[0])
    return refs


def looks_like_palette(a):
    if len(a) not in (32, 64, 128, 512):
        return False
    vals = struct.unpack_from('<%dH' % (len(a) // 2), a)
    return all(v < 0x8000 for v in vals[1:]) or len(set(v >> 15 for v in vals)) == 1


def classify_all(manifest, read_asset, read_chunk, sprite_refs=None):
    """Return {index: info dict}. read_asset(i) -> bytes, read_chunk(i, file) -> bytes.
    sprite_refs: the 'gfx' dict from project/sprite_refs.json (authoritative pairs
    from the game code); without it, layouts are paired by a nearest-ID guess."""
    E = manifest['entries']
    chunk_offs = {i: {c['off'] for c in e['chunks']} for i, e in enumerate(E) if e.get('chunks')}
    out = {}
    layouts = {}
    for i, e in enumerate(E):
        info = {'id': i + 1, 'file': e['file'], 'size': e['size'],
                'chunks': len(e.get('chunks', []))}
        if e.get('chunks'):
            screens = []
            for c in e['chunks']:
                d = read_chunk(i, c['file'])
                s = find_screen(d)
                if s:
                    screens.append(c['file'])
            if screens:
                info['type'] = 'screen'
                info['screens'] = screens
            elif len(e['chunks']) > 1:
                info['type'] = 'sprite-sheet?'
            else:
                info['type'] = 'packed-data'
        else:
            a = read_asset(i)
            refs = parse_sprite_layout(a)
            if refs is not None:
                layouts[i] = refs
                info['type'] = 'sprite-layout?'
            elif looks_like_palette(a):
                info['type'] = 'palette'
            else:
                info['type'] = 'data'
        out[i] = info
    if sprite_refs:
        for g, rec in sprite_refs.items():
            gi = int(g)
            if gi not in out:
                continue
            if out[gi]['type'] != 'screen':      # offset-0-only layouts can "match" screens
                out[gi]['type'] = 'sprite-sheet'
            for l in rec['layouts']:
                li = int(l)
                out[gi].setdefault('layouts', []).append(li)
                out[li]['type'] = 'sprite-layout'
                out[li].setdefault('gfx', gi)
            if rec.get('palettes'):
                out[gi]['palettes'] = [int(p) for p in rec['palettes']]
        for i in layouts:
            if out[i]['type'] == 'sprite-layout?':
                out[i]['type'] = 'data'
        for info in out.values():
            if info['type'] == 'sprite-sheet?':
                info['type'] = 'packed-multi'
        return out
    # Pair sprite layouts with the graphics asset whose chunk offsets they use,
    # preferring the nearest asset ID.
    for i, refs in layouts.items():
        need = set(refs)
        best = None
        for j in sorted(chunk_offs, key=lambda j: abs(j - i))[:40]:
            if need <= chunk_offs[j]:
                best = j
                break
        if best is not None:
            out[i]['type'] = 'sprite-layout'
            out[i]['gfx'] = best
            out[best]['type'] = 'sprite-sheet'
            out[best].setdefault('layouts', []).append(i)
        else:
            out[i]['type'] = 'data'
    for info in out.values():
        if info['type'] == 'sprite-sheet?':
            info['type'] = 'packed-multi'
    return out
