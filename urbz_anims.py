#!/usr/bin/env python3
"""New animations for the townspeople, drawn as PNG frames, in their own look.

  python urbz_anims.py template <mod> <person> [group ...]   frames to draw over + a guide sequence
  python urbz_anims.py placeholder <mod> <person> [group ...] fill a template with the guide (tests)
  python urbz_anims.py build <mod>                            PNGs -> new sheets + the game data
  python urbz_anims.py list                                   groups and who already has them

<person> is a character id (31-66) or a name ("hattie"). Groups: sit, eat, toilet, shower, sleep.

What you get (mods/<mod>/people/<id>-<name>/):
  <sheet>/front/NN.png, <sheet>/back/NN.png  the frames to draw: at first, copies of the person's own
                                             standing frame. One sheet can hold several animations
                                             (sit = sit down, stay seated, ... on one sheet).
  guide/<sheet>/...                          the same animation on someone who has it (Kris for most),
                                             frame by frame, to copy the pose and timing from
  anims.json                                 which game animation plays which frames, how fast
Every PNG is a 96x96 canvas; the person stands on pixel (40, 72) (their feet), like in the game.
Draw in the person's own colours (each person has 16; other colours snap to the nearest). Front =
the 3 facings towards you, back = the 2 away from you (the game mirrors them for the others).

`build` turns the PNGs into new sprite sheets (appended assets mods/<mod>/assets/NNNNN.bin), their
layouts and frame scripts, and writes mods/<mod>/code/ (C data + hooks.txt) that gives each person
the new animation rows (their list in npc_anim_lists, docs/systems.md). Then build the ROM as usual.
Only one mod may add assets (they are numbered after the game's last one).

The frames are derived from the game's art: keep the mod local (mods/ is not in git).
"""
import json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
PROJ = os.path.join(KIT, 'project')
ANIM_LISTS = 0x0211CDF4                    # npc_anim_lists: u8 *[character id], 12-byte rows, ends 0xC4
PALETTES = 0x020D0054                     # npc_palette_table: palette game id per character id
CANVAS, ORIGIN = 96, (40, 72)
CHUNK_FLAGS = 0x60                        # EA-compressed chunk, like the game's own sheets
# group -> (reference person, animation ids); the reference's frames and timing are the guide
GROUPS = {
    'sit': (45, [0x6B, 0x6C, 0x6D]),     # sit down, stay seated (chairs, sofas, benches)
    'eat': (45, [0x41]),                 # eat a snack standing (fridge, vending, grill)
    # (vending machines also play 0x7F, pressing the button: nobody but the player has it)
    'toilet': (54, [0x7B]),
    'shower': (45, [0x69]),
    'sleep': (45, [0x21, 0x20]),         # lie down, get up (beds)
}


# ------------------------------------------------------------------ game data

_A9 = []


def arm9():
    if not _A9:
        import ndspy.rom
        _A9.append(bytes(ndspy.rom.NintendoDSRom.fromFile(os.path.join(PROJ, 'base.nds')).arm9))
    return _A9[0]


def u32(a):
    return struct.unpack_from('<I', arm9(), a - 0x02000000)[0]


def anim_rows(cid):
    """[(raw 4 bytes, records address, script id)] of a person's animation list."""
    p, out = u32(ANIM_LISTS + 4 * cid), []
    while arm9()[p - 0x02000000] != 0xC4:
        out.append((arm9()[p - 0x02000000:p - 0x02000000 + 4], u32(p + 4), u32(p + 8)))
        p += 12
    return out


def anim_ids(cid):
    return [raw[0] for raw, _, _ in anim_rows(cid)]


def records(addr):
    """5 facings x (gfx game id, layout game id, palette, param)."""
    return [tuple(u32(addr + 16 * f + 4 * j) for j in range(4)) for f in range(5)]


def row_of(cid, anim):
    for raw, rec, script in anim_rows(cid):
        if raw[0] == anim:
            return records(rec), script
    raise KeyError('person %d has no animation %02x' % (cid, anim))


