"""Runtime probe: log every motive_apply_effect (0x0205DC20) call with r0 (needs ptr), r1 (row), r2 (quality), lr,
plus player needs/position/area at each shot.
usage: fxprobe.py SCRIPT.json|'[...]' [--state F] [--save out.dst] [--out DIR] [--tag T] [--poke A=HEX]... [--ents]
Needs printed as floats (8.24). Player needs at 0x02141204; player entity ptr at 0x02141C2C."""
import sys, os, json, struct, collections
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
args = sys.argv[1:]
def opt(n, d=None, many=False):
    out = [args[i + 1] for i, a in enumerate(args) if a == n]
    return out if many else (out[-1] if out else d)
rom = opt('--rom', '/root/urbz/work/van.nds')
script = json.loads(args[0]) if args[0].startswith('[') else json.load(open(args[0]))
state = opt('--state') or V.city_state(rom)
out = opt('--out', '/root/urbz/agentwork/objects/shots'); os.makedirs(out, exist_ok=True)
emu = V._emu(rom, opt('--rtc'), os.devnull)
emu.savestate.load_file(state)
for pk in opt('--poke', many=True):
    a, h = pk.split('=')
    for i, b in enumerate(bytes.fromhex(h)): emu.memory.write_byte(int(a, 0) + i, b)
regs = emu.memory.register_arm9; mem = emu.memory.unsigned
u32 = lambda a: struct.unpack('<I', bytes(mem[a:a + 4]))[0]
s32 = lambda a: struct.unpack('<i', bytes(mem[a:a + 4]))[0]
NEEDS = 0x02141204
def needs(p=NEEDS):
    return [round(s32(p + 4 * i) / 16777216, 3) for i in range(8)]
calls = collections.OrderedDict()
log = []
def on_fx(a, s):
    key = (regs.r0, regs.r1, regs.r2, regs.r14)
    c = calls.get(key)
    if c is None:
        c = calls[key] = dict(first=V.FRAME[0], n=0, needs_first=needs(regs.r0))
    c['n'] += 1; c['last'] = V.FRAME[0]
emu.memory.register_exec(0x0205DC20, on_fx)
# action begin: sim-state +4 holds the action id; log interaction begin calls through descriptor slot +0xC
def player():
    e = u32(0x02141C2C)
    return e if 0x02000000 <= e < 0x02400000 else None
def on_shot(name):
    e = player()
    pos = (u32(e + 0x18) >> 16, u32(e + 0x1C) >> 16) if e else None
    st = (mem[e + 0x104], mem[e + 0x105]) if e else None
    log.append((V.FRAME[0], 'shot', name, 'area', u32(0x02141FEC), 'pos', pos, 'state/action', st,
                'time', bytes(mem[0x0214112C:0x02141132]).hex(), 'needs', needs()))
print('start needs', needs(), 'flags@02141C30', hex(mem[0x02141C30] | mem[0x02141C31] << 8), 'phase', mem[0x02141C25])
V._run_script(emu, script, out, opt('--tag', 'fx'), None, on_shot)
for e in log: print(*e)
print('motive_apply_effect calls (needs_ptr, row, quality, lr): count, frames')
for (r0, r1, r2, lr), c in calls.items():
    print('  needs=%08x row=%d q=%d lr=%08x  n=%d frames %d..%d  needs_at_first=%s' % (r0, r1, r2, lr, c['n'], c['first'], c['last'], c['needs_first']))
print('end needs', needs())
if '--ents' in args:
    # list object entities (type 5): +0x0A object number, position
    m = bytes(mem[0x0215E344:0x0215E344 + 0x148 * 127])
    for k in range(127):
        b = k * 0x148
        t, c = struct.unpack_from('<HH', m, b + 8)
        x, y = struct.unpack_from('<ii', m, b + 0x18)
        beh = struct.unpack_from('<I', m, b + 0x4C)[0]
        if t == 5 and beh:
            print('obj ent %08x obj %d pos %d,%d beh %08x' % (0x0215E344 + b, c, x >> 16, y >> 16, beh))
if opt('--save'):
    emu.savestate.save_file(opt('--save')); print('saved', opt('--save'))
os._exit(0)
