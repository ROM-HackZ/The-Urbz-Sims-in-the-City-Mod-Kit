"""Dump OBJ palettes and OAM; find RAM copies of the palette rows; log CPU writes to OBJ palette RAM."""
from cabprobe import *
emu = emu_open(state='threads.dst')
regs = emu.memory.register_arm9
wl = {}
def mk(base):
    def cb(a, s):
        k = (base, hex(regs.r15), hex(regs.r14))
        wl[k] = wl.get(k, 0) + 1
    return cb
for b in (0x05000200, 0x05000600):
    for off in range(0, 0x200, 2):
        emu.memory.register_write(b + off, mk(b), 2)
# DMA source registers
dma = []
for ch in range(4):
    a = 0x040000B0 + ch * 12
    emu.memory.register_write(a + 8, (lambda ch: lambda ad, s: dma.append((ch, hex(u32(emu, 0x040000B0 + ch*12)), hex(u32(emu, 0x040000B4 + ch*12)), hex(u32(emu, 0x040000B8 + ch*12)), hex(regs.r15), hex(regs.r14))))(ch), 4)
run(emu, [["wait", 3]])
dc = u32(emu, 0x04000304)
print('POWCNT1 %08x (bit15 = main on top)' % dc)
for b in (0x05000200, 0x05000600):
    P = rd(emu, b, 0x200)
    print('pal', hex(b))
    for r in range(16):
        print('  row', r, P[r*32:(r+1)*32].hex())
print('palette CPU writes:', sorted(wl.items())[:30])
import collections
c = collections.Counter((d[2] >> 0 if False else d[2], d[4]) for d in dma)
print('dma (to pal):', [d for d in dma if d[2].startswith('0x50')][:20])
print('dma kinds:', collections.Counter((d[0], d[2][:6], d[4]) for d in dma).most_common(20))
open('pal_main.bin', 'wb').write(rd(emu, 0x05000200, 0x200))
open('pal_sub.bin', 'wb').write(rd(emu, 0x05000600, 0x200))
open('ram.bin', 'wb').write(rd(emu, 0x02000000, 0x400000))
open('oam.bin', 'wb').write(rd(emu, 0x07000000, 0x800))
os._exit(0)
