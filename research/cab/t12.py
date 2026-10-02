"""Count options per Create-a-Bod category (gender, skin, hair style, hair colour) and
per Threads category by cycling RIGHT until the look byte returns to its start value."""
from cabprobe import *
def count(emu, rows, byte_of_row):
    look = lambda: list(rd(emu, 0x02141144, 12))
    for r in range(rows):
        run(emu, [["wait", 20], ["press", "DOWN", 8], ["wait", 40]])
        b = byte_of_row[r]
        start = look()[b]
        vals = [start]
        for k in range(40):
            run(emu, [["press", "RIGHT", 8], ["wait", 30]])
            v = look()[b]
            if v == start:
                break
            vals.append(v)
        print('byte +%d: %d options seen: %s' % (b, len(vals), sorted(vals)))
emu = emu_open(state='cab.dst')
count(emu, 4, [0, 1, 2, 3])
os._exit(0)
