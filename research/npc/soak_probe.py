"""NPC Life soak: every player mod on, a save, N snapshots; flags people who look stuck or wrong.
Usage: soak_probe.py ROM SAVE_NAME STEPS EVERY [AREA]   (SAVE_NAME from verify/saves; AREA: --goto first)
Prints per snapshot: clock, people here (id state/action x,y), NPC Life's actors; then the suspects:
  orphan    action 0x30 (NPC Life drives them) but no actor holds them
  stuck     walking somewhere (state 0x26) without moving for 3 snapshots
  frozen    the same spot, state and action for 8+ snapshots (not at work standing)
  stacked   two people within 4 px of each other
Screenshots s00.. in the evidence folder printed at the end."""
import json, os, struct, sys
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rom, save, steps, every = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
area = int(sys.argv[5]) if len(sys.argv) > 5 else None
sys.path.insert(0, os.path.join(KIT, 'tests')); sys.argv = sys.argv[:1]
import proofs as P

SYM = json.load(open(os.path.join(KIT, 'mods', 'npc-life', 'code', 'build', 'patch.json')))['symbols']
NAMES = None


def name(i):
    global NAMES
    if NAMES is None:
        import urbz_text as T
        NAMES = T.project_strings(P.PROJ)
    try:
        return NAMES[512 + i - 31].decode('latin-1').split(' ')[0]
    except Exception:
        return '#%d' % i




def run_snaps(n_steps=None, player_at=None):
    """P.snapshots, with the boxes that come up first (the strays' intro) closed with B. player_at = (entity,
    x, y): the player is put there first (env PLAYER_AT=x,y: to watch a spot)."""
    import tempfile
    sys.path.insert(0, os.path.join(KIT, 'verify'))
    import urbz_verify as V
    out = tempfile.mkdtemp(prefix='urbz-soak-')
    script = [['wait', 500], ['press', 'B', 4], ['wait', 300], ['press', 'B', 4], ['wait', 60]]
    if area is not None:                          # (the loader's own goto only works once the game settled)
        script += P._area_goto(area) + [['wait', 120]]
    if player_at:
        pe, px, py = player_at
        script += [['poke', '0x%08X=%s' % (pe + 0x18, struct.pack('<iiii', px << 16, py << 16, px << 16, py << 16).hex())]]
    for k in range(steps if n_steps is None else n_steps):
        script += [['wait', every], ['shot', 's%02d' % k]]
    job = {'rom': os.path.abspath(rom), 'out': out, 'tag': 'snap',
           'state': V.city_state(os.path.abspath(rom), None, save), 'script': script,
           'snap': ['0x02100000:0x100000', '0x0214112C:6'], 'poke': []}
    res = V.run_child(job, timeout=3000)
    return [[open(f, 'rb').read() for f in files] for _, files in res['snaps']], out


player_at = None
if os.environ.get('PLAYER_AT'):
    first, _ = run_snaps(1)
    mem = first[0][0]
    rd = lambda a, k: mem[a - 0x02100000:a - 0x02100000 + k]
    e = struct.unpack('<I', rd(0x02121AF0, 4))[0]
    while e and struct.unpack('<H', rd(e + 8, 2))[0] != 0:
        e = struct.unpack('<I', rd(e, 4))[0]
    player_at = (e,) + tuple(int(v) for v in os.environ['PLAYER_AT'].split(','))
