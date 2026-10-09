#!/usr/bin/env python3
"""Borrowed poses: the townspeople's missing animations (sit, eat, toilet, shower, sleep), made from someone
who has them, in the person's own colours and with their own head.

Most townspeople only have stand, walk and a few gestures: their art is pre-rendered 3D, so their own frames
can't be bent into new poses. Each missing animation is taken from the closest-looking person who has it (the
"donor": similar height and build), scaled to the person's height, recoloured colour by colour (each donor
colour goes to the person's colour that plays the same part: same height on the body, similar brightness),
and the donor's head is swapped for the person's own (the top of the figure in each frame; lying down, the
donor's head stays, recoloured).

  python urbz_poses.py preview <out_dir> [person ...] [--group sit]   contact sheets to look at
  (the build does the rest: a mod with "poses.json" gets a generated mod build/new-poses; the sets are
  kept in build/cache/poses, so only the first build takes long)

The frames come from the game's art: they are made at build time from your extracted game, never committed.
"""
import json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import urbz_anims as A

HEAD = 0.17                      # the top of a standing person that is their head (fraction of their height)


# ------------------------------------------------------------------ index images

def _np():
    import numpy as np
    return np


def to_index(img, pal):
    """RGBA canvas -> palette index array (0 = see-through)."""
    np = _np()
    a = np.asarray(img.convert('RGBA'), dtype=np.int32)
    out = np.zeros(a.shape[:2], dtype=np.int16)
    lut = {}
    for i, c in enumerate(pal):
        if i and tuple(c[:3]) not in lut:
            lut[tuple(c[:3])] = i
    rgb = (a[:, :, 0] << 16) | (a[:, :, 1] << 8) | a[:, :, 2]
    for c, i in lut.items():
        out[(rgb == ((c[0] << 16) | (c[1] << 8) | c[2])) & (a[:, :, 3] > 0)] = i
    # colours not in the palette (shouldn't happen): nearest by brightness
    rest = (out == 0) & (a[:, :, 3] > 0)
    if rest.any():
        lum = a[:, :, 0] * 3 + a[:, :, 1] * 6 + a[:, :, 2]
        pl = [(c[0] * 3 + c[1] * 6 + c[2], i) for i, c in enumerate(pal) if i]
        for y, x in zip(*rest.nonzero()):
            out[y, x] = min(pl, key=lambda p: abs(p[0] - lum[y, x]))[1]
    return out


def to_rgba(idx, pal):
    from PIL import Image
    np = _np()
    h, w = idx.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for i in range(1, 16):
        m = idx == i
        if m.any():
            out[m] = list(pal[i][:3]) + [255]
    return Image.fromarray(out, 'RGBA')


def bbox(idx):
    np = _np()
    ys, xs = np.nonzero(idx)
    if not len(ys):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def scale_about_feet(idx, s):
    """Nearest-neighbour scale about the feet point (A.ORIGIN)."""
    np = _np()
    if abs(s - 1) < 0.04:
        return idx
    h, w = idx.shape
    ox, oy = A.ORIGIN
    ys, xs = np.mgrid[0:h, 0:w]
    sx = np.round((xs - ox) / s + ox).astype(int)
    sy = np.round((ys - oy) / s + oy).astype(int)
    ok = (sx >= 0) & (sx < w) & (sy >= 0) & (sy < h)
    out = np.zeros_like(idx)
    out[ok] = idx[sy[ok], sx[ok]]
    return out


# ------------------------------------------------------------------ who looks like whom

def standing(cid, view):
    recs, _ = A.row_of(cid, 0x04)
    views = A.views_of(recs)
    gfx, lay = views.get(view, views['front'])
    pal = A.palette16(cid)
    return to_index(A.sheet_frames(gfx, lay, pal)[0], pal), pal


def choose_donor(cid, donors):
    """The donor whose standing silhouette is closest (feet aligned): height, width, overlap."""
    np = _np()
    t, _ = standing(cid, 'front')
    tb = bbox(t)
    best = None
    for d in donors:
        if d == cid:
            continue
        s, _ = standing(d, 'front')
        sb = bbox(s)
        th, sh = tb[3] - tb[1], sb[3] - sb[1]
        ss = scale_about_feet(s, th / sh)
        inter = ((t > 0) & (ss > 0)).sum()
        union = ((t > 0) | (ss > 0)).sum()
        cost = 1 - inter / max(union, 1) + abs((tb[2] - tb[0]) - (sb[2] - sb[0])) / 40
        if best is None or cost < best[0]:
            best = (cost, d)
    return best[1]


