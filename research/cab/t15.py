"""From a city savestate with NPCs, list drawn entities, their OBJ palette row, and which
32-byte palette asset (if any) matches that row exactly. usage: t15.py state.dst [frames] [rom]"""
from cabprobe import *
import glob
st = sys.argv[1]
frames = int(sys.argv[2]) if len(sys.argv) > 2 else 10
rom = sys.argv[3] if len(sys.argv) > 3 else VAN
emu = emu_open(rom=rom, state=st)
regs = emu.memory.register_arm9
ents = set()
emu.memory.register_exec(0x02001bf4, lambda a, s: ents.add(regs.r0))
emu.memory.register_exec(0x02001bd4, lambda a, s: ents.add(regs.r0))
loads = []
emu.memory.register_exec(0x0206d73c, lambda a, s: loads.append((hex(regs.r0), u32(emu, regs.r1), hex(regs.r1))))
run(emu, [["wait", frames], ["shot", "t15"]], tag='t15')
pal = rd(emu, 0x05000200, 0x200)
pals = {}
for f in glob.glob('/root/urbz/kit9/project/assets/*.bin'):
    b = open(f, 'rb').read()
    if len(b) == 32:
        pals.setdefault(b[2:], []).append(os.path.basename(f)[:5])
for e in sorted(ents):
    typ, ch = struct.unpack('<HH', rd(emu, e + 8, 4))
    rec = u32(emu, e + 0x9c)
    row = (u32(emu, e + 0x90) >> 12) & 15
    r = struct.unpack('<4I', rd(emu, rec, 16)) if 0x02000000 <= rec < 0x02400000 else (0, 0, 0, 0)
    c8 = u32(emu, e + 0xC8)
    print('ent 0x%08x type %5d char %3d row %2d gfx %05d pal-asset-ptr %s matches %s' % (
        e, typ, ch, row, r[0] - 1, ('0x%08x -> %d' % (c8, u32(emu, c8))) if 0x02000000 <= c8 < 0x02400000 else '-',
        pals.get(pal[row * 32 + 2:row * 32 + 32], '?')))
print('palette row loads (FUN_0206d73c):', loads)
os._exit(0)
