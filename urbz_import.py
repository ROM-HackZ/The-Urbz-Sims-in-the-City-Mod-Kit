#!/usr/bin/env python3
"""Bring pets and furniture over from other Sims DS games: render their 3D models the way The Urbz
draws its world (2D sprites seen from above at a fixed angle), at Urbz size, in 16 colours.

  python urbz_import.py sources                        which source games are set up (sources.json)
  python urbz_import.py gallery [game ...]             render every model -> catalog/imports/index.html
  python urbz_import.py show GAME MODEL [out.png]      one model: 5 directions (+ walk frames for pets)
  python urbz_import.py build MOD                      fill MOD's art folders from MOD/imports.json

sources.json (next to this file; local, never committed) names your own copies of the games:
  {"aptpets": "D:/ROMS/Sims 2 - Apartment Pets.nds", "castaway": "...", "sims3": "...", "sims2": "..."}

The Urbz camera (docs/systems.md "The Urbz camera"): orthographic, 45 degrees round, 30 degrees down
(floor tiles are 2:1), about 42 pixels per metre. Nothing from the source games goes into git: mods keep
only imports.json, and the art is made from your ROMs when you run this.
"""
import json, os, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
SOURCES = os.path.join(KIT, 'sources.json')
GALLERY = os.path.join(KIT, 'catalog', 'imports')

PITCH = 30.0            # degrees down from horizontal (2:1 floor tiles)
PX_PER_M = 42.0         # Urbz pixels per metre (a 1.75 m person is ~64 px tall)
LIGHT = (-0.45, 0.8, 0.55)   # from the upper left, in front (view space)


# ------------------------------------------------------------------ rendering

def view(yaw_deg, pitch_deg=PITCH):
    """Rotation from model space (Y up, the model faces +Z) to view space (X right, Y up, +Z to the eye).
    yaw 0 = the model faces the viewer; positive yaw turns it to face screen-right."""
    import numpy as np
    y, p = np.radians(-yaw_deg), np.radians(pitch_deg)
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


def game(name):
    if name not in _GAMES:
        src = sources()
        if name not in src:
            sys.exit('error: no "%s" in sources.json (python urbz_import.py sources)' % name)
        import urbz_fullfat
        _GAMES[name] = urbz_fullfat.Game(src[name])
    return _GAMES[name]


class Model:
    """A Full Fat model ready to render: its parts with textures, its skeleton and animations."""

    def __init__(self, g, info, texture_swap=None):
        import urbz_fullfat as F
        self.g, self.info = g, info
        self.subs = F.mesh(info['mesh']['data'])
        self.bones = F.skeleton(info['skeleton']['data']) if info.get('skeleton') else None
        self.parts = []
        for s in self.subs:
            tex, f = None, g.textures.get(s['texture'])
            if f and texture_swap:
                for old, new in texture_swap.items():
                    if old in f['name']:
                        try:
                            f = g.find(f['name'].replace(old, new))
                        except KeyError:
                            pass
            translucent = False
            if f:
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


def find_model(gname, mname):
    g = game(gname)
    for m in g.models():
        if m['name'] == mname or m['folder'].endswith('/' + mname):
            return g, m
    sys.exit('error: no model "%s" in %s (see the gallery)' % (mname, gname))


def render_model(model, yaw, anim=None, frame=0, size=(96, 96), anchor=(48, 80), scale=1.0):
    return rasterize(model.posed(anim, frame), view(yaw + model.front), PX_PER_M * scale, size, anchor)


# ------------------------------------------------------------------ gallery

def gallery(names):
    from PIL import Image
    os.makedirs(os.path.join(GALLERY, 'img'), exist_ok=True)
    rows = []
    for gname in names or sorted(sources()):
        if gname not in ('aptpets', 'castaway'):
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
                    h = model.height()
                    big = 1.0 if h * PX_PER_M < 90 else 90.0 / (h * PX_PER_M)
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
            'model in a mod\'s <code>imports.json</code> to bring it over.</p>']
    for kind in ('pet', 'object', 'accessory'):
        html.append('<h2>%ss</h2><div class=g>' % kind)
        for gname, info, key, h in rows:
            if info['kind'] != kind:
                continue
            if key:
                html.append('<div class=c><img src="img/%s.png"><br><b>%s</b> <span class=k>%s, %.2f m tall, '
                            '%d animations</span></div>' % (key, info['name'], gname, h, len(info['anims'])))
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
