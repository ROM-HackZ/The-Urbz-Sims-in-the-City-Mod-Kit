"""Why the second melonDS session of pets-gate doesn't save: try variants of place/talk/save."""
import json, os, sys
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, 'verify')); sys.path.insert(0, os.path.join(KIT, 'tests'))
import urbz_melon as M
import proofs as P
rom, home, out, variant = sys.argv[1:5]
save = json.load(open(os.path.join(KIT, 'verify', 'scripts', 'savegame.json')))
place = [["touch", 236, 166, 8], ["wait", 90], ["touch", 84, 75, 8], ["wait", 90], ["touch", 131, 36, 8],
         ["wait", 30], ["touch", 131, 36, 8], ["wait", 90], ["touch", 236, 166, 8], ["wait", 60]] + \
    [["press", "DOWN", 12], ["wait", 20]] * 3 + [["press", "A", 6], ["wait", 20]]
talk = [['press', 'A', 4], ['wait', 40], ['shot', 'menu'], ['press', 'A', 4], ['wait', 150], ['shot', 'petting'],
        ['wait', 300], ['press', 'A', 4], ['wait', 40], ['press', 'DOWN', 4], ['wait', 10], ['press', 'DOWN', 4],
        ['wait', 10], ['press', 'A', 4], ['wait', 120], ['shot', 'feeding'], ['wait', 300]]
pre = {'A': place, 'B': place + talk + [['wait', 600]], 'C': place + talk + [['shot', 'before'], ['press', 'B', 6], ['wait', 60]],
       'D': place + [['shot', 'placed']]}[variant]
steps = save if variant != 'D' else [['wait', 120], ['touch', 128, 180, 8], ['shot', 'opt0'], ['wait', 60], ['shot', 'opt'],
                                      ['touch', 203, 52, 8], ['wait', 30], ['shot', 't30'], ['wait', 60], ['shot', 't90']]
print(M.run(rom, P.MELON_LOAD + pre + steps, sav=home, out=out))
