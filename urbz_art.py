#!/usr/bin/env python3
"""The art tool: draw new art for the game, as PNGs. (Pets now; furniture next. Townspeople's
animations: urbz_anims.py.)

  python urbz_art.py template <mod> <pet>      PNGs to draw over: the frames of the animal it starts from
  python urbz_art.py preview <mod> <pet>       art/<pet>/preview.png: every frame at 1x and 4x
  python urbz_art.py placeholder <mod> <pet>   (tests) the template, recoloured from a new palette

<pet> is a name from the mod's pets.json ("puppy"). The folder is the pet's "art" (default art/<pet>):
  palette.png        its 16 colours (16 squares; the first is "see-through"). Change a colour and every
                     pixel drawn in it changes. Every pixel you draw snaps to the nearest of the 16.
  0-stand/dir0/00.png ...   the frames: slot 0 = standing, 1 = walking, 2-4 = other moves; dir0-dir4 = the
                     5 directions the game draws (dir0 faces you, dir2 side-on, dir4 faces away; the
                     game mirrors them for the other 3). The shadow is part of each drawing. Each PNG is 88x88 and
                     the animal's feet sit on pixel (32, 64), like the game's own frames.
  timing.json        how long each frame shows ("default" = the game's own timing), which slots reuse
                     another ("same_as"), and the starting animal.
A slot or direction folder you delete keeps the starting animal's art there. The builder converts the
PNGs by itself when you build the ROM (urbz_pets.py). The template frames come from the game's art:
keep them to yourself; your own drawings are yours to share.
"""
import json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
PROJ = os.path.join(KIT, 'project')
PET_CANVAS, PET_ORIGIN = 88, (32, 64)
SLOTS = ['0-stand', '1-walk', '2-move', '3-move', '4-move']
DIRS = 5


# ------------------------------------------------------------------ the game's critter art

def critter_slots(kind):
    """[(records [(gfx, layout, palette, param) x 5] or None, script id)] x 5 for a critter kind."""
    from urbz_anims import u32
    from urbz_pets import CRIT_ANIMS, ANIM_ROW
    out = []
    for s in range(5):
        rec, script = u32(CRIT_ANIMS + ANIM_ROW * kind + 8 * s), u32(CRIT_ANIMS + ANIM_ROW * kind + 8 * s + 4)
        out.append(([tuple(u32(rec + 16 * d + 4 * j) for j in range(4)) for d in range(DIRS)] if rec else None,
                    script))
    return out


def critter_palette(kind):
    from urbz_anims import u32, asset
    from urbz_palette import bgr555
    from urbz_pets import CRIT_PALETTES
    data = asset(u32(CRIT_PALETTES + 4 * kind) - 1)
    return [bgr555(struct.unpack_from('<H', data, 2 * i)[0]) for i in range(16)]


def frames_of(gfx, layout, pal):
    """A sheet's frames on the pet canvas (RGBA)."""
    import urbz_composite as C
    from PIL import Image
    out = []
    for e, chunk in C.frames(gfx - 1, layout - 1):
        canvas = Image.new('RGBA', (PET_CANVAS, PET_CANVAS), (0, 0, 0, 0))
        fr = C.compose_frame(e, chunk, pal)
        canvas.paste(fr, (PET_ORIGIN[0] + e.x, PET_ORIGIN[1] + e.y), fr)
        out.append(canvas)
    return out


# ------------------------------------------------------------------ pets.json

def find_pet(mod, name):
    from urbz_anims import mod_dir
    from urbz_pets import FROM
    mdir = mod_dir(mod)
    pets = json.load(open(os.path.join(mdir, 'pets.json'), encoding='utf-8'))['pets']
    for pet in pets:
        if pet['name'].lower() == name.lower():
            return mdir, pet, FROM[pet['from']]
    sys.exit('no pet called %r in %s/pets.json (%s)' % (name, mod, ', '.join(p['name'] for p in pets)))


def art_dir(mdir, pet):
    return os.path.join(mdir, pet.get('art', 'art/' + pet['name'].lower()))


def save_palette(path, pal):
    from PIL import Image
    im = Image.new('RGBA', (16 * 16, 16), (0, 0, 0, 0))
    for i, c in enumerate(pal):
        for y in range(16):
            for x in range(16):
                im.putpixel((16 * i + x, y), tuple(c[:3]) + (0 if i == 0 else 255,))
    im.save(path)


