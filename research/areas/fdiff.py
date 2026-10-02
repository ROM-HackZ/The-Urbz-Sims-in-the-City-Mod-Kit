"""Record which arm9 functions execute during a script (hooks every function start).
usage: fdiff.py STATE SCRIPT_JSON OUT.json"""
import sys, os, json
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
emu = V._emu('/root/urbz/work/van.nds', None, os.devnull)
emu.savestate.load_file(sys.argv[1])
fs = json.load(open('/root/urbz/ghidra/functions_arm9.json'))
hit = {}
def mk(a):
    def f(addr, size):
        if a not in hit: hit[a] = V.FRAME[0]
    return f
for f in fs:
    if not f.get('thumb'):
        emu.memory.register_exec(f['addr'], mk(f['addr']))
V._run_script(emu, json.loads(sys.argv[2]), '/tmp', 'fd')
json.dump(hit, open(sys.argv[3], 'w'))
print(len(hit))
os._exit(0)
