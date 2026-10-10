# After the strays quest: talk to the adopter, then try to get their pet.
from ptlib import *
r = rom()
arrive, near, feed1, feed2, take, pets = P._strays_script(r)
base = arrive + near + feed1 + feed2 + take
st0 = OUT + '/after_quest.dst'
run_state(r, P.URBANIA, None, base + [['wait', 30]], 'stl0', st0)
m = play_from(r, P.URBANIA, st0, [['wait', 2], ['shot', 'z']], 'stl1')[0][-1][1]
st = state(m)[0]; adopter = st['adopter']
ents = P._world(m)
pl = [e for e, t, *_ in ents if t == 0][0]
who = [(x, y) for e, t, k, x, y in ents if t == 7 and k == adopter][0]
kit = [(x, y) for e, t, k, x, y in ents if t == 9 and k == 8]
print('adopter', adopter, who, 'kitten', kit, 'pockets', m[0x02141338 - 0x02100000])
def at(x, y):
    return ['poke', '0x%08X=%s' % (pl + 0x18, struct.pack('<iiii', x << 16, y << 16, x << 16, y << 16).hex())]
s = [at(who[0] + 18, who[1]), ['press', 'LEFT', 2], ['wait', 5], ['press', 'A', 4], ['wait', 90], ['shot', 'talk']]
for k in range(8):
    s += [['press', 'A', 4], ['wait', 60]]
s += [['wait', 100], ['shot', 'talked']]
snaps, out = play_from(r, P.URBANIA, st0, s, 'stl2')
m = snaps[-1][1]
ents = P._world(m)
kit = [(x, y) for e, t, k, x, y in ents if t == 9 and k == 8]
st = state(m)[0]
print('after talking: kitten', kit, 'pockets', m[0x02141338 - 0x02100000], 'msgs', st['msgs'])
import shutil; st1 = OUT + '/after_talk.dst'
run_state(r, P.URBANIA, st0, s, 'stl3', st1)
kx, ky = kit[0]
s2 = [at(kx + 18, ky), ['press', 'LEFT', 2], ['wait', 5], ['press', 'A', 4], ['wait', 120], ['shot', 'a'], ['press', 'A', 4], ['wait', 120], ['press', 'LEFT', 20], ['wait', 120], ['shot', 'b']]
snaps, out = play_from(r, P.URBANIA, st1, s2, 'stl4')
for n, m in snaps[-2:]:
    ents = P._world(m)
    print(n, 'kitten', [(x, y) for e, t, k, x, y in ents if t == 9 and k == 8], 'pockets', m[0x02141338 - 0x02100000],
          [struct.unpack_from('<H', m, 0x0214188C - 0x02100000 + 6 * i)[0] for i in range(m[0x02141338 - 0x02100000])])
