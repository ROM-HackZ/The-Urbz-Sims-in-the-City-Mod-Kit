"""New game; take shots every 40 frames after the city appears, to catch Kris walking.
usage: kris.py rom tag"""
from cabprobe import *
rom, tag = sys.argv[1], sys.argv[2]
ng = json.load(open('/root/urbz/kit9/verify/scripts/newgame.json'))
i = next(k for k, s in enumerate(ng) if s[0] == 'shot' and s[1] == 'city')
emu = emu_open(rom=rom)
regs = emu.memory.register_arm9
ev = []
emu.memory.register_exec(0x0206d73c, lambda a, s: ev.append(V.FRAME[0]))
run(emu, ng[:i], tag=tag)
sc = []
for k in range(14):
    sc += [["wait", 40], ["shot", "k%02d" % k]]
run(emu, sc, tag=tag)
print('row-assign frames', ev)
os._exit(0)
