from ptlib import *
r = rom(); sav = OUT + '/s2.sav'; st = OUT + '/day_allpets.dst'
s = P._area_goto(19) + P._area_goto(22)[:-1] + [['wait', 60], ['shot', 'h0'], ['wait', 120], ['shot', 'h1'], ['wait', 200], ['shot', 'h2'], ['wait', 300], ['shot', 'h3']]
snaps, out = play_from(r, sav, st, s, 's8')
for n, m in snaps[-4:]:
    stt = state(m)[0]; print(n, clock(m), 'greets', stt['greets'], [(d[0][:4], d[1], d[3], d[4], d[5], d[10], d[11], d[12]) for d in detail(m)])
zoom([glob.glob(out + '/*_%s.png' % n)[0] for n in ('h0', 'h1', 'h2', 'h3')], 's8.png', box=(0, 0, 256, 192), scale=1, cols=4)
