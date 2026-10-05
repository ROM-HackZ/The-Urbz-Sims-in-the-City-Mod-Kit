#!/usr/bin/env python3
"""Bring pets and furniture over from other Sims DS games: render their 3D models the way The Urbz
draws its world (2D sprites seen from above at a fixed angle), at Urbz size, in 16 colours.

  python urbz_import.py sources                        which source games are set up (sources.json)
  python urbz_import.py gallery [game ...]             render every model -> catalog/imports/index.html
                                                       (naming games lists only those; images are cached)
  python urbz_import.py show GAME MODEL [out.png]      one model: 5 directions (+ walk frames for pets)

To bring a model over, name it in a mod: objects.json {"id": 440, "like": 136, ..., "import": {"from":
"aptpets", "model": "armchair4"}} or pets.json {"name": "Puppy", ..., "import": {"from": "aptpets", "model":
"dog"}}. The builder renders it every build (README "Importing from other Sims games").

sources.json (next to this file; local, never committed) names your own copies of the games (.nds, or a
.zip holding one, unpacked once into build/sources):
  {"aptpets": "D:/ROMS/Sims 2 - Apartment Pets.nds", "castaway": "...", "sims3": "...", "sims2": "..."}

The Urbz camera (docs/systems.md "The Urbz camera"): orthographic, 45 degrees round, 30 degrees down
(floor tiles are 2:1), about 42 pixels per metre. Nothing from the source games goes into git: mods keep
only the "import" entries, and the art is made from your ROMs when you build.
"""
import json, os, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
SOURCES = os.path.join(KIT, 'sources.json')
GALLERY = os.path.join(KIT, 'catalog', 'imports')

PITCH = 30.0            # degrees down from horizontal (2:1 floor tiles)
PX_PER_M = 42.0         # Urbz pixels per metre (a 1.75 m person is ~64 px tall)
LIGHT = (-0.45, 0.8, 0.55)   # from the upper left, in front (view space)
SIMS3_FRONT = 180.0          # The Sims 3's furniture faces -Z
SIMS2_FRONT, SIMS2_UNIT = 180.0, 0.125   # The Sims 2 (DS): faces -Z; 8 units a metre (a chair is 6.6 units)


# ------------------------------------------------------------------ rendering

def view(yaw_deg, pitch_deg=PITCH):
    """Rotation from model space (Y up, the model faces +Z) to view space (X right, Y up, +Z to the eye).
    yaw 0 = the model faces the viewer; positive yaw turns it to face screen-right."""
    import numpy as np
    y, p = np.radians(yaw_deg), np.radians(pitch_deg)
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    return Rx @ Ry


def rasterize(parts, R, px_per_unit, size, anchor, supersample=3, ambient=0.5):
    """parts: [(tris [N,3,>=8] x y z u v nx ny nz, texture RGBA or None, (r, g, b))].
    The model's floor origin (0, 0, 0) lands on pixel `anchor`. -> RGBA uint8 [h, w, 4]."""
    import numpy as np
    W, H = size[0] * supersample, size[1] * supersample
    sc = px_per_unit * supersample
    col = np.zeros((H, W, 4), np.float32)
    zb = np.full((H, W), -1e9, np.float32)
    L = np.array(LIGHT, np.float32)
    L /= np.linalg.norm(L)
    ax, ay = (anchor[0] + 0.5) * supersample, (anchor[1] + 0.5) * supersample
    for tris, tex, rgb in parts:
        if len(tris) == 0:
            continue
        P = tris[..., :3] @ R.T
        SX, SY = P[..., 0] * sc + ax, -P[..., 1] * sc + ay
        N = tris[..., 5:8] @ R.T
        for t in range(len(tris)):
            x, y, z = SX[t], SY[t], P[t, :, 2]
            x0, x1 = int(max(0, np.floor(x.min()))), int(min(W - 1, np.ceil(x.max())))
            y0, y1 = int(max(0, np.floor(y.min()))), int(min(H - 1, np.ceil(y.max())))
            if x0 > x1 or y0 > y1:
                continue
            d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
            if abs(d) < 1e-12:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
            b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
            c = 1 - a - b
            m = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
            if not m.any():
                continue
            zz = a * z[0] + b * z[1] + c * z[2]
            sub = zb[y0:y1 + 1, x0:x1 + 1]
            m &= zz > sub
            if not m.any():
                continue
            if tex is not None:
                u = a * tris[t, 0, 3] + b * tris[t, 1, 3] + c * tris[t, 2, 3]
                v = a * tris[t, 0, 4] + b * tris[t, 1, 4] + c * tris[t, 2, 4]
                th, tw = tex.shape[:2]
                texel = tex[np.floor(v * th).astype(int) % th, np.floor(u * tw).astype(int) % tw].astype(np.float32)
                m &= texel[..., 3] > 127
                if not m.any():
                    continue
                rgbv = texel[..., :3] * (np.array(rgb, np.float32) / 255.0)
            else:
                rgbv = np.broadcast_to(np.array(rgb, np.float32), gx.shape + (3,))
            n = a[..., None] * N[t, 0] + b[..., None] * N[t, 1] + c[..., None] * N[t, 2]
            n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
            shade = ambient + (1 - ambient) * np.clip(np.abs(n @ L), 0, 1)
            sub[m] = zz[m]
            reg = col[y0:y1 + 1, x0:x1 + 1]
            reg[m, :3] = rgbv[m] * shade[m, None]
            reg[m, 3] = 255
    img = col.reshape(size[1], supersample, size[0], supersample, 4).mean((1, 3))
    rgb = np.where(img[..., 3:] > 0, img[..., :3] * 255.0 / np.maximum(img[..., 3:], 1e-3), 0)
    out = np.concatenate([rgb, img[..., 3:]], -1)
    out[..., 3] = np.where(img[..., 3] >= 128, 255, 0)      # sprites are either drawn or not
    return np.clip(out, 0, 255).astype(np.uint8)


