"""Dump visible OAM entries of main (top) engine from a state."""
from cabprobe import *
st = sys.argv[1] if len(sys.argv) > 1 else 'threads.dst'
emu = emu_open(state=st)
run(emu, [["wait", 2]])
for oam, dc in ((0x07000000, 0x04000000), (0x07000400, 0x04001000)):
    d = u32(emu, dc)
    print('DISPCNT %08x' % d, 'objmap1d', bool(d & 0x10), 'extpal', bool(d & (1 << 31)))
    for k in range(128):
        a0, a1, a2 = struct.unpack('<3H', rd(emu, oam + 8 * k, 6))
        if (a0 >> 8) & 3 == 2:
            continue
        print(' %3d y=%3d x=%3d shape=%d size=%d mode=%d 256c=%d tile=%4d prio=%d pal=%2d' % (
            k, a0 & 255, a1 & 511, a0 >> 14, a1 >> 14, (a0 >> 10) & 3, (a0 >> 13) & 1, a2 & 1023, (a2 >> 10) & 3, a2 >> 12))
print('VRAMCNT', rd(emu, 0x04000240, 10).hex())
os._exit(0)
