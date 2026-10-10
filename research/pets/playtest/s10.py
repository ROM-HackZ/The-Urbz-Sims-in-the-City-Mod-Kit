# A pet put out of sight (in the next room) comes back; coming home greeting.
from ptlib import *
r = rom(); sav = OUT + '/s2.sav'; st = OUT + '/day_allpets.dst'
m0 = play_from(r, sav, st, [['wait', 5], ['shot', 'z']], 's10a')[0][-1][1]
gp = [e for e, t, k, x, y in P._world(m0) if t == 9 and k == 11][0]
xy = struct.pack('<iiii', 308 << 16, 256 << 16, 308 << 16, 256 << 16).hex()
s = [['poke', '0x%08X=%s' % (gp + 0x18, xy)], ['wait', 20], ['shot', 'moved']]
for k in range(5): s += [['wait', 60], ['shot', 'g%d' % k]]
snaps, out = play_from(r, sav, st, s, 's10b')
for n, m in snaps[-6:]:
    print(n, 'brought', state(m)[0]['brought'], [(d[0], d[1], d[4], d[5]) for d in detail(m) if d[0] == 'GuineaPig'])
