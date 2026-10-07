"""Phase 10 beds: a pet in its bed at night (to tune pets.json "bed_spot"). Places the bed, then the pet, in
the apartment save at 23:30 and shoots after 600 frames. Usage: bed_shot.py ROM PET_OBJECT BED_OBJECT"""
import json, os, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom, pet, bed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1]
import proofs as P
work = tempfile.mkdtemp(prefix='bedshot-')
night = os.path.join(work, 'night.sav')
P.run([sys.executable, os.path.join(KIT, 'urbz_save.py'), 'set', os.path.join(KIT, 'verify', 'saves', 'apartment.sav'),
       night, '--clock', '23:30'])
load = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'))) + [['press', 'B', 6], ['wait', 60]]
p = os.path.join(work, 's.json')
pre = []
json.dump(load + pre + P._pocket_place(bed, ['RIGHT'] * 2) + P._pocket_place(pet, ['DOWN'] * 3) +
          [['wait', 600], ['shot', 'bed_%d_%d' % (pet, bed)]], open(p, 'w'))
out = P.run(P.VERIFY + ['ram', rom, '--sav', night, '--script', p, '--frames', '1', '--read', P.HEAP_SCAN])
st = P._pets_stats(bytes.fromhex([l for l in out.splitlines() if ' = ' in l][0].split(' = ')[1].strip()))
print(pet, bed, 'to_bed', st['to_bed'], 'in_bed', st['in_bed'], 'bed', st['bed0'] & 0xFFFF, st['bed0'] >> 16,
      'pet', st['pet0'] & 0xFFFF, st['pet0'] >> 16, 'action', st['mood0'] >> 24, out.strip().splitlines()[-1])