def load_palette(path):
    from PIL import Image
    im = Image.open(path).convert('RGBA')
    return [im.getpixel((16 * i + 8, 8))[:3] + (255,) for i in range(16)]


# ------------------------------------------------------------------ commands

def template(mod, name, recolour=None):
    from urbz_anims import script_of
    mdir, pet, kind = find_pet(mod, name)
    adir = art_dir(mdir, pet)
    pal = critter_palette(kind)
    os.makedirs(adir, exist_ok=True)
    timing = {'from': pet['from'], 'slots': {}}
    seen = {}
    for s, (recs, script) in enumerate(critter_slots(kind)):
        slot = SLOTS[s]
        if recs is None:
            timing['slots'][slot] = {'none': True}
            continue
        key = tuple(recs)
        if key in seen:
            timing['slots'][slot] = {'same_as': seen[key]}
            continue
        seen[key] = slot
        timing['slots'][slot] = {'script': script_of(script) or 'default', 'param': recs[0][3]}
        for d, (g, l, _, _) in enumerate(recs):
            out = os.path.join(adir, slot, 'dir%d' % d)
            if os.path.isdir(out) and os.listdir(out) and recolour is None:
                print('kept your frames in %s' % os.path.relpath(out, KIT))
                continue
            os.makedirs(out, exist_ok=True)
            for f in os.listdir(out):
                os.remove(os.path.join(out, f))
            for k, im in enumerate(frames_of(g, l, pal)):
                if recolour:
                    im = recolour(im, pal)
                im.save(os.path.join(out, '%02d.png' % k))
    save_palette(os.path.join(adir, 'palette.png'), recolour.palette if recolour else pal)
    json.dump(timing, open(os.path.join(adir, 'timing.json'), 'w'), indent=1)
    print('%s: frames to draw in %s (from the %s)' % (pet['name'], os.path.relpath(adir, KIT), pet['from']))
    return adir


