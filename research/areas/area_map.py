"""A picture of a whole area with world coordinates: the player is moved across it, each top-screen shot is
pasted where the view was (0x02122888: {s32 x, s32 y} << 16, the world point at the top-left of the top
screen, kept inside the area's edges; 0x02122D48 is where the camera aims: the player's feet minus 28 in y), and the area's object records (type 5) and people are marked.

  python research/areas/area_map.py ROM SAVE AREA OUT.png [STEP]

World units are screen pixels. Use it to find where things are drawn (e.g. chairs that aren't objects)."""
import json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT); sys.path.insert(0, os.path.join(KIT, 'verify')); sys.path.insert(0, os.path.join(KIT, 'tests'))
rom, save, area, out_png = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
step = int(sys.argv[5]) if len(sys.argv) > 5 else 96
sys.argv = sys.argv[:1]
import urbz_verify as V, proofs as P, urbz_anims as A
from PIL import Image, ImageDraw

VIEW = 0x02122888


def area_records(area):
    """[(type, x, y, raw)] of the area data's records, every section and group."""
    arm9 = A.arm9()
    gid = struct.unpack_from('<I', arm9, 0x020C87E0 + area * 0x14 + 8 - 0x02000000)[0]
    d = A.asset(gid - 1)
    H, ne = struct.unpack_from('<HH', d, 0)
    out = [('entry', x, y, b'') for x, y, _, _ in (struct.unpack_from('<hhHH', d, 4 + 8 * i) for i in range(ne))]
    for s in range(d[H]):
        so = struct.unpack_from('<H', d, H + 8 + 8 * s)[0]
        for k in range(struct.unpack_from('<H', d, so + 8)[0]):
            go = so + 8 + struct.unpack_from('<H', d, so + 10 + 2 * k)[0]
            n = struct.unpack_from('<H', d, go)[0]
            p = (go + 2 + n + 3) & ~3
            for sz in d[go + 2:go + 2 + n]:
                r = d[p:p + sz]
                t, _, x, y = struct.unpack_from('<HHhh', r)
                out.append((t, x, y, r))
                p += sz
    return out


def run(script):
    out = tempfile.mkdtemp(prefix='urbz-map-')
    state = V.city_state(os.path.abspath(rom), None, save)
    res = V.run_child({'rom': os.path.abspath(rom), 'out': out, 'tag': 'snap', 'script': script, 'poke': [],
                       'state': state, 'snap': ['0x02100000:0x100000']}, timeout=3000)
    return [(name, open(f[0], 'rb').read()) for name, f in res['snaps']], out


base = [['wait', 500], ['press', 'B', 4], ['wait', 300], ['press', 'B', 4], ['wait', 60]] + P._area_goto(area) + \
    [['wait', 200], ['press', 'B', 4], ['wait', 60]]
snaps, _ = run(base + [['shot', 'start']])
mem = snaps[0][1]
rd = lambda m, a, k: m[a - 0x02100000:a - 0x02100000 + k]
e = struct.unpack('<I', rd(mem, 0x02121AF0, 4))[0]
while e and struct.unpack('<H', rd(mem, e + 8, 2))[0] != 0:
    e = struct.unpack('<I', rd(mem, e, 4))[0]
recs = area_records(area)
xs = [x for _, x, _, _ in recs] + [struct.unpack('<i', rd(mem, e + 0x18, 4))[0] >> 16]
ys = [y for _, _, y, _ in recs] + [struct.unpack('<i', rd(mem, e + 0x1C, 4))[0] >> 16]
x0, x1, y0, y1 = min(xs) - 160, max(xs) + 160, min(ys) - 120, max(ys) + 140
entries = [(x, y) for t, x, y, _ in recs if t == 'entry'] + [(x, y) for t, x, y, _ in recs if t in (3, 20)]
pts = [(x, y) for y in range(y0, y1 + 1, step) for x in range(x0, x1 + 1, step * 2)
       if all(abs(x - ex) + abs(y - ey) > 90 for ex, ey in entries)]      # (not onto a door: it would leave)
script = list(base)
for k, (x, y) in enumerate(pts):
    script += [['poke', '0x%08X=%s' % (e + 0x18, struct.pack('<iiii', x << 16, y << 16, x << 16, y << 16).hex())],
               ['wait', 45], ['shot', 'p%03d' % k]]
snaps, out = run(script)
W, H = x1 - x0 + 512, y1 - y0 + 400
img = Image.new('RGB', (W, H), (40, 40, 50))
ox, oy = x0 - 256, y0 - 200                       # world -> image: (x - ox, y - oy)
people = {}
for name, m in snaps:
    if not name.startswith('p') or struct.unpack('<I', rd(m, 0x02141FEC, 4))[0] != area:
        continue                                  # (went through a door: elsewhere)
    vx, vy = (v >> 16 for v in struct.unpack('<ii', rd(m, VIEW, 8)))
    shot = Image.open(os.path.join(out, 'snap_%s.png' % name)).crop((0, 0, 256, 158))
    img.paste(shot, (vx - ox, vy - oy))
    q = struct.unpack('<I', rd(m, 0x02121AF0, 4))[0]
    while q and 0x02100000 <= q < 0x02200000:
        t, who = struct.unpack('<HH', rd(m, q + 8, 4))
        if t == 7:
            people[who] = tuple(v >> 16 for v in struct.unpack('<ii', rd(m, q + 0x18, 8)))
        q = struct.unpack('<I', rd(m, q, 4))[0]
dr = ImageDraw.Draw(img)
for t, x, y, r in recs:
    if t == 5:
        obj = struct.unpack_from('<H', r, 8)[0]
        dr.ellipse((x - ox - 3, y - oy - 3, x - ox + 3, y - oy + 3), outline=(255, 255, 0))
        dr.text((x - ox + 4, y - oy - 4), 'o%d f%d' % (obj, r[10]), fill=(255, 255, 0))
    elif t == 'entry':
        dr.rectangle((x - ox - 2, y - oy - 2, x - ox + 2, y - oy + 2), outline=(0, 255, 255))
for gx in range((x0 // 50) * 50, x1 + 200, 50):            # a 50-unit grid with labels
    dr.line((gx - ox, 0, gx - ox, 6), fill=(255, 255, 255))
    dr.text((gx - ox + 1, 8), str(gx), fill=(255, 255, 255))
for gy in range((y0 // 50) * 50, y1 + 200, 50):
    dr.line((0, gy - oy, 6, gy - oy), fill=(255, 255, 255))
    dr.text((8, gy - oy - 4), str(gy), fill=(255, 255, 255))
img.save(out_png)
json.dump({'origin': [ox, oy], 'records': [(t, x, y, r.hex()) for t, x, y, r in recs if t != 'entry'],
           'people': people}, open(out_png[:-4] + '.json', 'w'))
print(out_png, 'world origin', ox, oy, 'size', W, H)
