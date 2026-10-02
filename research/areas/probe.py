"""Custom emulator probe for area work.
usage: probe.py SCRIPT.json [--state F] [--save out.dst] [--out DIR] [--poke A=HEX] [--heap N] [--log-assets]
Logs: area changes (writes to current_area 0x02141FEC), area_load (0x0204C158) entries,
get_asset ids, type-7 spawn_from_record calls; screenshots on 'shot'."""
import sys, os, json, struct
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
args = sys.argv[1:]
def opt(n, d=None, many=False):
    out = [args[i+1] for i, a in enumerate(args) if a == n]
    return out if many else (out[-1] if out else d)
rom = opt('--rom', '/root/urbz/work/van.nds')
script = json.load(open(args[0])) if not args[0].startswith('[') else json.loads(args[0])
state = opt('--state') or V.city_state(rom)
out = opt('--out', '/root/urbz/agentwork/areas/shots'); os.makedirs(out, exist_ok=True)
emu = V._emu(rom, opt('--rtc'), os.devnull)
emu.savestate.load_file(state)
for pk in opt('--poke', many=True):
    a, h = pk.split('=')
    for i, b in enumerate(bytes.fromhex(h)): emu.memory.write_byte(int(a, 0) + i, b)
regs = emu.memory.register_arm9; mem = emu.memory.unsigned
u32 = lambda a: struct.unpack('<I', bytes(mem[a:a+4]))[0]
log = []
def L(*x):
    log.append((V.FRAME[0],) + x)
emu.memory.register_exec(0x0204C158, lambda a, s: L('area_load_enter', 'from', u32(0x02141FEC), 'to', u32(0x027C0078 + 0x8C * u32(0x027C0004)), 'mode', u32(0x027C0074 + 0x8C * u32(0x027C0004)), 'screen', u32(0x027C0004)))
emu.memory.register_write(0x02141FEC, lambda a, s: L('area_write', regs.r15, regs.r14))
emu.memory.register_exec(0x02064ED8, lambda a, s: L('spawn_from_record', regs.r0, regs.r1))
emu.memory.register_exec(0x0206499C, lambda a, s: L('spawn_npc', regs.r0, regs.r1, regs.r2 >> 16, regs.r3 >> 16))
if '--log-assets' in args:
    emu.memory.register_exec(0x02032CA8, lambda a, s: L('get_asset', regs.r0))
heapN = int(opt('--heap', 0) or 0)
heap = {'min_free': None, 'min_largest': None, 'max_used': 0, 'samples': 0}
def hs(frame):
    if heapN and frame % heapN == 0:
        st = V.heap_stats(mem)
        if st:
            f, b, u = st
            heap['samples'] += 1
            heap['min_free'] = f if heap['min_free'] is None else min(heap['min_free'], f)
            heap['min_largest'] = b if heap['min_largest'] is None else min(heap['min_largest'], b)
            heap['max_used'] = max(heap['max_used'], u)
V.PER_FRAME.append(hs)
def on_shot(name):
    e = u32(0x02141C2C)
    pos = (u32(e + 0x18) >> 16, u32(e + 0x1C) >> 16) if 0x02000000 <= e < 0x02400000 else None
    L('shot', name, 'area', u32(0x02141FEC), 'pos', pos, 'time', bytes(mem[0x0214112C:0x02141132]).hex(), 'heap', V.heap_stats(mem))
tag = opt('--tag', 'p')
V._run_script(emu, script, out, tag, None, on_shot)
for e in log:
    if e[1] == 'area_write':
        print(e[0], 'area_write pc=%08x lr=%08x' % (e[2], e[3]))
    else:
        print(*e)
print('final area', u32(0x02141FEC), 'variant', mem[0x02122794], 'heap', heap if heapN else V.heap_stats(mem))
if opt('--save'):
    emu.savestate.save_file(opt('--save')); print('saved', opt('--save'))
os._exit(0)
