from cabprobe import *
emu = emu_open(state='cab.dst')
print('gs', rd(emu, 0x02141140, 0x20).hex(' '))
print('ui', rd(emu, 0x02141FB0, 0x40).hex(' '))
run(emu, [["touch", 233, 165], ["wait", 90], ["shot", "threads0"]], tag='t4')
print('gs', rd(emu, 0x02141140, 0x20).hex(' '))
print('ui', rd(emu, 0x02141FB0, 0x40).hex(' '))
emu.savestate.save_file('/root/urbz/agentwork/cab/threads.dst')
os._exit(0)