def asset(file_no):
    return open(os.path.join(PROJ, 'assets', '%05d.bin' % file_no), 'rb').read()


def palette16(cid):
    from urbz_palette import bgr555
    data = asset(u32(PALETTES + 4 * cid) - 1)
    return [bgr555(struct.unpack_from('<H', data, 2 * i)[0]) for i in range(16)]


def script_of(script_id):
    """A frame script asset -> [[frame, ticks], ..., 'hold' | 'loop'] (0 = the game's default)."""
    if not script_id:
        return None
    b, out = asset(script_id - 1), []
    for k in range(0, len(b) - 1, 2):
        if b[k] == 0xFF:
            return out + ['hold']
        if b[k] == 0xFD:
            return out + ['loop']
        out.append([b[k], b[k + 1]])
    return out + ['hold']


def script_bytes(spec):
    out = bytearray()
    for step in spec:
        if step == 'hold':
            out += b'\xff\x00'
        elif step == 'loop':
            out += b'\xfd\x00'
        else:
            out += bytes([step[0], step[1]])
    while len(out) % 4:
        out += b'\0'
    return bytes(out)


def names():
    from urbz_text import project_strings
    s = project_strings(PROJ)
    return {c: (s[512 + c - 31].decode('latin-1') if isinstance(s[512 + c - 31], bytes) else s[512 + c - 31])
            for c in range(31, 67)}


def person(arg):
    n = names()
    if arg.isdigit() and int(arg) in n:
        return int(arg), n[int(arg)]
    hits = [(c, v) for c, v in n.items() if arg.lower() in v.lower()]
    if len(hits) != 1:
        sys.exit('person "%s": %s' % (arg, ', '.join('%d %s' % h for h in hits) or 'no match'))
    return hits[0]


def mod_dir(mod):
    """A mod name under mods/, or a folder path (tests build theirs elsewhere)."""
    return mod if os.path.sep in mod or os.path.isabs(mod) else os.path.join(KIT, 'mods', mod)


def folder(mod, cid, name):
    return os.path.join(mod_dir(mod), 'people', '%d-%s' % (cid, name.split()[0].lower()))


# ------------------------------------------------------------------ frames <-> canvas

def sheet_frames(gfx_gid, layout_gid, pal):
    """The frames of a game sheet as canvas images (RGBA)."""
    import urbz_composite as C
    from PIL import Image
    out = []
    for e, chunk in C.frames(gfx_gid - 1, layout_gid - 1):
        canvas = Image.new('RGBA', (CANVAS, CANVAS), (0, 0, 0, 0))
        fr = C.compose_frame(e, chunk, pal)
        canvas.paste(fr, (ORIGIN[0] + e.x, ORIGIN[1] + e.y), fr)
        out.append(canvas)
    return out


def views_of(recs):
    """{'front': (gfx, layout), 'back': ...} (one view when every facing uses the same sheet)."""
    front, back = recs[0][:2], recs[3][:2]
    return {'front': front} if front == back else {'front': front, 'back': back}


def cut_cells(idx):
    """Canvas colour indices -> [(x, y, size)] square cells (8/16/32) covering every drawn pixel,
    x/y relative to the feet. Big blocks where they are mostly filled, smaller ones elsewhere."""
    pts = [(x, y) for y in range(CANVAS) for x in range(CANVAS) if idx[y][x]]
    if not pts:
        return []
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)

    def filled(bx, by, s):
        n = 0
        for ty in range(by, by + s, 8):
            for tx in range(bx, bx + s, 8):
                if any(idx[y][x] for y in range(ty, min(ty + 8, CANVAS)) for x in range(tx, min(tx + 8, CANVAS))
                       if 0 <= y and 0 <= x):
                    n += 1
        return n

    for thresh in (0.5, 0.75, 1.01):
        cells = []

        def emit(bx, by, s):
            n = filled(bx, by, s)
            if not n:
                return
            if s == 8 or n * 64 >= thresh * s * s:
                cells.append((bx - ORIGIN[0], by - ORIGIN[1], s))
                return
            h = s // 2
            for dy in (0, h):
                for dx in (0, h):
                    emit(bx + dx, by + dy, h)
        for by in range(y0, y1 + 1, 32):
            for bx in range(x0, x1 + 1, 32):
                emit(bx, by, 32)
        if len(cells) <= 31:
            return cells
    raise ValueError('frame too spread out (more than 31 sprite pieces)')


