"""Talk to someone NPC Life sat down, then watch them (DeSmuME). From verify/saves/zz-lobby22.sav (lobby.sav at
21:55, made with urbz_save.py set --clock): Kris sits on the lobby sofa about 900 frames in; the player is put
beside him facing him, presses A (the chat), leaves it, and Kris's state/action is printed every 300 frames.
Usage: sit_talk_probe.py ROM [TALK=1] [LATE frames]"""
import json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom = sys.argv[1]
talk = len(sys.argv) < 3 or sys.argv[2] != '0'
late = int(sys.argv[3]) if len(sys.argv) > 3 else 0     # extra frames first (Kris up again: 1500)
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.path.insert(0, os.path.join(KIT, 'verify')); sys.argv = sys.argv[:1]
import urbz_verify as V
SYM = json.load(open(os.path.join(KIT, 'mods', 'npc-life', 'code', 'build', 'patch.json')))['symbols']


def run(script):
    out = tempfile.mkdtemp(prefix='urbz-talk-')
    job = {'rom': os.path.abspath(rom), 'out': out, 'tag': 'snap', 'script': script, 'poke': [],
           'state': V.city_state(os.path.abspath(rom), None, 'zz-lobby22'), 'snap': ['0x02100000:0x100000']}
    res = V.run_child(job, timeout=3000)
    return [open(f[0], 'rb').read() for _, f in res['snaps']], out


def look(mem):
    rd = lambda a, k: mem[a - 0x02100000:a - 0x02100000 + k]
    e, out = struct.unpack('<I', rd(0x02121AF0, 4))[0], {}
    while e and 0x02100000 <= e < 0x02200000:
        t, who = struct.unpack('<HH', rd(e + 8, 4))
        if t in (0, 7):
            x, y = struct.unpack('<ii', rd(e + 0x18, 8))
            out[(t, who)] = (e, rd(e + 0x104, 1)[0], rd(e + 0x105, 1)[0], x >> 16, y >> 16)
        e = struct.unpack('<I', rd(e, 4))[0]
    k = mem.find(struct.pack('<I', 0x5443414E))
    base = 0x02100000 + k - SYM['npc_act']
    acts = [struct.unpack_from('<IB', rd(base + SYM['actors'] + 28 * a, 5)) for a in range(4)]
    return out, [w for a, w in acts if a]


first, _ = run([['wait', 300], ['press', 'B', 4], ['wait', 660 + late], ['shot', 'x']])
ppl, _ = look(first[0])
pl, kris = ppl[(0, 0)], ppl[(7, 45)]
print('player', hex(pl[0]), pl[1:], 'Kris', kris[1:])
pos = lambda x, y: ['poke', '0x%08X=%s' % (pl[0] + 0x18, struct.pack('<iiii', x << 16, y << 16, x << 16, y << 16).hex())]
script = [['wait', 300], ['press', 'B', 4], ['wait', 660 + late]]
if talk:
    script += [pos(kris[3] - 18, kris[4] + 9), ['poke', '0x%08X=02' % (pl[0] + 0x12)], ['wait', 30], ['shot', 'near'],
               ['press', 'A', 4], ['wait', 240], ['shot', 'talk']] + [['press', 'B', 4], ['wait', 60]] * 4 + \
              [['touch', 30, 10, 6], ['wait', 120], ['shot', 'after']]
script += sum(([['wait', 300], ['shot', 's%02d' % k]] for k in range(4)), [])
snaps, out = run(script)
names = {0: 'near', 1: 'talk', 2: 'after'} if talk else {}
for k, m in enumerate(snaps):
    ppl, acts = look(m)
    p, kr = ppl.get((0, 0)), ppl.get((7, 45))
    print('%-6s player %s Kris %s actors %s' % (names.get(k, k - len(names)), p and (hex(p[1]), p[3], p[4]),
                                               kr and (hex(kr[1]), hex(kr[2]), kr[3], kr[4]), acts))
print(out)