def to_16_colours(img, colours=15, outline=None):
    """Cut an RGBA render to `colours` colours + see-through (index 0). -> (PIL 'P' image, palette)"""
    from PIL import Image
    import numpy as np
    a = img[..., 3] > 0
    if outline:
        edge = a & ~(np.roll(a, 1, 0) & np.roll(a, -1, 0) & np.roll(a, 1, 1) & np.roll(a, -1, 1))
        img = img.copy()
        img[edge, :3] = (img[edge, :3] * 0.45).astype(np.uint8)
    rgb = Image.fromarray(img[..., :3])
    q = rgb.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    idx = np.array(q) + 1
    idx[~a] = 0
    pal = [(0, 0, 0)] + [tuple(q.getpalette()[3 * i:3 * i + 3]) for i in range(colours)]
    out = Image.fromarray(idx.astype(np.uint8), 'P')
    flat = [c for rgb_ in pal for c in rgb_] + [0] * (768 - 3 * len(pal))
    out.putpalette(flat)
    out.info['transparency'] = 0
    return out, pal


# ------------------------------------------------------------------ sources

def sources():
    return json.load(open(SOURCES)) if os.path.exists(SOURCES) else {}


_GAMES = {}


class SourceMissing(Exception):
    """A mod imports from a game this computer has no copy of (sources.json)."""


