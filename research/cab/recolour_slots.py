"""Recolour the player clothing row (OBJ row 1) in hardware: colours 1-3 red, 4-7 green, 8-11 blue,
12-15 yellow, then screenshot. Shows which pixels each palette slot covers.
  python research/cab/recolour_slots.py STATE.dst OUT.png   (ROM: /root/urbz/work/van.nds, see README)"""
import sys,struct,os; sys.path.insert(0,'/root/urbz/toolkit/verify'); import urbz_verify as V
from PIL import Image
emu=V._emu('/root/urbz/work/van.nds',None,os.devnull); mem=emu.memory.unsigned
emu.savestate.load_file(sys.argv[1])
for _ in range(3): emu.cycle(with_joystick=False)
row=bytes(mem[0x05000220:0x05000240]); print('hw row1', row.hex())
ram=bytes(mem[0x02000000:0x02400000]); hits=[]
i=ram.find(row)
while i>=0: hits.append(0x02000000+i); i=ram.find(row,i+1)
print('shadow candidates', [hex(h) for h in hits])
cols={1:0x001F,2:0x001F,3:0x001F, 4:0x03E0,5:0x03E0,6:0x03E0,7:0x03E0, 8:0x7C00,9:0x7C00,10:0x7C00,11:0x7C00, 12:0x03FF,13:0x03FF,14:0x03FF,15:0x03FF}
# X red(1-3) Y green(4-7) Z blue(8-11) pants yellow(12-15)
for h in hits+[0x05000220]:
    for k,v in cols.items(): emu.memory.write_short(h+2*k,v)
emu.cycle(with_joystick=False)
print('hw row1 after', bytes(mem[0x05000220:0x05000240]).hex())
emu.screenshot().save(sys.argv[2])
