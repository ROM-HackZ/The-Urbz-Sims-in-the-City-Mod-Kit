# usage: snaps.py rom state script.json outprefix  -> outprefix_<shot>.bin (main RAM)
import sys, os, json
sys.path.insert(0, '/root/urbz/kit8/verify')
import urbz_verify as V
rom, state, script, pre = sys.argv[1:5]
job = {'rom': rom, 'state': state, 'script': json.load(open(script)), 'out': os.path.dirname(os.path.abspath(pre)),
       'tag': 'snaps', 'snap': ['0x02000000:0x400000']}
res = V.run_child(job)
for i, (name, files) in enumerate(res['snaps']):
    os.replace(files[0], '%s_%d.bin' % (pre, i))
print('ok', len(res['snaps']))
