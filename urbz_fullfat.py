#!/usr/bin/env python3
"""Read 3D art from Full Fat's Sims DS games: The Sims 2: Apartment Pets and The Sims 2: Castaway.

Read-only: the ROMs stay where they are and nothing from them goes into git. urbz_import.py renders
what this reads into Urbz-style sprites.

Formats (worked out 2026-10-05; details in docs/other-games.md):
  NTRO     every file is an 'NTRO' container: u32 'NTRO', u32 size, u32 block count, then blocks
           {u32 type, u32 size, u32 offset}. Archives (*.nitro_archive) are NTRO files whose blocks are a
           record table {u32 name hash, u32 group hash, u32 offset, u32 size, 0}, the data, and (Apartment
           Pets) a names block of 128-byte slots, one per record.
  texture  blocks {1: u32 TEXIMAGE_PARAM, u32 hash, char name[], 3: palette (BGR555), 2: texels}; DS texture
           formats 2/3/4 (4/16/256 colours), 1/6 (A3I5/A5I3 translucent), 7 (direct colour).
  mesh     blocks {0xB: header + name, 0xC: a GX display list (the DS 3D engine's own commands),
           0xE: materials 13 words each (+8 DIF_AMB, +11 texture hash), 0x10: bone slots
           {LOAD_4x4 offset, MULT_4x3 offset, SCALE offset, bone}}. Vertices are stored in the bind pose;
           the game writes a skin matrix per bone into each slot's MULT_4x3.
  skeleton blocks {0x11: bone count, 0x12: bones of 88 bytes {s32 parent, s32, 4x4 fx12 inverse bind
           matrix (row vectors), char name[16]}}.
  anim     blocks {0x13: {frames, bones, fps, 0}, 0x14: per bone {first rotation key, first position key, 0},
           0x15: rotation keys {u32 frame, s16 x, y, z, w quaternion fx12}, 0x16: position keys
           {u32 frame, s32 x, y, z fx12}}.

  python urbz_fullfat.py list ROM [filter]     every file in the game's archives
  python urbz_fullfat.py models ROM            the renderable models (pets, objects, accessories)
"""
import os, struct, sys

GAMES = {'CAPE': 'aptpets', 'YS2E': 'castaway'}
# object script keys (hashes of property names; meanings found by comparing objects of known size)
OFFSET_X, OFFSET_Y, OFFSET_Z = 0x4CD76E93, 0x8706EE93, 0xC1366E93
SIZE_X, SIZE_Y, SIZE_Z = 0x4C23274D, 0x8652A74D, 0xC082274D       # bounding box, metres (fx12)
TILES_X, TILES_Z = 0xB0CAD4EF, 0xB1DD53BD


# ------------------------------------------------------------------ containers

def blocks(d):
    if d[:4] != b'NTRO':
        raise ValueError('not an NTRO file')
    n = struct.unpack_from('<I', d, 8)[0]
    return {t: (o, s) for t, s, o in (struct.unpack_from('<3I', d, 12 + 12 * i) for i in range(n))}


def block(d, t):
    o, s = blocks(d)[t]
    return d[o:o + s]


class Archive:
    """One *.nitro_archive."""

    def __init__(self, data, label=''):
        if data[:4] != b'NTRO':
            raise ValueError('%s: not an NTRO archive' % label)
        self.label = label
        n = struct.unpack_from('<I', data, 0x3C)[0]
        self.records = [struct.unpack_from('<5I', data, 0x40 + 20 * i) for i in range(n)]
        base = 0x40 + 20 * n
        end = base + (max(r[2] + r[3] for r in self.records) if n else 0)
        names = [None] * n
        if len(data) - end == 128 * n:
            for i in range(n):
                names[i] = data[end + 128 * i:end + 128 * i + 128].split(b'\0')[0].decode('latin-1')
        self.files = []
        for i, (h, g, off, size, _) in enumerate(self.records):
            d = data[base + off:base + off + size]
            self.files.append({'name': names[i] or _inner_name(d) or '%08x' % h, 'hash': h, 'data': d,
                               'archive': label})


