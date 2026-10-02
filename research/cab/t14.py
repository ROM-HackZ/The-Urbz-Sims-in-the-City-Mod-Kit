"""Boot, load the city save, record which source fills each OBJ palette row (per engine),
then list every live entity: sprite record(s), palette row(s) -> palette source.
usage: t14.py [extra_script.json]"""
from cabprobe import *
import collections
emu = emu_open(sav='/root/urbz/kit9/verify/saves/city.sav')
regs = emu.memory.register_arm9
mem = emu.memory.unsigned
ENG = lambda: mem[0x027C0004]
src = {}          # (engine, row) -> description
def setrows(idx, n, desc):
    e = ENG()
    for r in range(idx // 16, (idx + n + 15) // 16):
        src[(e, r)] = desc
def on_load(a, s):     # FUN_02020100(asset, off, idx, n)
    setrows(regs.r2, regs.r3, 'asset %05d(file) +0x%x' % (regs.r0 - 1, regs.r1))
def on_queue(a, s):    # FUN_0202005c(asset, idx, n)
    setrows(regs.r1, regs.r2, 'asset %05d(file) queued' % (regs.r0 - 1))
def on_raw(a, s):      # FUN_02020174(src, idx, n)
    setrows(regs.r1, regs.r2, 'RAM 0x%08x' % regs.r0)
def on_comp(a, s):     # FUN_020833e0(look, rowA, rowB)
    look = rd(emu, regs.r0, 10).hex(' ')
    src[(ENG(), regs.r1)] = 'composed look@0x%08x [%s] skin/hair/shoes' % (regs.r0, look)
    src[(ENG(), regs.r2)] = 'composed look@0x%08x [%s] clothes' % (regs.r0, look)
emu.memory.register_exec(0x02020100, on_load)
emu.memory.register_exec(0x0202005c, on_queue)
emu.memory.register_exec(0x02020174, on_raw)
emu.memory.register_exec(0x020833e0, on_comp)
ents = set()
emu.memory.register_exec(0x02001bf4, lambda a, s: ents.add(regs.r0))
emu.memory.register_exec(0x02001bd4, lambda a, s: ents.add(regs.r0))
script = json.load(open('/root/urbz/kit9/verify/scripts/loadgame.json'))
if len(sys.argv) > 1:
    script += json.load(open(sys.argv[1]))
run(emu, script + [["wait", 30], ["shot", "end"]], tag='t14')
print('engine now', ENG(), 'POWCNT1 %08x' % u32(emu, 0x04000304))
for k in sorted(src):
    print('engine %d OBJ row %2d <- %s' % (k[0], k[1], src[k]))
print('\nentities:')
for i, e in enumerate(sorted(ents)):
    typ = struct.unpack('<H', rd(emu, e + 8, 2))[0]
    rec = u32(emu, e + 0x9c)
    a90 = u32(emu, e + 0x90)
    x, y = u32(emu, e + 0x18) >> 16, u32(emu, e + 0x1c) >> 16
    parts = []
    for s in range(4):
        p = u32(emu, e + 0xd4 + s * 0xc)
        if 0x02000000 <= p < 0x02400000:
            row = mem[e + 0xcd + s * 0xc]
            parts.append('slot%d tbl 0x%08x row %d' % (s, p, row))
    r = struct.unpack('<4I', rd(emu, rec, 16)) if 0x02000000 <= rec < 0x02400000 else None
    if r is None and not parts:
        continue
    if r and not (0 < r[0] < 13400):
        r = None
    print('ent %3d @0x%08x type %d char %d pos (%d,%d) anim %d palrow %d rec %s %s' % (
        i, e, typ, struct.unpack('<H', rd(emu, e + 0xA, 2))[0], x, y, mem[e + 0xC7], (a90 >> 12) & 15,
        ('gfx %05d lay %05d pal %s param %d' % (r[0] - 1, r[1] - 1, ('%05d' % (r[2] - 1)) if r[2] else '0', r[3])) if r else hex(rec),
        '; '.join(parts)))
open('/root/urbz/agentwork/cab/city_pal_main.bin', 'wb').write(rd(emu, 0x05000200, 0x200))
open('/root/urbz/agentwork/cab/city_oam_main.bin', 'wb').write(rd(emu, 0x07000000, 0x400))
os._exit(0)