def _rom_path(name, path):
    """A source may be a .nds or a .zip holding one: a zip is unpacked once into build/sources/."""
    if not path.lower().endswith('.zip'):
        return path
    import zipfile
    out = os.path.join(KIT, 'build', 'sources', name + '.nds')
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(path):
        return out
    with zipfile.ZipFile(path) as z:
        nds = [n for n in z.namelist() if n.lower().endswith('.nds')]
        if not nds:
            raise SourceMissing('%s: no .nds inside' % path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with z.open(nds[0]) as f, open(out + '.part', 'wb') as o:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                o.write(b)
    os.replace(out + '.part', out)
    return out


def game(name):
    if name not in _GAMES:
        src = dict(sources())
        if name not in src or not os.path.exists(src[name]):
            raise SourceMissing('no copy of "%s" set up in sources.json (python urbz_import.py help)' % name)
        src[name] = _rom_path(name, src[name])
        if name == 'sims3':
            import urbz_sims3
            _GAMES[name] = urbz_sims3.Game(src[name])
        elif name == 'sims2':
            import urbz_nsbmd
            _GAMES[name] = urbz_nsbmd.Game(src[name])
        else:
            import urbz_fullfat
            _GAMES[name] = urbz_fullfat.Game(src[name])
    return _GAMES[name]


class Model:
    """A Full Fat model ready to render: its parts with textures, its skeleton and animations."""

    def __init__(self, g, info, texture_swap=None, colour=0):
        import numpy as np
        import urbz_fullfat as F
        self.g, self.info = g, info
        self.texture_names = []
        if getattr(g, 'id', '') in ('sims3', 'sims2'):  # no skeleton here
            self.bones = None
            self.parts = []
            if g.id == 'sims3':
                import urbz_sims3
                raw = urbz_sims3.parts(info, colour)
            else:
                import urbz_nsbmd
                raw = [(t[..., :8], tex, col) for t, tex, col in urbz_nsbmd.model(info['bmd'], info.get('extra'))[1]]
            for tris, tex, col in raw:
                full = np.zeros(tris.shape[:2] + (10,))
                full[..., :8] = tris
                full[..., 9] = -1
                self.parts.append(({'tris': full}, tex, col))
            allp = np.concatenate([p[0]['tris'][..., :3].reshape(-1, 3) for p in self.parts]) \
                if self.parts else np.zeros((1, 3))
            lo, hi = allp.min(0), allp.max(0)
            self.unit, self.front = (1.0, SIMS3_FRONT) if g.id == 'sims3' else (SIMS2_UNIT, SIMS2_FRONT)
            self.offset = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
            return
        self.subs = F.mesh(info['mesh']['data'])
        self.bones = F.skeleton(info['skeleton']['data']) if info.get('skeleton') else None
        self.parts = []
        for s in self.subs:
            tex, f = None, g.textures.get(s['texture'])
            if f and texture_swap and '@coat' in texture_swap:     # a dog breed / cat coat: head_X, body_X
                f = _coat(g, f, texture_swap['@coat'])
            if f and texture_swap:
                for old, new in texture_swap.items():
                    if old.startswith('@'):
                        continue
                    if old in f['name']:
                        try:
                            f = g.find(f['name'].replace(old, new))
                        except KeyError:
                            pass
            translucent = False
            if f:
                self.texture_names.append(f['name'])
                try:
                    tex, _p, _n, translucent = F.texture(f['data'])
                except ValueError:
                    tex = None
            if translucent:            # drop shadows and glints: the sprite gets its own shadow
                continue
            self.parts.append((s, tex, (255, 255, 255) if tex is not None else s['colour']))
        # Units: pets are in metres around their own origin; objects are in quarter metres (a 1 m floor
        # tile = 4 units) and sit somewhere on their tile, so centre their footprint on the origin.
        import numpy as np
        allp = np.concatenate([s['tris'][..., :3].reshape(-1, 3) for s, _t, _c in self.parts]) \
            if self.parts else np.zeros((1, 3))
        self.front = 0.0 if info['kind'] == 'pet' else 180.0     # objects face -Z, pets +Z
        if info['kind'] == 'pet':
            self.unit, self.offset = 1.0, np.zeros(3)
        else:
            lo, hi = allp.min(0), allp.max(0)
            self.unit = 0.25 if info['kind'] == 'object' else 1.0
            size_y = g.definition(info['folder']).get(F.SIZE_Y) if info['kind'] == 'object' else None
            if size_y and hi[1] - lo[1] > 1e-3:         # the object's own height in metres
                self.unit = size_y / 4096.0 / (hi[1] - lo[1])
            self.offset = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])

    def posed(self, anim=None, frame=0):
        import urbz_fullfat as F
        W = None
        if anim and self.bones:
            a = F.animation(self.info['anims'][anim]['data'])
            W = F.pose(self.bones, a, frame)
        out = []
        for s, t, c in self.parts:
            tr = (F.skin(s['tris'], self.bones, W) if W is not None else s['tris'])[..., :8].copy()
            tr[..., :3] = (tr[..., :3] - self.offset) * self.unit
            out.append((tr, t, c))
        return out

    def frames(self, anim):
        import urbz_fullfat as F
        return F.animation(self.info['anims'][anim]['data'])['frames']

    def height(self):
        import numpy as np
        ys = np.concatenate([s['tris'][..., 1].ravel() for s, _t, _c in self.parts]) if self.parts else np.zeros(1)
        return float((ys.max() - self.offset[1]) * self.unit)


def _coat(g, f, coat):
    """head_<coat> / body_<coat> instead of the model's own head_/body_ texture (collie: head_collie2)."""
    d, base = f['name'].rsplit('/', 1)
    part = base.split('_', 1)[0]
    if part not in ('head', 'body') or '_' not in base:
        return f
    for name in (coat, coat + '2', coat + '1'):
        try:
            return g.find('%s/%s_%s.nitro_texture' % (d, part, name))
        except KeyError:
            pass
    raise KeyError('no %s_%s texture next to %s (coats: see docs/other-games.md)' % (part, coat, f['name']))


