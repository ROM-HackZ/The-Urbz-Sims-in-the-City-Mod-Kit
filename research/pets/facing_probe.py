"""Do strays face the way they walk? (DeSmuME) From verify/saves/urbania.sav: the Puppy is put about 120 px
from its spot in each of four directions so it walks home (S_HOME, steered by pets-kit), with the player
beside its spot; screenshots every 12 frames go into one contact sheet per direction.
Usage: facing_probe.py ROM OUTDIR"""
import glob, json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom, outdir = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1]
import proofs as P
from PIL import Image

sys.path.insert(0, os.path.join(KIT, 'research', 'pets'))
SAV = os.path.join(KIT, 'verify', 'saves', 'urbania.sav')
load = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'))) + [['press', 'B', 6], ['wait', 60]]
start = load + [['wait', 500], ['press', 'A', 4], ['wait', 60]]
work = tempfile.mkdtemp(prefix='facing-')
os.makedirs(outdir, exist_ok=True)
SYM = json.load(open(os.path.join(KIT, 'code', 'pets-kit', 'build', 'patch.json')))['symbols']


def run(script, *reads):
    p = os.path.join(work, 's.json')
    json.dump(script, open(p, 'w'))
    cmd = P.VERIFY + ['ram', rom, '--sav', SAV, '--script', p, '--frames', '1', '--read', '0x02100000:0x100000']
    for r in reads:
        cmd += ['--read', r]
    out = P.run(cmd)
    vals = {l.split(' = ')[0].strip(): bytes.fromhex(l.split(' = ')[1].strip()) for l in out.splitlines() if ' = ' in l}
    ev = [l for l in out.splitlines() if 'evidence' in l.lower()]
    return vals, out


def entities(mem):
    rd = lambda a, n: mem[a - 0x02100000:a - 0x02100000 + n]
    e, out = struct.unpack('<I', rd(0x02121AF0, 4))[0], []
    while e and 0x02100000 <= e < 0x02200000 and len(out) < 300:
        t, k = struct.unpack('<HH', rd(e + 8, 4))
        x, y = struct.unpack('<ii', rd(e + 0x18, 8))
        out.append((e, t, k, x >> 16, y >> 16, rd(e + 0x12, 1)[0]))
        e = struct.unpack('<I', rd(e, 4))[0]
    return out


def pos(addr, x, y):
    return ['poke', '0x%08X=%s' % (addr + 0x18, struct.pack('<iiii', x << 16, y << 16, x << 16, y << 16).hex())]


vals, _ = run(start)
ents = entities(vals['0x02100000:0x100000'])
player = [e for e, t, *_ in ents if t == 0][0]
crit = [(e, x, y) for e, t, k, x, y, f in ents if t == 9]
print('critters', [(hex(e), x, y) for e, x, y in crit])
pup, hx, hy = crit[0]
ONLY = os.environ.get('ONLY')
for name, (ox, oy) in {'from-east': (120, 0), 'from-west': (-120, 0), 'from-south': (0, 115),
                       'from-north': (0, -115)}.items():
    if ONLY and name != ONLY:
        continue
    script = start + [pos(player, hx + ox // 2, hy + oy // 2 + 30), ['wait', 200], pos(pup, hx + ox, hy + oy), ['wait', 4]]
    for i in range(8):
        script += [['shot', '%s%d' % (name, i)], ['wait', 12]]
    vals, out = run(script)
    ev = sorted(glob.glob(os.path.join(KIT, 'verify', 'evidence', '*-ram')))[-1]
    shots = [Image.open(os.path.join(ev, 'ram_%s%d.png' % (name, i))).crop((0, 0, 256, 160)) for i in range(8)]
    sheet = Image.new('RGB', (shots[0].width * 4, shots[0].height * 2))
    for i, s in enumerate(shots):
        sheet.paste(s, ((i % 4) * s.width, (i // 4) * s.height))
    sheet.save(os.path.join(outdir, name + '.png'))
    e2 = [(hex(e), k, x, y, f) for e, t, k, x, y, f in entities(vals['0x02100000:0x100000']) if t in (0, 9) and abs(x - hx) < 200 and abs(y - hy) < 200]
    mem = vals['0x02100000:0x100000']
    rd = lambda a, n: mem[a - 0x02100000:a - 0x02100000 + n]
    base = struct.unpack('<I', rd(pup + 0x4C, 4))[0] - SYM['strays_behaviour']
    sl = [struct.unpack_from('<IBBBBH', rd(base + SYM['stray_live'] + 16 * k, 16)) for k in range(2)]
    print(name, 'end', e2, 'stray_live', [(hex(a), m, t) for a, m, _, mv, _, t in sl], ev)