snaps, out = run_snaps(None, player_at)
hist, suspects = {}, []
for n, (mem, clock) in enumerate(snaps):
    rd = lambda a, k: mem[a - 0x02100000:a - 0x02100000 + k]
    day, hh, mm = struct.unpack_from('<hBB', clock)
    people = []
    e = struct.unpack('<I', rd(0x02121AF0, 4))[0]
    while e and 0x02100000 <= e < 0x02200000 and len(people) < 200:
        t, who = struct.unpack('<HH', rd(e + 8, 4))
        if t == 7:
            x, y = struct.unpack('<ii', rd(e + 0x18, 8))
            st, ac, _, fl = rd(e + 0x104, 4)
            people.append((e, who, st, ac, fl, x >> 16, y >> 16))
        e = struct.unpack('<I', rd(e, 4))[0]
    k = mem.find(struct.pack('<I', 0x5443414E))         # 'NACT'
    actors = []
    if k >= 0:
        base = 0x02100000 + k - SYM['npc_act']
        for a in range(4):
            ea, who, need, obj, kind, since, until, partner, pwho, phase = struct.unpack_from(
                '<IBBBBIIIBB', rd(base + SYM['actors'] + 28 * a, 26))
            if ea:
                actors.append((ea, who, need, kind, partner, pwho, phase, since, until))
        nact = struct.unpack_from('<8I', rd(base + SYM['npc_act'], 32))
        more = struct.unpack_from('<10I', rd(base + SYM['npc_act'] + 36, 40))  # rounds, seen, cand, no_object, chats, loose, forced, kept, walked_off, looks
        if os.environ.get('NACT'):
            print('   nact sent %d fin %d abort %d rescued %d left %d refused %d busy %d | rounds %d seen %d cand %d noobj %d chats %d loose %d forced %d kept %d walked_off %d looks %d' % (nact[1:] + more))
    held = {a[0] for a in actors} | {a[4] for a in actors if a[3] == 1}
    print('%02d day %d %02d:%02d  %s | actors %s' % (n, day, hh, mm, ' '.join(
        '%s %x/%x %d,%d' % (name(w), st, ac, x, y) for _, w, st, ac, fl, x, y in people),
        ['%s %s%s' % (name(a[1]), 'chat ' + name(a[5]) if a[3] == 1 else 'look %d' % a[5] if a[3] == 2 else 'obj need %d %d..%d' % (a[2], a[7], a[8]), '') for a in actors]))
    if k >= 0:
        print('   act_ticks %d' % struct.unpack('<I', rd(base + SYM['act_ticks'], 4))[0])
    for e_, w, st, ac, fl, x, y in people:
        h = hist.setdefault(e_, [])
        h.append((n, st, ac, x, y))
        if st == 0x11 and e_ not in held and k >= 0:
            suspects.append('%02d using an object, nobody tracking them %s %x/%x at %d,%d' % (n, name(w), st, ac, x, y))
        run = 0
        for p_ in reversed(h):
            if p_[1] != 0x11:
                break
            run += 1
        if run * every > 1800:                        # using one thing for over a minute of real time
            suspects.append('%02d sitting/using too long (%d s) %s at %d,%d' % (n, run * every // 60, name(w), x, y))
        if st == 0x23 and len(h) >= 6 and all(p[1:] == h[-1][1:] for p in h[-6:]) and h[-6][2] == 7:
            pass
        if ac == 0x30 and e_ not in held and k >= 0:
            suspects.append('%02d orphan %s %x/%x at %d,%d' % (n, name(w), st, ac, x, y))
        last = [p for p in h if p[0] > n - 3]
        if st == 0x26 and len(last) == 3 and all(p[3:] == last[0][3:] for p in last):
            suspects.append('%02d stuck walking %s at %d,%d' % (n, name(w), x, y))
        last8 = [p for p in h if p[0] > n - 8] if st != 0x31 else []   # (0x31: a shop clerk at the counter)
        if len(last8) == 8 and all(p[1:] == last8[0][1:] for p in last8) and n - 8 >= 0:
            suspects.append('%02d frozen %s %x/%x at %d,%d' % (n, name(w), st, ac, x, y))
    for i in range(len(people)):
        for j in range(i + 1, len(people)):
            a, b = people[i], people[j]
            if abs(a[5] - b[5]) < 4 and abs(a[6] - b[6]) < 4:
                suspects.append('%02d stacked %s and %s at %d,%d' % (n, name(a[1]), name(b[1]), a[5], a[6]))
print('npc_act (sent, finished, aborted, rescued, left, refused, busy_paths):', nact[1:] if 'nact' in globals() else '-')
print('suspects:' if suspects else 'suspects: none')
for s in suspects:
    print('  ' + s)
print('screens:', out)
