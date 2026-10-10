from ptlib import *
r = KIT + '/build/proofs/pets-play-x.nds'; sav = OUT + '/s2.sav'
SY = json.load(open(KIT + '/code/pets-kit/build/patch.json'))['symbols']
st = glob.glob(OUT + '/sv1-*.dst'); st = sorted(st, key=os.path.getmtime)[-1]
m0 = play_from(r, sav, st, [['wait', 5], ['shot', 'z']], 'sv0')[0][-1][1]
k = m0.find(struct.pack('<I', 0x53544550), 0x4DE20); base = 0x02100000 + k - SY['pets_stats']
ents = P._world(m0); pl = [e for e, t, *_ in ents if t == 0][0]
px, py = [(x, y) for e, t, kk, x, y in ents if t == 9][0]; pe = [e for e, t, kk, x, y in ents if t == 9][0]
xy = struct.pack('<iiii', (px + 18) << 16, py << 16, (px + 18) << 16, py << 16).hex()
pxy = struct.pack('<iiii', px << 16, py << 16, px << 16, py << 16).hex()
A = [int(a, 16) for a in sys.argv[1:]]
s = []
for a in A:
    s += [['poke', '0x%08X=%s' % (pl + 0x18, xy)], ['poke', '0x%08X=%s' % (pe + 0x18, pxy)], ['press', 'LEFT', 2], ['wait', 5],
          ['poke', '0x%08X=%s' % (base + SY['pets_play_anim'], struct.pack('<I', a).hex())],
          ['press', 'A', 4], ['wait', 40], ['press', 'DOWN', 4], ['wait', 10], ['press', 'A', 4], ['wait', 25]]
    for f in range(6): s += [['wait', 15], ['shot', 'a%02x_%d' % (a, f)]]
    s += [['wait', 120]]
snaps, out = play_from(r, sav, st, s, 'sv2', timeout=4000)
fs, lab = [], []
for a in A:
    for f in range(6): fs.append(glob.glob(out + '/*_a%02x_%d.png' % (a, f))[0]); lab.append('%02x %d' % (a, f))
zoom(fs, 'survey2.png', box=(100, 70, 190, 160), scale=1, cols=6, labels=lab)
