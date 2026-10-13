"""The kit's own models: pets, pet beds and furniture built from simple shapes in code, with their own
animations. They are rendered the way the other Sims games' models are (urbz_import.py: the Urbz camera, 16
colours), but everything here is original, so the art can ship with the kit and a build needs nothing but
your Urbz ROM.

  python urbz.py models list                     every model
  python urbz.py models show NAME [out.png]      a sheet: 5 directions; pets also every action

A mod names one like any import: pets.json "import": {"from": "kit", "model": "puppy"}, objects.json
"import": {"from": "kit", "model": "club_sofa"}. "import" may be a list: the first one whose game you
have is used, so [{"from": "aptpets", ...}, {"from": "kit", ...}] renders from Apartment Pets when
sources.json names it and from the kit's own model otherwise.

Units are metres, Y up, the model faces +Z (pets and furniture alike: a chair's back is at -Z, a bed's head
board at -Z). Pets stand on the floor at the origin; furniture is centred on its footprint.
"""
import math
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, 'kit'))


# ------------------------------------------------------------------ shapes
# A shape is an array [N, 3, 8] of triangles: x y z, u v, nx ny nz (what urbz_import.rasterize draws).

def _grid_tris(P, Nn):
    """P, Nn: [rows, cols, 3] points and normals on a (u, v) grid -> triangles."""
    r, c = P.shape[:2]
    out = []
    for i in range(r - 1):
        for j in range(c - 1):
            a, b, cc, d = (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
            for tri in ((a, b, cc), (a, cc, d)):
                pts = np.array([P[k] for k in tri])
                if np.linalg.norm(np.cross(pts[1] - pts[0], pts[2] - pts[0])) < 1e-12:
                    continue
                t = np.zeros((3, 8))
                t[:, :3] = pts
                t[:, 5:8] = [Nn[k] for k in tri]
                out.append(t)
    return np.array(out) if out else np.zeros((0, 3, 8))


def _spow(x, e):
    return np.sign(x) * np.abs(x) ** e


LOD = 1.0                           # detail of pets' shapes (set by Model: they're only 9-28 pixels tall)


def blob(radii, e1=1.0, e2=1.0, n=10):
    """A superellipsoid at the origin: e1 = e2 = 1 an ellipsoid, smaller = boxier (0.2 a rounded box)."""
    n = max(3, int(round(n * LOD)))
    rx, ry, rz = radii
    th = np.linspace(-np.pi / 2, np.pi / 2, n + 1)          # latitude
    ph = np.linspace(-np.pi, np.pi, 2 * n + 1)              # longitude
    T, F = np.meshgrid(th, ph, indexing='ij')
    ct, st, cf, sf = np.cos(T), np.sin(T), np.cos(F), np.sin(F)
    P = np.stack([rx * _spow(ct, e1) * _spow(sf, e2), ry * _spow(st, e1), rz * _spow(ct, e1) * _spow(cf, e2)], -1)
    Nn = np.stack([_spow(ct, 2 - e1) * _spow(sf, 2 - e2) / rx, _spow(st, 2 - e1) / ry,
                   _spow(ct, 2 - e1) * _spow(cf, 2 - e2) / rz], -1)
    Nn /= np.linalg.norm(Nn, axis=-1, keepdims=True) + 1e-9
    return _grid_tris(P, Nn)


def box(size):
    """A box centred on the origin, flat faces."""
    sx, sy, sz = (s / 2.0 for s in size)
    out = []
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
             ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, -1, 0), (0, 0, -1), (1, 0, 0)),
             ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0))]
    h = np.array([sx, sy, sz])
    for n, u, v in faces:
        n, u, v = np.array(n, float), np.array(u, float), np.array(v, float)
        c = n * h
        du, dv = u * h, v * h
        q = [c - du - dv, c + du - dv, c + du + dv, c - du + dv]
        for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
            t = np.zeros((3, 8))
            t[:, :3] = tri
            t[:, 5:8] = n
            out.append(t)
    return np.array(out)


