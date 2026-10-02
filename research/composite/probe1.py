import sys, os, json, struct, collections
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
rom = '/root/urbz/work/van.nds'
st = V.city_state(rom)
emu = V._emu(rom, None, os.devnull)
emu.savestate.load_file(st)
R = emu.memory.register_arm9
mem = emu.memory.unsigned
u32 = lambda a: struct.unpack('<I', bytes(mem[a:a+4]))[0]
log = collections.Counter(); ex = {}
def h0(a, s):
    k = ('ae0c8', u32(R.r0), u32(R.r0+4), R.r1, R.r2, R.r14)
    log[k] += 1
def h5534(a, s):
    k = ('5534', R.r0, R.r1, R.r2, R.r14); log[k] += 1
def he774(a, s):
    k = ('e774', R.r0, R.r14); log[k] += 1
def h70a8(a, s):
    k = ('70a8', R.r0, R.r14); log[k] += 1
emu.memory.register_exec(0x020ae0c8, h0)
emu.memory.register_exec(0x02005534, h5534)
emu.memory.register_exec(0x0206e774, he774)
emu.memory.register_exec(0x020670a8, h70a8)
out = '/root/urbz/agentwork/composite/rt'
V._run_script(emu, [['wait', 60], ['shot', 'a']], out, 'p1')
for k, v in sorted(log.items(), key=lambda kv: str(kv[0])):
    print(v, [hex(x) if isinstance(x, int) else x for x in k])
oam = bytes(mem[0x07000000:0x07000800])
open(out + '/oam_a.bin', 'wb').write(oam)
for base in (0, 0x400):
    for i in range(128):
        a0, a1, a2 = struct.unpack_from('<HHH', oam, base + i*8)
        if (a0 >> 8) & 3 != 2:
            print('sub' if base else 'main', i, hex(a0), hex(a1), hex(a2))
print('POWCNT', hex(struct.unpack('<H', bytes(mem[0x04000304:0x04000306]))[0]), 'DISPCNT', hex(u32(0x04000000)), 'DISPCNT_B', hex(u32(0x04001000)))
os._exit(0)
