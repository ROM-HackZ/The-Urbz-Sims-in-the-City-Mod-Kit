"""Put new furniture down in the apartment (from Pockets, as tests/proofs.py does for pets) and screenshot it.

  python research/objects/furniture_room.py OUT.png 430 431 432 ...     (up to 12 at once)"""
import os, shutil, sys
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, 'kit')); sys.path.insert(0, os.path.join(KIT, 'verify')); sys.path.insert(0, os.path.join(KIT, 'tests'))
out_png, objs = sys.argv[1], [int(a) for a in sys.argv[2:]]
sys.argv = sys.argv[:1]
import proofs as P

rom = P.build('furniture-room', [os.path.join(KIT, 'mods', 'more-furniture')])[0]
script = P._load()
for obj, (_, steps) in zip(objs, P.MANY_PLACES):
    script += P._rested(P._pocket_place(obj, steps))
script += [['wait', 120], ['shot', 'room']]
vals, ev = P._ram_run(rom, P.APARTMENT, script, P.WORLD)
shot = [f for f in os.listdir(ev) if f.endswith('room.png')]
shutil.copy(os.path.join(ev, shot[0]), out_png)
print(out_png, [(k, x, y) for e, t, k, x, y in P._world(vals[P.WORLD]) if t == 5 and k >= 430])
