# ex.py in.dst out.dst 'json steps'  -> runs steps on vanilla, saves state, writes strip.png of all shots
import sys, os, json
sys.path.insert(0, '/root/urbz/kit8/verify')
import urbz_verify as V
from PIL import Image
src, dst, steps = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
rom = os.environ.get('ROM', '/root/urbz/work/van.nds')
out = '/root/urbz/work/re/ex'
os.makedirs(out, exist_ok=True)
for f in os.listdir(out): os.remove(os.path.join(out, f))
if not any(s[0] == 'shot' for s in steps): steps.append(['shot', 'end'])
job = {'rom': rom, 'sav': os.environ.get('SAV'), 'state': src if src != '-' else None, 'script': steps, 'out': out, 'tag': 'x', 'save': os.path.abspath(dst)}
res = V.run_child(job)
ims = [Image.open(p) for _, p, _ in res['shots']]
cols = min(len(ims), 4); rows = (len(ims) + cols - 1) // cols
s = Image.new('RGB', (256 * cols, 384 * rows), 'white')
for i, im in enumerate(ims): s.paste(im, ((i % cols) * 256, (i // cols) * 384))
if rows * cols > 4: s = s.resize((s.width * 2 // 3, s.height * 2 // 3))
p = '/tmp/claude-0/-home-claude/3211abdb-3351-5abf-ab40-d96a91992068/scratchpad/ex.png'
s.save(p); print('shots:', [n for n, _, _ in res['shots']], '->', p)
