#!/usr/bin/env python3
"""Read 3D furniture from The Sims 3 (DS). Read-only: your ROM stays where it is; nothing goes into git.
urbz_import.py renders what this reads.

Formats (worked out 2026-10-05; docs/other-games.md):
  *.package  a plain run of DSM1 meshes and DST1 textures, no index. Each object is a group: its meshes
             (5 levels of detail of each part, the most detailed first), then its textures, each a chain of
             smaller copies (128, 64, 32, 16, 8). Several chains of the first texture = colour choices.
  DSM1       'DSM1' 03 01 01 01, u32 n, a GX display list of n bytes (the DS 3D engine's own commands,
             vertices in metres), then the materials (texture file names, e.g. "bathtubvalue-green-clean.dst")
             and named points.
  DST1       'DST1' 02 01 01 01, u32 format (low 16 bits: DS texture format; bit 16 starts a new texture),
             u16 width, u16 height, u16 colours, the colours (BGR555), the texels.

  python urbz_sims3.py models ROM      the furniture this reads
"""
import os, re, struct, sys

PACKAGES = ['DATA/BACKEND/Furniture.package']
MESH, TEX = b'DSM1\x03\x01\x01\x01', b'DST1\x02\x01\x01\x01'


def texture(d, o):
    """DST1 at offset o -> RGBA array, (w, h)."""
    import numpy as np
    from urbz_fullfat import _bgr
    fmt, w, h, nc = struct.unpack_from('<IHHH', d, o + 8)
    P = [_bgr(c) for c in struct.unpack_from('<%dH' % nc, d, o + 18)]
    po, f = o + 18 + 2 * nc, fmt & 0xFFFF
    if f not in (2, 3, 4):
        raise ValueError('Sims 3 texture format %d is not decoded' % f)
    bits = {2: 2, 3: 4, 4: 8}[f]
    idx = np.frombuffer(d[po:po + w * h * bits // 8], np.uint8)
    if bits < 8:
        idx = np.stack([(idx >> (bits * k)) & ((1 << bits) - 1) for k in range(8 // bits)], 1).reshape(-1)
    idx = idx[:w * h].reshape(h, w)
    lut = np.array([P[i] + (255,) if i < len(P) else (255, 0, 255, 255) for i in range(1 << bits)], np.uint8)
    return lut[idx]


def _mesh_names(d, o, end):
    size = struct.unpack_from('<I', d, o + 8)[0]
    return [n.decode('latin-1') for n in re.findall(rb'([A-Za-z0-9_\-]{2,}\.dst)\x00', d[o + 12 + size:end])]


class Game:
    id = 'sims3'

    def __init__(self, rom_path):
        import ndspy.rom
        rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
        self._models = []
        seen = {}
        for pk in PACKAGES:
            d = bytes(rom.getFileByName(pk))
            recs = sorted([(m.start(), 'M') for m in re.finditer(re.escape(MESH), d)] +
                          [(m.start(), 'T') for m in re.finditer(re.escape(TEX), d)])
            groups, cur = [], None
            for o, k in recs:
                if k == 'M' and (cur is None or cur['T']):
                    cur = {'M': [], 'T': []}
                    groups.append(cur)
                if cur is not None:
                    cur[k].append(o)
            for gr in groups:
                ends = gr['M'][1:] + [gr['T'][0] if gr['T'] else len(d)]
                meshes = [(o, (_mesh_names(d, o, e) or [''])[0]) for o, e in zip(gr['M'], ends)]
                parts, last = [], None                # the most detailed mesh of each part
                for o, n in meshes:
                    if n != last:
                        parts.append((o, n))
                        last = n
                chains = []                           # textures: chains of smaller copies
                for o in gr['T']:
                    fmt, w, _h, _n = struct.unpack_from('<IHHH', d, o + 8)
                    if not chains or fmt >> 16 or w >= chains[-1][-1][1]:
                        chains.append([])
                    chains[-1].append((o, w))
                names = []
                for _o, n in parts:
                    if n and n not in names:
                        names.append(n)
                tex = {}
                if names and chains:
                    extra = max(0, len(chains) - len(names))    # extra chains: colour choices of the first
                    tex[names[0]] = [c[0][0] for c in chains[:1 + extra]]
                    for k, n in enumerate(names[1:]):
                        if 1 + extra + k < len(chains):
                            tex[n] = [chains[1 + extra + k][0][0]]
                base = re.split(r'[-_.]', names[0])[0] if names else 'object%d' % len(self._models)
                seen[base] = seen.get(base, 0) + 1
                name = base if seen[base] == 1 else '%s%d' % (base, seen[base])
                self._models.append({'name': name, 'kind': 'object', 'folder': '%s/%s' % (pk, name),
                                     'data': d, 'parts': parts, 'textures': tex, 'anims': {},
                                     'colours': len(tex.get(names[0], [])) if names else 0})

    def models(self):
        return self._models


def parts(info, colour=0):
    """-> [(tris [N,3,8], texture RGBA or None, (r, g, b))] in metres, UVs 0..1."""
    import numpy as np
    from urbz_fullfat import gx_run
    d, out = info['data'], []
    for o, name in info['parts']:
        size = struct.unpack_from('<I', d, o + 8)[0]
        tex = None
        offs = info['textures'].get(name)
        if offs:
            try:
                tex = texture(d, offs[min(colour, len(offs) - 1)])
            except ValueError:
                tex = None
        for s in gx_run(d, o + 12, o + 12 + size):
            a = np.array(s['tris'], np.float64).reshape(-1, 3, 10)
            if tex is not None:
                a[..., 3] /= tex.shape[1]
                a[..., 4] /= tex.shape[0]
            out.append((a[..., :8], tex, (255, 255, 255) if tex is not None else (190, 190, 190)))
    return out


def main(argv):
    if len(argv) < 2 or argv[0] != 'models':
        print(__doc__)
        return
    for m in Game(argv[1]).models():
        print('%-28s parts %d  colours %d' % (m['name'], len(m['parts']), m['colours']))


if __name__ == '__main__':
    main(sys.argv[1:])
