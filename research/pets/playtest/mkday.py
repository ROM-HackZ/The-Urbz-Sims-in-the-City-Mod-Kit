from ptlib import *
import shutil
r = rom(); sav = setclock(P.os.path.join(KIT, 'verify/saves/apartment.sav'), '08:00', OUT + '/s2.sav')
st = place_all(r, sav, [397, 398, 399, 400, 401, 386, 389, 390, 391, 392, 393, 394, 395], 'dp')
shutil.copy(st, OUT + '/day_allpets.dst')
for f in glob.glob(OUT + '/dp-*.dst'): os.remove(f)
