"""(pet_probe) Petting a trusted stray: does the player stay put? Built on the strays quest in Urbania Park, step by step (DeSmuME). From verify/saves/urbania.sav (out of jail,
no home yet): the strays appear with the intro box; the player is put next to the Puppy with two Pet Treats;
stand still (it comes up), A, Feed; next day (clock poke) A, Feed again; A, Take Home; the Kitten gets adopted.
Prints pets_stats after each stage and leaves screenshots. Usage: strays_probe.py ROM"""
import json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom = sys.argv[1]
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1]
import proofs as P

SAV = os.path.join(KIT, 'verify', 'saves', 'urbania.sav')
load = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'))) + [['press', 'B', 6], ['wait', 60]]
work = tempfile.mkdtemp(prefix='strays-')


def run(script, *reads):
    p = os.path.join(work, 's.json')
    json.dump(script, open(p, 'w'))
    cmd = P.VERIFY + ['ram', rom, '--sav', SAV, '--script', p, '--frames', '1', '--read', P.HEAP_SCAN,
                      '--read', '0x02100000:0x100000']
    for r in reads:
        cmd += ['--read', r]
    out = P.run(cmd)
    vals = {l.split(' = ')[0].strip(): bytes.fromhex(l.split(' = ')[1].strip()) for l in out.splitlines() if ' = ' in l}
    return vals, out.strip().splitlines()[-1]


def entities(mem):
    rd = lambda a, n: mem[a - 0x02100000:a - 0x02100000 + n]
    head = struct.unpack('<I', rd(0x02121AF0, 4))[0]
    e, out = head, []
    while e and 0x02100000 <= e < 0x02200000 and len(out) < 300:
        t, k = struct.unpack('<HH', rd(e + 8, 4))
        x, y = struct.unpack('<ii', rd(e + 0x18, 8))
        out.append((e, t, k, x >> 16, y >> 16))
        e = struct.unpack('<I', rd(e, 4))[0]
    return out


def show(tag, vals, ev):
    st = P._pets_stats(vals[P.HEAP_SCAN])
    ents = entities(vals['0x02100000:0x100000'])
    crit = [(k, x, y) for _, t, k, x, y in ents if t == 9]
    pl = [(x, y) for _, t, k, x, y in ents if t == 0]
    print('%-10s quest %d strays %d msgs %d fed %d trust %08x adopter %d walk %d critters %s player %s last_pick %d %s' % (
        tag, st['quest'], st['stray_n'], st['msgs'], st['stray_fed'], st['trust'], st['adopter'], st['adopt_walk'],
        crit, pl, st['last_pick'], ev))
    return st, ents


# 1. arrive: the strays and the intro box
vals, ev = run(load + [['wait', 500], ['shot', 'intro0'], ['wait', 200], ['shot', 'intro'], ['wait', 300], ['shot', 'intro2'], ['press', 'A', 4], ['wait', 60]])
st, ents = show('arrive', vals, ev)
player = [e for e, t, *_ in ents if t == 0][0]
puppy = [(x, y) for _, t, k, x, y in ents if t == 9][0]

# 2. next to the Puppy, two treats, stand still (it comes up), A, Feed (option 1)
treats = ['poke', '0x0214188C=' + (struct.pack('<HI', 396, 0) * 2).hex()], ['poke', '0x02141338=02']
near = ['poke', '0x%08X=%s' % (player + 0x18, struct.pack('<iiii', (puppy[0] - 50) << 16, (puppy[1] + 10) << 16,
                                                            (puppy[0] - 50) << 16, (puppy[1] + 10) << 16).hex())]
day1 = load + [['wait', 1000], ['press', 'A', 4], ['wait', 60]] + list(treats) + [near, ['wait', 150], ['shot', 'came'],
       ['press', 'A', 4], ['wait', 120], ['shot', 'menu1'], ['press', 'A', 4], ['wait', 400], ['shot', 'fed1'],
       ['press', 'A', 4], ['wait', 60]]

# 3. the next day: feed again -> it trusts you; then Take Home (option 3 of Pet / Feed / Take Home / Leave)
nextday = [['poke', '0x0214112C=0500']]          # game_time.day = 5
day2 = day1 + [['wait', 100]] + nextday + [['wait', 150], ['press', 'A', 4], ['wait', 120], ['shot', 'menu2'],
       ['press', 'DOWN', 4], ['wait', 10], ['press', 'A', 4], ['wait', 400], ['shot', 'fed2'], ['press', 'A', 4], ['wait', 60]]

# 4. trusted: A, Pet (the first option); positions during the petting
def ppos(vals):
    ents = entities(vals['0x02100000:0x100000'])
    return [(x, y) for _, t, k, x, y in ents if t == 0][0], [(k, x, y) for _, t, k, x, y in ents if t == 9 and abs(x - 806) < 120]
base = day2 + [['wait', 150]]
vals, _ = run(base)
print('before A', *ppos(vals))
for w in (30, 90, 200, 400):
    vals, ev = run(base + [['press', 'A', 4], ['wait', 120], ['shot', 'menu'], ['press', 'A', 4], ['wait', w], ['shot', 'pet%d' % w]])
    st = P._pets_stats(vals[P.HEAP_SCAN])
    print('pet +%3d' % w, *ppos(vals), 'trust %08x' % st['trust'], ev)
