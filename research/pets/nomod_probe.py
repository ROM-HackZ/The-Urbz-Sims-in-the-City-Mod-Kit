"""A save holding new things (a placed Dog Basket 397, a Cat Bed 398 and Pet Treats 396 in Pockets), loaded by
builds with and without the mods that add them. Makes the save with ROM_WITH from apartment.sav (DeSmuME),
then loads it with each ROM and prints the placed objects, Pockets and whether the game got to the city.
Usage: nomod_probe.py OUTDIR ROM_WITH ROM ... (screenshots and the save in OUTDIR)"""
import json, os, shutil, struct, sys
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out, rom_with, roms = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1]
import proofs as P

os.makedirs(out, exist_ok=True)
sav0 = os.path.join(KIT, 'verify', 'saves', 'apartment.sav')
load = P._load()
save = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'savegame.json')))


def place(steps):
    return [["touch", 236, 166, 8], ["wait", 90], ["touch", 84, 75, 8], ["wait", 90], ["touch", 131, 36, 8],
            ["wait", 30], ["touch", 131, 36, 8], ["wait", 90], ["touch", 236, 166, 8], ["wait", 60]] + \
        sum(([["press", k, 12], ["wait", 20]] for k in steps), []) + [["press", "A", 6], ["wait", 200]]


def objects(mem):
    rd = lambda a, n: mem[a - 0x02100000:a - 0x02100000 + n]
    node, objs = struct.unpack('<I', rd(0x0214490C, 4))[0], []
    while node and 0x02100000 <= node < 0x02200000 and len(objs) < 400:
        objs.append(struct.unpack('<H', rd(node + 8, 2))[0])
        node = struct.unpack('<I', rd(node, 4))[0]
    n = rd(0x02141338, 1)[0]
    pockets = [struct.unpack_from('<H', rd(0x0214188C, 6 * 8), 6 * k)[0] for k in range(min(n, 8))]
    area = rd(0x02141C20, 4)
    return sorted(objs), pockets


def core(heap):
    k = heap.find(struct.pack('<I', 0x45524F43))
    if k < 0:
        return 'none'
    f = struct.unpack_from('<21I', heap, k)
    return 'stashed %d restored %d dropped %d lost %d carry %d' % (f[17], f[18], f[19], f[20], f[12])


# round trip: load in the first build without the mod, save there, load that in the build with it
def round_trip(rom_without):
    p = os.path.join(out, 'rt.json')
    json.dump(load + [['wait', 300]] + save, open(p, 'w'))
    sav2 = os.path.join(out, 'saved-without.sav')
    P.run(P.VERIFY + ['play', rom_without, '--sav', sav, '--script', p, '--save', os.path.join(out, 'y.dst'),
                      '--export-sav', sav2])
    vals, ev = P._ram_run(rom_with, sav2, load + [['wait', 600], ['shot', 'back']], P.WORLD)
    objs, pockets = objects(vals[P.WORLD])
    print('round trip: saved in %s, loaded with the mod: new placed %s, Pockets %s; core %s; %s' % (
        os.path.basename(rom_without), [o for o in objs if o >= 386], pockets, core(vals[P.HEAP_SCAN]), ev))
    P._shot(ev, 'back', os.path.join(out, 'round-trip.png'))


pokes = [['poke', '0x02141338=03'],
         ['poke', '0x0214188C=' + struct.pack('<HIHIHI', 397, 0, 398, 0, 396, 0).hex()]]
script = load + pokes + [['wait', 30]] + place(['RIGHT'] * 2) + place(['DOWN'] * 3) + [['wait', 60], ['shot', 'placed']]
p = os.path.join(out, 'make.json')
json.dump(script + save, open(p, 'w'))
sav = os.path.join(out, 'new-things.sav')
P.run(P.VERIFY + ['play', rom_with, '--sav', sav0, '--script', p, '--save', os.path.join(out, 'x.dst'),
                  '--export-sav', sav])
for rom in [rom_with] + roms:
    try:
        vals, ev = P._ram_run(rom, sav, load + [['wait', 600], ['shot', 'loaded']], P.WORLD)
    except RuntimeError as e:
        print('%-28s FAILED: %s' % (os.path.basename(rom), str(e).splitlines()[-1][:300]))
        continue
    objs, pockets = objects(vals[P.WORLD])
    new = [o for o in objs if o >= 386]
    print('%-28s placed objects %d (new: %s), Pockets %s; core %s; %s' % (os.path.basename(rom), len(objs), new,
                                                                        pockets, core(vals[P.HEAP_SCAN]), ev))
    P._shot(ev, 'loaded', os.path.join(out, 'loaded-' + os.path.basename(rom) + '.png'))

if roms:
    round_trip(roms[0])