def find_model(gname, mname):
    g = game(gname)
    for m in g.models():
        if m['name'] == mname or m['folder'].endswith('/' + mname):
            return g, m
    raise KeyError('no model "%s" in %s (see the gallery: python urbz_import.py gallery)' % (mname, gname))


def render_model(model, yaw, anim=None, frame=0, size=(96, 96), anchor=(48, 80), scale=1.0):
    return rasterize(model.posed(anim, frame), view(yaw + model.front), PX_PER_M * scale, size, anchor)


# ------------------------------------------------------------------ art folders for the builder

def shadow_tris(parts, darkness=(34, 30, 40)):
    """A flat shadow right under the animal (like the Urbz critters'): every triangle squashed straight down
    onto the floor, drawn first. (A slanted light made a shadow that swung round with the animal's facing.)"""
    import numpy as np
    L = np.array([0.0, -1.0, 0.0])
    out = []
    for tris, _t, _c in parts:
        t = tris.copy()
        k = t[..., 1] / -L[1]
        t[..., 0] += k * L[0]
        t[..., 2] += k * L[2]
        t[..., 1] = -0.002                      # just under the floor, behind everything drawn on it
        t[..., 5:8] = (0.0, 1.0, 0.0)
        out.append((t, None, darkness))
    return out


def _fit_palette(images, colours=15):
    """One palette (index 0 see-through + `colours`) for several RGBA renders; returns
    (palette, [RGBA images using only those colours])."""
    import numpy as np
    from PIL import Image
    opaque = np.concatenate([im[im[..., 3] > 0][:, :3] for im in images if (im[..., 3] > 0).any()] or
                            [np.zeros((1, 3), np.uint8)])
    strip = Image.fromarray(opaque.reshape(1, -1, 3).astype(np.uint8))
    q = strip.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = [(0, 0, 0)] + [tuple(q.getpalette()[3 * i:3 * i + 3]) for i in range(colours)]
    P = np.array(pal[1:], np.int32)
    out = []
    for im in images:
        rgb = im[..., :3].reshape(-1, 3).astype(np.int32)
        idx = ((rgb[:, None, :] - P[None]) ** 2).sum(-1).argmin(1)
        o = np.zeros_like(im)
        o[..., :3] = P[idx].reshape(im.shape[:2] + (3,)).astype(np.uint8)
        o[..., 3] = np.where(im[..., 3] > 0, 255, 0)
        out.append(Image.fromarray(o, 'RGBA'))
    return pal, out


def _place(img, bbox_target):
    """Move a canvas-sized RGBA render so its drawn box's centre-x and bottom match bbox_target."""
    from PIL import Image
    b = img.getbbox()
    if not b or not bbox_target:
        return img
    dx = round((bbox_target[0] + bbox_target[2]) / 2 - (b[0] + b[2]) / 2)
    dy = bbox_target[3] - b[3]
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy), img)
    return out


def object_art(cfg, like, folder):
    """Render an imported model into an urbz_art furniture folder (view-away/-toward, icon, palettes).
    cfg = {"from": game, "model": name, "scale": 1.0, "textures": {"old": "new"} (Full Fat games),
    "colour": 0 (The Sims 3: which of the piece's colour choices)}; all but from/model optional."""
    import numpy as np
    from PIL import Image
    import urbz_art as A
    g, info = find_model(cfg['from'], cfg['model'])
    model = Model(g, info, cfg.get('textures'), cfg.get('colour', 0))
    os.makedirs(folder, exist_ok=True)
    ramp = A.object_colours(like)
    recs = A.object_records(like)
    views = []
    for name, yaw, rec in (('view-away', 135, recs[1]), ('view-toward', -45, recs[3])):
        target = A._sheet_frames(rec[0], rec[1], ramp, A.OBJ_CANVAS, A.OBJ_ORIGIN)[0].getbbox()
        im = rasterize(model.posed(), view(yaw + model.front), PX_PER_M * cfg.get('scale', 1.0),
                       (A.OBJ_CANVAS, A.OBJ_CANVAS), A.OBJ_ORIGIN)
        views.append((name, np.array(_place(Image.fromarray(im), target))))
    pal, imgs = _fit_palette([v for _, v in views])
    for (name, _), im in zip(views, imgs):
        im.save(os.path.join(folder, name + '.png'))
    A.save_palette(os.path.join(folder, 'palette.png'), pal)
    hp = max(model.height(), 0.05)
    icon = rasterize(model.posed(), view(-45 + model.front), min(26.0 / (hp * 0.9), 40.0 / hp) / 1.0,
                     (A.ICON_CANVAS, A.ICON_CANVAS), (16, 28))
    icon = np.array(_place(Image.fromarray(icon), (2, 2, 30, 30)))
    ipal, (iim,) = _fit_palette([icon])
    iim.save(os.path.join(folder, 'icon.png'))
    A.save_palette(os.path.join(folder, 'icon-palette.png'), ipal)
    json.dump(cfg, open(os.path.join(folder, 'import.json'), 'w'))
    return folder


