"""Where must the player stand to be "at" a placed object? Places OBJ at home (as use_probe.py), then pokes the
player to each spot around it and each facing (+0x12, 0-7), and reads the game's current object under the
player's attention (*0x021473FC, set by FUN_02084104 when the tile in front is inside an object's bounds).
Usage: face_scan.py ROM OBJ [RANGE STEP]"""
import json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom, obj = sys.argv[1], int(sys.argv[2])
R, S = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (48, 8)
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.path.insert(0, os.path.join(KIT, 'verify')); sys.argv = sys.argv[:1]
import proofs as P
import urbz_verify as V

PLACE = json.load(open(P.place_script()))
AREAS = json.load(open(V.AREAS_JSON))['areas'][68]['entry_points']


def job(script, snap):
    out = tempfile.mkdtemp(prefix='urbz-scan-')
    return {'rom': os.path.abspath(rom), 'out': out, 'tag': 'snap', 'poke': P.pocket_pokes(obj),
            'state': V.city_state(os.path.abspath(rom)), 'goto': (68, AREAS[0]['id'] if AREAS else 0),
            'script': PLACE + [['wait', 30]] + script, 'snap': snap}


def ents(mem):
    rd = lambda a, k: mem[a - 0x02100000:a - 0x02100000 + k]
    e, out = struct.unpack('<I', rd(0x02121AF0, 4))[0], []
    while e and 0x02100000 <= e < 0x02200000:
        t, who = struct.unpack('<HH', rd(e + 8, 4))
        x, y = struct.unpack('<ii', rd(e + 0x18, 8))
        out.append((e, t, who, x >> 16, y >> 16))
        e = struct.unpack('<I', rd(e, 4))[0]
    return out


res = V.run_child(job([['shot', 'x']], ['0x02100000:0x100000']), timeout=600)
es = ents(open(res['snaps'][0][1][0], 'rb').read())
pl = [e for e in es if e[1] == 0][0]
ob = [e for e in es if e[1] == 5 and e[2] == obj][0]
print('player entity %08x, object entity %08x at %d,%d' % (pl[0], ob[0], ob[3], ob[4]))
hits = []
for dy in range(-R, R + 1, S):                    # (one emulator run per row: the job goes on a command line)
    cands, script = [], []
    for dx in range(-R, R + 1, S):
        x, y = ob[3] + dx, ob[4] + dy
        for f in range(8):
            cands.append((dx, dy, f))
            script += [['poke', '0x%08X=%s' % (pl[0] + 0x18, struct.pack('<iiii', x << 16, y << 16, x << 16, y << 16).hex())],
                       ['poke', '0x%08X=%02x' % (pl[0] + 0x12, f)], ['wait', 4], ['shot', 'c%d' % len(cands)]]
    res = V.run_child(job(script, ['0x021473FC:4']), timeout=6000)
    for (dx_, dy_, f), (_, files) in zip(cands, res['snaps']):
        if struct.unpack('<I', open(files[0], 'rb').read())[0] == ob[0]:
            hits.append((dx_, dy_, f))
print('at the object from:', hits)
