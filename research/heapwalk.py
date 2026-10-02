import sys, os, struct
sys.path.insert(0, '/root/urbz/kit8/verify')
import urbz_verify as V
rom, state = sys.argv[1], sys.argv[2]
emu = V._emu(rom, None, os.devnull)
emu.savestate.load_file(state)
for _ in range(2): emu.cycle(with_joystick=False)
m = emu.memory.unsigned
u32 = lambda a: struct.unpack('<I', bytes(m[a:a+4]))[0]
h = u32(0x02142004)
print('handle %08x' % h, bytes(m[h:h+0x40]).hex())
for name, off in (('free', 0x24), ('used', 0x2C)):
    b = u32(h + off); n = tot = big = 0
    while b and n < 100000:
        sig = bytes(m[b:b+2]); size = u32(b + 4)
        if n < 3: print(name, '%08x' % b, sig, hex(u32(b)), size, '%08x %08x' % (u32(b+8), u32(b+12)))
        tot += size; big = max(big, size); n += 1
        b = u32(b + 12)
    print(name, 'blocks', n, 'total', tot, 'largest', big)
os._exit(0)
