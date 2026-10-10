# Pets page with 8 pets; save and load with 8 pets and beds.
from ptlib import *
r = rom(); sav = OUT + '/s2.sav'; st = OUT + '/day_allpets.dst'
taps = [['wait', 60], ['touch', 128, 180, 8], ['wait', 60], ['touch', 61, 120, 8], ['wait', 60], ['shot', 'mods'],
        ['touch', 64, 28, 8], ['wait', 60], ['shot', 'page0']]
for k in range(6):
    taps += [['press', 'R', 4], ['wait', 30], ['shot', 'page%d' % (k + 1)]]
snaps, out = play_from(r, sav, st, taps, 's6')
tile([glob.glob(out + '/*_%s.png' % n)[0] for n in ('mods', 'page0', 'page2', 'page4', 'page6')], 's6_page.png', cols=5, crop=False)
# save and load
save = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'savegame.json')))
out2 = os.path.join(OUT, 's6b'); os.makedirs(out2, exist_ok=True)
job = {'rom': os.path.abspath(r), 'out': out2, 'tag': 's6b', 'sav': sav, 'state': st, 'script': [['wait', 30]] + save,
       'export_sav': OUT + '/eight.sav'}
V.run_child(job, timeout=900)
snaps, out = play(r, OUT + '/eight.sav', P._load() + [['wait', 300], ['shot', 'loaded']], 's6c')
m = snaps[-1][1]
print('after load:', clock(m), [(d[0], d[4], d[5]) for d in detail(m)])
print('objects:', sorted((k, x, y) for e, t, k, x, y in P._world(m) if t == 5 and k >= 386))