PET_ANIMS = {'0-stand': ['standidle', 'idle', 'stand'], '1-walk': ['walk', 'swim', 'fly', 'move'],
             '2-move': ['sniff', 'happy', 'walk'], '3-move': ['sitidle', 'happy', 'walk'],
             '4-move': ['happy', 'walk']}

# Each Apartment Pets animal as an Urbz pet: which animation for each slot, its height in Urbz pixels
# (standing), and a hop for animals that have no walk cycle (the caged ones: they get their busiest idle
# plus a hop of that many metres, so they don't slide along). Fish are left out (they need water).
ANIMALS = {
    'dog':       {'anims': {'0-stand': 'standidle', '1-walk': 'walk', '2-move': 'sniffwag', '3-move': 'sitidle',
                            '4-move': 'happy'}, 'height': 28},
    'cat':       {'anims': {'0-stand': 'cat_standidle', '1-walk': 'walk', '2-move': 'catsniffwalk',
                            '3-move': 'idlesit', '4-move': 'happy'}, 'height': 23},
    'rabbit':    {'anims': {'0-stand': 'idle', '1-walk': 'idle2', '2-move': 'lookround', '3-move': 'idlesitup',
                            '4-move': 'idlescratch'}, 'height': 18, 'hop': 0.10},
    'hamster':   {'anims': {'0-stand': 'idle', '1-walk': 'idleshimmy', '2-move': 'idlenose', '3-move': 'idlecircle',
                            '4-move': 'idlenose'}, 'height': 9, 'hop': 0.06},
    'guineapig': {'anims': {'0-stand': 'idle', '1-walk': 'idleshimmy', '2-move': 'idlenose', '3-move': 'idlecircle',
                            '4-move': 'idlenose'}, 'height': 10, 'hop': 0.06},
    'cockatoo':  {'anims': {'0-stand': 'idle_varient', '1-walk': 'idlebob', '2-move': 'idlemove2',
                            '3-move': 'cleans', '4-move': 'idlemove1'}, 'height': 20, 'hop': 0.06},
    'macaw':     {'anims': {'0-stand': 'idle_varient', '1-walk': 'idlebob', '2-move': 'idlemove2',
                            '3-move': 'cleans', '4-move': 'idlemove1'}, 'height': 19, 'hop': 0.06},
    'snake2':    {'anims': {'0-stand': 'idle', '1-walk': 'idlesway', '2-move': 'idlenoise', '3-move': 'idledance',
                            '4-move': 'idlesway'}, 'height': 22},
}


