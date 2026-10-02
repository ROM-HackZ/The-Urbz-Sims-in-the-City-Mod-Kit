"""Where is the look struct (0x02141144, 12 bytes) in the save stream?
Poke a distinctive look in the city, Save Game, log the save writer calls that read it."""
from cabprobe import *
CITY = V.city_state(VAN)
emu = emu_open(state=CITY)
regs = emu.memory.register_arm9
LOOK = bytes([1, 3, 2, 4, 5, 0x11, 0, 0x15, 0x1b, 9, 5, 0])
for i, b in enumerate(LOOK):
    emu.memory.write_byte(0x02141144 + i, b)
log = []
def mk(name):
    def cb(a, s):
        ctx = 0x021470FC
        log.append((name, regs.r0, regs.r1, u32(emu, ctx + 0x84), emu.memory.unsigned[ctx + 0x88], u32(emu, ctx + 0x8C), hex(regs.r14)))
    return cb
for n, a in (('bits', 0x0207E944), ('nib', 0x0207E9CC), ('bytes', 0x0207EAAC)):
    emu.memory.register_exec(a, mk(n))
run(emu, [["touch", 128, 180], ["wait", 60], ["touch", 203, 52], ["wait", 60], ["touch", 220, 117], ["wait", 90], ["shot", "ow"], ["touch", 160, 96, 12], ["wait", 120], ["shot", "ow2"], ["press", "A"], ["wait", 400], ["shot", "saved"]], tag='t10')
for l in log:
    if 0x02141140 <= l[1] < 0x02141160:
        print(l[0], hex(l[1]), 'n=%d' % l[2], 'cursor 0x%x bit %d used %d' % (l[3], l[4], l[5]), l[6])
print('total save writer calls', len(log), 'first', [(l[0], hex(l[1]), l[2]) for l in log[:12]])
emu.backup.export_file('/root/urbz/agentwork/cab/look.sav')
os._exit(0)
