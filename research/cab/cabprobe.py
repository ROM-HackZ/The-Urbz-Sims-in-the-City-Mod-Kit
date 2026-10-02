"""Helper: run emulator in-process from power-on or a savestate, with custom hooks."""
import sys, os, json, struct
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
VAN = '/root/urbz/work/van.nds'
INTRO = json.load(open('/root/urbz/kit9/verify/scripts/intro.json'))

def emu_open(rom=VAN, state=None, sav=None):
    emu = V._emu(rom, None, os.devnull, sav)
    if state:
        emu.savestate.load_file(state)
    return emu

def run(emu, script, outdir='/root/urbz/agentwork/cab/shots', tag='s'):
    os.makedirs(outdir, exist_ok=True)
    return V._run_script(emu, script, outdir, tag)

def rd(emu, a, n):
    return bytes(emu.memory.unsigned[a:a+n])

def u32(emu, a):
    return struct.unpack('<I', rd(emu, a, 4))[0]
