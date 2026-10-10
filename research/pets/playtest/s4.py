# Night then morning, all pets, with per-pet detail.
from ptlib import *
import pickle
r = rom(); sav = OUT + '/s2.sav'; st = OUT + '/day_allpets.dst'
s = [['poke', '0x0214112E=151e'], ['wait', 30], ['shot', 'n']]   # 21:30
for k in range(40):
    s += [RESTED, ['wait', 1000], ['shot', 'n%02d' % k]]
snaps, out = play_from(r, sav, st, s, 's4')
pickle.dump([(n, detail(m), clock(m)) for n, m in snaps], open('s4.pkl', 'wb'))
for name, mem in snaps[2:]:
    print(name, clock(mem), 'brought', state(mem)[0]['brought'], ' | '.join('%s %s/%s %d,%d h%d%s' % (d[0][:4], d[1], d[2], d[4], d[5], d[6], ' B' if d[8] else '') for d in detail(mem)))
