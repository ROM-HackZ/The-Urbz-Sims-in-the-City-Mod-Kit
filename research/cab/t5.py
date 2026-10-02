"""Threads screen: per category, press RIGHT repeatedly; record game_state bytes and the
sprite assets fetched (get_asset from the entity draw code)."""
from cabprobe import *
import collections
st = sys.argv[1] if len(sys.argv) > 1 else 'threads.dst'
rows = int(sys.argv[2]) if len(sys.argv) > 2 else 6
emu = emu_open(state=st)
regs = emu.memory.register_arm9
cur = collections.Counter()
def on_get(a, s):
    if regs.r14 in (0x2001be8 + 0, 0x2001978):
        cur[(regs.r0, hex(regs.r14))] += 1
emu.memory.register_exec(0x02032CA8, on_get)
def look():
    return rd(emu, 0x02141144, 12).hex(' ')
print('start', look())
for r in range(rows):
    if r:
        run(emu, [["press", "DOWN"], ["wait", 30]])
    seen = []
    for k in range(40):
        cur.clear()
        run(emu, [["press", "RIGHT"], ["wait", 30]])
        ids = sorted(set(i for i, _ in cur))
        l = look()
        seen.append(l)
        print('row', r, 'step', k + 1, l, ids)
        if k > 0 and l == seen[0]:
            break
        if k == 0 and r == 0:
            run(emu, [["shot", "row0"]], tag='t5')
os._exit(0)