class Recolour:
    """Placeholder art for tests: the same pictures, every colour moved towards orange."""

    def __init__(self, pal):
        self.map = {}
        self.palette = [pal[0]]
        for c in pal[1:]:
            lum = (c[0] * 3 + c[1] * 6 + c[2]) // 10
            n = (min(255, lum + 70), max(0, lum - 10), max(0, lum // 3 - 20), 255)
            self.map[tuple(c[:3])] = n
            self.palette.append(n)

    def __call__(self, im, pal):
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                r, g, b, a = px[x, y]
                if a:
                    px[x, y] = self.map.get((r, g, b), (r, g, b, a))
        return im


def placeholder(mod, name):
    _, _, kind = find_pet(mod, name)
    template(mod, name, Recolour(critter_palette(kind)))


def preview(mod, name):
    from PIL import Image
    mdir, pet, kind = find_pet(mod, name)
    adir = art_dir(mdir, pet)
    pal = load_palette(os.path.join(adir, 'palette.png'))
    rows = []
    for slot in SLOTS:
        for d in range(DIRS):
            f = os.path.join(adir, slot, 'dir%d' % d)
            if os.path.isdir(f):
                rows.append(['%s/dir%d' % (slot, d)] + [Image.open(os.path.join(f, x)).convert('RGBA')
                                                        for x in sorted(os.listdir(f)) if x.endswith('.png')])
    if not rows:
        sys.exit('no frames in %s' % os.path.relpath(adir, KIT))
    box = None                                          # crop every frame to the drawn area (+2 px)
    for r in rows:
        for im in r[1:]:
            b = im.getbbox()
            if b:
                box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    box = box or (0, 0, PET_CANVAS, PET_CANVAS)
    box = (max(0, box[0] - 2), max(0, box[1] - 2), min(PET_CANVAS, box[2] + 2), min(PET_CANVAS, box[3] + 2))
    fw, fh, z, label = box[2] - box[0], box[3] - box[1], 4, 90
    cols = max(len(r) - 1 for r in rows)
    sheet = Image.new('RGBA', (label + cols * (fw * z + 4) + fw + 8, len(rows) * (fh * z + 4)), (96, 96, 96, 255))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(sheet)
    bad = 0
    allowed = {tuple(c[:3]) for c in pal[1:]}
    for k, r in enumerate(rows):
        y0 = k * (fh * z + 4)
        draw.text((4, y0 + 4), r[0], fill=(255, 255, 255, 255))
        for j, im in enumerate(r[1:]):
            snap = im.crop(box)
            px = snap.load()
            for y in range(snap.height):
                for x in range(snap.width):
                    if px[x, y][3] >= 128 and px[x, y][:3] not in allowed:
                        px[x, y] = (255, 0, 255, 255)          # not one of the 16: shown pink
                        bad += 1
            if j == 0:                                          # real size, at the end of the row
                sheet.paste(snap, (label + cols * (fw * z + 4) + 4, y0), snap)
            big = snap.resize((fw * z, fh * z), Image.NEAREST)
            sheet.paste(big, (label + j * (fw * z + 4), y0), big)
    out = os.path.join(adir, 'preview.png')
    sheet.save(out)
    print('%s (%d frames; %d pixel(s) not in the 16 colours, shown pink)' % (
        os.path.relpath(out, KIT), sum(len(r) - 1 for r in rows), bad))


# ------------------------------------------------------------------ for the builder (urbz_pets.py)

def build_pet_art(adir, kind, new_asset):
    """A pet's art folder -> new art files. new_asset(bytes) returns the file's game id.
    Returns {'slots': [(records bytes (5 x 16) or None, script game id)] x 5, 'palette': game id}; a slot
    with None keeps the starting animal's records."""
    import urbz_composite as C
    from PIL import Image
    from urbzcomp import pack_chunk
    from urbz_anims import frame_data, asset, script_bytes, CHUNK_FLAGS
    timing = json.load(open(os.path.join(adir, 'timing.json')))
    pal = load_palette(os.path.join(adir, 'palette.png'))
    src = critter_slots(kind)
    first = next(r for r, _ in src if r)
    lay0 = C.parse_layout(asset(first[0][1] - 1))
    extra, head = lay0.entries[0].extra, lay0.head
    out, done = [], {}
    for s, slot in enumerate(SLOTS):
        cfg = timing['slots'].get(slot, {})
        recs, script = src[s]
        if cfg.get('same_as') in done:
            out.append(done[cfg['same_as']])
            continue
        if recs is None or not os.path.isdir(os.path.join(adir, slot)):
            out.append((None, script))
            continue
        records = bytearray()
        for d in range(DIRS):
            fdir = os.path.join(adir, slot, 'dir%d' % d)
            g, l = recs[d][0], recs[d][1]
            pngs = sorted(x for x in os.listdir(fdir) if x.endswith('.png')) if os.path.isdir(fdir) else []
            if pngs:
                gfx, entries = bytearray(), []
                for f in pngs:
                    e, content = frame_data(Image.open(os.path.join(fdir, f)), pal, extra, PET_CANVAS, PET_ORIGIN)
                    e.index, e.chunk_off = len(entries), len(gfx)
                    gfx += pack_chunk(CHUNK_FLAGS, content)
                    while len(gfx) % 4:
                        gfx += b'\0'
                    entries.append(e)
                if len(gfx) > 0xFFFF:
                    raise ValueError('%s: the sheet is %d bytes; the game allows 64 KB' % (fdir, len(gfx)))
                lay = C.Layout(bytes([max(e.w for e in entries), max(e.h for e in entries)]) + head[2:],
                               entries, 0, len(extra) // 6)
                g, l = new_asset(bytes(gfx)), new_asset(C.build_layout(lay))
            records += struct.pack('<4I', g, l, recs[d][2], cfg.get('param', recs[d][3]))
        sc = cfg.get('script', 'default')
        sid = 0 if sc == 'default' else new_asset(script_bytes(sc))
        done[slot] = (bytes(records), sid)
        out.append(done[slot])
    from urbz_palette import to555
    pdata = b''.join(struct.pack('<H', to555(c)) for c in pal)
    return {'slots': out, 'palette': new_asset(pdata)}


def main(argv):
    if len(argv) == 3 and argv[0] in ('template', 'preview', 'placeholder'):
        {'template': template, 'preview': preview, 'placeholder': placeholder}[argv[0]](argv[1], argv[2])
        return
    print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
