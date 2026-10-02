"""Who writes the OBJ palette shadow rows (main OBJ shadow at 0x02168C60, rows 9..12)?"""
from cabprobe import *
import collections
st = sys.argv[1] if len(sys.argv) > 1 else 'cab.dst'
script = json.loads(sys.argv[2]) if len(sys.argv) > 2 else [["press", "DOWN"], ["wait", 30], ["press", "DOWN"], ["wait", 30]]
emu = emu_open(state=st)
regs = emu.memory.register_arm9
log = collections.Counter()
LO, HI = 0x02168C60, 0x02168C60 + 3 * 32
def cb(a, s):
    log[(hex(regs.r15), hex(regs.r14), tuple(hex(x) for x in V._stack_calls(regs, emu.memory.unsigned, 6)))] += 1
run(emu, script)
for a in range(LO, HI, 2):
    emu.memory.register_write(a, cb, 2)
print('before', rd(emu, LO, HI - LO).hex())
run(emu, [["press", "RIGHT"], ["wait", 30]])
print('after ', rd(emu, LO, HI - LO).hex())
print('look', rd(emu, 0x02141144, 12).hex(' '))
for k, v in sorted(log.items()): print(v, k)
os._exit(0)
