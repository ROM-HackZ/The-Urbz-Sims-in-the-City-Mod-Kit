"""Look at the player's own animations: tests/mods/player-anim plays each id on the player (from the apartment
save), and a sheet shows 4 moments of each, zoomed on the player.

  python research/objects/player_anims.py OUT.png 0x5c 0x5d 0x6f ..."""
import os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT); sys.path.insert(0, os.path.join(KIT, 'verify')); sys.path.insert(0, os.path.join(KIT, 'tests'))
out_png, ids = sys.argv[1], [int(a, 0) for a in sys.argv[2:]]
sys.argv = sys.argv[:1]
import urbz_verify as V, proofs as P
from PIL import Image, ImageDraw

rom = P.build('player-anim', ['player-anim'])[0]
state = V.city_state(os.path.abspath(rom), None, 'apartment')
base = [['wait', 500], ['press', 'B', 4], ['wait', 300], ['press', 'B', 4], ['wait', 60]]


def run(script):
    out = tempfile.mkdtemp(prefix='urbz-panim-')
    res = V.run_child({'rom': os.path.abspath(rom), 'out': out, 'tag': 'snap', 'script': script, 'poke': [],
                       'state': state, 'snap': ['0x02100000:0x100000']}, timeout=3000)
    return res, out


res, _ = run(base + [['shot', 'x']])
mem = open(res['snaps'][0][1][0], 'rb').read()
k = mem.find(struct.pack('<I', 0x4D494E41))
g = 0x02100000 + k
e = struct.unpack('<I', mem[0x21AF0:0x21AF4])[0]
while e and struct.unpack('<H', mem[e - 0x02100000 + 8:e - 0x02100000 + 10])[0] != 0:
    e = struct.unpack('<I', mem[e - 0x02100000:e - 0x02100000 + 4])[0]
px, py = (v >> 16 for v in struct.unpack('<ii', mem[e - 0x02100000 + 0x18:e - 0x02100000 + 0x20]))
vx, vy = (v >> 16 for v in struct.unpack('<ii', mem[0x22888:0x22890]))
sx, sy = px - vx, py - vy                           # the player's feet on screen
script = list(base)
for a in ids:
    script += [['poke', '0x%08X=%s' % (g + 4, struct.pack('<HH', a, 240).hex())]]
    for t in range(4):
        script += [['wait', 20 if t == 0 else 30], ['shot', 'a%03x_%d' % (a, t)]]
res, out = run(script)
W = 64
Z = int(os.environ.get('ZOOM', 3))                  # zoom; COLS ids per row (each 4 moments wide)
C = int(os.environ.get('COLS', 1))
rows = (len(ids) + C - 1) // C
sheet = Image.new('RGB', (W * Z * 4 * C + 4 * C, W * Z * rows), (40, 40, 50))
d = ImageDraw.Draw(sheet)
for n, a in enumerate(ids):
    r, c = n // C, n % C
    x0 = c * (W * Z * 4 + 4)
    for t in range(4):
        im = Image.open(os.path.join(out, 'snap_a%03x_%d.png' % (a, t))).crop((sx - 32, sy - 56, sx + 32, sy + 8))
        sheet.paste(im.resize((W * Z, W * Z), Image.NEAREST), (x0 + W * Z * t, W * Z * r))
    d.text((x0 + 2, W * Z * r + 2), '%02x' % a, fill=(255, 255, 0))
sheet.save(out_png)
print(out_png)
