"""Who is in the area over time, and where: from a save, with the clock set, snapshots every N frames list each
person (id, name, x, y, entity +0x104 state) and a screenshot.

  python research/npc/who_where.py ROM SAVE DAY HH:MM STEPS EVERY [OUT_DIR] [AREA [ENTRY]]   (AREA: load it first)"""
import json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, 'kit')); sys.path.insert(0, os.path.join(KIT, 'verify'))
import urbz_verify as V

rom, save, day, hm, steps, every = sys.argv[1:7]
out = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] != '-' else tempfile.mkdtemp(prefix='urbz-who-')
os.makedirs(out, exist_ok=True)
h, m = map(int, hm.split(':'))
names = {int(k): v['name'] for k, v in json.load(open(os.path.join(KIT, 'docs', 'data', 'areas.json')))['xref'].items()}
script = []
for k in range(int(steps)):
    script += [['wait', int(every)], ['shot', 's%02d' % k]]
clock = struct.pack('<hbbbb', int(day), h, m, 0, 0).hex()
job = {'rom': os.path.abspath(rom), 'out': out, 'tag': 'snap', 'state': V.city_state(os.path.abspath(rom), None, save),
       'script': script, 'poke': ['0x0214112C=%s' % clock], 'snap': ['0x02100000:0x300000']}
if len(sys.argv) > 8:
    goto = int(sys.argv[8])
    pts = json.load(open(V.AREAS_JSON))['areas'][goto]['entry_points']
    job['goto'] = (goto, int(sys.argv[9]) if len(sys.argv) > 9 else pts[0]['id'] if pts else 0)
res = V.run_child(job, timeout=6000)
B = 0x02100000
for k, (_, files) in enumerate(res['snaps']):
    mem = open(files[0], 'rb').read()
    rd = lambda a, f='<I': struct.unpack_from(f, mem, a - B)[0]
    d, hh, mm = struct.unpack_from('<hbb', mem, 0x0214112C - B)
    area = None
    e, ppl = rd(0x02121AF0), []
    while e and B <= e < B + len(mem):
        t, i = rd(e + 8, '<H'), rd(e + 10, '<H')
        x, y = rd(e + 0x18, '<i') >> 16, rd(e + 0x1C, '<i') >> 16
        if t == 0:
            ppl.append('player(%d,%d)' % (x, y))
        elif t == 7:
            ppl.append('%d %s (%d,%d) st=%02x' % (i, names.get(i, '?'), x, y, rd(e + 0x104, '<B')))
        e = rd(e)
    print('s%02d day %d %02d:%02d | %s' % (k, d, hh, mm, ' | '.join(ppl)))
print(out)