BANDS = 8


def _lum(c):
    return c[0] * 3 + c[1] * 6 + c[2]


def band_counts(idx):
    """counts[band][colour] for a standing person (bands from the top of the head to the feet)."""
    np = _np()
    b = bbox(idx)
    h = max(b[3] - b[1], 1)
    counts = np.zeros((BANDS, 16), dtype=int)
    ys, xs = np.nonzero(idx)
    np.add.at(counts, (np.minimum(BANDS - 1, (ys - b[1]) * BANDS // h), idx[ys, xs]), 1)
    counts[:, 0] = 0
    return counts


def _skin(counts, pal):
    """Face colours (skin-like, mostly in the top bands) that also show lower down (hands)."""
    main = counts.argmax(axis=0)
    return sorted((c for c in range(1, 16) if counts[:, c].sum() and main[c] <= 2 and counts[3:BANDS - 1, c].sum()
                   and pal[c][0] >= pal[c][1] >= pal[c][2] and pal[c][0] - pal[c][2] > 35),
                  key=lambda c: _lum(pal[c]))


def colour_map(t_idx, t_pal, d_idx, d_pal):
    """donor index -> the person's index. Each donor colour lives mostly at some height on the body (hair,
    face, shirt, trousers, shoes); it becomes the person's colour at that height at the same brightness
    quantile, counting pixels (a donor's big dark vest becomes the person's big dark jacket, its shadows the
    jacket's shadows). Face skin goes to face skin. Colours a standing donor doesn't show: nearest brightness."""
    tc, dc = band_counts(t_idx), band_counts(d_idx)
    t_skin, d_skin = _skin(tc, t_pal), _skin(dc, d_pal)
    every = [i for i in range(1, 16) if tc[:, i].sum()]
    m = {0: 0}
    for i in range(1, 16):
        if i in d_skin and t_skin:
            r = d_skin.index(i) / max(len(d_skin) - 1, 1)
            m[i] = t_skin[round(r * (len(t_skin) - 1))]
            continue
        if dc[:, i].sum():
            k = int(dc[:, i].argmax())
            dk = sorted((c for c in range(1, 16) if dc[k, c] and c not in d_skin), key=lambda c: _lum(d_pal[c]))
            tk = sorted((c for c in range(1, 16) if tc[k, c] and c not in t_skin), key=lambda c: _lum(t_pal[c]))
            if i in dk and tk:
                tot = sum(dc[k, c] for c in dk)
                q = (sum(dc[k, c] for c in dk[:dk.index(i)]) + dc[k, i] / 2) / tot
                ttot, acc = sum(tc[k, c] for c in tk), 0
                for c in tk:
                    acc += tc[k, c]
                    if acc / ttot >= q:
                        m[i] = c
                        break
                else:
                    m[i] = tk[-1]
                continue
        m[i] = min(every, key=lambda t: abs(_lum(t_pal[t]) - _lum(d_pal[i])))
    return m


def head_size(idx):
    """(rows, width) of a standing person's head: the top HEAD of them, as wide as it is there."""
    np = _np()
    b = bbox(idx)
    hh = max(5, round((b[3] - b[1]) * HEAD))
    rows = idx[b[1]:b[1] + hh] > 0
    w = max(int(np.ptp(r.nonzero()[0])) + 1 if r.any() else 0 for r in rows)
    return hh, w


def head_box(idx, hh, hw):
    """(top, centre x) of the head in a frame: the top of the figure, centred on what is in its top rows.
    None when the figure lies down (wider than tall)."""
    np = _np()
    b = bbox(idx)
    if not b or (b[2] - b[0]) > (b[3] - b[1]) * 1.1:
        return None
    y0 = b[1]
    xs = np.nonzero(idx[y0:y0 + 3])[1]
    c = xs.mean()
    for _ in range(2):                            # re-centre on the whole head
        ys, xs = np.nonzero(idx[y0:y0 + hh])
        near = np.abs(xs - c) <= hw / 2 + 1
        if near.any():
            c = xs[near].mean()
    return y0, c


def _box_mask(shape, y0, c, hh, hw):
    np = _np()
    m = np.zeros(shape, dtype=bool)
    x0, x1 = int(np.floor(c - hw / 2 - 1)), int(np.ceil(c + hw / 2 + 1))
    m[max(0, y0):max(0, y0 + hh), max(0, x0):max(0, x1)] = True
    return m


def restyle(cid, donor, frames, view):
    """Donor canvas frames (RGBA, donor's palette) -> the person's frames (RGBA, their palette)."""
    np = _np()
    t_idx, t_pal = standing(cid, view)
    d0, d_pal = standing(donor, view)
    tb, db = bbox(t_idx), bbox(d0)
    s = (tb[3] - tb[1]) / (db[3] - db[1])
    d_idx = scale_about_feet(d0, s)
    cmap = colour_map(t_idx, t_pal, d_idx, d_pal)
    lut = np.array([cmap.get(i, 0) for i in range(16)], dtype=np.int16)
    # heads: the top of the figure (sitting, eating, on the toilet, in the shower people are upright)
    d_hh, d_hw = head_size(d0)
    t_hh, t_hw = head_size(t_idx)
    ty0, tc = head_box(t_idx, t_hh, t_hw)
    t_head = _box_mask(t_idx.shape, ty0, tc, t_hh, t_hw) & (t_idx > 0)
    tys, txs = np.nonzero(t_head)
    ox, oy = A.ORIGIN
    out = []
    for fr in frames:
        f0 = to_index(fr, d_pal)
        f = scale_about_feet(f0, s)
        g = lut[f]
        hb = head_box(f0, d_hh, d_hw)
        if hb is not None:
            y0, c = hb
            hm = _box_mask(f0.shape, y0, c, d_hh, d_hw) & (f0 > 0)
            g[scale_about_feet(hm.astype(np.int16), s) > 0] = 0
            dx = round((c - ox) * s + ox - tc)
            dy = round((y0 - oy) * s + oy - ty0)
            Y, X = tys + dy, txs + dx
            ok = (Y >= 0) & (Y < g.shape[0]) & (X >= 0) & (X < g.shape[1])
            g[Y[ok], X[ok]] = t_idx[tys[ok], txs[ok]]
        out.append(to_rgba(g, t_pal))
    return out


def donors_for(group):
    ids = A.GROUPS[group][1]
    return [c for c in range(31, 67) if all(a in A.anim_ids(c) for a in ids)]


def missing(cid):
    have = A.anim_ids(cid)
    return [g for g, (_, ids) in A.GROUPS.items() if not any(a in have for a in ids)]


# ------------------------------------------------------------------ the build: a generated mod

class PosesError(Exception):
    pass


def _pack(content):
    """A frame's chunk: the quick encoder (the full one takes minutes for a few hundred sheets)."""
    import urbzcomp as Z
    return Z.compress_fast(content, A.CHUNK_FLAGS)


def make_set(cid, group):
    """One person's borrowed animation group, encoded: {'donor', 'sheets': {name: (gfx bytes, layout bytes)},
    'rows': [(anim id, [(sheet name, palette, param) x 5 facings], script id)]}."""
    import urbz_composite as C
    donor = choose_donor(cid, donors_for(group))
    pal, d_pal = A.palette16(cid), A.palette16(donor)
    stand = C.parse_layout(A.asset(A.row_of(cid, 0x04)[0][0][1] - 1))
    extra, head = stand.entries[0].extra, stand.head
    sheets, rows = {}, []
    for aid in A.GROUPS[group][1]:
        recs, script = A.row_of(donor, aid)
        facings = []
        for f in range(5):
            gfx_gid, lay_gid, palette, param = recs[f]
            name = '%x-%x' % (gfx_gid, lay_gid)
            if name not in sheets:
                view = 'front' if f < 3 else 'back'
                frames = restyle(cid, donor, A.sheet_frames(gfx_gid, lay_gid, d_pal), view)
                gfx, entries = bytearray(), []
                for im in frames:
                    e, content = A.frame_data(im, pal, extra)
                    e.index, e.chunk_off = len(entries), len(gfx)
                    gfx += _pack(content)
                    while len(gfx) % 4:
                        gfx += b'\0'
                    entries.append(e)
                if len(gfx) > 0xFFFF:
                    raise PosesError('%s %s: a sheet of %d bytes (the game allows 64 KB)' % (cid, group, len(gfx)))
                lay = C.Layout(bytes([max(e.w for e in entries), max(e.h for e in entries)]) + head[2:],
                               entries, 0, len(extra) // 6)
                sheets[name] = (bytes(gfx), C.build_layout(lay))
            facings.append((name, palette, param))
        rows.append((aid, facings, script))
    return {'donor': donor, 'sheets': sheets, 'rows': rows}


def _cache_key():
    import hashlib
    h = hashlib.sha1()
    for f in ('urbz_poses.py', 'urbz_anims.py', 'urbz_composite.py'):
        h.update(open(os.path.join(KIT, f), 'rb').read())
    h.update(A.arm9())
    return h.hexdigest()[:16]


def cached_set(cid, group, cache_dir):
    """make_set, kept in build/cache/poses (made again when this code or the game changes)."""
    import pickle
    path = os.path.join(cache_dir, '%d-%s.pkl' % (cid, group))
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except (OSError, EOFError, pickle.PickleError):
        pass
    s = make_set(cid, group)
    os.makedirs(cache_dir, exist_ok=True)
    tmp = path + '.%d.tmp' % os.getpid()
    with open(tmp, 'wb') as f:
        pickle.dump(s, f)
    os.replace(tmp, path)
    return s


def _hooked_people(mod_dirs):
    """People whose animation list a mod already replaces (urbz_anims.py drawings win)."""
    out = set()
    for md in mod_dirs:
        hp = os.path.join(md, 'code', 'hooks.txt')
        for line in (open(hp).read().splitlines() if os.path.exists(hp) else ()):
            p = line.split('#', 1)[0].split()
            if len(p) >= 2 and p[1].startswith('npc_anim_lists+'):
                out.add(int(p[1].split('+')[1], 0) // 4)
    return out


def poses_mod(proj, mod_dirs, out_dir, first_asset, progress=print):
    """A mod with poses.json ({"groups": [...], "skip": [person ids]}) -> the generated mod out_dir: new sheets
    (assets/, numbered from first_asset()), each person's animation list with the new rows (code/build
    patch.bin+json, data only) and hooks.txt pointing npc_anim_lists at them.
    Returns ([out_dir], report line) or (None, None) when no mod asks for poses."""
    cfgs = []
    for md in mod_dirs:
        p = os.path.join(md, 'poses.json')
        if os.path.exists(p):
            try:
                cfgs.append((md, json.load(open(p))))
            except ValueError as e:
                raise PosesError('%s: %s' % (p, e))
    adir = os.path.join(out_dir, 'assets')
    if os.path.isdir(adir):
        for f in os.listdir(adir):
            os.remove(os.path.join(adir, f))
    if not cfgs:
        return None, None
    groups, skip = [], set(_hooked_people(mod_dirs))
    for md, cfg in cfgs:
        for g in cfg.get('groups', list(A.GROUPS)):
            if g not in A.GROUPS:
                raise PosesError('%s/poses.json: unknown group "%s" (groups: %s)' % (md, g, ', '.join(A.GROUPS)))
            if g not in groups:
                groups.append(g)
        skip |= {int(c) for c in cfg.get('skip', [])}
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(out_dir)), 'cache', 'poses', _cache_key())
    todo = [(cid, g) for cid in range(31, 67) if cid not in skip for g in groups if g in missing(cid)]
    fresh = [t for t in todo if not os.path.exists(os.path.join(cache_dir, '%d-%s.pkl' % t))]
    if fresh:
        progress('poses: making %d borrowed animation set(s), about %d s (once: they are kept in build/cache)'
                 % (len(fresh), 1 + len(fresh) // 2))
    nxt = [first_asset()]
    start = nxt[0]

    def new_asset(data):
        os.makedirs(adir, exist_ok=True)
        open(os.path.join(adir, '%05d.bin' % nxt[0]), 'wb').write(data)
        nxt[0] += 1
        return nxt[0]                           # game id = file number + 1

    blob, relocs, syms, lines, people, shared = bytearray(b'POSE'), [], {}, [], {}, {}
    for cid, g in todo:
        people.setdefault(cid, []).append((g, cached_set(cid, g, cache_dir)))
    for cid, sets in sorted(people.items()):
        rows = [struct.pack('<4sII', raw, rec, script) for raw, rec, script in A.anim_rows(cid)]
        new = []
        for g, s in sets:
            ids = {name: (new_asset(gfx), new_asset(lay)) for name, (gfx, lay) in sorted(s['sheets'].items())}
            for aid, facings, script in s['rows']:
                recs = b''.join(struct.pack('<4I', ids[name][0], ids[name][1], palette, param)
                                for name, palette, param in facings)
                if recs not in shared:          # (sit's three rows use the same records: once. The code
                    while len(blob) % 4:        #  region is tight: all of it is copied at boot, 160 KB)
                        blob.append(0)
                    shared[recs] = len(blob)
                    blob += recs
                new.append((aid, shared[recs], script))
        while len(blob) % 4:
            blob.append(0)
        syms['anims_%d' % cid] = len(blob)
        for r in rows:
            blob += r
        for aid, rec, script in new:
            relocs.append(len(blob) + 4)
            blob += struct.pack('<III', aid, rec, script)
        blob += struct.pack('<III', 0xC4, 0, 0)
        lines.append('u32 npc_anim_lists+0x%X @anims_%d' % (4 * cid, cid))
    cdir = os.path.join(out_dir, 'code')
    os.makedirs(os.path.join(cdir, 'build'), exist_ok=True)
    open(os.path.join(cdir, 'hooks.txt'), 'w').write(
        '# Generated by urbz_poses.py: each person\'s animation list, with the borrowed ones\n' + '\n'.join(lines) + '\n')
    open(os.path.join(cdir, 'build', 'patch.bin'), 'wb').write(bytes(blob))
    json.dump({'relocs': relocs, 'symbols': syms, 'bss': 0, 'sources': {}},
              open(os.path.join(cdir, 'build', 'patch.json'), 'w'))
    json.dump({'name': 'new-poses', 'description': 'Kit: the townspeople\'s borrowed animations', 'toggle': False,
               'hidden': True}, open(os.path.join(out_dir, 'mod.json'), 'w'))
    n = sum(len(v) for v in people.values())
    return [out_dir], 'poses: %d animation set(s) for %d people (%s), %d new files, %d bytes of lists' % (
        n, len(people), ', '.join(groups), nxt[0] - start, len(blob))



# ------------------------------------------------------------------ preview

def preview(out, people, groups):
    from PIL import Image
    os.makedirs(out, exist_ok=True)
    n = A.names()
    for cid in people:
        for g in groups:
            if g not in missing(cid):
                continue
            donor = choose_donor(cid, donors_for(g))
            aid = A.GROUPS[g][1][0]
            recs, _ = A.row_of(donor, aid)
            sheets = []
            for view, (gfx, lay) in A.views_of(recs).items():
                fr = A.sheet_frames(gfx, lay, A.palette16(donor))
                mine = restyle(cid, donor, fr, view)
                own = to_rgba(standing(cid, view)[0], A.palette16(cid))
                pick = [k * (len(fr) - 1) // 5 for k in range(6)]
                sheets.append([own] + [fr[k] for k in pick] + [mine[k] for k in pick])
            W = 96 * 7
            img = Image.new('RGBA', (W, 96 * 2 * len(sheets)), (96, 96, 120, 255))
            for r, row in enumerate(sheets):
                own, donor_fr, mine = row[0], row[1:7], row[7:]
                img.alpha_composite(own, (0, 96 * 2 * r))
                for k in range(6):
                    img.alpha_composite(donor_fr[k], (96 * (k + 1), 96 * 2 * r))
                    img.alpha_composite(mine[k], (96 * (k + 1), 96 * 2 * r + 96))
            name = '%d-%s-%s-from-%s.png' % (cid, n[cid].split()[0].lower(), g, n[donor].split()[0].lower())
            img.resize((img.width * 2, img.height * 2), Image.NEAREST).save(os.path.join(out, name))
            print(name)


def main(argv):
    if len(argv) >= 2 and argv[0] == 'preview':
        groups = list(A.GROUPS)
        if '--group' in argv:
            k = argv.index('--group')
            groups = [argv[k + 1]]
            argv = argv[:k] + argv[k + 2:]
        people = [A.person(p)[0] for p in argv[2:]] or list(range(31, 67))
        preview(argv[1], people, groups)
        return
    print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
