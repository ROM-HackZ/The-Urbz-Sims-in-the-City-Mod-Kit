"""Threads screen: which look byte does each category change? Screenshot each row."""
from cabprobe import *
emu = emu_open(state='threads.dst')
look = lambda: rd(emu, 0x02141144, 12).hex(' ')
print('start   ', look())
for r in range(6):
    if r:
        run(emu, [["wait", 20], ["press", "DOWN", 8], ["wait", 40]])
    run(emu, [["press", "RIGHT", 8], ["wait", 40], ["shot", "row%d" % r]], tag='t11')
    print('row %d +1' % r, look())
os._exit(0)
