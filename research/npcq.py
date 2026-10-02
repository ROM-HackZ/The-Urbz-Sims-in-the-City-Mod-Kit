import sys, os, json
sys.path.insert(0, '/root/urbz/kit8/verify')
import urbz_verify as V
rom = sys.argv[1]; script = json.load(open(sys.argv[2])); state = sys.argv[3] if len(sys.argv) > 3 else None
emu = V._emu(rom, None, os.devnull)
if state: emu.savestate.load_file(state)
regs = emu.memory.register_arm9
calls = []
def on(a, s):
    calls.append((V.FRAME[0], regs.r0, regs.r1, regs.r14))
emu.memory.register_exec(0x02065ad0, on)
# result: hook the return? record r0 at the caller's next instruction (0x02064ef0 region) instead
res = []
emu.memory.register_exec(0x02064f08, lambda a, s: res.append((V.FRAME[0], bytes(emu.memory.unsigned[regs.r4:regs.r4+12]).hex())))
V._run_script(emu, script, '/tmp', 'x')
import collections
print('calls', len(calls))
for c in calls[:80]: print('frame %d char %d (0x%x) area %d lr %08x' % (c[0], c[1], c[1], c[2], c[3]))
print('results', res[:40])
os._exit(0)