def pet_art(cfg, kind, folder):
    """Render an imported animal into an urbz_art pet folder: every slot and direction the starting
    animal (critter kind) has, with as many frames; a shadow under it; one 16-colour palette.
    cfg = {"from", "model", "coat", "anims": {"0-stand": "standidle", ...}, "height" (pixels standing) or
    "scale", "hop" (metres), "textures"}."""
    import numpy as np
    import urbz_art as A
    from urbz_anims import script_of
    g, info = find_model(cfg['from'], cfg['model'])
    animal = ANIMALS.get(info['name'], {}) if cfg['from'] == 'aptpets' else {}
    swap = dict(cfg.get('textures') or {})
    if cfg.get('coat'):
        swap['@coat'] = cfg['coat']
    model = Model(g, info, swap or None)
    src = A.critter_slots(kind)
    spal = A.critter_palette(kind)
    os.makedirs(folder, exist_ok=True)
    anims = dict(animal.get('anims', {}))
    anims.update(cfg.get('anims', {}))
    stand = next((a for a in [anims.get('0-stand')] + PET_ANIMS['0-stand'] if a and a in info['anims']), None)
    ys = np.concatenate([t[..., 1].ravel() for t, _x, _c in model.posed(stand, 0)])
    tall = max(float(ys.max()), 0.05)                       # standing height in metres
    if 'scale' in cfg:
        ppm = PX_PER_M * cfg['scale']
    elif cfg.get('height') or animal.get('height'):
        ppm = (cfg.get('height') or animal['height']) / tall
    else:                    # as tall as the animal it replaces (its standing frame)
        ref = A.frames_of(src[0][0][2][0], src[0][0][2][1], spal)[0].getbbox() if src[0][0] else None
        ppm = ((ref[3] - ref[1]) * 0.9 if ref else 24) / tall
    hop = cfg.get('hop', animal.get('hop', 0))
    for _try in range(4):                  # shrink until every frame fits the critter's sprite memory
        timing, frames = _pet_frames(model, info, src, spal, anims, ppm, hop, folder)
        worst = max(_tiles(im) for _p, im in frames)
        edge = any(im[0, :, 3].any() or im[-1, :, 3].any() or im[:, 0, 3].any() or im[:, -1, 3].any()
                   for _p, im in frames)                  # cut off by the canvas
        if worst <= PET_MAX_TILES and not edge:
            break
        if worst <= PET_MAX_TILES:
            worst = PET_MAX_TILES * 1.3
        ppm *= (PET_MAX_TILES / worst) ** 0.5 * 0.95
    else:
        raise ValueError('%s: frames still need %d tiles of sprite memory (%d fit)' % (info['name'], worst,
                                                                                     PET_MAX_TILES))
    pal, imgs = _fit_palette([im for _, im in frames])
    for (path, _), im in zip(frames, imgs):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        im.save(path)
    A.save_palette(os.path.join(folder, 'palette.png'), pal)
    json.dump(timing, open(os.path.join(folder, 'timing.json'), 'w'), indent=1)
    return folder


# A critter's frame may use 32 tiles (8x8) of sprite memory: seen in the game, a 24-tile Puppy draws
# fine and a 40-tile Macaw (wings spread) came out as garbage. pet_art shrinks an animal until it fits.
PET_MAX_TILES = 32