def tube(p0, p1, r0, r1=None, n=8, caps=True):
    """A tapered cylinder from p0 to p1 (radius r0 to r1), with round ends."""
    r1 = r0 if r1 is None else r1
    n = max(4, int(round(n * LOD)))
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    L = np.linalg.norm(d)
    if L < 1e-6:
        return move(blob((r0, r0, r0), n=max(4, n // 2)), p0)
    w = d / L
    a = np.array([1.0, 0, 0]) if abs(w[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(w, a)
    u /= np.linalg.norm(u)
    v = np.cross(w, u)
    ang = np.linspace(0, 2 * np.pi, n + 1)
    ring = np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v
    P = np.stack([p0 + r0 * ring, p1 + r1 * ring])
    slope = (r0 - r1) / L
    Nn = ring + slope * w
    Nn = np.stack([Nn, Nn]) / np.linalg.norm(Nn, axis=-1, keepdims=True)[None]
    out = [_grid_tris(P, Nn)]
    if caps:
        out += [move(blob((r0, r0, r0), n=max(4, n // 2)), p0), move(blob((r1, r1, r1), n=max(4, n // 2)), p1)]
    return np.concatenate(out)


def disc_ring(r_out, r_in, h, n=16):
    """A flat ring (a hoop, a rim) lying on the floor plane, height h, centred on the origin."""
    out = []
    ang = np.linspace(0, 2 * np.pi, n + 1)
    for i in range(n):
        a0, a1 = ang[i], ang[i + 1]
        for r, s in ((r_out, 1), (r_in, -1)):        # outer and inner walls
            p = [np.array([r * np.sin(a0), 0, r * np.cos(a0)]), np.array([r * np.sin(a1), 0, r * np.cos(a1)])]
            q = [p[0] + (0, h, 0), p[1] + (0, h, 0)]
            nn = [s * np.array([np.sin(a0), 0, np.cos(a0)]), s * np.array([np.sin(a1), 0, np.cos(a1)])]
            for tri, nt in (((p[0], p[1], q[1]), (nn[0], nn[1], nn[1])), ((p[0], q[1], q[0]), (nn[0], nn[1], nn[0]))):
                t = np.zeros((3, 8))
                t[:, :3] = tri
                t[:, 5:8] = nt
                out.append(t)
        top = [np.array([r_out * np.sin(a0), h, r_out * np.cos(a0)]), np.array([r_out * np.sin(a1), h, r_out * np.cos(a1)]),
               np.array([r_in * np.sin(a1), h, r_in * np.cos(a1)]), np.array([r_in * np.sin(a0), h, r_in * np.cos(a0)])]
        for tri in ((top[0], top[1], top[2]), (top[0], top[2], top[3])):
            t = np.zeros((3, 8))
            t[:, :3] = tri
            t[:, 5:8] = (0, 1, 0)
            out.append(t)
    return np.array(out)


def rot(rx=0.0, ry=0.0, rz=0.0):
    """Rotation matrix, degrees: first about Z, then X, then Y."""
    x, y, z = (math.radians(a) for a in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    Rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def move(tris, t=(0, 0, 0), R=None):
    """Rotate (R about the origin), then move by t."""
    out = tris.copy()
    if R is not None:
        out[..., :3] = out[..., :3] @ R.T
        out[..., 5:8] = out[..., 5:8] @ R.T
    out[..., :3] += np.asarray(t, float)
    return out


class Xf:
    """A joint: a place and a turn; xf.at(point) / xf.put(shape) work in its own space."""

    def __init__(self, t=(0, 0, 0), R=None):
        self.t, self.R = np.asarray(t, float), (np.eye(3) if R is None else R)

    def then(self, t=(0, 0, 0), R=None):
        R = np.eye(3) if R is None else R
        return Xf(self.t + self.R @ np.asarray(t, float), self.R @ R)

    def at(self, p):
        return self.t + self.R @ np.asarray(p, float)

    def put(self, tris):
        return move(tris, self.t, self.R)


def C(hexrgb):
    hexrgb = hexrgb.lstrip('#')
    return tuple(int(hexrgb[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------ four-legged pets
# One rig for the dog, cat, rabbit, hamster and guinea pig: a pose is a dict of joint values (below); each
# action is a function of time 0-1 giving a pose. Species differ in their proportions and parts.

QUAD = {
    'puppy': dict(body=(0.085, 0.085, 0.16), leg=0.13, leg_r=0.032, paw=0.034, shoulder_w=0.06,
                  head=(0.075, 0.072, 0.08), snout=(0.042, 0.036, 0.055), neck=(0.0, 0.07, 0.13),
                  ears='floppy', ear=(0.022, 0.07, 0.045), tail='up', tail_len=0.13, tail_r=0.016,
                  colours={'body': '#C8873E', 'belly': '#F2E8D8', 'saddle': '#3A2C26', 'head': '#C8873E',
                           'snout': '#F2E8D8', 'ear': '#7A4A22', 'leg': '#C8873E', 'paw': '#F2E8D8', 'tail': '#C8873E',
                           'tip': '#F2E8D8', 'nose': '#1E1A1A', 'eye': '#1E1A1A'}),
    'kitten': dict(body=(0.06, 0.065, 0.14), leg=0.13, leg_r=0.02, paw=0.024, shoulder_w=0.045,
                   head=(0.065, 0.06, 0.06), snout=(0.03, 0.022, 0.025), neck=(0.0, 0.065, 0.11),
                   ears='pointy', ear=(0.028, 0.045, 0.012), tail='long', tail_len=0.24, tail_r=0.014,
                   colours={'body': '#E08A3C', 'belly': '#FBEFE0', 'saddle': '#B8602A', 'head': '#E08A3C',
                            'snout': '#FBEFE0', 'ear': '#E08A3C', 'inner': '#F2A8A8', 'leg': '#E08A3C',
                            'tail': '#E08A3C', 'tip': '#B8602A', 'nose': '#D9737A', 'eye': '#2E5A2A'}),
    'bunny': dict(body=(0.075, 0.08, 0.1), leg=0.05, leg_r=0.025, paw=0.03, shoulder_w=0.045,
                  head=(0.055, 0.055, 0.058), snout=(0.03, 0.026, 0.025), neck=(0.0, 0.07, 0.07),
                  ears='long', ear=(0.02, 0.085, 0.01), tail='puff', tail_len=0.035, tail_r=0.03,
                  rear='haunch', colours={'body': '#B9AFA6', 'belly': '#F4F1EC', 'saddle': '#9C9188',
                                          'head': '#B9AFA6', 'snout': '#F4F1EC', 'ear': '#B9AFA6',
                                          'inner': '#E8B4B8', 'leg': '#B9AFA6', 'tail': '#F4F1EC',
                                          'nose': '#D98A92', 'eye': '#1E1A1A'}),
    'hamster': dict(body=(0.04, 0.035, 0.05), leg=0.012, leg_r=0.008, paw=0.009, shoulder_w=0.025,
                    head=(0.032, 0.03, 0.03), snout=(0.016, 0.014, 0.012), neck=(0.0, 0.025, 0.04),
                    ears='round', ear=(0.012, 0.012, 0.005), tail='none', tail_len=0.0, tail_r=0.0,
                    colours={'body': '#D9A24A', 'belly': '#FAF2E2', 'saddle': '#C4893A', 'head': '#D9A24A',
                             'snout': '#FAF2E2', 'ear': '#C78A7A', 'inner': '#E8B4B8', 'leg': '#F0C8B8',
                             'nose': '#D98A92', 'eye': '#1E1A1A'}),
    'guinea_pig': dict(body=(0.05, 0.042, 0.075), leg=0.014, leg_r=0.009, paw=0.01, shoulder_w=0.03,
                       head=(0.036, 0.034, 0.036), snout=(0.02, 0.018, 0.014), neck=(0.0, 0.022, 0.06),
                       ears='round', ear=(0.014, 0.012, 0.005), tail='none', tail_len=0.0, tail_r=0.0,
                       colours={'body': '#8A5A34', 'belly': '#F4EEE4', 'saddle': '#F4EEE4', 'head': '#2C2420',
                                'snout': '#F4EEE4', 'ear': '#6A4A3A', 'inner': '#C89A8A', 'leg': '#F0D0C0',
                                'nose': '#C88A8A', 'eye': '#1E1A1A'}),
}

POSE0 = dict(front_drop=0.0, rear_drop=0.0, lie=0.0, head_pitch=0.0, head_yaw=0.0, head_roll=0.0,
             legs=(0.0, 0.0, 0.0, 0.0), lift=(0.0, 0.0, 0.0, 0.0), tail_yaw=0.0, tail_pitch=0.0,
             ear=0.0, eyes=1.0, up=0.0, breathe=0.0, curl=0.0, scratch=0.0, body_yaw=0.0)


def quad_parts(spec, pose):
    """The parts of a four-legged pet in a pose: [(tris, None, rgb)]."""
    p = dict(POSE0)
    p.update(pose)
    col = {k: C(v) for k, v in spec['colours'].items()}
    bx, by, bz = spec['body']
    leg = spec['leg']
    lr = spec['leg_r']
    sw = spec['shoulder_w']
    out = []

    def add(tris, c):
        out.append((tris, None, col.get(c, col['body'])))

    # Body: from the hips to the shoulders. Sitting lowers the hips, lying lowers both (to the floor).
    lie = p['lie']
    stand_y = leg + by * 0.55
    floor_y = by * 0.95
    sh_y = stand_y + (floor_y - stand_y) * lie - p['front_drop'] * leg + p['up']
    hip_y = stand_y + (floor_y - stand_y) * lie - p['rear_drop'] * leg + p['up']
    half = bz * 0.62
    sh = np.array([0.0, sh_y, half])
    hip = np.array([0.0, hip_y, -half])
    pitch = -math.degrees(math.atan2(sh_y - hip_y, 2 * half))
    mid = (sh + hip) / 2
    R_body = rot(pitch, p['body_yaw'])
    body = Xf(mid, R_body)
    k = 1.0 + 0.03 * p['breathe']
    add(body.put(blob((bx * k, by * k, bz), n=10)), 'body')
    add(body.put(move(blob((bx * 0.85, by * 0.55, bz * 0.85), n=8), (0, -by * 0.42, 0.01))), 'belly')
    if 'saddle' in col and spec['colours']['saddle'] != spec['colours']['body']:
        add(body.put(move(blob((bx * 0.9, by * 0.6, bz * 0.62), n=8), (0, by * 0.48, -bz * 0.12))), 'saddle')

    # Legs: front pair at the shoulders, back pair at the hips. legs[] swing (degrees, + forward);
    # lying, the front legs point forward along the floor and the back legs tuck under.
    shoulders = [body.at((s * sw, -by * 0.3, half)) for s in (-1, 1)]
    hips = [body.at((s * sw, -by * 0.3, -half)) for s in (-1, 1)]
    for i, top in enumerate(shoulders + hips):
        front = i < 2
        swing = p['legs'][i]
        lift = p['lift'][i]
        if spec.get('rear') == 'haunch' and not front:          # a rabbit's big folded back legs
            add(move(blob((bx * 0.55, by * 0.55, bz * 0.5), n=8), (top[0] * 1.1, max(top[1] - 0.01, by * 0.5),
                                                                   top[2] + 0.01)), 'body')
            foot = np.array([top[0], spec['paw'] * 0.6 + lift * 0.02, top[2] + bz * 0.35])
            add(tube(foot - (0, 0, bz * 0.3), foot + (0, 0, bz * 0.05), spec['paw'] * 0.7, n=6), 'leg')
            continue
        length = max(top[1] - spec['paw'] * 0.6, 0.0)
        if lie > 0.5:
            d = np.array([0, -0.15, 1.0]) if front else np.array([0, -0.1, 0.9])
            d /= np.linalg.norm(d)
            foot = top + d * leg * (0.9 if front else 0.6)
            foot[1] = spec['paw'] * 0.6
        elif not front and p['rear_drop'] > 0.4:                  # sitting: thigh folded, paw forward
            add(move(blob((lr * 1.9, lr * 2.2, bz * 0.42), n=8), (top[0], top[1], top[2] + 0.01)), 'body')
            foot = np.array([top[0], spec['paw'] * 0.6, top[2] + bz * 0.55])
            if i == 3 and p['scratch']:                            # a back paw up to the ear
                foot = body.at((sw * 1.6, by * 0.9, half * 1.3)) + (0, 0.02 * math.sin(p['scratch'] * 6.28), 0)
        else:
            a = math.radians(swing)
            foot = top + np.array([0, -length * math.cos(a), length * math.sin(a)])
            foot[1] = max(foot[1], spec['paw'] * 0.6) + lift * leg * 0.25
        add(tube(top, foot, lr * 1.15, lr, n=6, caps=False), 'leg')
        add(move(blob((spec['paw'], spec['paw'] * 0.6, spec['paw'] * 1.2), n=5), foot), 'paw' if 'paw' in col else 'leg')

    # Head on the neck, from the shoulders.
    nx, ny, nz = spec['neck']
    neck_base = body.at((0, by * 0.35, half * 0.9))
    head_R = rot(p['head_pitch'], p['head_yaw'] + p['body_yaw'] * 0.5, p['head_roll'])
    head = Xf(neck_base, head_R).then((nx, ny, nz - half * 0.9 + bz * 0.25))
    add(tube(neck_base, head.at((0, -spec['head'][1] * 0.3, -spec['head'][2] * 0.3)), spec['head'][0] * 0.55,
             n=6, caps=False), 'body')
    hx, hy, hz = spec['head']
    add(head.put(blob((hx, hy, hz), n=9)), 'head')
    sx, sy, sz = spec['snout']
    snout_c = (0, -hy * 0.3, hz * 0.75 + sz * 0.4)
    add(head.put(move(blob((sx, sy, sz), n=7), snout_c)), 'snout')
    add(head.put(move(blob((sx * 0.38, sy * 0.33, sz * 0.25), n=4), (0, snout_c[1] + sy * 0.55, snout_c[2] + sz * 0.85))),
        'nose')
    if p['eyes'] > 0.5:
        for s in (-1, 1):
            add(head.put(move(blob((hx * 0.16, hy * 0.2, hz * 0.12), n=4), (s * hx * 0.48, hy * 0.18, hz * 0.8))), 'eye')
    ex, ey, ez = spec['ear']
    for s in (-1, 1):
        if spec['ears'] == 'floppy':
            R = rot(0, 0, s * (12 + 25 * p['ear']))
            add(head.put(move(blob((ex, ey, ez), n=6), (s * hx * 1.02, -ey * 0.25, -hz * 0.1), R)), 'ear')
        elif spec['ears'] == 'pointy':
            base = head.at((s * hx * 0.6, hy * 0.75, -hz * 0.05))
            R = head_R @ rot(-10 - 30 * p['ear'], 0, s * (-18 - 20 * p['ear']))
            tip = base + R @ np.array([0, ey, 0])
            add(tube(base, tip, ex, ex * 0.12, n=5, caps=False), 'ear')
            add(tube(base + R @ np.array([0, ey * 0.1, ez]), tip + R @ np.array([0, -ey * 0.2, ez * 0.6]), ex * 0.55,
                     ex * 0.08, n=4, caps=False), 'inner')
        elif spec['ears'] == 'long':
            base = head.at((s * hx * 0.38, hy * 0.75, -hz * 0.3))
            R = head_R @ rot(-12 - 60 * p['ear'], 0, s * -10)
            add(move(blob((ex, ey, ez * 2.2), n=6), base + R @ np.array([0, ey * 0.9, 0]), R), 'ear')
            add(move(blob((ex * 0.6, ey * 0.85, ez * 1.2), n=5), base + R @ np.array([0, ey * 0.9, ez * 1.3]), R), 'inner')
        elif spec['ears'] == 'round':
            add(head.put(move(blob((ex, ey, ez), n=5), (s * hx * 0.62, hy * 0.78, -hz * 0.15))), 'ear')

    # Tail from the hips.
    base = body.at((0, by * 0.45, -bz * 0.92))
    if spec['tail'] == 'puff':
        add(move(blob((spec['tail_r'],) * 3, n=6), body.at((0, by * 0.25, -bz * 1.02))), 'tail')
    elif spec['tail'] in ('up', 'long'):
        # elevation of each segment above the horizontal, going back from the hips: a dog's tail goes up,
        # a cat's starts down and curls up at the end (J); tail_pitch adds to it (sad: down, happy: up).
        n = 5
        pts = [base]
        seg = spec['tail_len'] / n
        for j in range(n):
            if spec['tail'] == 'up':
                e = 45 + 6 * j + p['tail_pitch'] - p['curl'] * 20 * j
            else:
                e = -35 + 22 * j + p['tail_pitch'] * (1 - j / n) - p['curl'] * 30 * j
            yaw = math.radians(p['tail_yaw'] * (j + 1) / n + p['body_yaw'])
            er = math.radians(e)
            d = np.array([-math.sin(yaw) * math.cos(er), math.sin(er), -math.cos(yaw) * math.cos(er)])
            nxt = pts[-1] + d * seg
            nxt[1] = max(nxt[1], spec['tail_r'])
            pts.append(nxt)
        for j in range(n):
            r0 = spec['tail_r'] * (1 - 0.12 * j)
            add(tube(pts[j], pts[j + 1], r0, r0 * 0.88, n=5), 'tip' if j == n - 1 and 'tip' in col else 'tail')
    return out


def _wave(t, k=1.0, ph=0.0):
    return math.sin(2 * math.pi * (k * t + ph))


def quad_action(name, t, kind):
    """The pose of a four-legged pet at time t (0-1) through an action."""
    small = kind in ('hamster', 'guinea_pig')
    w = _wave(t)
    p = {}
    if name == 'stand':
        p = dict(breathe=w, tail_yaw=12 * _wave(t, 2), head_yaw=8 * _wave(t, 1, 0.25), ear=0.1 * w)
    elif name == 'walk':
        a = 24 if not small else 30
        p = dict(legs=(a * w, -a * w, -a * w, a * w), lift=(max(0, w), max(0, -w), max(0, -w), max(0, w)),
                 up=0.006 * abs(w), tail_yaw=15 * _wave(t, 2), head_pitch=3 * _wave(t, 2))
        if kind == 'bunny':
            hop = abs(math.sin(math.pi * t * 2))
            p = dict(up=0.045 * hop, legs=(20 * hop, 20 * hop, 0, 0), front_drop=-0.2 * hop, ear=0.2 * hop)
    elif name == 'sit':
        p = dict(rear_drop=0.75 if kind != 'bunny' else 0.3, front_drop=-0.05, head_pitch=-12, breathe=w,
                 tail_yaw=8 * _wave(t, 1), head_yaw=10 * _wave(t, 1, 0.3), curl=0.3)
    elif name == 'lie':
        p = dict(lie=1.0, head_pitch=-5, breathe=w, tail_yaw=10 * _wave(t, 1), head_yaw=15 * _wave(t, 1, 0.2))
    elif name == 'sleep':
        p = dict(lie=1.0, head_pitch=30, head_yaw=-25, eyes=0.0, breathe=w, ear=0.4, curl=1.0, tail_yaw=60,
                 tail_pitch=-50, body_yaw=8)
    elif name == 'sniff':
        p = dict(front_drop=0.25, head_pitch=28, head_yaw=25 * _wave(t, 1), legs=(5 * w, -5 * w, 0, 0),
                 tail_yaw=10 * _wave(t, 2), ear=0.2)
    elif name == 'play':
        if kind == 'kitten':
            pounce = max(0.0, _wave(t, 1))
            p = dict(front_drop=0.35 - 0.5 * pounce, rear_drop=-0.05, up=0.03 * pounce, head_pitch=-10 + 20 * pounce,
                     legs=(-30 * pounce, -30 * pounce, -10, -10), tail_yaw=30 * _wave(t, 3), tail_pitch=-10)
        else:                                                  # a play bow and a happy bounce
            b = abs(_wave(t, 1))
            p = dict(front_drop=0.45 * (1 - b), up=0.025 * b, head_pitch=-15, legs=(30, 30, -5, -5),
                     tail_yaw=35 * _wave(t, 4), ear=0.3 * b, body_yaw=10 * _wave(t, 1))
    elif name == 'eat':
        p = dict(front_drop=0.3, head_pitch=38 + 8 * abs(_wave(t, 3)), tail_yaw=8 * _wave(t, 2))
    elif name == 'happy':
        j = abs(math.sin(math.pi * t * 2))
        p = dict(up=0.04 * j, legs=(-15 * j, -15 * j, 10 * j, 10 * j), tail_yaw=40 * _wave(t, 4), head_pitch=-15,
                 ear=0.5 * j, head_roll=10 * _wave(t, 1))
    elif name == 'sad':
        p = dict(front_drop=0.1, head_pitch=25, ear=1.0, tail_pitch=-95, breathe=0.5 * w)
    elif name == 'petted':
        p = dict(rear_drop=0.6, head_pitch=-25, head_roll=12 * _wave(t, 1), eyes=0.0, tail_yaw=30 * _wave(t, 3),
                 ear=0.6)
    elif name == 'scratch':
        p = dict(rear_drop=0.75, head_pitch=-5, head_roll=-15, head_yaw=-15, scratch=t * 4 % 1 + 0.01, eyes=0.0)
    if small and name in ('sit', 'petted', 'scratch'):         # small rodents sit up instead
        p = dict(rear_drop=0.2, front_drop=-0.6, head_pitch=-20, head_yaw=15 * _wave(t, 1), breathe=w)
    return p


# ------------------------------------------------------------------ birds

BIRDS = {
    'cockatoo': dict(colours={'body': '#F4F2EA', 'wing': '#E8E4D6', 'tail': '#E8E4D6', 'crest': '#F2D23C',
                              'beak': '#3A3A40', 'leg': '#6A6A72', 'eye': '#1E1A1A', 'cheek': '#F4F2EA',
                              'under': '#F2E8A8'}, crest=True, tail_len=0.11),
    'macaw': dict(colours={'body': '#F2B42C', 'wing': '#2A6CD0', 'tail': '#2A6CD0', 'crest': '#3FA048',
                           'beak': '#2A2A30', 'leg': '#5A5A62', 'eye': '#1E1A1A', 'cheek': '#F4F2EA',
                           'under': '#1E4E9E'}, crest=False, tail_len=0.2),
}


def bird_parts(kind, pose):
    spec = BIRDS[kind]
    col = {k: C(v) for k, v in spec['colours'].items()}
    p = dict(lean=0.0, head_pitch=0.0, head_yaw=0.0, flap=0.0, up=0.0, fluff=0.0, eyes=1.0, step=0.0, tuck=0.0,
             crest=0.0)
    p.update(pose)
    out = []

    def add(tris, c):
        out.append((tris, None, col[c]))

    leg_h = 0.03
    tilt = 30 + p['lean']                                     # body leans forward from upright
    body = Xf((0, leg_h + 0.06 + p['up'], 0), rot(tilt))
    f = 1 + 0.15 * p['fluff']
    add(body.put(blob((0.04 * f, 0.07 * f, 0.042 * f), n=9)), 'body')
    add(body.put(move(blob((0.032 * f, 0.05 * f, 0.02), n=6), (0, -0.01, 0.026 * f))), 'under')
    for s in (-1, 1):                                          # wings: folded at the side, open to flap
        a = p['flap']
        R = rot(-8, 0, s * (6 + 70 * a))
        add(body.put(move(blob((0.012, 0.06, 0.034), n=6), (s * 0.038 * f, 0.0, -0.008), R)), 'wing')
    tail_base = body.at((0, -0.06, -0.01))
    tail_dir = np.array([0, -0.45, -1.0])
    tail_dir /= np.linalg.norm(tail_dir)
    tip = tail_base + tail_dir * spec['tail_len']
    tip[1] = max(tip[1], 0.006)
    add(tube(tail_base, tip, 0.016, 0.006, n=5), 'tail')
    for s in (-1, 1):
        hip = np.array([s * 0.016, leg_h + 0.02 + p['up'], 0.005])
        step = p['step'] * s
        foot = np.array([s * 0.018, 0.004 + max(0, step) * 0.015, 0.012 + step * 0.012])
        add(tube(hip, foot, 0.005, 0.004, n=4), 'leg')
        add(move(blob((0.008, 0.003, 0.012), n=4), foot), 'leg')
    neck = body.at((0, 0.06, 0.012))
    hR = rot(-tilt + p['head_pitch'] + 10, p['head_yaw'])
    head = Xf(neck + (0, 0.02 - 0.03 * p['tuck'], 0.008), hR)
    add(head.put(blob((0.03, 0.03, 0.03), n=8)), 'body')
    add(head.put(move(blob((0.018, 0.016, 0.012), n=5), (0, -0.005, 0.02))), 'cheek')
    add(head.put(move(blob((0.012, 0.016, 0.014), n=5), (0, -0.004, 0.034), rot(25))), 'beak')
    if p['eyes'] > 0.5:
        for s in (-1, 1):
            add(head.put(move(blob((0.004, 0.005, 0.004), n=3), (s * 0.022, 0.007, 0.016))), 'eye')
    if spec['crest']:
        for j, (dz, h) in enumerate(((0.0, 0.05), (-0.012, 0.045), (-0.022, 0.035))):
            base = head.at((0, 0.025, dz))
            R = hR @ rot(-20 - 25 * j + 40 * p['crest'])
            add(tube(base, base + R @ np.array([0, h, -0.02]), 0.007, 0.002, n=4, caps=False), 'crest')
    else:
        add(head.put(move(blob((0.022, 0.012, 0.02), n=5), (0, 0.022, 0.01))), 'crest')
    return out


def bird_action(name, t, kind):
    w = _wave(t)
    if name == 'stand':
        return dict(head_yaw=25 * _wave(t, 1, 0.1), head_pitch=5 * w)
    if name == 'walk':
        return dict(step=w, lean=6, head_pitch=6 * _wave(t, 2), up=0.004 * abs(w))
    if name in ('sit', 'lie'):
        return dict(fluff=0.6, head_yaw=20 * _wave(t, 1), lean=-5)
    if name == 'sleep':
        return dict(fluff=1.0, tuck=1.0, head_yaw=150, head_pitch=20, eyes=0.0, lean=-5)
    if name == 'sniff':
        return dict(head_pitch=30 + 10 * w, head_yaw=40 * _wave(t, 1), lean=10)
    if name == 'play':
        return dict(flap=0.5 + 0.5 * _wave(t, 3), up=0.01 * abs(w), head_pitch=-10, crest=1.0)
    if name == 'eat':
        return dict(lean=35, head_pitch=40 + 10 * abs(_wave(t, 3)))
    if name == 'happy':
        return dict(flap=0.5 + 0.5 * _wave(t, 4), up=0.03 * abs(math.sin(math.pi * t * 2)), crest=1.0, head_pitch=-15)
    if name == 'sad':
        return dict(fluff=0.4, head_pitch=25, lean=10)
    if name == 'petted':
        return dict(head_pitch=30, head_yaw=-20, eyes=0.0, fluff=0.5, crest=0.6)
    if name == 'scratch':
        return dict(head_yaw=-110, head_pitch=35 + 8 * _wave(t, 3), lean=5)   # preening
    return {}


# ------------------------------------------------------------------ the snake

SNAKE = {'body': C('#E2622A'), 'band': C('#B8341E'), 'belly': C('#F2D8A0'), 'eye': C('#1E1A1A'),
         'tongue': C('#C8243A')}


def snake_parts(pose):
    p = dict(raise_=0.6, sway=0.0, coil=1.0, slither=0.0, eyes=1.0, tongue=0.0, head_pitch=0.0)
    p.update(pose)
    n = 26
    L = 0.75
    r_max = 0.018
    pts = []
    for j in range(n):
        s = j / (n - 1)                                        # 0 = tail tip, 1 = head
        if p['coil'] > 0:                                      # a coil on the floor, the front raised
            ang = s * 4.2 * math.pi * p['coil'] + (1 - p['coil']) * 0
            rad = 0.025 + 0.05 * (1 - s)
            x, z = rad * math.cos(ang), rad * math.sin(ang)
            y = r_max
            if s > 0.62:
                lift = (s - 0.62) / 0.38
                y += p['raise_'] * 0.14 * lift ** 1.4
                x += p['sway'] * 0.05 * math.sin(lift * 3.0) * lift
                z += 0.06 * lift
            x = x * p['coil'] + (1 - p['coil']) * 0.03 * math.sin(s * 9 + p['slither'] * 6.28)
            z = z * p['coil'] + (1 - p['coil']) * (s - 0.5) * L * 0.6
        else:
            x = 0.03 * math.sin(s * 9 + p['slither'] * 6.28)
            z = (s - 0.5) * L * 0.45
            y = r_max
        pts.append(np.array([x, y, z]))
    out = []
    for j in range(n - 1):
        s = j / (n - 1)
        r = r_max * (0.35 + 0.65 * min(1.0, 3 * s)) * (1 - 0.25 * max(0, s - 0.85) / 0.15)
        c = SNAKE['band'] if (j // 2) % 3 == 0 else SNAKE['body']
        out.append((tube(pts[j], pts[j + 1], r, r, n=6), None, c))
    head = pts[-1]
    d = pts[-1] - pts[-3]
    d /= np.linalg.norm(d) + 1e-9
    yaw = math.degrees(math.atan2(d[0], d[2]))
    pitch = -math.degrees(math.asin(max(-1, min(1, d[1])))) + p['head_pitch']
    hd = Xf(head, rot(pitch, yaw))
    out.append((hd.put(move(blob((0.019, 0.013, 0.028), n=7), (0, 0, 0.012))), None, SNAKE['body']))
    if p['eyes'] > 0.5:
        for s in (-1, 1):
            out.append((hd.put(move(blob((0.004, 0.004, 0.004), n=3), (s * 0.014, 0.006, 0.02))), None, SNAKE['eye']))
    if p['tongue'] > 0.5:
        out.append((tube(hd.at((0, -0.002, 0.04)), hd.at((0, -0.002, 0.06)), 0.002, 0.0015, n=3), None,
                    SNAKE['tongue']))
    return out


def snake_action(name, t):
    w = _wave(t)
    if name == 'walk':
        return dict(coil=0.0, slither=t, raise_=0.0)
    if name in ('lie', 'sleep'):
        return dict(raise_=0.0, eyes=0.0 if name == 'sleep' else 1.0, coil=1.0)
    if name in ('sniff', 'eat'):
        return dict(raise_=0.4, sway=0.4 * w, tongue=1.0 if (t * 4) % 1 < 0.5 else 0.0, head_pitch=25)
    if name in ('play', 'happy'):
        return dict(raise_=0.9, sway=1.0 * _wave(t, 2))
    if name == 'sad':
        return dict(raise_=0.15)
    return dict(raise_=0.6, sway=0.35 * w, tongue=1.0 if name == 'stand' and t > 0.8 else 0.0)


# ------------------------------------------------------------------ pets as import models

PET_KINDS = {'puppy': 'quad', 'kitten': 'quad', 'bunny': 'quad', 'hamster': 'quad', 'guinea_pig': 'quad',
             'cockatoo': 'bird', 'macaw': 'bird', 'snake': 'snake'}
ACTIONS = ['stand', 'walk', 'sit', 'lie', 'sleep', 'sniff', 'play', 'eat', 'happy', 'sad', 'petted', 'scratch']
FRAMES = 16                         # frames in one loop of an action (sampled down by the importer)
PET_LOD = 0.6                       # pets' shapes at 60% detail: the same at 9-28 pixels, a third of the drawing time
HEIGHT = {'puppy': 28, 'kitten': 23, 'bunny': 18, 'hamster': 9, 'guinea_pig': 10, 'cockatoo': 20, 'macaw': 20,
          'snake': 18}             # Urbz pixels standing (like the Apartment Pets animals)
HOP = {'bunny': 0.0, 'hamster': 0.0, 'guinea_pig': 0.0, 'cockatoo': 0.0, 'macaw': 0.0}


def pet_parts(name, action, t):
    kind = PET_KINDS[name]
    if kind == 'quad':
        return quad_parts(QUAD[name], quad_action(action, t, name))
    if kind == 'bird':
        return bird_parts(name, bird_action(action, t, name))
    return snake_parts(snake_action(action, t))


# ------------------------------------------------------------------ pet beds and furniture
# Each one: a function returning [(tris, None, rgb)], in metres, facing +Z, centred on its footprint.

def _wood_legs(out, xs, zs, h, r, c):
    for x in xs:
        for z in zs:
            out.append((tube((x, 0, z), (x, h, z), r, r, n=6, caps=False), None, c))


def dog_basket():
    """Big enough for the Puppy (pets are drawn about twice furniture's scale: a 28-pixel dog)."""
    return [(disc_ring(0.5, 0.42, 0.22, n=20), None, C('#B07A3E')),          # wicker
            (move(disc_ring(0.51, 0.45, 0.03, n=20), (0, 0.2, 0)), None, C('#8A5A2C')),
            (move(blob((0.44, 0.06, 0.44), e1=0.6, n=12), (0, 0.07, 0)), None, C('#C8443C'))]   # cushion


def cat_bed():
    return [(move(blob((0.4, 0.07, 0.4), e1=0.7, n=12), (0, 0.06, 0)), None, C('#7A5AA8')),
            (move(disc_ring(0.41, 0.3, 0.15, n=20), (0, 0.04, 0)), None, C('#6A4A98')),
            (move(disc_ring(0.42, 0.29, 0.035, n=20), (0, 0.18, 0)), None, C('#8A6AB8')),
            (move(blob((0.3, 0.045, 0.3), e1=0.5, n=10), (0, 0.11, 0)), None, C('#E6D8F0'))]


def rabbit_hutch():
    wood, dark, mesh, roof = C('#A8743A'), C('#7A5028'), C('#B8C0C4'), C('#5A3A22')
    out = []
    _wood_legs(out, (-0.36, 0.36), (-0.2, 0.2), 0.16, 0.025, dark)
    out.append((move(box((0.8, 0.04, 0.46)), (0, 0.18, 0)), None, dark))
    out.append((move(box((0.8, 0.34, 0.03)), (0, 0.37, -0.215)), None, wood))       # back
    for x in (-0.385, 0.385):
        out.append((move(box((0.03, 0.34, 0.46)), (x, 0.37, 0)), None, wood))
    out.append((move(box((0.3, 0.34, 0.03)), (-0.24, 0.37, 0.215)), None, wood))     # closed side of the front
    out.append((move(box((0.46, 0.32, 0.01)), (0.15, 0.37, 0.22)), None, mesh))      # mesh door
    for x in np.linspace(-0.07, 0.37, 6):
        out.append((move(box((0.012, 0.32, 0.015)), (x, 0.37, 0.225)), None, dark))
    out.append((move(box((0.88, 0.04, 0.54)), (0, 0.56, 0), rot(-8)), None, roof))
    return out


def small_pet_house():
    wood, roof, door = C('#C89050'), C('#B8462E'), C('#4A2C1A')
    out = [(move(box((0.34, 0.2, 0.26)), (0, 0.1, 0)), None, wood)]
    for s in (-1, 1):
        out.append((move(box((0.2, 0.02, 0.32)), (s * 0.085, 0.25, 0), rot(0, 0, -s * 35)), None, roof))
    out.append((move(blob((0.055, 0.065, 0.01), n=8), (0, 0.075, 0.132)), None, door))
    return out


def bird_cage():
    """A round cage on a short stand: bars, rings and a wire dome you can see through."""
    metal, base, perch, tray = C('#D8B848'), C('#5A5A62'), C('#8A5A2C'), C('#3A3A44')
    out = [(move(blob((0.2, 0.025, 0.2), n=10), (0, 0.015, 0)), None, base),
           (tube((0, 0.0, 0), (0, 0.4, 0), 0.022, 0.018, n=6), None, base),
           (move(blob((0.24, 0.03, 0.24), e1=0.4, n=12), (0, 0.43, 0)), None, tray)]
    r, y0, y1 = 0.22, 0.45, 0.8
    for k in range(12):                                                        # bars, and over the dome
        a = 2 * math.pi * k / 12
        x, z = r * math.sin(a), r * math.cos(a)
        out.append((tube((x, y0, z), (x, y1, z), 0.006, 0.006, n=4, caps=False), None, metal))
        prev = (x, y1, z)
        for m in range(1, 5):
            t = m / 4 * math.pi / 2
            q = (r * math.cos(t) * math.sin(a), y1 + 0.16 * math.sin(t), r * math.cos(t) * math.cos(a))
            out.append((tube(prev, q, 0.006, 0.006, n=4, caps=False), None, metal))
            prev = q
    for y in (y0 + 0.01, (y0 + y1) / 2, y1):
        out.append((move(disc_ring(r + 0.008, r - 0.008, 0.012, n=16), (0, y, 0)), None, metal))
    out.append((tube((-0.18, 0.6, 0), (0.18, 0.6, 0), 0.01, 0.01, n=4), None, perch))
    out.append((move(blob((0.03, 0.035, 0.03), n=5), (0, y1 + 0.18, 0)), None, metal))
    return out


def _sofa(width, colour, frame=None, seat_h=0.42, depth=0.88, back_h=0.82, arm_h=0.62, e=0.35, cushions=None,
          legs='#3A2A20', arm_w=0.16, camel=False):
    c, f = C(colour), C(frame or colour)
    out = []
    w2 = width / 2
    out.append((move(blob((w2 - 0.02, 0.12, depth / 2 - 0.02), e1=e, e2=e, n=10), (0, 0.2, 0)), None, f))  # base
    n = cushions or max(1, int(round((width - 2 * arm_w) / 0.6)))
    cw = (width - 2 * arm_w) / n
    for k in range(n):                                            # seat cushions
        x = -w2 + arm_w + cw * (k + 0.5)
        out.append((move(blob((cw / 2 - 0.01, 0.07, depth / 2 - 0.1), e1=e, e2=e, n=8), (x, seat_h - 0.05, 0.05)),
                    None, c))
    if camel:                                                     # a curved back, higher in the middle
        for k in range(5):
            x = -w2 + arm_w + (width - 2 * arm_w) * (k + 0.5) / 5
            h = back_h - 0.12 + 0.14 * math.cos((k - 2) / 2.5 * math.pi / 2)
            out.append((move(blob(((width - 2 * arm_w) / 10 + 0.04, h / 2, 0.1), e1=0.5, e2=0.5, n=7),
                             (x, h / 2 + 0.05, -depth / 2 + 0.1)), None, f))
    else:
        out.append((move(blob((w2 - 0.04, (back_h - 0.1) / 2, 0.1), e1=e, e2=e, n=10),
                         (0, (back_h - 0.1) / 2 + 0.1, -depth / 2 + 0.1)), None, f))
        for k in range(n):                                        # back cushions
            x = -w2 + arm_w + cw * (k + 0.5)
            out.append((move(blob((cw / 2 - 0.02, 0.17, 0.07), e1=e, e2=e, n=8), (x, seat_h + 0.2, -depth / 2 + 0.2),
                             rot(-10)), None, c))
    for s in (-1, 1):                                             # arms
        out.append((move(blob((arm_w / 2, arm_h / 2, depth / 2 - 0.02), e1=e, e2=e, n=8),
                         (s * (w2 - arm_w / 2), arm_h / 2 + 0.04, 0)), None, f))
    _wood_legs(out, (-w2 + 0.08, w2 - 0.08), (-depth / 2 + 0.08, depth / 2 - 0.08), 0.08, 0.025, C(legs))
    return out


def club_armchair():
    return _sofa(0.95, '#7A3E22', '#6A321A', cushions=1, arm_w=0.22, e=0.3)


def red_lounge_chair():
    out = _sofa(0.85, '#C8302C', '#A82424', cushions=1, arm_w=0.16, e=0.55, back_h=0.9, legs='#C8C8D0')
    return out


def club_sofa():
    return _sofa(2.1, '#3E6A4A', '#2E5A3A', cushions=3, arm_w=0.24, e=0.3)


def country_sofa():
    return _sofa(2.0, '#E2D2B0', '#8AA0C8', cushions=3, e=0.55, legs='#6A4A2A')


def leather_sofa():
    return _sofa(2.0, '#2E2A2C', '#262224', cushions=2, arm_w=0.2, e=0.4, legs='#888890')


def camelback_loveseat():
    return _sofa(1.5, '#8A2A3A', '#7A2030', cushions=2, arm_w=0.14, e=0.5, camel=True, back_h=0.9,
                 legs='#4A2A1A')


def mission_recliner():
    wood, cush = C('#8A5A2C'), C('#5A3A2A')
    out = []
    for s in (-1, 1):                                             # slatted wooden sides
        out.append((move(box((0.06, 0.06, 0.84)), (s * 0.4, 0.6, 0)), None, wood))
        for z in (-0.38, 0.38):
            out.append((move(box((0.06, 0.6, 0.06)), (s * 0.4, 0.3, z)), None, wood))
        for z in np.linspace(-0.25, 0.25, 4):
            out.append((move(box((0.03, 0.3, 0.04)), (s * 0.4, 0.38, z)), None, wood))
    out.append((move(blob((0.36, 0.08, 0.38), e1=0.35, e2=0.35, n=8), (0, 0.4, 0.04)), None, cush))
    out.append((move(blob((0.34, 0.32, 0.07), e1=0.35, e2=0.35, n=8), (0, 0.78, -0.36), rot(-18)), None, cush))
    out.append((move(blob((0.32, 0.06, 0.16), e1=0.4, e2=0.4, n=6), (0, 0.26, 0.5), rot(55)), None, cush))   # foot rest
    return out


def mission_dining_chair():
    wood, seat = C('#8A5A2C'), C('#5A3A2A')
    out = []
    _wood_legs(out, (-0.2, 0.2), (-0.2, 0.2), 0.45, 0.022, wood)
    out.append((move(box((0.46, 0.05, 0.46)), (0, 0.46, 0)), None, seat))
    for x in (-0.2, 0.2):
        out.append((tube((x, 0.45, -0.2), (x, 1.0, -0.21), 0.022, 0.022, n=6, caps=False), None, wood))
    out.append((move(box((0.44, 0.07, 0.03)), (0, 0.97, -0.21)), None, wood))
    for x in np.linspace(-0.12, 0.12, 4):
        out.append((move(box((0.035, 0.42, 0.02)), (x, 0.72, -0.21)), None, wood))
    return out


def bistro_table():
    top, metal = C('#4A3226'), C('#2A2A2E')
    return [(move(blob((0.45, 0.02, 0.45), e1=0.2, n=14), (0, 0.74, 0)), None, top),
            (tube((0, 0.02, 0), (0, 0.72, 0), 0.03, 0.03, n=6, caps=False), None, metal),
            (move(blob((0.24, 0.02, 0.24), e1=0.4, n=10), (0, 0.02, 0)), None, metal)]


def mission_dining_table():
    wood, dark = C('#9A6A3A'), C('#7A4E28')
    out = [(move(box((1.7, 0.05, 0.9)), (0, 0.74, 0)), None, wood),
           (move(box((1.56, 0.08, 0.76)), (0, 0.67, 0)), None, dark)]
    _wood_legs(out, (-0.78, 0.78), (-0.38, 0.38), 0.7, 0.035, dark)
    return out


def _bed(width, length, frame, sheet, blanket, posts=None, head_h=1.0, foot_h=0.55, metal=False):
    f, s, b = C(frame), C(sheet), C(blanket)
    out = []
    w2, l2 = width / 2, length / 2
    out.append((move(box((width, 0.2, length)), (0, 0.25, 0)), None, f))                 # frame
    out.append((move(blob((w2 - 0.03, 0.09, l2 - 0.04), e1=0.25, e2=0.25, n=8), (0, 0.42, 0)), None, s))   # mattress
    out.append((move(blob((w2 - 0.01, 0.06, l2 * 0.62), e1=0.3, e2=0.3, n=8), (0, 0.5, l2 * 0.36)), None, b))  # blanket
    pillows = 2 if width > 1.3 else 1
    for k in range(pillows):
        x = (k - (pillows - 1) / 2) * width / 2
        out.append((move(blob((width / (2 * pillows) - 0.06, 0.05, 0.13), e1=0.5, n=7), (x, 0.53, -l2 + 0.22)), None,
                    C('#F4F4F0')))
    for z, h in ((-l2, head_h), (l2, foot_h)):                                          # head and foot boards
        if metal:
            out.append((tube((-w2, h, z), (w2, h, z), 0.025, 0.025, n=6), None, f))
            for x in np.linspace(-w2 + 0.12, w2 - 0.12, 5):
                out.append((tube((x, 0.3, z), (x, h, z), 0.012, 0.012, n=4, caps=False), None, f))
        else:
            out.append((move(box((width, h - 0.3, 0.05)), (0, (h + 0.3) / 2, z)), None, f))
        for x in (-w2, w2):
            out.append((tube((x, 0, z), (x, h + (posts or 0), z), 0.035, 0.035, n=6), None, f))
    return out


def colonial_bed():
    return _bed(1.05, 2.05, '#F0EEE6', '#F4F4F0', '#5A7AB8', posts=0.25)


def brass_bed():
    return _bed(1.05, 2.05, '#D8B040', '#F4F4F0', '#B83A3A', metal=True, head_h=1.1, foot_h=0.75)


def mission_double_bed():
    return _bed(1.6, 2.1, '#8A5A2C', '#F4F4F0', '#3E6A4A', head_h=1.05, foot_h=0.6)


FURNITURE = {f.__name__: f for f in (dog_basket, cat_bed, rabbit_hutch, small_pet_house, bird_cage, club_armchair,
                                     red_lounge_chair, club_sofa, country_sofa, leather_sofa, camelback_loveseat,
                                     mission_recliner, mission_dining_chair, bistro_table, mission_dining_table,
                                     colonial_bed, brass_bed, mission_double_bed)}


# ------------------------------------------------------------------ the "kit" game for urbz_import

class Game:
    """The kit's models, looked up by urbz_import like a source game's."""
    id = 'kit'

    def models(self):
        out = [{'name': n, 'folder': 'kit/' + n, 'kind': 'pet', 'anims': {a: a for a in ACTIONS},
                'animal': {'anims': {'0-stand': 'stand', '1-walk': 'walk', '2-move': 'sniff', '3-move': 'sit',
                                     '4-move': 'happy'}, 'height': HEIGHT[n], 'hop': HOP.get(n, 0)},
                'actions': {a: a for a in ACTIONS}} for n in PET_KINDS]
        out += [{'name': n, 'folder': 'kit/' + n, 'kind': 'object', 'anims': {}} for n in FURNITURE]
        return out


class Model:
    """A kit model with the interface urbz_import.Model has: posed(anim, frame), frames(anim), height(), front."""

    def __init__(self, info):
        self.info = info
        self.front = 0.0
        self.texture_names = []
        self.name = info['name']

    def frames(self, anim):
        return FRAMES if anim else 1

    def posed(self, anim=None, frame=0):
        global LOD
        if self.info['kind'] == 'pet':
            LOD = PET_LOD
            try:
                return [(t[..., :8].copy(), None, c) for t, _x, c in pet_parts(self.name, anim or 'stand', (frame % FRAMES) / FRAMES)]
            finally:
                LOD = 1.0
        return [(t[..., :8].copy(), None, c) for t, _x, c in FURNITURE[self.name]()]

    def height(self):
        ys = np.concatenate([t[..., 1].ravel() for t, _x, _c in self.posed()])
        return float(ys.max())


# ------------------------------------------------------------------ preview

def sheet(name, out=None):
    """5 directions of a model (pets: one row per action, 4 moments each) -> PNG."""
    from PIL import Image, ImageDraw
    import urbz_import as I
    info = next(m for m in Game().models() if m['name'] == name)
    m = Model(info)
    Z = 3
    if info['kind'] == 'pet':
        ppm = HEIGHT[name] / max(m.height(), 0.01)
        cell = 64
        rows = []
        for a in [x for x in os.environ.get('ACTIONS', ','.join(ACTIONS)).split(',') if x]:
            row = []
            for d in range(5):
                for k in (0, 4, 8, 12) if d == 4 else (0,):
                    parts = m.posed(a, k)
                    img = I.rasterize(I.shadow_tris(parts) + parts, I.view(180 - 45 * d), ppm, (cell, cell), (32, 50))
                    row.append(Image.fromarray(img))
            rows.append((a, row))
        W = cell * len(rows[0][1])
        sh = Image.new('RGBA', (W * Z + 90, cell * len(rows) * Z), (60, 70, 60, 255))
        dr = ImageDraw.Draw(sh)
        for r, (a, row) in enumerate(rows):
            dr.text((4, r * cell * Z + 4), a, fill=(255, 255, 0, 255))
            for c, im in enumerate(row):
                sh.paste(im.resize((cell * Z, cell * Z), Image.NEAREST), (90 + c * cell * Z, r * cell * Z), im.resize((cell * Z, cell * Z), Image.NEAREST))
    else:
        cell = 160
        ims = [Image.fromarray(I.rasterize(m.posed(), I.view(y), I.PX_PER_M, (cell, cell), (80, 120)))
               for y in (135, -45, 0, 90)]
        sh = Image.new('RGBA', (cell * len(ims) * 2, cell * 2), (60, 70, 60, 255))
        for c, im in enumerate(ims):
            big = im.resize((cell * 2, cell * 2), Image.NEAREST)
            sh.paste(big, (c * cell * 2, 0), big)
    out = out or os.path.join(KIT, 'build', 'models', name + '.png')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sh.save(out)
    return out


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    if argv[0] == 'list':
        for m in Game().models():
            print('%-22s %s' % (m['name'], m['kind']))
    elif argv[0] == 'show':
        print(sheet(argv[1], argv[2] if len(argv) > 2 else None))
    else:
        sys.exit('unknown command %s (list, show)' % argv[0])


if __name__ == '__main__':
    main(sys.argv[1:])