def frame_data(img, pal, extra):
    """A canvas PNG -> (layout Entry, chunk content bytes)."""
    import urbz_composite as C
    idx = C._image_indices(img.convert('RGBA'), pal, None)
    cells, tiles, t = [], bytearray(), 0
    size_code = {8: 0, 16: 1, 32: 2}
    for x, y, s in cut_cells(idx):
        cells.append(C.Cell(x, y, 0, size_code[s], t, 0))
        for ty in range(0, s, 8):
            for tx in range(0, s, 8):
                for yy in range(8):
                    for xx in range(0, 8, 2):
                        def at(px, py):
                            X, Y = ORIGIN[0] + x + px, ORIGIN[1] + y + py
                            return idx[Y][X] if 0 <= X < CANVAS and 0 <= Y < CANVAS else 0
                        lo, hi = at(tx + xx, ty + yy), at(tx + xx + 1, ty + yy)
                        tiles.append(lo | hi << 4)
        t += (s // 8) ** 2
    if not cells:
        cells.append(C.Cell(0, 0, 0, 0, 0, 0))                 # an empty frame: one blank tile
        tiles += bytes(32)
    xs = [c.x for c in cells] + [c.x + c.dims[0] for c in cells]
    ys = [c.y for c in cells] + [c.y + c.dims[1] for c in cells]
    e = C.Entry(0, 4, max(xs) - min(xs), max(ys) - min(ys), 0, min(xs), min(ys), extra, cells, 0)
    return e, bytes(tiles)


# ------------------------------------------------------------------ commands

def save_canvas_set(path, frames):
    os.makedirs(path, exist_ok=True)
    for k, im in enumerate(frames):
        im.save(os.path.join(path, '%02d.png' % k))


def template(mod, who, groups):
    cid, name = person(who)
    base = folder(mod, cid, name)
    pal = palette16(cid)
    stand = views_of(row_of(cid, 0x04)[0])
    cfg_path = os.path.join(base, 'anims.json')
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {'person': cid, 'name': name, 'anims': {}}
    for g in groups:
        ref, ids = GROUPS[g]
        have = [a for a in ids if a in anim_ids(cid)]
        if have:
            print('%s already has %s (%s): nothing to draw' % (name, g, ' '.join('%02x' % a for a in have)))
            continue
        rpal = palette16(ref)
        sheets = {}
        for a in ids:
            recs, script = row_of(ref, a)
            key = recs[0][0]
            if key not in sheets:
                sheets[key] = ('%s_%02x' % (g, a), views_of(recs))
            sheet = sheets[key][0]
            cfg['anims']['%02x' % a] = {'group': g, 'sheet': sheet, 'param': recs[0][3],
                                        'script': script_of(script), 'guide': ref}
        for key, (sheet, views) in sheets.items():
            for view, (gfx, lay) in views.items():
                guide = sheet_frames(gfx, lay, rpal)
                save_canvas_set(os.path.join(base, 'guide', sheet, view), guide)
                own = sheet_frames(*stand.get(view, stand['front']), pal)[0]
                d = os.path.join(base, sheet, view)
                if os.path.isdir(d) and os.listdir(d):
                    print('kept your frames in %s' % os.path.relpath(d, KIT))
                    continue
                save_canvas_set(d, [own.copy() for _ in guide])
        print('%s %s: %d frame(s) per view to draw in %s' % (name, g, len(guide), os.path.relpath(base, KIT)))
    os.makedirs(base, exist_ok=True)
    write_cfg(cfg_path, cfg)


def write_cfg(path, cfg):
    """anims.json with one line per animation (script = [[frame, ticks], ...] then hold/loop)."""
    lines = ['{', ' "person": %d,' % cfg['person'], ' "name": %s,' % json.dumps(cfg['name']), ' "anims": {']
    items = sorted(cfg['anims'].items())
    for k, (aid, a) in enumerate(items):
        lines.append('  %s: %s%s' % (json.dumps(aid), json.dumps(a, separators=(', ', ': ')),
                                     ',' if k + 1 < len(items) else ''))
    lines += [' }', '}']
    open(path, 'w').write('\n'.join(lines) + '\n')


def placeholder(mod, who, groups):
    """Fill the frames with the guide, its colours moved to the nearest of the person's (tests only)."""
    from PIL import Image
    cid, name = person(who)
    base = folder(mod, cid, name)
    template(mod, who, groups)
    cfg = json.load(open(os.path.join(base, 'anims.json')))
    sheets = {a['sheet'] for a in cfg['anims'].values() if a['group'] in groups}
    pal = palette16(cid)
    for sheet in sheets:
        for view in os.listdir(os.path.join(base, 'guide', sheet)):
            gd = os.path.join(base, 'guide', sheet, view)
            frames = []
            for f in sorted(os.listdir(gd)):
                im = Image.open(os.path.join(gd, f)).convert('RGBA')
                px = im.load()
                for y in range(im.height):
                    for x in range(im.width):
                        r, g, b, a = px[x, y]
                        if a:
                            lum = r * 3 + g * 6 + b
                            c = min(pal[1:], key=lambda q: abs(q[0] * 3 + q[1] * 6 + q[2] - lum))
                            px[x, y] = tuple(c[:3]) + (255,)
                frames.append(im)
            save_canvas_set(os.path.join(base, sheet, view), frames)
    print('placeholder frames for %s: %s' % (name, ', '.join(sorted(sheets))))


def build(mod):
    from PIL import Image
    import urbz_composite as C
    from urbzcomp import pack_chunk
    mdir = mod_dir(mod)
    pdir = os.path.join(mdir, 'people')
    first = len(json.load(open(os.path.join(PROJ, 'manifest.json')))['entries'])
    adir = os.path.join(mdir, 'assets')
    os.makedirs(adir, exist_ok=True)
    for f in os.listdir(adir):
        if f.endswith('.bin'):
            os.remove(os.path.join(adir, f))
    nxt = [first]

    def new_asset(data):
        n = nxt[0]
        open(os.path.join(adir, '%05d.bin' % n), 'wb').write(data)
        nxt[0] += 1
        return n + 1                                            # game id = file number + 1

    c_lines = ['/* Generated by urbz_anims.py build from mods/%s/people. Do not edit. */' % mod,
               '#include "game.h"', '']
    hooks = ['# Generated by urbz_anims.py: each person\'s animation list -> the list below', '']
    for pd in sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []:
        cfg_path = os.path.join(pdir, pd, 'anims.json')
        if not os.path.exists(cfg_path):
            continue
        cfg = json.load(open(cfg_path))
        cid, pal = cfg['person'], palette16(cfg['person'])
        stand_recs = row_of(cid, 0x04)[0]
        extra = C.parse_layout(asset(stand_recs[0][1] - 1)).entries[0].extra
        head = C.parse_layout(asset(stand_recs[0][1] - 1)).head
        sheets = {}                                             # sheet -> {view: (gfx gid, layout gid)}
        for a in cfg['anims'].values():
            sheet = a['sheet']
            if sheet in sheets:
                continue
            sheets[sheet] = {}
            for view in ('front', 'back'):
                d = os.path.join(pdir, pd, sheet, view)
                if not os.path.isdir(d):
                    continue
                gfx, entries = bytearray(), []
                for f in sorted(x for x in os.listdir(d) if x.endswith('.png')):
                    e, content = frame_data(Image.open(os.path.join(d, f)), pal, extra)
                    e.index, e.chunk_off = len(entries), len(gfx)
                    gfx += pack_chunk(CHUNK_FLAGS, content)
                    while len(gfx) % 4:
                        gfx += b'\0'
                    entries.append(e)
                if len(gfx) > 0xFFFF:
                    sys.exit('%s/%s/%s: the sheet is %d bytes; the game allows 64 KB' % (pd, sheet, view, len(gfx)))
                lay = C.Layout(bytes([max(e.w for e in entries), max(e.h for e in entries)]) + head[2:],
                               entries, 0, len(extra) // 6)
                g = new_asset(bytes(gfx))
                l = new_asset(C.build_layout(lay))
                sheets[sheet][view] = (g, l)
        rows = []
        for raw, rec, script in anim_rows(cid):
            rows.append('0x%08X, 0x%08X, 0x%X,' % (struct.unpack('<I', raw)[0], rec, script))
        for k, (aid, a) in enumerate(sorted(cfg['anims'].items())):
            views = sheets[a['sheet']]
            if not views:
                continue
            front, back = views['front'], views.get('back', views['front'])
            facings = [front, front, front, back, back]
            c_lines.append('static const u32 rec_%d_%s[20] = { %s };' % (cid, aid, ', '.join(
                '%d, %d, 0, %d' % (g, l, a['param']) for g, l in facings)))
            script = new_asset(script_bytes(a['script'])) if a['script'] else 0
            rows.append('0x%s, (u32)rec_%d_%s, %d,' % (aid.upper().rjust(8, '0'), cid, aid, script))
        c_lines.append('const u32 anims_%d[] = {   /* %s: the original rows, then the new ones */' % (cid, cfg['name']))
        c_lines += ['    ' + r for r in rows] + ['    0xC4, 0, 0', '};', '']
        hooks.append('u32 npc_anim_lists+0x%X @anims_%d        # %s' % (4 * cid, cid, cfg['name']))
    cdir = os.path.join(mdir, 'code')
    os.makedirs(cdir, exist_ok=True)
    open(os.path.join(cdir, 'anims.c'), 'w', newline='\n').write('\n'.join(c_lines) + '\n')
    open(os.path.join(cdir, 'hooks.txt'), 'w', newline='\n').write('\n'.join(hooks) + '\n')
    mj = os.path.join(mdir, 'mod.json')
    if not os.path.exists(mj):
        json.dump({'name': os.path.basename(os.path.normpath(mdir)), 'version': '1.0', 'description': 'New animations for the townspeople '
                   '(urbz_anims.py)', 'toggle': True, 'default': True}, open(mj, 'w'), indent=2)
    print('built %d new asset(s) (%05d-%05d) and %s' % (nxt[0] - first, first, nxt[0] - 1,
                                                         os.path.relpath(cdir, KIT)))


def list_groups():
    n = names()
    for g, (ref, ids) in GROUPS.items():
        has = [c for c in range(31, 67) if all(a in anim_ids(c) for a in ids)]
        print('%-7s %-14s guide: %-14s has it: %s' % (g, ' '.join('%02x' % a for a in ids), n[ref].split()[0],
                                                       ', '.join(n[c].split()[0] for c in has)))


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd = argv[0]
    if cmd == 'list':
        return list_groups()
    if cmd == 'build' and len(argv) == 2:
        return build(argv[1])
    if cmd in ('template', 'placeholder') and len(argv) >= 3:
        groups = argv[3:] or list(GROUPS)
        bad = [g for g in groups if g not in GROUPS]
        if bad:
            sys.exit('unknown group %s (groups: %s)' % (', '.join(bad), ', '.join(GROUPS)))
        return (template if cmd == 'template' else placeholder)(argv[1], argv[2], groups)
    sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
