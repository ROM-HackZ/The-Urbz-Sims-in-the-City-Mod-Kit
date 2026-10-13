"""Pets test-play helpers: run a script from a save in DeSmuME, snapshot RAM at every shot."""
import sys, os, json, struct, tempfile, glob
KIT = '/root/urbz/repo'
sys.path.insert(0, KIT + '/tests'); sys.path.insert(0, KIT + '/verify'); sys.path.insert(0, KIT); sys.path.insert(0, os.path.join(KIT, 'kit'))
_argv = sys.argv; sys.argv = sys.argv[:1]
import proofs as P, urbz_verify as V
sys.argv = _argv
OUT = os.path.join(KIT, 'build', 'playtest')
os.makedirs(OUT, exist_ok=True)
NAMES = {7: 'Puppy', 8: 'Kitten', 9: 'Bunny', 10: 'Hamster', 11: 'GuineaPig', 12: 'Cockatoo', 13: 'Macaw', 14: 'Snake'}
RESTED = ['poke', '0x02141204=' + '00000060' * 8]

def rom(fresh=False):
    r = os.path.join(KIT, 'build', 'proofs', 'pets-play.nds')
    return P.build('pets-play', [os.path.join(KIT, 'mods', 'pets')])[0] if fresh or not os.path.exists(r) else r

def play(rom, sav, script, tag, timeout=3000, export=None):
    out = os.path.join(OUT, tag); os.makedirs(out, exist_ok=True)
    for f in glob.glob(out + '/*'): os.remove(f)
    job = {'rom': os.path.abspath(rom), 'out': out, 'tag': tag, 'sav': sav, 'script': script, 'snap': [P.WORLD]}
    if export: job['export_sav'] = export
    res = V.run_child(job, timeout=timeout)
    snaps = []
    for name, files in res['snaps']:
        mem = open(files[0], 'rb').read()
        snaps.append((name, mem))
        os.remove(files[0])
    return snaps, out

def clock(mem):
    d, h, m = struct.unpack_from('<hbb', mem, 0x0214112C - 0x02100000)
    return '%d %02d:%02d' % (d, h, m)

def state(mem):
    heap = mem[0x0214DE20 - 0x02100000:]
    st = P._pets_stats(heap)
    ents = P._world(mem)
    pets = [(NAMES.get(k, k), x, y) for _, t, k, x, y in ents if t == 9 and k >= 7]
    player = [(x, y) for _, t, k, x, y in ents if t == 0]
    return st, pets, player

def mood(st):
    m = st['mood0']
    a = m >> 24
    return 'hunger %d happy %d mode %d act %s' % (m & 0xFF, (m >> 8) & 0xFF, (m >> 16) & 0xFF,
                                                   P.PET_ACTIONS[a] if a < len(P.PET_ACTIONS) else a)

def place(obj, steps):
    return P._pocket_place(obj, steps)

def setclock(sav, hhmm, out):
    P.run([sys.executable, os.path.join(KIT, 'kit', 'urbz_save.py'), 'set', sav, out, '--clock', hhmm])
    return out

