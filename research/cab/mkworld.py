from cabprobe import *
emu = emu_open()
run(emu, json.load(open('/root/urbz/kit9/verify/scripts/newgame.json')), tag='ng')
emu.savestate.save_file('/root/urbz/agentwork/cab/world.dst')
os._exit(0)
