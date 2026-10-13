"""Borrowed poses: the townspeople's missing animations (sit, eat, toilet, shower, sleep, and the three chat
gestures for the eight who have none), made from someone who has them, in the person's own colours and with
their own head.

Most townspeople only have stand, walk and a few gestures: their art is pre-rendered 3D, so their own frames
can't be bent into new poses. Each missing animation is taken from the closest-looking person who has it (the
"donor": similar height and build), scaled to the person's height, recoloured, and the donor's head is swapped
for the person's own (the top of the figure in each frame; lying down, the donor's head stays, recoloured).

Recolouring (colour_map): black stays black, the donor's skin becomes the person's skin (SKIN, checked by hand;
in the shower all of the donor's bare skin), and every other donor colour goes to the person's garment it lands
on when the two standing figures are laid over each other (overlay_counts), its shades shared out light to
dark. Standing poses (eat, gestures) colour the top and bottom half apart, so a white shirt and white trainers
become a red shirt and black shoes.

Lincoln Broadsheet (47) is in a wheelchair: he eats sitting in his own chair (the donor's upper body over his
seated frame, restyle_in_chair), borrows sleep, and gets no sit, toilet or shower (poses.json "skip"). He is
never used as a donor.

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


# Who is a man and who a woman (from the game's bios, string 471 + id, and the art): a pose is borrowed from
# someone of the same sex when there is anyone (a woman's body in the shower on Gary looked wrong).
WOMEN = {35, 43, 45, 46, 48, 50, 52, 54, 55, 57, 58, 59, 61, 66}


def choose_donor(cid, donors):
    """The donor whose standing silhouette is closest (feet aligned): height, width, overlap; same sex first."""
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
        # and as covered up: a donor in a swimsuit made everyone they lent a pose to bare-legged
        cost += 2 * abs(_skin_share(t, SKIN.get(cid)) - _skin_share(s, SKIN.get(d)))
        cost += 1.5 * ((cid in WOMEN) != (d in WOMEN))
        if best is None or cost < best[0]:
            best = (cost, d)
    return best[1]


def _skin_share(idx, skin):
    np = _np()
    return float(np.isin(idx, skin or []).sum()) / max(int((idx > 0).sum()), 1)


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


def colour_map_v1(t_idx, t_pal, d_idx, d_pal):
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


# Skin colours, looked at person by person (2026-10-12: research/npc/skin_check.py highlights them): the face
# and hands of everyone (finding them by machine took hats, hair and tan trousers for skin), and the donors' bare
# skin in their shower animation (BODY_SKIN; Dusty's 5 and 6 are also his vest, so only there).
SKIN = {31: [1, 2, 3, 4], 32: [1, 2, 3], 33: [7, 8, 9], 34: [1, 2, 3, 4], 35: [1, 2, 3, 4], 36: [1, 2, 3],
        37: [5, 6, 7], 38: [9, 10, 11, 12], 39: [2, 3, 4], 40: [1, 2, 3], 41: [2, 3, 4], 42: [5, 6, 7, 8],
        43: [11, 12, 13, 14], 44: [1, 2, 3, 4], 45: [1, 2, 3, 4], 46: [4, 5, 6, 7], 47: [1, 2, 3], 48: [9, 10, 11],
        49: [1, 2, 3], 50: [3, 4, 5], 51: [1, 2, 3], 52: [11, 12, 13], 53: [1, 2, 3], 54: [10, 11, 12, 13],
        55: [1, 2, 3, 4], 56: [7, 8, 9], 57: [1, 2, 3, 4], 58: [1, 2, 3], 59: [1, 2, 3], 60: [13, 11], 61: [2, 3],
        62: [6, 7, 8], 63: [9, 10, 11], 64: [6, 7, 11], 65: [9, 10, 11, 12], 66: [7, 8]}
BODY_SKIN = {33: [7, 8, 9], 39: [1, 2, 3, 4, 5, 6], 41: [1, 2, 3, 4], 45: [1, 2, 3, 4, 5], 52: [11, 12, 13, 14],
             54: [10, 11, 12, 13, 14], 58: [1, 2, 3, 4]}

# ---- colours, v2 (2026-10-12): garments as palette ramps ------------------------------------------------
# A townsperson's 16 colours come in ramps, light to dark, one per part (skin 2-6, a blue shirt 8-11, grey
# trousers 12-14, black 15 for outlines and the shadow). Each donor ramp goes to the person's ramp that plays the
# same part (skin to skin, then by where it sits on the body), colour by colour at the same place in the ramp.
# Donor colours a standing donor never shows (bare skin in the shower) go with their own ramp.

def _hls(c):
    import colorsys
    return colorsys.rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)


def _is_black(rgb):
    """The outline / shadow colour: black or all but (some people's is 080808 or 200020)."""
    return max(rgb[:3]) <= 0x20


def ramps(pal):
    """[[index, ...], ...]: runs of the palette (1-15) that go darker in one hue; black on its own."""
    out, cur = [], []
    for c in range(1, 16):
        h, l, s = _hls(pal[c])
        if _is_black(pal[c]):
            if cur:
                out.append(cur)
            out.append([c])
            cur = []
            continue
        if cur:
            ph, pl, ps = _hls(pal[cur[-1]])
            grey, pgrey = s < 0.15 or l < 0.08, ps < 0.15 or pl < 0.08
            dh = min(abs(h - ph), 1 - abs(h - ph)) * 360
            if l > pl + 0.04 or grey != pgrey or (not grey and dh > 28):
                out.append(cur)
                cur = []
        cur.append(c)
    if cur:
        out.append(cur)
    return out


def _skinlike(c):
    h, l, s = _hls(c)
    return 0.02 <= h <= 0.14 and s >= 0.18 and 0.15 <= l <= 0.92


def ramp_info(idx, pal, extra_counts=None):
    """Per ramp: (indices, pixel count, mean height on the body 0-1, share of pixels in the face rows, skin-like)."""
    np = _np()
    b = bbox(idx)
    h = max(b[3] - b[1], 1)
    hh, hw = head_size(idx)
    info = []
    for r in ramps(pal):
        ys = np.concatenate([np.nonzero(idx == c)[0] for c in r])
        n = len(ys) + sum((extra_counts or {}).get(c, 0) for c in r)
        y = float((ys.mean() - b[1]) / h) if len(ys) else 0.5
        face = float(((ys >= b[1] + hh * 0.35) & (ys < b[1] + hh)).sum()) / max(len(ys), 1) if len(ys) else 0.0
        sk = sum(1 for c in r if _skinlike(pal[c])) * 2 >= len(r)
        info.append({'idx': r, 'n': n, 'y': y, 'face': face, 'skin': sk, 'black': _is_black(pal[r[0]])})
    return info


def _skin_ramp(info):
    cand = [r for r in info if r['skin'] and not r['black'] and r['n']]
    if not cand:
        return None
    return max(cand, key=lambda r: r['face'] * 3 + min(r['n'], 60) / 60 + (0.5 if r['y'] < 0.5 else 0))


CELL = 3


def overlay_counts(t_idx, d_idx, head=True):
    """[donor colour, person colour] -> how much they cover each other with the two figures laid over each
    other: feet on the same line, middles lined up, counted in CELL x CELL cells; heads left out (a cap is
    swapped for the person's head, so it must not decide what colour the donor's shirt of the same blue gets)."""
    np = _np()
    tb, db = bbox(t_idx), bbox(d_idx)
    if not tb or not db:
        return np.zeros((16, 16))
    def cells(idx, b, dx):
        ys, xs = np.nonzero(idx)
        keep = ys >= b[1] + round(HEAD * (b[3] - b[1])) if head else ys >= 0   # not the head: theirs anyway
        ys, xs = ys[keep], xs[keep]
        cy = (b[3] - 1 - ys) // CELL
        cx = np.floor((xs - dx) / CELL).astype(int)
        return cy, cx, idx[ys, xs]
    tcx, dcx = (tb[0] + tb[2]) / 2, (db[0] + db[2]) / 2
    ty, tx, tv = cells(t_idx, tb, tcx)
    dy, dx, dv = cells(d_idx, db, dcx)
    H = max(ty.max(), dy.max()) + 1
    x0 = min(tx.min(), dx.min())
    W = max(tx.max(), dx.max()) - x0 + 1
    T = np.zeros((H, W, 16)); D = np.zeros((H, W, 16))
    np.add.at(T, (ty, tx - x0, tv), 1)
    np.add.at(D, (dy, dx - x0, dv), 1)
    Tn = T / np.maximum(T.sum(axis=2, keepdims=True), 1)
    return np.einsum('hwc,hwt->ct', D, Tn)


def colour_map(t_idx, t_pal, d_idx, d_pal, d_extra=None, body_skin=None, t_known=None, d_known=None,
               head=True):
    """donor index -> the person's index. Skin goes to the person's skin (face colours, by brightness; a donor's
    whole skin ramp, so bare skin in the shower is skin too); black to black; every other donor ramp (a garment)
    to the person's ramp that covers the same parts of the body (bands from head to feet, histogram overlap), its
    pixels shared out like the person's (a black suit with a white collar stays mostly black). d_extra: {donor
    colour: pixels} the animation uses that the standing donor doesn't show."""
    np = _np()
    tc, dc = band_counts(t_idx), band_counts(d_idx)
    t_skin = list(t_known) if t_known else _skin(tc, t_pal)
    d_skin = list(d_known) if d_known else _skin(dc, d_pal)
    t_ramps, d_ramps = ramps(t_pal), ramps(d_pal)
    black = lambda pal, c: _is_black(pal[c])
    t_black = [c for c in range(1, 16) if black(t_pal, c)]
    if not t_skin:
        sr = _skin_ramp(ramp_info(t_idx, t_pal))
        t_skin = [c for c in sr['idx'] if tc[:, c].sum()] if sr else []
    # the donor's skin: their face colours; in the shower all of their skin (BODY_SKIN: the colours their bare
    # skin uses there; some of them are a vest or a beard when dressed, so only then)
    d_skin_all = sorted(set(d_skin) | set(body_skin or ()), key=lambda c: -_lum(d_pal[c]))
    t_skin_l = sorted(t_skin, key=lambda c: -_lum(t_pal[c]))
    garments = [g for g in ([c for c in r if c not in t_skin] for r in t_ramps)   # (skin is never a garment)
                if g and not all(black(t_pal, c) for c in g) and sum(tc[:, c].sum() for c in g)]
    hist = lambda counts, r: counts[:, r].sum(axis=1) / max(counts[:, r].sum(), 1)
    m = {0: 0}
    rests = []
    for r in d_ramps:
        if all(black(d_pal, c) for c in r):
            for c in r:
                m[c] = t_black[0] if t_black else min(range(1, 16), key=lambda t: _lum(t_pal[t]))
            continue
        skin_part = [c for c in r if c in d_skin_all or (body_skin and t_skin_l and not black(d_pal, c))]
        # (in the shower everything but black is skin: the head, hair and all, is the person's own)
        for c in skin_part:
            if c in d_skin_all:
                q = d_skin_all.index(c) / max(len(d_skin_all) - 1, 1)
            else:                                     # by brightness among the donor's skin colours
                q = sum(1 for k in d_skin_all if _lum(d_pal[k]) > _lum(d_pal[c])) / max(len(d_skin_all), 1)
            if t_skin_l:
                m[c] = t_skin_l[min(len(t_skin_l) - 1, round(q * (len(t_skin_l) - 1)))]
        rest = [c for c in r if c not in skin_part]
        if rest:
            rests.append(rest)
    # each donor garment goes to the person's garment it lands on when the two standing figures are laid over
    # each other (same height, feet and middle lined up; counted in small cells, so a slightly wider or
    # narrower person still lines up), and that is about as dark. Colours that are one piece of clothing on
    # the donor but split over several small ramps on the person (or the other way round) land where they are.
    over = overlay_counts(t_idx, d_idx, head)               # [donor colour, person colour] -> pixels
    mean_l = lambda counts, pal, r: (sum(counts[:, c].sum() * _lum(pal[c]) / 2550 for c in r)
                                     / max(counts[:, r].sum(), 1))
    given = {}                                        # person's garment -> the donor colours it gets
    for rest in sorted(rests, key=lambda r: -dc[:, r].sum()):
        if not garments:
            for c in rest:
                m[c] = min(range(1, 16), key=lambda t: abs(_lum(t_pal[t]) - _lum(d_pal[c])))
            continue
        on = over[rest].sum(axis=0)
        if not dc[:, rest].sum() or not on[1:].sum():  # never shown standing: like the nearest-hued garment
            tr = min(garments, key=lambda g: min(abs(_hls(t_pal[g[0]])[0] - _hls(d_pal[rest[0]])[0]), 1))
        else:
            ld, tot = mean_l(dc, d_pal, rest), on[1:].sum()
            tr = max(garments, key=lambda g: on[g].sum() / tot - 0.25 * abs(ld - mean_l(tc, t_pal, g)))
        given.setdefault(tuple(tr), []).extend(rest)
    # all the donor colours one garment of the person's gets (often from several donor ramps), light to dark,
    # their pixels laid over that garment's pixels, light to dark: a white shirt and a dark vest that both
    # become the person's jacket are its light and its dark
    for tr, dcols in given.items():
        dl = sorted(dcols, key=lambda c: -_lum(d_pal[c]))
        tl = sorted(tr, key=lambda c: -_lum(t_pal[c]))
        dn = [dc[:, c].sum() + (d_extra or {}).get(c, 0) for c in dl]
        tn = [tc[:, c].sum() for c in tl]
        if sum(tn) == 0:
            tn = [1] * len(tl)
        dtot, ttot, acc = max(sum(dn), 1), sum(tn), 0
        cum_t = np.cumsum(tn) / ttot
        for k, c in enumerate(dl):
            q = (acc + dn[k] / 2) / dtot if sum(dn) else k / max(len(dl) - 1, 1)
            acc += dn[k]
            m[c] = tl[int(np.searchsorted(cum_t, q - 1e-9))] if q < 1 else tl[-1]
    for c in range(1, 16):
        m.setdefault(c, min(range(1, 16), key=lambda t: abs(_lum(t_pal[t]) - _lum(d_pal[c]))))
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


UPRIGHT = {'eat', 'gesture'}      # groups where people stand: coloured top half and bottom half apart
WAIST = 0.5                       # of a standing person's height, from the top


def lut_of_half(t_idx, t_pal, d_idx, d_pal, half, whole, cid, donor):
    """The colour lookup for the top (0) or bottom (1) half of a standing figure (both scaled to the same
    height, feet at the bottom). A donor colour not in that half when standing keeps its whole-figure colour."""
    np = _np()
    def cut(idx):
        b = bbox(idx)
        y = b[1] + round(WAIST * (b[3] - b[1]))
        out = idx.copy()
        if half == 0:
            out[y:] = 0
            out[:b[1] + round(HEAD * (b[3] - b[1]))] = 0     # (and not the head)
        else:
            out[:y] = 0
        return out
    th, dh = cut(t_idx), cut(d_idx)
    m = colour_map(th, t_pal, dh, d_pal, None, None, SKIN.get(cid), SKIN.get(donor), head=False)
    there = set(int(c) for c in np.unique(dh))
    return np.array([m.get(i, 0) if i in there else whole.get(i, 0) for i in range(16)], dtype=np.int16)


def restyle(cid, donor, frames, view, group=None):
    """Donor canvas frames (RGBA, donor's palette) -> the person's frames (RGBA, their palette)."""
    np = _np()
    t_idx, t_pal = standing(cid, view)
    d0, d_pal = standing(donor, view)
    tb, db = bbox(t_idx), bbox(d0)
    s = (tb[3] - tb[1]) / (db[3] - db[1])
    d_idx = scale_about_feet(d0, s)
    f_idx = [to_index(fr, d_pal) for fr in frames]
    extra = {}
    for f0 in f_idx:                               # colours the animation itself uses (bare skin in the shower)
        for c, n in zip(*np.unique(f0, return_counts=True)):
            extra[int(c)] = extra.get(int(c), 0) + int(n)
    seen = {int(c) for c in np.unique(d0)}
    cmap = colour_map(t_idx, t_pal, d_idx, d_pal, {c: n for c, n in extra.items() if c not in seen},
                      BODY_SKIN.get(donor) if group == 'shower' else None, SKIN.get(cid), SKIN.get(donor))
    lut = np.array([cmap.get(i, 0) for i in range(16)], dtype=np.int16)
    # standing up (eating, a gesture), the top and the bottom half are coloured each on their own: a donor's
    # white shirt and white trainers are one colour, but on the person they are a red shirt and black shoes
    halves = None
    if group in UPRIGHT:
        halves = [lut_of_half(t_idx, t_pal, d_idx, d_pal, half, cmap, cid, donor) for half in (0, 1)]
        th = tb[3] - tb[1]
    # heads: the top of the figure (sitting, eating, on the toilet, in the shower people are upright)
    d_hh, d_hw = head_size(d0)
    t_hh, t_hw = head_size(t_idx)
    ty0, tc = head_box(t_idx, t_hh, t_hw)
    t_head = _box_mask(t_idx.shape, ty0, tc, t_hh, t_hw) & (t_idx > 0)
    tys, txs = np.nonzero(t_head)
    ox, oy = A.ORIGIN
    out = []
    for f0 in f_idx:
        f = scale_about_feet(f0, s)
        g = lut[f]
        if halves and f.any():
            cut = bbox(f)[3] - round((1 - WAIST) * th)
            g[:cut] = halves[0][f[:cut]]
            g[cut:] = halves[1][f[cut:]]
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


# People in a wheelchair (47 Lincoln Broadsheet): they do things sitting in their own chair. The donor's upper
# body (above the waist), in the person's colours and with their head, goes over the person's own seated frame:
# eating a snack in his chair. They get no sit, toilet or shower (poses.json skips those).
WHEELCHAIR = {47}
UPPER = 0.46                    # how much of a standing donor is above the waist; of the person in the chair, 0.52


def restyle_in_chair(cid, donor, frames, view, group=None):
    np = _np()
    t_idx, t_pal = standing(cid, view)
    d0, d_pal = standing(donor, view)
    tb, db = bbox(t_idx), bbox(d0)
    th, dh = tb[3] - tb[1], db[3] - db[1]
    s = (0.52 * th) / (UPPER * dh)
    d_idx = scale_about_feet(d0, s)
    whole = colour_map(t_idx, t_pal, d_idx, d_pal, None, None, SKIN.get(cid), SKIN.get(donor))
    # coloured from the two upper bodies only (the donor's above the waist, the person's above the seat):
    # the rest of the person is chair and legs, which the donor's shirt must not take after
    t_up, d_up = t_idx.copy(), d_idx.copy()
    t_up[tb[1] + round(0.52 * th):] = 0
    b2 = bbox(d_idx)
    d_up[b2[1] + round(UPPER * (b2[3] - b2[1])):] = 0
    cmap = colour_map(t_up, t_pal, d_up, d_pal, None, None, SKIN.get(cid), SKIN.get(donor))
    there = set(int(c) for c in np.unique(d_up))
    lut = np.array([cmap.get(i, 0) if i in there else whole.get(i, 0) for i in range(16)], dtype=np.int16)
    t_hh, t_hw = head_size(t_idx)
    ty0, tc = head_box(t_idx, t_hh, t_hw)
    t_head = _box_mask(t_idx.shape, ty0, tc, t_hh, t_hw) & (t_idx > 0)
    d_hh, d_hw = head_size(d0)
    out = []
    for fr in frames:
        f0 = to_index(fr, d_pal)
        hb = head_box(f0, d_hh, d_hw)
        if hb is None:
            out.append(to_rgba(t_idx, t_pal))
            continue
        y0, c = hb
        g = lut[scale_about_feet(f0, s)]
        hm = scale_about_feet((_box_mask(f0.shape, y0, c, d_hh, d_hw) & (f0 > 0)).astype(np.int16), s) > 0
        g[hm] = 0                                  # the donor's head out: the person's own stays
        ox, oy = A.ORIGIN
        sy0, sc = round((y0 - oy) * s + oy), round((c - ox) * s + ox)   # the donor's head top, scaled
        dy, dx = ty0 - sy0, round(tc - sc)
        cut = ty0 + round(0.52 * th)               # the waist, in the person's frame
        res = t_idx.copy()
        ys, xs = np.nonzero(g)
        Y, X = ys + dy, xs + dx
        ok = (Y >= 0) & (Y < res.shape[0]) & (X >= 0) & (X < res.shape[1]) & (Y < cut)
        res[Y[ok], X[ok]] = g[ys[ok], xs[ok]]
        res[t_head] = t_idx[t_head]                # their head on top
        out.append(to_rgba(res, t_pal))
    return out


def donors_for(group):
    ids = A.GROUPS[group][1]
    return [c for c in range(31, 67) if all(a in A.anim_ids(c) for a in ids) and c not in WHEELCHAIR]


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
                how = restyle_in_chair if cid in WHEELCHAIR and group == 'eat' else restyle
                frames = how(cid, donor, A.sheet_frames(gfx_gid, lay_gid, d_pal), view, group)
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
    """A mod with poses.json ({"groups": [...], "skip": [person ids] or {person id: [groups]}}) -> the generated mod out_dir: new sheets
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
    groups, skip, skip_groups = [], set(_hooked_people(mod_dirs)), {}
    for md, cfg in cfgs:
        for g in cfg.get('groups', list(A.GROUPS)):
            if g not in A.GROUPS:
                raise PosesError('%s/poses.json: unknown group "%s" (groups: %s)' % (md, g, ', '.join(A.GROUPS)))
            if g not in groups:
                groups.append(g)
        sk = cfg.get('skip', [])
        if isinstance(sk, dict):                # {"47": ["sit", ...]}: just those groups for that person
            for c, gs in sk.items():
                skip_groups.setdefault(int(c), set()).update(gs)
        else:
            skip |= {int(c) for c in sk}
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(out_dir)), 'cache', 'poses', _cache_key())
    todo = [(cid, g) for cid in range(31, 67) if cid not in skip for g in groups if g in missing(cid)
            and g not in skip_groups.get(cid, ())]
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
                mine = (restyle_in_chair if cid in WHEELCHAIR and g == 'eat' else restyle)(cid, donor, fr, view, g)
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
