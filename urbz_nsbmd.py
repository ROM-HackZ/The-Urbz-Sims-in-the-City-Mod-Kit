#!/usr/bin/env python3
"""Read 3D models from The Sims 2 (DS): Nintendo's standard NSBMD format ('BMD0': MDL0 models + TEX0
textures), stored inside the game's EA-compressed rom.bin assets (the same container as The Urbz).
Read-only: your ROM stays where it is; nothing goes into git. urbz_import.py renders what this reads.

What is decoded (2026-10-05): dictionaries, nodes (translation / rotation incl. the compressed pivot form
/ scale), the render bytecode (NODEDESC with store/restore, MTX, MAT, SHP, RET), materials (diffuse
colour, texture and palette by name), polygons (GX display lists, run with the node matrices), TEX0
textures in every DS format including 4x4 compressed. Not: skinning (NODEMIX), billboards, texture
matrices, animations (BCA0).

  python urbz_nsbmd.py models ROM          the models in The Sims 2 (DS)
"""
import struct, sys


def _dict(d, o):
    """NSBMD dictionary at o -> [(name, data bytes)]."""
    num = d[o + 1]
    unk_size = struct.unpack_from('<H', d, o + 6)[0]
    p = o + unk_size                          # the size counts from the dictionary's start
    esize, _sect = struct.unpack_from('<HH', d, p)
    data = [d[p + 4 + esize * i:p + 4 + esize * (i + 1)] for i in range(num)]
    np_ = p + 4 + esize * num
    names = [d[np_ + 16 * i:np_ + 16 * (i + 1)].split(b'\0')[0].decode('latin-1') for i in range(num)]
    return list(zip(names, data))


def _fx(v):
    return v / 4096.0


PIVOT = [  # rows of the compressed "pivot" rotation (DS SDK)
    (0, 1, 2, 3, 4, 5, 6, 7, 8)]


