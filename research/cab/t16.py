"""New game from power-on: log dynamic palette-row assignments (FUN_0206d73c) and the
character-palette table reads, to confirm NPC palettes come from 0x020D0054[char]."""
from cabprobe import *
emu = emu_open()
regs = emu.memory.register_arm9
log = []
def on(a, s):
    e = regs.r0
    typ, ch = struct.unpack('<HH', rd(emu, e + 8, 4))
    log.append(('row-assign', V.FRAME[0], 'type', typ, 'char', ch, 'table@0x%08x' % regs.r1, 'asset(file) %05d' % (u32(emu, regs.r1) - 1)))
emu.memory.register_exec(0x0206d73c, on)
def on_ret(a, s):
    pass
run(emu, json.load(open('/root/urbz/kit9/verify/scripts/newgame.json')), tag='t16')
for l in log: print(*l)
os._exit(0)
