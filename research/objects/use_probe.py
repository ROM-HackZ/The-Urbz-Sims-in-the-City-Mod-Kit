"""Use a placed object at home (DeSmuME): put OBJ in Pockets, place it in the starting home (area 68), stand the
player next to it (DX, DY px from it, facing FACE: 1-8 clockwise, 8 = up), press A and watch.
Usage: use_probe.py ROM OBJ [DX DY FACE] [presses]   presses: e.g. "A,A" or "A,DOWN,A" (default "A")
Prints the player's and the object's entity state per shot, and the evidence folder."""
import json, os, struct, sys
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom, obj = sys.argv[1], int(sys.argv[2])
dx, dy, face = (int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (0, 20, 8)
presses = (sys.argv[6] if len(sys.argv) > 6 else 'A').split(',')
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1]
import proofs as P
MEM = '0x02100000:0x100000'


def run(extra):
    out = P.run(P.VERIFY + ['ram', rom, '--city', '--goto', '68', '--frames', '1', '--script', P.place_script(extra),
                            '--read', MEM] + sum((['--poke', p] for p in P.pocket_pokes(obj)), []))
    vals = dict(l.split(' = ', 1) for l in out.splitlines() if ' = ' in l)
    return bytes.fromhex(vals[MEM].strip()), out.strip().splitlines()[-1]


def ents(mem):
    rd = lambda a, k: mem[a - 0x02100000:a - 0x02100000 + k]
    e, out = struct.unpack('<I', rd(0x02121AF0, 4))[0], []
    while e and 0x02100000 <= e < 0x02200000:
        t, who = struct.unpack('<HH', rd(e + 8, 4))
        x, y = struct.unpack('<ii', rd(e + 0x18, 8))
        out.append((e, t, who, x >> 16, y >> 16, rd(e + 0x104, 1)[0], rd(e + 0x105, 1)[0], rd(e + 0xC7, 1)[0]))
        e = struct.unpack('<I', rd(e, 4))[0]
    return out


def nodes(mem):
    rd = lambda a, k: mem[a - 0x02100000:a - 0x02100000 + k]
    n, out = struct.unpack('<I', rd(0x0214490C, 4))[0], []
    while n and 0x02100000 <= n < 0x02200000 and len(out) < 100:
        out.append((n, struct.unpack('<H', rd(n + 8, 2))[0], struct.unpack('<4h', rd(n + 0x7C, 8)),
                    struct.unpack('<I', rd(n + 0x24, 4))[0]))
        n = struct.unpack('<I', rd(n, 4))[0]
    return out


mem, _ = run([['wait', 30]])
for n in nodes(mem):
    print('node %08x object %d bounds %s entity %08x' % n)
es = ents(mem)
pl = [e for e in es if e[1] == 0][0]
ob = [e for e in es if e[1] == 5 and e[2] == obj]
print('player', pl[3:], 'object', [o[3:5] for o in ob])
if not ob:
    sys.exit('object not placed')
ox, oy = ob[0][3], ob[0][4]
px, py = ox + dx, oy + dy
step = [['poke', '0x%08X=%s' % (pl[0] + 0x18, struct.pack('<iiii', px << 16, py << 16, px << 16, py << 16).hex())],
        ['poke', '0x%08X=%02x' % (pl[0] + 0x12, face)], ['wait', 30], ['shot', 'near']]
for k, b in enumerate(presses):
    step += [['press', b, 6], ['wait', 90], ['shot', 'p%d' % k]]
step += [['wait', 300], ['shot', 'later']]
mem, ev = run([['wait', 30]] + step)
for e in ents(mem):
    if e[1] == 0 or (e[1] == 5 and e[2] == obj):
        print('type %d id %d at %d,%d: state %02x action %02x anim %02x' % e[1:])
print(ev)
