"""Who copies into OBJ palette RAM? Hook the palette copy wrapper 0x0204e2e4 and the raw
copiers 0x020b84ac / 0x020b84dc; log src/dst/len and callers."""
from cabprobe import *
import collections
st = sys.argv[1] if len(sys.argv) > 1 else 'threads.dst'
emu = emu_open(state=st)
regs = emu.memory.register_arm9
log = collections.Counter()
def hk(name, srcreg, dstreg, lenreg):
    def cb(a, s):
        r = [regs.r0, regs.r1, regs.r2, regs.r3]
        dst = r[dstreg]
        if 0x05000000 <= dst < 0x05000800:
            log[(name, hex(r[srcreg]), hex(dst), r[lenreg], hex(regs.r14), tuple(hex(x) for x in V._stack_calls(regs, emu.memory.unsigned, 5)))] += 1
    return cb
emu.memory.register_exec(0x0204e2e4, hk('wrap', 1, 2, 3))
emu.memory.register_exec(0x020b84ac, hk('cp16', 0, 1, 2))
emu.memory.register_exec(0x020b84dc, hk('cp32', 0, 1, 2))
run(emu, [["wait", 5]])
print('--- idle')
for k, v in sorted(log.items()): print(v, k)
log.clear()
run(emu, [["press", "RIGHT"], ["wait", 30]])
print('--- after RIGHT')
for k, v in sorted(log.items()): print(v, k)
os._exit(0)
