"""Borrowed poses in melonDS: DeSmuME takes pizza.sav to Slice O' Life Pizza (area 51) and saves there, then
melonDS loads that save and takes a screenshot every 10 s (people sitting with borrowed poses, e.g. Gramma).
Usage: poses_melon.py ROM [SAVE AREA SHOTS]   (defaults: pizza 51 18). Prints the screenshot folder."""
import json, os, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom = os.path.abspath(sys.argv[1])
save, area, shots = (sys.argv[2], int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else ('pizza', 51, 18)
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.path.insert(0, os.path.join(KIT, 'verify')); sys.argv = sys.argv[:1]
import proofs as P
import urbz_melon as M

work = tempfile.mkdtemp(prefix='urbz-poses-melon-')
script = P._load() + P._area_goto(area) + [['wait', 300]] + json.load(open(os.path.join(KIT, 'verify', 'scripts', 'savegame.json')))
sp = os.path.join(work, 'to-area.json')
json.dump(script, open(sp, 'w'))
there = os.path.join(work, 'there.sav')
P.run(P.VERIFY + ['play', rom, '--sav', os.path.join(KIT, 'verify', 'saves', save + '.sav'), '--script', sp,
                  '--save', os.path.join(work, 'there.dst'), '--export-sav', there], timeout=1500)
look = P.MELON_LOAD + sum(([['wait', 600], ['shot', 'm%02d' % k]] for k in range(shots)), [])
for attempt in range(2):                          # (melonDS now and then fails to start under xvfb)
    try:
        res = M.run(rom, look, sav=there, out=os.path.join(work, 'melon'))
        break
    except RuntimeError as e:
        err = e
else:
    sys.exit('melonDS failed: %s' % err)
for name, f in res:
    print(name, f)
