#!/usr/bin/env python3
"""Which sprite *layout* assets point into which multi-chunk *graphics* assets.

Sprite layouts store, per frame entry, a u16 byte offset (entry+4) to a chunk
inside their graphics asset. The game pairs them through 16-byte sprite
definition records in its ARM9 code: {u32 gfx gameID, u32 layout gameID,
u32 palette gameID or 0, u32 param} (game ID = file number + 1), plus a few
pairs inlined in code. We scan the ARM9 for such pairs and keep only pairs
where EVERY offset the layout uses is a real chunk start in that graphics
asset, which filters out coincidental numbers. Four sheets whose ids the game
computes (07279, 09195, 09197, 10368) are paired with the layout right after
them, whose offsets match their chunks exactly.

The builder uses project/sprite_refs.json to re-point layouts when an edited
chunk grows and the chunks after it move.

  python urbz_sprites.py [project_dir]     (re)write project/sprite_refs.json
"""
import json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)


def layout_offsets(a):
    """Offsets referenced by a sprite layout asset, or None if it isn't one.
    Returns a list of (entry_field_position, offset)."""
    if len(a) < 0x10:
        return None
    n = struct.unpack_from('<H', a, 6)[0]
    if not 1 <= n <= 512 or 0xC + 2 * n > len(a):
        return None
    out = []
    for k in range(n):
        eo = 0xC + struct.unpack_from('<H', a, 0xC + 2 * k)[0]
        if eo + 6 > len(a):
            return None
        out.append((eo + 4, struct.unpack_from('<H', a, eo + 4)[0]))
    return out


def _tiles_fit(proj, E, g, l):
    """Every frame of layout l fits in the chunk it points at in gfx g (cell format from
    urbz_composite). Filters one-frame layouts that 'match' any asset at offset 0."""
    try:
        from urbz_composite import parse_layout
        lay = parse_layout(open(os.path.join(proj, 'assets', E[l]['file']), 'rb').read())
    except Exception:
        return True                                   # unknown shape: keep the offset test only
    for e in lay.entries:
        p = os.path.join(proj, 'unpacked', '%05d' % g, '%06X.bin' % e.chunk_off)
        if not os.path.exists(p) or e.tiles * 32 > os.path.getsize(p):
            return False
    return True


def build_refs(proj):
    import ndspy.rom
    m = json.load(open(os.path.join(proj, 'manifest.json')))
    E = m['entries']
    N = len(E)
    rom = ndspy.rom.NintendoDSRom.fromFile(os.path.join(proj, 'base.nds'))
    a9 = bytes(rom.arm9)

    layout_cache = {}

    def layout(i):
        if i not in layout_cache:
            a = open(os.path.join(proj, 'assets', E[i]['file']), 'rb').read()
            layout_cache[i] = layout_offsets(a) if not E[i].get('chunks') else None
        return layout_cache[i]

    chunk_offs = {i: {c['off'] for c in e['chunks']} for i, e in enumerate(E) if e.get('chunks')}
    gfx = {}
    for pos in range(0, len(a9) - 8, 4):
        g, l = struct.unpack_from('<II', a9, pos)
        if not (1 <= g <= N and 1 <= l <= N):
            continue
        g, l = g - 1, l - 1
        if g not in chunk_offs:
            continue
        lo = layout(l)
        if lo is None:
            continue
        refs = {o for _, o in lo}
        if not refs <= chunk_offs[g]:
            continue                                  # coincidental numbers, not a real pair
        if not _tiles_fit(proj, E, g, l):
            continue                                  # frames need more tiles than the chunks hold
        rec = gfx.setdefault(g, {'layouts': set(), 'palettes': set()})
        rec['layouts'].add(l)
        if pos + 12 <= len(a9):
            p = struct.unpack_from('<I', a9, pos + 8)[0]
            if 1 <= p <= N and E[p - 1]['size'] in (32, 64, 128, 512) and not E[p - 1].get('chunks'):
                rec['palettes'].add(p - 1)

    # A few pairs are built in code from computed ids, so the scan above misses them.
    # For those, accept the neighbouring layout asset (file number +1, then -1) when its
    # offsets are exactly this asset's chunk starts (every chunk used, nothing else).
    for g, offs in chunk_offs.items():
        if g in gfx or len(offs) < 2:
            continue
        for l in (g + 1, g - 1):
            if 0 <= l < N and not E[l].get('chunks'):
                lo = layout(l)
                if lo and {o for _, o in lo} == offs:
                    gfx[g] = {'layouts': {l}, 'palettes': set(), 'neighbor': True}
                    break

    out = {'note': 'file numbers (game ID - 1); offsets are byte offsets of chunks inside the gfx asset',
           'gfx': {}}
    for g in sorted(gfx):
        lays = sorted(gfx[g]['layouts'])
        moved = sorted(set().union(*({o for _, o in layout(l)} for l in lays)) - {0})
        out['gfx']['%05d' % g] = {
            'layouts': ['%05d' % l for l in lays],
            'referenced_offsets': moved,               # nonzero offsets that layouts point at
            'all_chunks_referenced': chunk_offs[g] - {0} <= set(moved),
            'palettes': ['%05d' % p for p in sorted(gfx[g]['palettes'])],
        }
        if gfx[g].get('neighbor'):
            out['gfx']['%05d' % g]['source'] = 'neighbour layout (exact chunk match)'
    path = os.path.join(proj, 'sprite_refs.json')
    json.dump(out, open(path, 'w'), indent=1)
    multi = sum(1 for e in E if len(e.get('chunks', [])) > 1)
    covered = sum(1 for g in gfx if len(E[g]['chunks']) > 1)
    return path, len(gfx), covered, multi


if __name__ == '__main__':
    proj = sys.argv[1] if len(sys.argv) > 1 else os.path.join(KIT, 'project')
    path, n, covered, multi = build_refs(proj)
    print('wrote %s: %d graphics assets with known layouts; %d of %d multi-chunk assets can grow'
          % (path, n, covered, multi))