def _node_matrix(d, o):
    """Local transform of a node (row-vector convention, 4x4)."""
    import numpy as np
    flag, m0 = struct.unpack_from('<Hh', d, o)
    p = o + 4
    T = np.zeros(3)
    if not flag & 1:
        T = np.array(struct.unpack_from('<3i', d, p), np.float64) / 4096.0
        p += 12
    R = np.eye(3)
    if not flag & 2:
        if flag & 8:                          # pivot form: one axis +-1, a and b for the other four
            a, b = (x / 4096.0 for x in struct.unpack_from('<2h', d, p))
            p += 4
            pv = (flag >> 4) & 0xF
            neg = (flag >> 8) & 0xF
            one = -1.0 if neg & 1 else 1.0
            c = -b if neg & 2 else b
            dd = -a if neg & 4 else a
            M = np.zeros(9)
            M[pv] = one
            row, col = pv // 3, pv % 3
            rest = [i for i in range(9) if i // 3 != row and i % 3 != col]
            M[rest[0]], M[rest[1]], M[rest[2]], M[rest[3]] = a, b, c, dd
            R = M.reshape(3, 3)
        else:
            m = (m0,) + struct.unpack_from('<8h', d, p)
            p += 16
            R = np.array(m, np.float64).reshape(3, 3) / 4096.0
    S = np.ones(3)
    if not flag & 4:
        S = np.array(struct.unpack_from('<3i', d, p), np.float64) / 4096.0
        p += 12
    M = np.eye(4)
    M[:3, :3] = np.diag(S) @ R
    M[3, :3] = T
    return M


def _bgr(c):
    r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


class Tex0:
    def __init__(self, d, o):
        self.d, self.o = d, o
        tsize, tinfo = struct.unpack_from('<HH', d, o + 0xC)
        self.tdata = o + struct.unpack_from('<I', d, o + 0x14)[0]
        csize, cinfo = struct.unpack_from('<HH', d, o + 0x1C)
        self.cdata = o + struct.unpack_from('<I', d, o + 0x24)[0]
        self.cidx = o + struct.unpack_from('<I', d, o + 0x28)[0]
        self.pdict = o + struct.unpack_from('<I', d, o + 0x34)[0]
        self.pdata = o + struct.unpack_from('<I', d, o + 0x38)[0]
        self.textures = {n: struct.unpack_from('<2I', v) for n, v in _dict(d, o + tinfo) if len(v) >= 8}
        self.palettes = {n: struct.unpack_from('<H', v)[0] * 8 for n, v in _dict(d, self.pdict) if len(v) >= 2}

    def image(self, tname, pname):
        import numpy as np
        d = self.d
        param, _ = self.textures[tname]
        w, h = 8 << ((param >> 20) & 7), 8 << ((param >> 23) & 7)
        fmt, zero = (param >> 26) & 7, (param >> 29) & 1
        off = (param & 0xFFFF) * 8
        pal_off = self.pdata + self.palettes.get(pname, 0)
        def P(n):                                # palettes may hold fewer colours than the format allows
            n = max(0, min(n, (len(d) - pal_off) // 2))
            got = [_bgr(c) for c in struct.unpack_from('<%dH' % n, d, pal_off)]
            return got + [(255, 0, 255)] * (max(n, 1) - len(got)) if got else [(255, 0, 255)]
        out = np.zeros((h, w, 4), np.uint8)
        if fmt in (2, 3, 4):
            bits = {2: 2, 3: 4, 4: 8}[fmt]
            idx = np.frombuffer(d[self.tdata + off:self.tdata + off + w * h * bits // 8], np.uint8)
            if bits < 8:
                idx = np.stack([(idx >> (bits * k)) & ((1 << bits) - 1) for k in range(8 // bits)], 1).reshape(-1)
            idx = idx[:w * h].reshape(h, w)
            pal = P(1 << bits)
            pal += [(255, 0, 255)] * ((1 << bits) - len(pal))
            out = np.array([c + (255,) for c in pal], np.uint8)[idx]
            if zero:
                out[idx == 0, 3] = 0
        elif fmt in (1, 6):
            ib, ab = (5, 3) if fmt == 1 else (3, 5)
            v = np.frombuffer(d[self.tdata + off:self.tdata + off + w * h], np.uint8).reshape(h, w)
            pal = np.array(P(1 << ib), np.uint8)
            out[..., :3] = pal[v & ((1 << ib) - 1)]
            out[..., 3] = ((v >> ib) * 255 // ((1 << ab) - 1)).astype(np.uint8)
        elif fmt == 7:
            v = np.frombuffer(d[self.tdata + off:self.tdata + off + 2 * w * h], '<u2').reshape(h, w)
            for k, sh in enumerate((0, 5, 10)):
                c = (v >> sh) & 31
                out[..., k] = (c << 3 | c >> 2)
            out[..., 3] = np.where(v >> 15, 255, 0)
        elif fmt == 5:                          # 4x4 compressed: 2-bit texels, a palette mode per block
            blocks = (w // 4) * (h // 4)
            tex = struct.unpack_from('<%dI' % blocks, d, self.cdata + off)
            ext = struct.unpack_from('<%dH' % blocks, d, self.cidx + off // 2)
            for k in range(blocks):
                bx, by = (k % (w // 4)) * 4, (k // (w // 4)) * 4
                e = ext[k]
                po, mode = (e & 0x3FFF) * 4, e >> 14
                c = [_bgr(x) for x in struct.unpack_from('<4H', d, pal_off + po)]
                if mode == 0:
                    cols = [c[0] + (255,), c[1] + (255,), c[2] + (255,), (0, 0, 0, 0)]
                elif mode == 1:
                    mid = tuple((a + b) // 2 for a, b in zip(c[0], c[1]))
                    cols = [c[0] + (255,), c[1] + (255,), mid + (255,), (0, 0, 0, 0)]
                elif mode == 2:
                    cols = [x + (255,) for x in c]
                else:
                    m1 = tuple((5 * a + 3 * b) // 8 for a, b in zip(c[0], c[1]))
                    m2 = tuple((3 * a + 5 * b) // 8 for a, b in zip(c[0], c[1]))
                    cols = [c[0] + (255,), c[1] + (255,), m1 + (255,), m2 + (255,)]
                t = tex[k]
                for yy in range(4):
                    for xx in range(4):
                        out[by + yy, bx + xx] = cols[(t >> (2 * (4 * yy + xx))) & 3]
        else:
            raise ValueError('texture %s: format %d' % (tname, fmt))
        return out


def _splice_textures(d, extra):
    """Many models keep TEX0's texels and palettes in the next rom.bin asset (colours, then texels), with
    zeros in the model file. Copy them in when the sizes match."""
    nblk = struct.unpack_from('<H', d, 0xE)[0]
    for o in struct.unpack_from('<%dI' % nblk, d, 0x10):
        if d[o:o + 4] != b'TEX0':
            continue
        tsize = struct.unpack_from('<H', d, o + 0xC)[0] * 8
        tdata = o + struct.unpack_from('<I', d, o + 0x14)[0]
        psize = struct.unpack_from('<I', d, o + 0x30)[0] * 8
        pdata = o + struct.unpack_from('<I', d, o + 0x38)[0]
        if not extra or any(d[tdata:tdata + tsize]) or len(extra) < tsize + psize:
            return d
        b = bytearray(d)
        b[pdata:pdata + psize] = extra[:psize]          # colours first, then the texels
        b[tdata:tdata + tsize] = extra[psize:psize + tsize]
        return bytes(b)
    return d


def model(d, extra=None):
    """A BMD0 file -> (name, parts) with parts = [(tris [N,3,10], texture RGBA or None, (r, g, b))] in model
    units, UVs 0..1. Uses the first model in MDL0."""
    import numpy as np
    from urbz_fullfat import gx_run
    if d[:4] != b'BMD0':
        raise ValueError('not a BMD0 file')
    d = _splice_textures(d, extra)
    nblk = struct.unpack_from('<H', d, 0xE)[0]
    offs = struct.unpack_from('<%dI' % nblk, d, 0x10)
    mdl = next(o for o in offs if d[o:o + 4] == b'MDL0')
    tex0 = None
    for o in offs:
        if d[o:o + 4] == b'TEX0':
            try:
                tex0 = Tex0(d, o)
            except (struct.error, IndexError):
                tex0 = None
    (mname, mdata), = _dict(d, mdl + 8)[:1]
    m = mdl + struct.unpack_from('<I', mdata)[0]
    sbc, mats_o, polys_o = (m + x for x in struct.unpack_from('<3I', d, m + 4))
    up = _fx(struct.unpack_from('<i', d, m + 0x1C)[0])
    nodes = [m + 0x40 + struct.unpack_from('<I', v)[0] for _n, v in _dict(d, m + 0x40)]
    tdict_o, pdict_o = struct.unpack_from('<HH', d, mats_o)
    mats = []
    for _n, v in _dict(d, mats_o + 4):
        mo = mats_o + struct.unpack_from('<I', v)[0]
        dif = struct.unpack_from('<I', d, mo + 4)[0]
        mats.append({'colour': _bgr(dif & 0x7FFF), 'tex': None, 'pal': None})
    for key, o in (('tex', tdict_o), ('pal', pdict_o)):
        if not o:
            continue
        for name, v in _dict(d, mats_o + o):
            lo, num = struct.unpack_from('<HB', v)
            for mid in d[mats_o + lo:mats_o + lo + num]:
                if mid < len(mats):
                    mats[mid][key] = name
    polys = []
    for _n, v in _dict(d, polys_o):
        po = polys_o + struct.unpack_from('<I', v)[0]
        dl_off, dl_size = struct.unpack_from('<2I', d, po + 8)
        polys.append((po + dl_off, dl_size))
    stack = [np.eye(4) for _ in range(32)]
    cur = np.eye(4)
    mat = None
    parts, cache = [], {}
    p = sbc
    while p < polys_o:
        op = d[p]
        c, var = op & 0x1F, op >> 5
        if c == 0x01:
            break
        if c == 0x00:
            p += 1
        elif c == 0x02:
            p += 3
        elif c == 0x03:
            cur = stack[d[p + 1] & 31].copy()
            p += 2
        elif c == 0x04:
            mat = d[p + 1]
            p += 2
        elif c == 0x05:
            o, n = polys[d[p + 1]]
            mt = mats[mat] if mat is not None and mat < len(mats) else {'colour': (200, 200, 200), 'tex': None}
            tex = None
            if tex0 and mt.get('tex') in tex0.textures:
                key = (mt['tex'], mt.get('pal'))
                if key not in cache:
                    try:
                        cache[key] = tex0.image(*key)
                    except (ValueError, struct.error, KeyError):
                        cache[key] = None
                tex = cache[key]
            M = cur.T.copy()                    # gx_run uses column vectors
            for s in gx_run(d, o, o + n, init=M, stack=[x.T.copy() for x in stack]):
                a = np.array(s['tris'], np.float64).reshape(-1, 3, 10)
                if not len(a):
                    continue
                a[..., :3] *= up
                if tex is not None:
                    a[..., 3] /= tex.shape[1]
                    a[..., 4] /= tex.shape[0]
                parts.append((a, tex, (255, 255, 255) if tex is not None else mt['colour']))
            p += 2
        elif c == 0x06:
            node, parent, _flags = d[p + 1], d[p + 2], d[p + 3]
            extra = {0: 0, 1: 1, 2: 1, 3: 2}[var]
            if var in (2, 3):                   # restore first
                cur = stack[d[p + 4 + (1 if var == 3 else 0)] & 31].copy()
            if node < len(nodes):
                cur = _node_matrix(d, nodes[node]) @ cur
            if var in (1, 3):
                stack[d[p + 4] & 31] = cur.copy()
            p += 4 + extra
        elif c in (0x07, 0x08):
            p += 2 + {0: 0, 1: 1, 2: 1, 3: 2}[var]
        elif c == 0x09:                          # NODEMIX: skinning; keep the bind pose
            n = d[p + 2]
            stack[d[p + 1] & 31] = cur.copy()
            p += 3 + 3 * n
        elif c == 0x0A:
            p += 9
        elif c == 0x0B:
            p += 1
        elif c == 0x0C:
            p += 3
        elif c == 0x0D:
            p += 3
        else:
            break
    return mname, parts


class Game:
    """The Sims 2 (DS): every BMD0 model inside rom.bin, named by its model name."""
    id = 'sims2'

    def __init__(self, rom_path):
        import ndspy.rom
        from urbz_extract import split_rombin
        from scan_chunks import asset_chunks
        rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
        entries = split_rombin(bytes(rom.getFileByName('rom.bin')))
        self._models, seen = [], {}
        for i, e in enumerate(entries):
            try:
                chunks = asset_chunks(e)
            except Exception:
                continue
            for ch in chunks or []:
                out = ch[-1]
                if out[:4] == b'BMD0':
                    name = out[0x38 + 0:0x48].split(b'\0')[0].decode('latin-1') or 'model%d' % i
                    try:
                        mdl = next(o for o in struct.unpack_from('<%dI' % struct.unpack_from('<H', out, 0xE)[0], out, 0x10)
                                   if out[o:o + 4] == b'MDL0')
                        name = _dict(out, mdl + 8)[0][0] or name
                    except (StopIteration, struct.error, IndexError):
                        pass
                    seen[name] = seen.get(name, 0) + 1
                    if seen[name] > 1:
                        name = '%s%d' % (name, seen[name])
                    extra = None                # the texels may be in the next asset
                    if i + 1 < len(entries):
                        try:
                            nxt = asset_chunks(entries[i + 1])
                            extra = bytes(nxt[0][-1]) if nxt else None
                        except Exception:
                            extra = None
                    self._models.append({'name': name, 'kind': 'object', 'folder': 'rom.bin/%05d' % i,
                                         'bmd': bytes(out), 'extra': extra, 'anims': {}})
                    break

    def models(self):
        return self._models


def main(argv):
    if len(argv) < 2 or argv[0] != 'models':
        print(__doc__)
        return
    for m in Game(argv[1]).models():
        print('%-24s %s' % (m['name'], m['folder']))


if __name__ == '__main__':
    main(sys.argv[1:])
