"""List live entities whose behaviour fn (+0x4C) is one of the given pointers, by scanning main RAM.
usage: ents.py STATE [behaviour hex ...]"""
import sys, os, struct
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
emu = V._emu('/root/urbz/work/van.nds', None, os.devnull)
emu.savestate.load_file(sys.argv[1])
emu.cycle(with_joystick=False)
mem = bytes(emu.memory.unsigned[0x02000000:0x02400000])
want = [int(x, 16) for x in sys.argv[2:]]
for w in want:
    pat = struct.pack('<I', w)
    i = 0
    while True:
        i = mem.find(pat, i)
        if i < 0: break
        b = i - 0x4C
        if b >= 0 and b % 4 == 0:
            t, c = struct.unpack_from('<HH', mem, b + 8)
            x, y = struct.unpack_from('<ii', mem, b + 0x18)
            print('ent %08x beh %08x type %d c %d pos %d,%d 11c=%s st=%d act=%d flags=%08x' % (
                0x02000000 + b, w, t, c, x >> 16, y >> 16, mem[b + 0x11c:b + 0x123].hex(), mem[b + 0x104], mem[b + 0x105],
                struct.unpack_from('<I', mem, b + 0xc)[0]))
        i += 4
os._exit(0)
