from cabprobe import *
emu = emu_open()
run(emu, INTRO + [["wait", 120], ["shot", "cab0"]], tag='mk')
emu.savestate.save_file('/root/urbz/agentwork/cab/cab.dst')
os._exit(0)
