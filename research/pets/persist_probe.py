"""Probe (Phase 9 step 1): do placed pets survive leaving home and coming back, and save/load?"""
import json, os, struct, subprocess, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, 'tests'))
import proofs as P

ROM = sys.argv[1] if len(sys.argv) > 1 else os.path.join(KIT, 'build', 'play-pets.nds')
SAV = os.path.join(KIT, 'verify', 'saves', 'apartment.sav')
LOAD = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'loadgame.json')))


def goto(area, entry=0):
    return [['poke', '0x027C009C=81000000'], ['poke', '0x027C00A0=00000000'],
            ['poke', '0x027C00A4=%s' % struct.pack('<I', area).hex()], ['poke', '0x02141C28=%02x' % entry],
            ['wait', 500]]


def place(obj):
    return [['poke', '0x0214188C=' + struct.pack('<HI', obj, 0).hex()], ['poke', '0x02141338=01'], ['wait', 20],
            ["touch", 236, 166, 8], ["wait", 90], ["touch", 84, 75, 8], ["wait", 90],
            ["touch", 131, 36, 8], ["wait", 30], ["touch", 131, 36, 8], ["wait", 90], ["touch", 236, 166, 8],
            ["wait", 60]] + [["press", "DOWN", 12], ["wait", 20]] * 3 + [["press", "A", 6], ["wait", 300]]


def run(script, sav=SAV, extra=()):
    p = os.path.join(tempfile.mkdtemp(), 's.json')
    json.dump(script, open(p, 'w'))
    out = P.run(P.VERIFY + ['ram', ROM, '--sav', sav, '--script', p, '--frames', '30', '--read', P.HEAP_SCAN,
                            '--read', '0x02141338:1', '--read', '0x02141FEC:4'] + list(extra))
    vals = {l.split(' = ')[0].strip(): bytes.fromhex(l.split(' = ')[1].strip()) for l in out.splitlines() if ' = ' in l}
    heap = vals[P.HEAP_SCAN]
    live = [(hex(a), k, hex(struct.unpack_from('<I', heap, a - 0x0214DE20 + 0xC)[0])) for a, k in P.critters(heap)]
    k = heap.find(struct.pack('<I', 0x53544550))
    stats = struct.unpack_from('<7I', heap, k) if k >= 0 else None
    return live, 'pockets', vals['0x02141338:1'][0], 'area', struct.unpack('<I', vals['0x02141FEC:4'])[0], 'stats', stats[1:] if stats else None


base = LOAD + [['press', 'B', 6], ['wait', 60]]
obj = int(sys.argv[2]) if len(sys.argv) > 2 else 386
if not os.environ.get('PROBE_SAVE_ONLY'):
    print('placed:              ', run(base + place(obj)))
    print('out to 19 and back:  ', run(base + place(obj) + goto(19) + goto(22)))
sav = os.environ.get('PROBE_SAV') or os.path.join(tempfile.mkdtemp(), 'p.sav')
s = os.path.join(tempfile.mkdtemp(), 's.json')
json.dump(base + place(obj) + json.load(open(os.path.join(KIT, 'verify', 'scripts', 'savegame.json'))), open(s, 'w'))
P.run(P.VERIFY + ['play', ROM, '--sav', SAV, '--script', s, '--save', os.path.join(tempfile.mkdtemp(), 'x.dst'),
                  '--export-sav', sav])
print('saved, power-off, load:', run(LOAD + [['press', 'B', 6], ['wait', 300]], sav=sav))
print(subprocess.run([sys.executable, os.path.join(KIT, 'urbz_save.py'), 'info', sav], capture_output=True, text=True).stdout)
