"""Snapshot RAM between Create-a-Bod option changes; find bytes that track the options."""
from cabprobe import *
import numpy as np
emu = emu_open(state='cab.dst')
def snap():
    return np.frombuffer(rd(emu, 0x02000000, 0x400000), dtype=np.uint8).copy()
S = {}
run(emu, [["wait", 10]]); S['g0'] = snap()
run(emu, [["press", "DOWN"], ["wait", 30], ["press", "RIGHT"], ["wait", 40]]); S['g1'] = snap()   # female
run(emu, [["press", "DOWN"], ["wait", 30], ["press", "RIGHT"], ["wait", 40]]); S['s1'] = snap()   # skin +1
run(emu, [["press", "RIGHT"], ["wait", 40]]); S['s2'] = snap()   # skin +2
run(emu, [["press", "DOWN"], ["wait", 30], ["press", "RIGHT"], ["wait", 40]]); S['h1'] = snap()   # hair +1
run(emu, [["press", "RIGHT"], ["wait", 40]]); S['h2'] = snap()
run(emu, [["press", "DOWN"], ["wait", 30], ["press", "RIGHT"], ["wait", 40]]); S['c1'] = snap()   # hcol +1
run(emu, [["press", "RIGHT"], ["wait", 40]]); S['c2'] = snap()
np.savez_compressed('/root/urbz/agentwork/cab/snaps.npz', **S)
emu.savestate.save_file('/root/urbz/agentwork/cab/cab_f_s2h2c2.dst')
def cand(name, pairs):
    m = np.ones(0x400000, bool)
    for a, b, d in pairs:
        m &= (S[b].astype(int) - S[a].astype(int)) == d
    idx = np.nonzero(m)[0]
    print(name, len(idx), [hex(0x02000000 + i) for i in idx[:40]])
same = lambda a, b: (S[a] == S[b])
cand('gender', [('g0', 'g1', 1), ('g1', 's1', 0), ('s1', 'h2', 0), ('h2', 'c2', 0)])
cand('skin', [('g1', 's1', 1), ('s1', 's2', 1), ('s2', 'h1', 0), ('h1', 'c2', 0)])
cand('hair', [('s2', 'h1', 1), ('h1', 'h2', 1), ('h2', 'c1', 0), ('c1', 'c2', 0), ('g1', 's2', 0)])
cand('hcol', [('h2', 'c1', 1), ('c1', 'c2', 1), ('g1', 'h2', 0)])
os._exit(0)