def _tiles(im):
    from urbz_anims import cut_cells
    import urbz_art as A
    idx = (im[..., 3] > 0).astype(int).tolist()
    return sum((sz // 8) ** 2 for _x, _y, sz in cut_cells(idx, A.PET_CANVAS, A.PET_ORIGIN))


def _pet_frames(model, info, src, spal, anims, ppm, hop, folder):
    import numpy as np
    import urbz_art as A
    from urbz_anims import script_of
    timing = {'from': 'import', 'slots': {}}
    frames, seen = [], {}
    for s, (recs, script) in enumerate(src):
        slot = A.SLOTS[s]
        if recs is None:
            timing['slots'][slot] = {'none': True}
            continue
        if tuple(recs) in seen:
            timing['slots'][slot] = {'same_as': seen[tuple(recs)]}
            continue
        seen[tuple(recs)] = slot
        timing['slots'][slot] = {'script': script_of(script) or 'default', 'param': recs[0][3]}
        want_anims = [anims.get(slot)] + PET_ANIMS[slot]
        anim = next((a for a in want_anims if a and a in info['anims']), None)
        for d, (gfx, lay, _, _) in enumerate(recs):
            n = len(A.frames_of(gfx, lay, spal))
            yaw = 180 - 45 * d                    # dir0 faces away ... dir4 faces you
            nf = model.frames(anim) if anim else 1
            for k in range(n):
                f = (k * nf) // n if anim else 0
                parts = model.posed(anim, f)
                shadow = shadow_tris(parts)
                if hop and slot == '1-walk':      # two hops per walk cycle
                    up = hop * abs(np.sin(2 * np.pi * k / n))
                    for t, _x, _c in parts:
                        t[..., 1] += up
                im = rasterize(shadow + parts, view(yaw + model.front), ppm,
                               (A.PET_CANVAS, A.PET_CANVAS), A.PET_ORIGIN)
                frames.append((os.path.join(folder, slot, 'dir%d' % d, '%02d.png' % k), im))
    return timing, frames


# ------------------------------------------------------------------ gallery

def gallery(names):
    from PIL import Image
    os.makedirs(os.path.join(GALLERY, 'img'), exist_ok=True)
    rows = []
    for gname in names or sorted(sources()):
        if gname not in ('aptpets', 'castaway', 'sims3', 'sims2'):
            continue
        g = game(gname)
        for info in g.models():
            if info['kind'] not in ('pet', 'object', 'accessory'):
                continue
            key = '%s-%s-%s' % (gname, info['kind'], info['name'])
            path = os.path.join(GALLERY, 'img', key + '.png')
            try:
                model = Model(g, info)
                if not os.path.exists(path):
                    hp = max(model.height() * PX_PER_M, 1e-3)
                    big = min(90.0 / hp, max(1.0, 40.0 / hp))     # tiny things shown bigger
                    views = [render_model(model, yaw, scale=big, size=(110, 110), anchor=(55, 90))
                             for yaw in (-45, 135)]
                    sheet = Image.new('RGBA', (220, 110), (0, 0, 0, 0))
                    for k, v in enumerate(views):
                        sheet.alpha_composite(Image.fromarray(v), (110 * k, 0))
                    sheet.save(path)
                rows.append((gname, info, key, model.height()))
            except Exception as e:                        # report and carry on
                rows.append((gname, info, None, str(e)[:80]))
            print('%s %s' % (key, 'ok' if rows[-1][2] else rows[-1][3]))
    html = ['<!doctype html><meta charset=utf-8><title>Imports gallery</title><style>',
            'body{font:13px sans-serif;background:#222;color:#ddd;margin:16px}',
            '.g{display:flex;flex-wrap:wrap;gap:8px}.c{background:#333;padding:6px;width:220px}',
            'img{image-rendering:pixelated;width:220px;background:#3a3a46}.k{color:#aaa;font-size:11px}</style>',
            '<h1>Models you can import</h1><p>Front and back at the Urbz angle (2:1), ~42 px per metre. Name a '
            'model in a mod\'s <code>objects.json</code> or <code>pets.json</code> (<code>"import"</code>) to bring it over.</p>']
    for kind in ('pet', 'object', 'accessory'):
        html.append('<h2>%ss</h2><div class=g>' % kind)
        for gname, info, key, h in rows:
            if info['kind'] != kind:
                continue
            if key:
                hp = max(h * PX_PER_M, 1e-3)
                zoom = min(90.0 / hp, max(1.0, 40.0 / hp))
                html.append('<div class=c><img src="img/%s.png"><br><b>%s</b> <span class=k>%s, %.2f m tall '
                            '(~%d px in the Urbz)%s, %d animations</span></div>' % (
                                key, info['name'], gname, h, round(hp), '' if abs(zoom - 1) < 0.01 else
                                ', shown x%.1f' % zoom, len(info['anims'])))
            else:
                html.append('<div class=c><b>%s</b> <span class=k>%s: %s</span></div>' % (info['name'], gname, h))
        html.append('</div>')
    open(os.path.join(GALLERY, 'index.html'), 'w').write('\n'.join(html))
    print('wrote %s (%d models)' % (os.path.join(GALLERY, 'index.html'), sum(1 for r in rows if r[2])))


def show(gname, mname, out=None):
    from PIL import Image
    g, info = find_model(gname, mname)
    model = Model(g, info)
    views = [Image.fromarray(render_model(model, yaw)) for yaw in (0, 45, 90, 135, 180)]
    walk = []
    if 'walk' in info['anims']:
        n = model.frames('walk')
        walk = [Image.fromarray(render_model(model, 90, 'walk', f)) for f in range(0, n, max(1, n // 8))]
    allv = views + walk
    sheet = Image.new('RGBA', (96 * len(allv), 96), (58, 58, 70, 255))
    for k, v in enumerate(allv):
        sheet.alpha_composite(v, (96 * k, 0))
    out = out or os.path.join(GALLERY, '%s-%s.png' % (gname, mname))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out)
    print('wrote', out)


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd = argv[0]
    if cmd == 'sources':
        src = sources()
        if not src:
            print('no sources.json yet; create it next to urbz_import.py (see help)')
        for k, v in src.items():
            print('%-9s %s %s' % (k, v, '' if os.path.exists(v) else '(missing)'))
    elif cmd == 'gallery':
        gallery(argv[1:])
    elif cmd == 'show' and len(argv) >= 3:
        show(argv[1], argv[2], argv[3] if len(argv) > 3 else None)
    else:
        sys.exit('usage: see python urbz_import.py help')


if __name__ == '__main__':
    main(sys.argv[1:])