def tile(files, out, cols=4, crop=True):
    from PIL import Image
    ims = [Image.open(f).convert('RGB') for f in files]
    if crop: ims = [i.crop((0, 0, 256, 192)) for i in ims]
    w, h = ims[0].size
    o = Image.new('RGB', (w * cols, h * ((len(ims) + cols - 1) // cols)))
    for k, i in enumerate(ims): o.paste(i, ((k % cols) * w, (k // cols) * h))
    o.save(out)

CANDS = [['DOWN'] * 2, ['RIGHT'] * 2, ['UP'] * 2, ['LEFT'] * 2, ['DOWN'] * 3 + ['RIGHT'] * 2, ['UP'] * 3 + ['RIGHT'] * 3,
         ['LEFT'] * 3 + ['DOWN'] * 2, ['RIGHT'] * 4, ['DOWN'] * 4, ['UP'] * 4 + ['LEFT'] * 2, ['RIGHT'] * 3 + ['UP'] * 2]

def run_state(rom, sav, state, script, tag, save):
    out = os.path.join(OUT, tag); os.makedirs(out, exist_ok=True)
    job = {'rom': os.path.abspath(rom), 'out': out, 'tag': tag, 'sav': sav, 'script': script, 'snap': [P.WORLD], 'save': save}
    if state: job['state'] = state
    res = V.run_child(job, timeout=1500)
    mems = [(n, open(f[0], 'rb').read()) for n, f in res['snaps']]
    return mems

def place_all(rom, sav, objs, tag, first=None):
    """Load sav, then place each object in Pockets at some free spot nearby (retrying other walks if blocked).
    Returns the savestate after the last placement."""
    st = os.path.join(OUT, tag + '-0.dst')
    run_state(rom, sav, None, P._load() + [RESTED] + (first or []) + [['shot', 'ready']], tag, st)
    k = 0
    for obj in objs:
        for c in CANDS[k % len(CANDS):] + CANDS[:k % len(CANDS)]:
            k += 1
            nxt = os.path.join(OUT, '%s-%d.dst' % (tag, k))
            mems = run_state(rom, sav, st, place(obj, c) + [['wait', 30], ['shot', 'chk']], tag, nxt)
            if mems[-1][1][0x02141338 - 0x02100000] == 0:
                st = nxt
                print('placed', obj, c)
                break
        else:
            print('could not place', obj)
    return st

def play_from(rom, sav, state, script, tag, timeout=5000):
    out = os.path.join(OUT, tag); os.makedirs(out, exist_ok=True)
    for f in glob.glob(out + '/*'): os.remove(f)
    job = {'rom': os.path.abspath(rom), 'out': out, 'tag': tag, 'sav': sav, 'state': state, 'script': script, 'snap': [P.WORLD]}
    res = V.run_child(job, timeout=timeout)
    snaps = []
    for name, files in res['snaps']:
        snaps.append((name, open(files[0], 'rb').read())); os.remove(files[0])
    return snaps, out

def zoom(files, out, box=(60, 40, 256, 170), scale=2, cols=3, labels=None):
    from PIL import Image, ImageDraw
    ims = [Image.open(f).convert('RGB').crop(box) for f in files]
    ims = [i.resize((i.width * scale, i.height * scale), Image.NEAREST) for i in ims]
    w, h = ims[0].size
    o = Image.new('RGB', (w * cols, h * ((len(ims) + cols - 1) // cols)))
    d = ImageDraw.Draw(o)
    for k, i in enumerate(ims):
        o.paste(i, ((k % cols) * w, (k // cols) * h))
        if labels: d.rectangle(((k % cols) * w, (k // cols) * h, (k % cols) * w + 90, (k // cols) * h + 12), fill=(0, 0, 0)); d.text(((k % cols) * w + 2, (k // cols) * h), labels[k], fill=(255, 255, 0))
    o.save(out)

MODES = ['wander', 'act', 'go', 'talk', 'bed', 'back']
def detail(mem):
    """Per pet: (name, mode, action, timer, x, y, hunger, happy, has bed)."""
    base0 = 0x02100000
    k = mem.find(struct.pack('<I', 0x53544550), 0x4DE20)
    if k < 0: return []
    SY = json.load(open(KIT + '/code/pets-kit/build/patch.json'))['symbols']
    base = base0 + k - SY['pets_stats']
    rd = lambda a, n: mem[a - base0:a - base0 + n]
    n = struct.unpack('<I', rd(base + SY['n_mine'], 4))[0]
    out = []
    for i in range(min(n, 16)):
        e, mode, action, timer, age, bfail, _pad, bed, seen, ax, ay, gd, cool, phase, _p2 = struct.unpack('<IBBHHBBIIhhiHBB', rd(base + SY['live'] + 32 * i, 32))
        obj, kind, facing, x, y, area, hu, ha, fl = struct.unpack('<HBBhhBBBB', rd(base + SY['mine'] + 12 * i, 12))
        if e and base0 <= e < 0x02200000:
            x, y = [v >> 16 for v in struct.unpack('<ii', rd(e + 0x18, 8))]
        an = P.PET_ACTIONS[action] if action < len(P.PET_ACTIONS) else action
        out.append((NAMES.get(kind, kind), MODES[mode] if mode < 6 else mode, an, timer, x, y, hu, ha, bool(bed), bool(e), seen, ax, ay))
    return out
