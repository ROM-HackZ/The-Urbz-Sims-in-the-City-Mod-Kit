"""EXPERIMENT (uses memory pokes): load every area via the game's own state machine and
measure the heap. From STATE (default tower_lobby.dst), for each area id:
  poke next-state of screen 0: 0x027C009C = 0x81 (state 1 = area), 0x027C00A0 = 0 (mode),
  0x027C00A4 = area id, 0x02141C28 = entry id (first entry point of that area);
then run N frames sampling the heap every 10 frames. Writes heap_sweep.json + a screenshot per area."""
import sys, os, json, struct
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
HERE = os.path.dirname(os.path.abspath(__file__))
state = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'tower_lobby.dst')
N = int(sys.argv[2]) if len(sys.argv) > 2 else 450
only = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else list(range(80))
A = json.load(open(os.path.join(HERE, 'areas.json')))['areas']
emu = V._emu('/root/urbz/work/van.nds', None, os.devnull)
mem = emu.memory.unsigned
regs = emu.memory.register_arm9
u32 = lambda a: struct.unpack('<I', bytes(mem[a:a + 4]))[0]
spawns = []
emu.memory.register_exec(0x0206499C, lambda a, s: spawns.append(regs.r0))
loads = []
emu.memory.register_exec(0x0204C158, lambda a, s: loads.append(u32(0x027C0078)))
out = {}
os.makedirs(os.path.join(HERE, 'sweep'), exist_ok=True)
for aid in only:
    emu.savestate.load_file(state)
    entry = A[aid]['entry_points'][0]['id'] if A[aid]['entry_points'] else 0
    for addr, val in ((0x027C009C, 0x81), (0x027C00A0, 0), (0x027C00A4, aid)):
        for i, b in enumerate(struct.pack('<I', val)):
            emu.memory.write_byte(addr + i, b)
    emu.memory.write_byte(0x02141C28, entry)
    spawns.clear(); loads.clear()
    mf = ml = None; mu = 0
    for f in range(N):
        emu.cycle(with_joystick=False)
        if f % 10 == 0 and loads:
            st = V.heap_stats(mem)
            if st:
                fr, big, used = st
                mf = fr if mf is None else min(mf, fr)
                ml = big if ml is None else min(ml, big)
                mu = max(mu, used)
    cur = u32(0x02141FEC)
    end = V.heap_stats(mem)
    emu.screenshot().save(os.path.join(HERE, 'sweep', 'area%02d.png' % aid))
    out[aid] = dict(name=A[aid]['name'], loaded=(cur == aid), current_area=cur, load_calls=loads[:], entry=entry,
                    min_free=mf, min_largest=ml, max_used=mu, end_free=end[0] if end else None,
                    end_largest=end[1] if end else None, spawned=spawns[:])
    print(aid, out[aid]['name'], 'loaded' if cur == aid else 'NOT LOADED (cur %d)' % cur,
          'min_free', mf, 'min_largest', ml, 'end_free', end[0] if end else None, 'spawned', spawns, flush=True)
json.dump(out, open(os.path.join(HERE, 'heap_sweep.json'), 'w'), indent=1)
os._exit(0)