def _inner_name(d):
    """Files carry their own name inside (mesh header, texture params): used when the archive has none."""
    try:
        B = blocks(d)
    except ValueError:
        return None
    for t, at in ((0xB, 0x30), (1, 8)):
        if t in B:
            o, s = B[t]
            raw = d[o + at:o + s].split(b'\0')[0]
            if len(raw) > 3 and all(32 <= c < 127 for c in raw):
                return raw.decode('latin-1')
    return None


class Game:
    """All archives of one Full Fat Sims DS ROM, indexed by name and texture hash."""

    def __init__(self, rom_path):
        import ndspy.rom
        rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
        code = bytes(rom.idCode).decode('latin-1')
        self.id = GAMES.get(code, code)
        self.files, self.by_name, self.textures = [], {}, {}
        for fid, data in enumerate(rom.files):
            name = rom.filenames.filenameOf(fid) or ''
            if not name.endswith('.nitro_archive'):
                continue
            a = Archive(bytes(data), os.path.basename(name))
            for f in a.files:
                self.files.append(f)
                self.by_name.setdefault(f['name'], f)
                if f['name'].endswith('nitro_texture') or 'texture' in f['name']:
                    try:
                        p = block(f['data'], 1)
                        self.textures.setdefault(struct.unpack_from('<I', p, 4)[0], f)
                    except (ValueError, KeyError, struct.error):
                        pass

    def definition(self, folder):
        """An object's script (object_definitions archive) as {key hash: s32}. Known keys: SIZE_X/Y/Z
        (metres, fx12), OFFSET_X/Y/Z, TILES_X/Z."""
        try:
            d = self.find(folder + '/script.object.nitro_script')['data']
            raw = block(d, 0x403)
        except (KeyError, ValueError):
            return {}
        w = struct.unpack_from('<%di' % (len(raw) // 4), raw)
        return {w[i] & 0xFFFFFFFF: w[i + 1] for i in range(0, len(w) - 1, 2)}

    def find(self, suffix):
        for f in self.files:
            if f['name'] == suffix or f['name'].endswith(suffix):
                return f
        raise KeyError(suffix)

    def models(self):
        """[{'name', 'kind': pet|object|accessory, 'mesh', 'skeleton', 'anims': {name: file}}]"""
        out = []
        meshes = [f for f in self.files if f['name'].endswith('nitro_mesh') and '/lots/' not in f['name']
                  and '/debug/' not in f['name']]
        folders = {}
        for f in meshes:
            folders.setdefault(os.path.dirname(f['name']), []).append(f)
        anims = [f for f in self.files if '.anim' in f['name'] and f['name'].endswith('nitro_animation')]
        skels = {os.path.dirname(f['name']): f for f in self.files if f['name'].endswith('nitro_skeleton')
                 and 'lod' not in f['name'].lower()}
        for folder, fs in sorted(folders.items()):
            low = folder.lower()
            if '/lod' in low or low.endswith('lod'):
                continue
            if '/pets/' in low and '/accessories/' not in low and '/objects/' not in low:
                kind = 'pet'
            elif '/accessories/' in low:
                kind = 'accessory'
            elif '/objects/' in low:
                kind = 'object'
            else:
                kind = 'other'
            if kind == 'object':
                best = [f for f in fs if os.path.basename(f['name']).startswith(('object_mesh', 'mesh.'))] or \
                       [f for f in fs if '_low' not in f['name']] or fs
                picks = best[:1]
            else:
                picks = [f for f in fs if 'lod' not in os.path.basename(f['name']).lower()]
            for m in picks:
                base = os.path.basename(m['name']).split('.')[0]
                nm = os.path.basename(folder) if kind == 'object' else base
                a = {os.path.basename(x['name']).split('.')[0]: x for x in anims
                     if os.path.dirname(os.path.dirname(x['name'])) == folder
                     or os.path.dirname(x['name']) == folder}
                out.append({'name': nm, 'kind': kind, 'folder': folder, 'mesh': m,
                            'skeleton': skels.get(folder), 'anims': a})
        return out


# ------------------------------------------------------------------ textures

def _bgr(c):
    r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


def texture(d):
    """-> (RGBA array [h, w, 4], TEXIMAGE_PARAM, name, translucent?)"""
    import numpy as np
    B = blocks(d)
    p = d[B[1][0]:B[1][0] + B[1][1]]
    param = struct.unpack_from('<I', p, 0)[0]
    name = p[8:].split(b'\0')[0].decode('latin-1')
    w, h = 8 << ((param >> 20) & 7), 8 << ((param >> 23) & 7)
    fmt, zero_clear = (param >> 26) & 7, (param >> 29) & 1
    pal = d[B[3][0]:B[3][0] + B[3][1]] if 3 in B else b''
    P = [_bgr(v) for v in struct.unpack_from('<%dH' % (len(pal) // 2), pal)]
    px = d[B[2][0]:B[2][0] + B[2][1]]
    out = np.zeros((h, w, 4), np.uint8)
    if fmt in (2, 3, 4):
        bits = {2: 2, 3: 4, 4: 8}[fmt]
        idx = np.frombuffer(px, np.uint8)
        if bits < 8:
            idx = np.stack([(idx >> (bits * k)) & ((1 << bits) - 1) for k in range(8 // bits)], 1).reshape(-1)
        idx = idx[:w * h].reshape(h, w)
        lut = np.array([P[i] + (255,) if i < len(P) else (255, 0, 255, 255) for i in range(1 << bits)], np.uint8)
        out = lut[idx]
        if zero_clear:
            out[idx == 0, 3] = 0
    elif fmt in (1, 6):
        ib, ab = (5, 3) if fmt == 1 else (3, 5)
        v = np.frombuffer(px, np.uint8)[:w * h].reshape(h, w)
        lut = np.array([P[k] if k < len(P) else (255, 0, 255) for k in range(1 << ib)], np.uint8)
        out[..., :3] = lut[v & ((1 << ib) - 1)]
        out[..., 3] = ((v >> ib) * 255 // ((1 << ab) - 1)).astype(np.uint8)
    elif fmt == 7:
        v = np.frombuffer(px, '<u2')[:w * h].reshape(h, w)
        for k, sh in enumerate((0, 5, 10)):
            c = (v >> sh) & 31
            out[..., k] = (c << 3 | c >> 2)
        out[..., 3] = np.where(v >> 15, 255, 0)
    else:
        raise ValueError('texture %s: format %d (4x4 compressed) is not decoded' % (name, fmt))
    return out, param, name, fmt in (1, 6)


# ------------------------------------------------------------------ GX display lists

NPARAMS = {0x00: 0, 0x10: 1, 0x11: 0, 0x12: 1, 0x13: 1, 0x14: 1, 0x15: 0, 0x16: 16, 0x17: 12, 0x18: 16,
           0x19: 12, 0x1A: 9, 0x1B: 3, 0x1C: 3, 0x20: 1, 0x21: 1, 0x22: 1, 0x23: 2, 0x24: 1, 0x25: 1,
           0x26: 1, 0x27: 1, 0x28: 1, 0x29: 1, 0x2A: 1, 0x2B: 1, 0x30: 1, 0x31: 1, 0x32: 1, 0x33: 1,
           0x34: 32, 0x40: 1, 0x41: 0, 0x50: 1, 0x60: 1, 0x70: 3, 0x71: 2, 0x72: 1}


def gx_commands(data, off=0, end=None):
    """Yield (command, params, byte offset of the params) from a packed GX command stream."""
    end = len(data) if end is None else end
    p = off
    while p + 4 <= end:
        hdr = struct.unpack_from('<I', data, p)[0]
        p += 4
        for k in range(4):
            c = (hdr >> (8 * k)) & 0xFF
            n = NPARAMS.get(c)
            if n is None:
                raise ValueError('unknown GX command %02x at %x' % (c, p - 4))
            params = list(struct.unpack_from('<%dI' % n, data, p)) if n else []
            at = p
            p += 4 * n
            yield c, params, at
            if p > end:
                return


def _s(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _fx(v, bits, frac):
    return _s(v, bits) / float(1 << frac)


def gx_run(data, off, end, tags=None, init=None, stack=None):
    """Execute a display list with the matrices as stored (the bind pose). -> submeshes, one per
    BEGIN_VTXS: {'tris': [(v, v, v)], 'polyattr', 'tex'} with v = (x, y, z, s, t, nx, ny, nz, colour, bone)."""
    import numpy as np
    I = np.eye(4)
    cur = {'pos': I.copy() if init is None else init.copy(), 'proj': I.copy(), 'tex': I.copy()}
    mode = [2]
    stack = stack if stack is not None else [I.copy() for _ in range(32)]
    tstack, sp, tag = [-1] * 32, [0], [-1]
    tags = tags or {}
    st = {'v': [0.0, 0.0, 0.0], 'uv': (0.0, 0.0), 'n': (0.0, 0.0, 1.0), 'c': 0x7FFF}
    subs, verts = [], []
    m = {'tris': [], 'prim': 0, 'polyattr': 0, 'tex': 0}

    def key():
        return ('proj', 'pos', 'pos', 'tex')[mode[0]]

    def emit():
        x, y, z = st['v']
        q = cur['pos'] @ np.array([x, y, z, 1.0])
        verts.append((q[0], q[1], q[2], st['uv'][0], st['uv'][1]) + tuple(st['n']) + (st['c'], tag[0]))
        prim, k = m['prim'], len(verts)
        if prim == 0 and k % 3 == 0:
            m['tris'].append(tuple(verts[-3:]))
        elif prim == 1 and k % 4 == 0:
            a, b, c, d = verts[-4:]
            m['tris'] += [(a, b, c), (a, c, d)]
        elif prim == 2 and k >= 3:
            a, b, c = verts[-3:]
            m['tris'].append((a, b, c) if k % 2 else (b, a, c))
        elif prim == 3 and k >= 4 and k % 2 == 0:
            a, b, c, d = verts[-4:]
            m['tris'] += [(a, b, d), (a, d, c)]

    for c, p, at in gx_commands(data, off, end):
        K = key()
        if c == 0x10:
            mode[0] = p[0] & 3
        elif c == 0x11:
            stack[sp[0] & 31], tstack[sp[0] & 31] = cur[K].copy(), tag[0]
            sp[0] += 1
        elif c == 0x12:
            sp[0] -= _s(p[0], 6)
            cur[K], tag[0] = stack[sp[0] & 31].copy(), tstack[sp[0] & 31]
        elif c == 0x13:
            stack[p[0] & 31], tstack[p[0] & 31] = cur[K].copy(), tag[0]
        elif c == 0x14:
            cur[K], tag[0] = stack[p[0] & 31].copy(), tstack[p[0] & 31]
        elif c == 0x15:
            cur[K] = I.copy()
        elif c in (0x16, 0x17, 0x18, 0x19, 0x1A):
            v = [_fx(x, 32, 12) for x in p]
            if c in (0x16, 0x18):
                M = np.array(v).reshape(4, 4).T
            elif c in (0x17, 0x19):
                M = np.eye(4)
                M[:3, :4] = np.array(v).reshape(4, 3).T
            else:
                M = np.eye(4)
                M[:3, :3] = np.array(v).reshape(3, 3).T
            cur[K] = M if c in (0x16, 0x17) else cur[K] @ M
            if c == 0x16 and (at - off) in tags:
                tag[0] = tags[at - off]
        elif c == 0x1B:
            cur[K] = cur[K] @ np.diag([_fx(p[0], 32, 12), _fx(p[1], 32, 12), _fx(p[2], 32, 12), 1.0])
        elif c == 0x1C:
            T = np.eye(4)
            T[:3, 3] = [_fx(x, 32, 12) for x in p]
            cur[K] = cur[K] @ T
        elif c == 0x20:
            st['c'] = p[0] & 0x7FFF
        elif c == 0x21:
            st['n'] = (_fx(p[0], 10, 9), _fx(p[0] >> 10, 10, 9), _fx(p[0] >> 20, 10, 9))
        elif c == 0x22:
            st['uv'] = (_fx(p[0], 16, 4), _fx(p[0] >> 16, 16, 4))
        elif c == 0x23:
            st['v'] = [_fx(p[0], 16, 12), _fx(p[0] >> 16, 16, 12), _fx(p[1], 16, 12)]
            emit()
        elif c == 0x24:
            st['v'] = [_fx(p[0], 10, 6), _fx(p[0] >> 10, 10, 6), _fx(p[0] >> 20, 10, 6)]
            emit()
        elif c == 0x25:
            st['v'][0], st['v'][1] = _fx(p[0], 16, 12), _fx(p[0] >> 16, 16, 12)
            emit()
        elif c == 0x26:
            st['v'][0], st['v'][2] = _fx(p[0], 16, 12), _fx(p[0] >> 16, 16, 12)
            emit()
        elif c == 0x27:
            st['v'][1], st['v'][2] = _fx(p[0], 16, 12), _fx(p[0] >> 16, 16, 12)
            emit()
        elif c == 0x28:
            st['v'] = [st['v'][0] + _fx(p[0], 10, 12), st['v'][1] + _fx(p[0] >> 10, 10, 12),
                       st['v'][2] + _fx(p[0] >> 20, 10, 12)]
            emit()
        elif c == 0x29:
            m['polyattr'] = p[0]
        elif c == 0x2A:
            m['tex'] = p[0]
        elif c == 0x40:
            m = {'tris': [], 'prim': p[0] & 3, 'polyattr': m['polyattr'], 'tex': m['tex'], 'at': at - off}
            verts = []
            subs.append(m)
    return subs


# ------------------------------------------------------------------ meshes, skeletons, animations

def mesh(d):
    """-> [{'tris': array [N, 3, 10], 'texture': hash or 0, 'colour': (r, g, b), 'alpha': 0-31}]"""
    import numpy as np
    B = blocks(d)
    o, s = B[0xC]
    tags = {}
    if 0x10 in B:
        bo, bs = B[0x10]
        for i in range(bs // 16):
            lo, _mo, _so, bone = struct.unpack_from('<4I', d, bo + 16 * i)
            tags[lo] = bone
    subs = gx_run(d, o, o + s, tags)
    mats = []
    if 0xE in B:
        eo, es = B[0xE]
        w = struct.unpack_from('<%dI' % (es // 4), d, eo)
        mats = [w[13 * i:13 * i + 13] for i in range(es // 52)]
    # A material's words 1-7 are the display-list offsets of the commands it sets (colours, polygon
    # attributes, texture): it applies to every BEGIN_VTXS after them, until the next material.
    starts = [min(x for x in mt[1:8] if x) if any(mt[1:8]) else 0 for mt in mats]
    out = []
    for i, m in enumerate(subs):
        a = np.array(m['tris'], np.float64).reshape(-1, 3, 10)
        a[..., 3:5] /= 128.0                    # display lists address a 128x128 texture space
        before = [k for k, st0 in enumerate(starts) if st0 <= m['at']]
        mat = mats[before[-1]] if before else (mats[i] if i < len(mats) else None)
        dif = (mat[8] if mat else 0x7FFF) & 0x7FFF
        pa = mat[10] if mat else m['polyattr']
        out.append({'tris': a, 'texture': mat[11] if mat else 0, 'colour': _bgr(dif),
                    'alpha': (pa >> 16) & 31})
    return out


def skeleton(d):
    import numpy as np
    o, s = blocks(d)[0x12]
    bones = []
    for i in range(s // 88):
        r = o + 88 * i
        w = struct.unpack_from('<18i', d, r)
        bones.append({'parent': w[0], 'invbind': np.array(w[2:18], np.float64).reshape(4, 4) / 4096.0,
                      'name': d[r + 72:r + 88].split(b'\0')[0].decode('latin-1')})
    return bones


def animation(d):
    B = blocks(d)
    frames, nb, fps, _ = struct.unpack_from('<4i', d, B[0x13][0])
    o14, s14 = B[0x14]
    idx = [struct.unpack_from('<3i', d, o14 + 12 * i) for i in range(s14 // 12)]
    o15, s15 = B[0x15]
    rk = [(struct.unpack_from('<I', d, o15 + 12 * i)[0],) + struct.unpack_from('<4h', d, o15 + 12 * i + 4)
          for i in range(s15 // 12)]
    o16, s16 = B[0x16]
    pk = [struct.unpack_from('<I3i', d, o16 + 16 * i) for i in range(s16 // 16)]
    tracks = []
    for b in range(nb):
        r0, p0 = idx[b][0], idx[b][1]
        r1 = idx[b + 1][0] if b + 1 < nb else len(rk)
        p1 = idx[b + 1][1] if b + 1 < nb else len(pk)
        tracks.append({'rot': rk[r0:r1], 'pos': pk[p0:p1]})
    return {'frames': frames, 'fps': fps, 'tracks': tracks}


def _quat(x, y, z, w):
    import numpy as np
    n = (x * x + y * y + z * z + w * w) ** 0.5 or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)],
                     [2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)],
                     [2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)]])


def _key(keys, f, n):
    import numpy as np
    if len(keys) == 1:
        return np.array(keys[0][1:1 + n], np.float64)
    before = [k for k in keys if k[0] <= f] or keys[:1]
    after = [k for k in keys if k[0] >= f] or keys[-1:]
    a, b = before[-1], after[0]
    va, vb = np.array(a[1:1 + n], np.float64), np.array(b[1:1 + n], np.float64)
    if b[0] == a[0]:
        return va
    t = (f - a[0]) / float(b[0] - a[0])
    if n == 4 and va @ vb < 0:
        vb = -vb
    return va + (vb - va) * t


def pose(bones, anim, f, keep_root=False):
    """World matrices of every bone at frame f (row vectors). Root motion is removed unless keep_root."""
    import numpy as np
    W = []
    for b, bone in enumerate(bones):
        tr = anim['tracks'][b] if b < len(anim['tracks']) else {'rot': [(0, 0, 0, 0, 4096)], 'pos': [(0, 0, 0, 0)]}
        q = _key(tr['rot'], f, 4) / 4096.0
        t = _key(tr['pos'], f, 3) / 4096.0
        if b == 0 and not keep_root:
            t = _key(tr['pos'], 0, 3) / 4096.0
        L = np.eye(4)
        L[:3, :3] = _quat(*q)
        L[3, :3] = t
        W.append(L @ W[bone['parent']] if bone['parent'] >= 0 else L)
    return W


def skin(tris, bones, world):
    """Pose vertices: v' = v @ invbind[bone] @ world[bone]."""
    import numpy as np
    t = tris.copy()
    if not bones or world is None:
        return t
    K = np.array([b['invbind'] @ W for b, W in zip(bones, world)])
    flat = t.reshape(-1, 10)
    b = flat[:, 9].astype(int)
    ok = (b >= 0) & (b < len(K))
    P = np.concatenate([flat[:, :3], np.ones((len(flat), 1))], 1)
    flat[ok, :3] = np.einsum('ni,nij->nj', P[ok], K[b[ok]])[:, :3]
    flat[ok, 5:8] = np.einsum('ni,nij->nj', flat[ok, 5:8], K[b[ok]][:, :3, :3])
    return flat.reshape(t.shape)


# ------------------------------------------------------------------ command line

def main(argv):
    if len(argv) < 2 or argv[0] not in ('list', 'models'):
        print(__doc__)
        return
    g = Game(argv[1])
    if argv[0] == 'list':
        flt = argv[2] if len(argv) > 2 else ''
        for f in g.files:
            if flt in f['name']:
                print('%-28s %8d  %s' % (f['archive'], len(f['data']), f['name']))
    else:
        for m in g.models():
            print('%-9s %-28s anims %3d  %s' % (m['kind'], m['name'], len(m['anims']), m['folder']))


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except BrokenPipeError:
        pass
