"""Two strays side by side: does A talk to the one you face? (DeSmuME) From verify/saves/urbania.sav: the
player stands still between the strays' spots until both come and sit by them, turns LEFT or RIGHT with a
short tap, presses A; prints which stray is talking (stray_live mode 1 = S_TALK), where each one is, and
whether the player moved while the menu was open. Usage: pick_probe.py ROM"""
import json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom = sys.argv[1]
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1]
import proofs as P

SAV = os.path.join(KIT, 'verify', 'saves', 'urbania.sav')
SYM = json.load(open(os.path.join(KIT, 'code', 'pets-kit', 'build', 'patch.json')))['symbols']
load = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'))) + [['press', 'B', 6], ['wait', 60]]
start = load + [['wait', 500], ['press', 'A', 4], ['wait', 60]]
work = tempfile.mkdtemp(prefix='pick-')


def run(script):
    p = os.path.join(work, 's.json')
    json.dump(script, open(p, 'w'))
    out = P.run(P.VERIFY + ['ram', rom, '--sav', SAV, '--script', p, '--frames', '1', '--read', '0x02100000:0x100000'])
    mem = [bytes.fromhex(l.split(' = ')[1].strip()) for l in out.splitlines() if ' = ' in l][0]
    return mem, out.strip().splitlines()[-1]


def rd(mem, a, n):
    return mem[a - 0x02100000:a - 0x02100000 + n]


def entities(mem):
    e, out = struct.unpack('<I', rd(mem, 0x02121AF0, 4))[0], []
    while e and 0x02100000 <= e < 0x02200000 and len(out) < 300:
        t, k = struct.unpack('<HH', rd(mem, e + 8, 4))
        x, y = struct.unpack('<ii', rd(mem, e + 0x18, 8))
        out.append((e, t, k, x >> 16, y >> 16, rd(mem, e + 0x12, 1)[0]))
        e = struct.unpack('<I', rd(mem, e, 4))[0]
    return out


def state(mem):
    ents = entities(mem)
    pl = [(x, y, f) for e, t, k, x, y, f in ents if t == 0][0]
    crit = {e: (k, x, y, f) for e, t, k, x, y, f in ents if t == 9}
    some = [e for e in crit if 0x0200 < crit[e][1] and abs(crit[e][1] - 806) < 150 and abs(crit[e][2] - 670) < 150]
    base = struct.unpack('<I', rd(mem, some[0] + 0x4C, 4))[0] - SYM['strays_behaviour'] if some else 0
    sl = [struct.unpack_from('<IBBBBH', rd(mem, base + SYM['stray_live'] + 16 * k, 16)) for k in range(2)]
    return pl, [(k, crit.get(a, ('?',))[:4], m) for k, (a, m, *_ ) in enumerate(sl)]


def pos(addr, x, y):
    return ['poke', '0x%08X=%s' % (addr + 0x18, struct.pack('<iiii', x << 16, y << 16, x << 16, y << 16).hex())]


mem, ev = run(start)
player = [e for e, t, *_ in entities(mem) if t == 0][0]
wait = start + [pos(player, 806, 690), ['wait', 600]]
mem, ev = run(wait)
print('waited     player %s strays %s' % state(mem))
for turn in ('LEFT', 'RIGHT', 'UP', 'DOWN'):
    s = wait + [['press', turn, 2], ['wait', 10]]
    mem, _ = run(s)
    before = state(mem)
    mem, ev = run(s + [['press', 'A', 4], ['wait', 120], ['shot', 'menu-' + turn]])
    after = state(mem)
    print('%-6s before player %s strays %s\n       after  player %s strays %s  %s' % (turn, before[0], before[1],
                                                                                     after[0], after[1], ev))
