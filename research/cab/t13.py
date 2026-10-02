"""City: log every OBJ/BG palette load through the palette manager and the look-composer."""
from cabprobe import *
import collections
st = sys.argv[1] if len(sys.argv) > 1 else V.city_state(VAN)
frames = int(sys.argv[2]) if len(sys.argv) > 2 else 600
emu = emu_open(state=None if st == 'boot' else st, sav='/root/urbz/kit9/verify/saves/city.sav' if st == 'boot' else None)
regs = emu.memory.register_arm9
log = collections.Counter()
eng = lambda: emu.memory.unsigned[0x02123000] if False else None
def H(name, fmt):
    def cb(a, s):
        r = [regs.r0, regs.r1, regs.r2, regs.r3]
        extra = ''
        if name == 'compose':
            extra = rd(emu, r[0], 12).hex(' ')
        log[(name, fmt(r), extra, hex(regs.r14))] += 1
    return cb
emu.memory.register_exec(0x0202005c, H('obj_queue(asset,idx,n)', lambda r: (r[0], r[1], r[2])))
emu.memory.register_exec(0x0202015c, H('obj_queue2(asset,idx,n)', lambda r: (r[0], r[1], r[2])))
emu.memory.register_exec(0x02020100, H('obj_load(asset,off,idx,n)', lambda r: (r[0], hex(r[1]), r[2], r[3])))
emu.memory.register_exec(0x020201a4, H('bg_load(asset,off,idx,n)', lambda r: (r[0], hex(r[1]), r[2], r[3])))
emu.memory.register_exec(0x02020174, H('obj_raw(src,idx,n)', lambda r: (hex(r[0]), r[1], r[2])))
def on_slot(a, s):
    t = regs.r1
    vals = struct.unpack('<8I', rd(emu, t, 32))
    log[('pal_slot(row,table)', regs.r0, hex(t), str(vals), hex(regs.r14))] += 1
emu.memory.register_exec(0x0206d8d8, on_slot)
emu.memory.register_exec(0x020833e0, H('compose', lambda r: (hex(r[0]), r[1], r[2])))
script = [["wait", frames]]
if len(sys.argv) > 3:
    script = json.load(open(sys.argv[3]))
run(emu, script, tag='t13')
for k, v in sorted(log.items(), key=lambda x: str(x[0])):
    print(v, k)
os._exit(0)
