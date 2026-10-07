"""Phase 10 beds: at night, does the Puppy walk to its Dog Basket and lie on it? Prints pets_stats and leaves
screenshots (evidence dir)."""
import json, os, sys, subprocess, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1] + sys.argv[1:]
import proofs as P
rom = sys.argv[1] if len(sys.argv) > 1 else P.build('pets-beds', [os.path.join(P.KIT, 'mods', 'pets')])[0]
work = tempfile.mkdtemp(prefix='beds-')
night = os.path.join(work, 'night.sav')
P.run([sys.executable, os.path.join(KIT, 'urbz_save.py'), 'set', os.path.join(KIT, 'verify', 'saves', 'apartment.sav'),
       night, '--clock', '23:30'])
load = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'))) + [['press', 'B', 6], ['wait', 60]]
script = load + P._pocket_place(397, ['RIGHT'] * 2) + [['shot', 'basket']] + P._pocket_place(386, ['DOWN'] * 3) + \
    [['shot', 'placed'], ['wait', 300], ['shot', 'w300'], ['wait', 600], ['shot', 'w900']]
p = os.path.join(work, 's.json')
json.dump(script, open(p, 'w'))
out = P.run(P.VERIFY + ['ram', rom, '--sav', night, '--script', p, '--frames', '30', '--read', P.HEAP_SCAN])
st = P._pets_stats(bytes.fromhex([l for l in out.splitlines() if ' = ' in l][0].split(' = ')[1].strip()))
xy = lambda v: (v & 0xFFFF, v >> 16)
print({k: st[k] for k in ('kept', 'n', 'acts', 'act_mask', 'to_bed', 'in_bed')}, 'bed', xy(st['bed0']), 'pet', xy(st['pet0']),
      'mode/action', (st['mood0'] >> 16) & 0xFF, st['mood0'] >> 24)
print(out.strip().splitlines()[-1])
