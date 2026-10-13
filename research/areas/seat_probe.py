"""Where do people sit on seats added with seats.json? Builds tests/mods/seat-test + a test mod holding SEATS,
watches AREA from SAVE for STEPS snapshots, and draws every sitter's spot (state 0x11, a sit animation) on the
area's picture MAP (from area_map.py, with its .json for the origin), with the added seats marked.

  python research/areas/seat_probe.py SEATS.json SAVE AREA MAP.png OUT.png [STEPS]"""
import json, os, shutil, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT); sys.path.insert(0, os.path.join(KIT, 'tests'))
seats, save, area, map_png, out_png = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
steps = int(sys.argv[6]) if len(sys.argv) > 6 else 60
sys.argv = sys.argv[:1]
import proofs as P
from PIL import Image, ImageDraw

mod = tempfile.mkdtemp(prefix='seat-test-')
json.dump({'name': 'seat-spots', 'description': 'test seats'}, open(os.path.join(mod, 'mod.json'), 'w'))
shutil.copy(seats, os.path.join(mod, 'seats.json'))
shutil.copy(os.path.join(KIT, 'mods', 'npc-life', 'poses.json'), mod)   # (everyone needs the sit animation)
rom, log, _ = P.build('seat-probe', ['seat-test', mod])     # (tests/mods/seat-test sends people to each seat)
print([l for l in log.splitlines() if l.startswith('seats:')])
mems, out = P._area_snaps(rom, save, area, steps, 60)
sat = {}
k0 = mems[-1].find(struct.pack('<I', 0x54414553))
if k0 >= 0:
    sent, refused, ticks = struct.unpack_from('<3I', mems[-1], k0 + 4)
    objs = struct.unpack_from('<24H', mems[-1], k0 + 16)
    xs = struct.unpack_from('<24h', mems[-1], k0 + 64); ys = struct.unpack_from('<24h', mems[-1], k0 + 112)
    tries = mems[-1][k0 + 160:k0 + 184]
    print('seat-test: sent', sent, 'refused', refused, 'ticks', ticks)
    print('seats seen:', [(o, x, y, t) for o, x, y, t in zip(objs, xs, ys, tries) if o])
    sts = struct.unpack_from('<64H', mems[-1], k0 + 184)
    print('states of the people sent (ticks):', {hex(i): n for i, n in enumerate(sts) if n})
    nlog = struct.unpack_from('<I', mems[-1], k0 + 184 + 128 + 16)[0]
    lg = mems[-1][k0 + 184 + 128 + 20:k0 + 184 + 128 + 20 + 256]
    print('log', nlog, ' '.join('%d:%02x/%02x/%d' % tuple(lg[4 * i:4 * i + 4]) for i in range(min(nlog, 64))))
for k, mem in enumerate(mems):
    rd = lambda a, n: mem[a - 0x02100000:a - 0x02100000 + n]
    e = struct.unpack('<I', rd(0x02121AF0, 4))[0]
    while e and 0x02100000 <= e < 0x02200000:
        t, who = struct.unpack('<HH', rd(e + 8, 4))
        st, an = rd(e + 0x104, 1)[0], rd(e + 0xC7, 1)[0]
        if t == 7 and st == 0x11:
            x, y = (v >> 16 for v in struct.unpack('<ii', rd(e + 0x18, 8)))
            sat.setdefault((x, y, an, rd(e + 0x12, 1)[0]), []).append((k, who))
        e = struct.unpack('<I', rd(e, 4))[0]
meta = json.load(open(map_png[:-4] + '.json'))
ox, oy = meta['origin']
img = Image.open(map_png).convert('RGB')
dr = ImageDraw.Draw(img)
for i in json.load(open(seats))['areas'][str(area)]:
    x, y = i['x'] - ox, i['y'] - oy
    dr.rectangle((x - 3, y - 3, x + 3, y + 3), outline=(255, 0, 255))
    dr.text((x + 4, y + 2), 'n%d f%d' % (i['object'], i.get('facing', 3)), fill=(255, 0, 255))
for (x, y, an, face), who in sat.items():
    dr.ellipse((x - ox - 2, y - oy - 2, x - ox + 2, y - oy + 2), fill=(0, 255, 0))
    print('sat at', x, y, 'anim %02x facing %d' % (an, face), 'snapshots', [k for k, _ in who][:6], 'who', sorted({w for _, w in who}))
img.save(out_png)
shots = []                                        # the first snapshot of each sitting spot, as the game drew it
for (x, y, an, face), who in sorted(sat.items(), key=lambda kv: kv[1][0][0]):
    if an in (0x6C, 0x6D) and len(shots) < 8 and not any(abs(x - a) + abs(y - b) < 8 for a, b, _ in shots):
        shots.append((x, y, who[0][0]))
if shots:
    sheet = Image.new('RGB', (512, 160 * ((len(shots) + 1) // 2)))
    for i, (x, y, k) in enumerate(shots):
        sheet.paste(Image.open(os.path.join(out, 'snap_s%02d.png' % k)).crop((0, 0, 256, 160)), ((i % 2) * 256, (i // 2) * 160))
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out_png[:-4] + '-shots.png')
print(out_png, 'screens', out)
