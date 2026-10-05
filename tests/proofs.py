#!/usr/bin/env python3
"""Regression proofs: build test mods and check, in the emulator, that each one does
what the docs claim. Every claim in docs/systems.md marked "Proven" has a proof here.

  python tests/proofs.py              run all (about an hour; never two runs at once)
  python tests/proofs.py NAME ...     run some (names: python tests/proofs.py --list)

Needs project/ (extracted from your ROM), py-desmume, and LLVM (clang, ld.lld) for the
proofs that compile C. Test mods live in tests/mods/; data files that would come from the
game (asset bytes) are generated here at run time, so nothing from the ROM is committed.
Built ROMs go to build/proofs/. Exit code 1 if any proof fails.
"""
import glob, json, os, random, shutil, struct, subprocess, sys, tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(TESTS)
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, 'verify'))
PROJ = os.path.join(KIT, 'project')
OUT = os.path.join(KIT, 'build', 'proofs')
VERIFY = [sys.executable, os.path.join(KIT, 'verify', 'urbz_verify.py')]
CODE_BASE = 0x0214DE20


# ---------------------------------------------------------------- helpers

def build(name, mods):
    """Build a ROM from test mods (names under tests/mods, or paths). Returns (rom, log)."""
    import urbz_build
    os.makedirs(OUT, exist_ok=True)
    dirs = [m if os.path.isabs(m) else os.path.join(TESTS, 'mods', m) for m in mods]
    for d in dirs:
        cdir = os.path.join(d, 'code')
        if os.path.isdir(cdir) and any(f.endswith('.c') for f in os.listdir(cdir)):
            run([sys.executable, os.path.join(KIT, 'urbz_patch.py'), 'build', '--dir', d])
    rom = os.path.join(OUT, name + '.nds')
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sha = urbz_build.build(PROJ, rom, dirs)
    return rom, buf.getvalue(), sha


def run(cmd, timeout=900):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('%s failed:\n%s%s' % (' '.join(cmd[:3]), p.stdout[-2000:], p.stderr[-2000:]))
    return p.stdout


def ram(rom, frames, *reads, pokes=(), script=None, start=('--city',)):
    """{ADDR:LEN -> bytes} after `frames` frames from the build's city state."""
    cmd = VERIFY + ['ram', rom] + list(start) + ['--frames', str(frames)]
    for p in pokes:
        cmd += ['--poke', p]
    if script:
        cmd += ['--script', script]
    for r in reads:
        cmd += ['--read', r]
    out = {}
    for line in run(cmd).splitlines():
        if ' = ' in line and ':' in line.split(' = ')[0]:
            k, v = line.split(' = ')
            out[k.strip()] = bytes.fromhex(v.strip())
    return out


def find_magic(rom, frames, magic, size):
    """Read `size` bytes of a code mod's struct that starts with the u32 `magic`."""
    r = ram(rom, frames, '0x%08X:0x8000' % CODE_BASE)['0x%08X:0x8000' % CODE_BASE]
    i = r.find(struct.pack('<I', magic))
    if i < 0:
        raise RuntimeError('magic %08x not found in the code region' % magic)
    return r[i:i + size], CODE_BASE + i


HEAP_SCAN = '0x0214DE20:0x70000'   # code region + the start of the heap (the entity pool moves with the code)


def people_in(mem, base=0x0214DE20):
    """Character ids of the people (entity type 7) in a RAM dump that starts at base."""
    out = set()
    for k in range(0, len(mem) - 0x148, 4):
        t, i = struct.unpack_from('<HH', mem, k + 8)
        if t == 7 and 31 <= i < 80 and struct.unpack_from('<H', mem, k + 0x146)[0] == i:
            out.add(i)
    return sorted(out)


def s824(b, i):
    return struct.unpack_from('<i', b, 4 * i)[0] / 16777216.0


def new_mod(name):
    d = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), name)
    os.makedirs(d)
    return d


# ---------------------------------------------------------------- proofs

def p_vanilla():
    rom, log, sha = build('vanilla', [])
    m = json.load(open(os.path.join(PROJ, 'manifest.json')))
    return sha == m['source_sha1'], 'sha1 %s' % sha


def p_clock_speed():
    rom, _, _ = build('clock-speed', [os.path.join(TESTS, 'mods', 'clock-speed')])
    a = ram(rom, 1, '0x0214112C:6')['0x0214112C:6']
    b = ram(rom, 61, '0x0214112C:6')['0x0214112C:6']
    secs = lambda t: t[2] * 3600 + t[3] * 60 + t[4] + t[5] / 30
    d = secs(b) - secs(a)
    return abs(d - 45) < 1, 'clock advanced %.1f s in 60 frames (expect 45; original 90)' % d


def p_hooks_wrap_call():
    rom, _, _ = build('hello', ['hello'])
    a, _ = find_magic(rom, 1, 0x4F4C4548, 18)
    b, _ = find_magic(rom, 61, 0x4F4C4548, 18)
    t0, c0 = struct.unpack_from('<II', a, 4)
    t1, c1 = struct.unpack_from('<II', b, 4)
    clock = ram(rom, 61, '0x0214112C:6')['0x0214112C:6']
    ok = t1 - t0 == 30 and c1 - c0 == 30 and b[12:18] == clock
    return ok, 'wrap ticks +%d, call count +%d per 60 frames; copied clock == game clock: %s' % (
        t1 - t0, c1 - c0, b[12:18] == clock)


def p_hooks_thumb():
    rom, _, _ = build('thumbtest', ['thumbtest'])
    a, _ = find_magic(rom, 1, 0x424D5554, 8)
    b, _ = find_magic(rom, 61, 0x424D5554, 8)
    d = struct.unpack_from('<I', b, 4)[0] - struct.unpack_from('<I', a, 4)[0]
    return d == 30, 'ARM call -> Thumb function ran %d times in 60 frames (expect 30)' % d


def p_hooks_jump():
    rom, _, _ = build('jtest', ['jtest'])
    bars = ram(rom, 30, '0x02141CA8:8')['0x02141CA8:8']
    return bars == bytes([100] * 8), 'HUD need values with motive_get replaced: %s' % list(bars)


def p_relayout():
    rom, log, _ = build('relayout', ['hello', 'bigtest'])
    h = open(rom, 'rb').read(0x200)
    arm7 = struct.unpack_from('<I', h, 0x30)[0]
    big, _ = find_magic(rom, 61, 0x47494221, 12)
    heap = struct.unpack_from('<I', ram(rom, 1, '0x02142008:4')['0x02142008:4'])[0]
    smoke = subprocess.run(VERIFY + ['smoke', rom], capture_output=True, text=True).stdout
    ok = arm7 > 0x1000000 and struct.unpack_from('<I', big, 8)[0] == 6 and 'SMOKE PASS' in smoke
    return ok, 'arm7 moved to %#x; big mod sum %d; heap starts %#x; %s' % (
        arm7, struct.unpack_from('<I', big, 8)[0], heap, 'smoke PASS' if 'SMOKE PASS' in smoke else 'smoke FAIL')


def p_needs_decay():
    rom, _, _ = build('slow-hunger', ['slow-hunger'])
    unfreeze = ['0x02141c30=00']
    a = ram(rom, 1, '0x02141204:8', pokes=unfreeze)['0x02141204:8']
    b = ram(rom, 1201, '0x02141204:8', pokes=unfreeze)['0x02141204:8']
    dh, dy = s824(a, 0) - s824(b, 0), s824(a, 1) - s824(b, 1)
    return abs(dh - 1.389) < 0.05 and abs(dy - 1.667) < 0.05, \
        'over 600 ticks: hunger -%.3f (expect -1.389, half), hygiene -%.3f (expect -1.667)' % (dh, dy)


def p_action_effect():
    rom, _, _ = build('accident', ['accident-test'])
    b = ram(rom, 241, '0x02141218:4', pokes=['0x02141c30=00', '0x02141218=00000000'])['0x02141218:4']
    v = s824(b, 0)
    return abs(v - 49.6) < 1.5, 'bladder after the accident: %.1f (expect ~49.6; original ~99.6)' % v


def p_lz77_repack():
    mod = new_mod('lz-proof')
    shutil.copytree(os.path.join(TESTS, 'mods', 'lz-proof', 'code'), os.path.join(mod, 'code'))
    random.seed(7)
    data = bytes(random.randrange(256) for _ in range(32))      # incompressible: the stream grows
    os.makedirs(os.path.join(mod, 'unpacked', '00150'))
    open(os.path.join(mod, 'unpacked', '00150', '000274.bin'), 'wb').write(data)
    rom, log, _ = build('lz-proof', [mod])
    s, _ = find_magic(rom, 4, 0x50525A4C, 12 + 64)
    state, size = struct.unpack_from('<II', s, 4)
    got = s[12:12 + size]
    return state == 4 and got == data and 'grew' in log, \
        'game decoded %d bytes, equal to our chunk: %s; build: %s' % (size, got == data, 'grew' in log)


def p_npc_schedule_hook():
    rom, _, _ = build('npc-visit', [os.path.join(TESTS, 'mods', 'npc-visit')])
    s, _ = find_magic(rom, 300, 0x54495356, 8)
    answered = struct.unpack_from('<I', s, 4)[0]
    found = 31 in people_in(ram(rom, 300, HEAP_SCAN)[HEAP_SCAN])
    return answered > 0 and found, \
        'schedule hook answered %d time(s); Bayou Boo (type 7, id 31) in the entity pool: %s' % (
            answered, found)


# ---------------------------------------------------------------- Phase 5: mod platform

CORE_MAGIC = 0x45524F43          # 'CORE': the mod core's state (code/core/core.h)
TABLE_ROW = 80


def core_request(rom, index, on):
    """--poke that asks the mod core to switch mod `index` on/off at the next tick."""
    _, addr = find_magic(rom, 1, CORE_MAGIC, 8)
    return '0x%08X=%s' % (addr + 4, struct.pack('<I', 0x80000000 | on << 8 | index).hex())


def table_on(rom, frames, index, pokes=()):
    """The switch byte of mod `index` in the mod table (0x0214DE20)."""
    a = CODE_BASE + 32 + TABLE_ROW * index + 28
    return ram(rom, frames, '0x%08X:1' % a, pokes=pokes)['0x%08X:1' % a][0]


def p_toggle_call():
    """A call hook (npc-visit) switched off in-game: the game's own schedule answers again."""
    rom, _, _ = build('toggle-call', [os.path.join(TESTS, 'mods', 'npc-visit')])
    reg = '0x%08X:0x8000' % CODE_BASE

    def answered(region):
        i = region.find(struct.pack('<I', 0x54495356))
        return struct.unpack_from('<I', region, i + 4)[0]

    def run(pokes):
        early = answered(ram(rom, 30, reg, pokes=pokes)[reg])
        r = ram(rom, 330, HEAP_SCAN, pokes=pokes)[HEAP_SCAN]
        region = r[:0x8000]
        return answered(region) - early, 31 in people_in(r), region[32 + 28]
    on = run(())
    off = run((core_request(rom, 0, 0),))
    ok = on[0] > 0 and on[1] and on[2] == 1 and off[0] == 0 and not off[1] and off[2] == 0
    return ok, 'on: hook answered %d time(s) in 300 frames, Bayou Boo present %s; switched off: answered %d, ' \
        'present %s, switch byte %d' % (on[0], on[1], off[0], off[1], off[2])


def p_toggle_data():
    """A data hook (clock-speed) switched off and on in-game: the core restores and re-applies the bytes."""
    rom, _, _ = build('toggle-data', [os.path.join(TESTS, 'mods', 'clock-speed')])
    secs = lambda t: t[2] * 3600 + t[3] * 60 + t[4] + t[5] / 30

    def rate(pokes):
        a = ram(rom, 2, '0x0214112C:6', pokes=pokes)['0x0214112C:6']
        r = ram(rom, 62, '0x0214112C:6', '0x02113B60:2', pokes=pokes)
        return secs(r['0x0214112C:6']) - secs(a), r['0x02113B60:2'].hex()
    on = rate(())
    req_off = core_request(rom, 0, 0)
    off = rate((req_off,))
    ok = abs(on[0] - 45) < 1 and on[1] == '010f' and abs(off[0] - 90) < 1 and off[1] == '0300'
    return ok, 'on: %.1f s per 60 frames, table %s; switched off: %.1f s, table %s (original 90 s, 0300)' % (
        on[0], on[1], off[0], off[1])


SAVEGAME = os.path.join(KIT, 'verify', 'scripts', 'savegame.json')
LOADGAME = os.path.join(KIT, 'verify', 'scripts', 'loadgame.json')


def play_export(rom, name, start, script, pokes=()):
    """Run an input script and export the cartridge save memory -> path of the .sav."""
    os.makedirs(OUT, exist_ok=True)
    sav = os.path.join(OUT, name + '.sav')
    cmd = VERIFY + ['play', rom] + list(start) + ['--script', script, '--save',
                                                  os.path.join(OUT, name + '.dst'), '--export-sav', sav]
    for p in pokes:
        cmd += ['--poke', p]
    run(cmd)
    return sav


def with_switches(sav, out, entries):
    """Copy of a .sav with a switch record [(mod folder name, on)] at 0x1FE0 (as the core writes it)."""
    from urbz_code import name_hash
    buf = bytearray(open(sav, 'rb').read())
    rec = bytearray(b'\xff' * 32)
    rec[0:6] = b'MODS' + bytes([1, len(entries)])
    for k, (name, on) in enumerate(entries):
        struct.pack_into('<H', rec, 8 + 2 * k, (name_hash(name) & 0x7FFF) | (0x8000 if on else 0))
    struct.pack_into('<H', rec, 6, sum(rec[8:]) & 0xFFFF)
    buf[0x1FE0:0x2000] = rec
    open(out, 'wb').write(buf)
    return out


def probe_state(rom, start, frames, script=None):
    """save-probe's counters after a run: dict."""
    reg = '0x%08X:0x8000' % CODE_BASE
    r = ram(rom, frames, reg, '0x02141FEC:4', '0x0214112C:6', start=start, script=script)
    b = r[reg]
    i = b.find(struct.pack('<I', 0x52505653))
    names = 'magic minutes saves loads fresh last_loaded boots enables disables ticks'.split()
    st = dict(zip(names, struct.unpack_from('<10I', b, i))) if i >= 0 else {}
    st['area'] = struct.unpack('<I', r['0x02141FEC:4'])[0]
    st['clock'] = r['0x0214112C:6']
    return st


def p_save_block():
    """Per-mod save data: written after the game's data, read back after power-off, defaults on a
    vanilla save, ignored by a vanilla build, and kept unchanged while the mod is switched off."""
    import urbz_save
    from urbz_code import name_hash
    rom, _, _ = build('save-block', ['save-probe'])
    van, _, _ = build('vanilla', [])
    h = name_hash('save-probe')
    fresh = probe_state(rom, ['--city'], 1)                       # city.sav is a vanilla save
    s1 = play_export(rom, 'save-block-1', ['--city'], SAVEGAME)
    buf = open(s1, 'rb').read()
    blk = urbz_save.mod_block(buf[0x20:0x20 + urbz_save.SLOT_SIZE]) or []
    mine = [d for hh, d in blk if hh == h]
    saved = struct.unpack_from('<I', mine[0], 4)[0] if mine and mine[0][:4] == b'PRB1' else None
    valid = urbz_save.slot_valid(bytearray(buf), 0)
    back = probe_state(rom, ['--sav', s1], 30, LOADGAME)           # power-off, boot, Load-an-Urb
    vback = probe_state(van, ['--sav', s1], 30, LOADGAME)          # a build without mods
    off_sav = with_switches(s1, os.path.join(OUT, 'save-block-off.sav'), [('save-probe', False)])
    s2 = play_export(rom, 'save-block-2', ['--sav', off_sav], LOADGAME)
    s3 = play_export(rom, 'save-block-3', ['--state', os.path.join(OUT, 'save-block-2.dst')], SAVEGAME)
    blk3 = urbz_save.mod_block(open(s3, 'rb').read()[0x20:0x20 + urbz_save.SLOT_SIZE]) or []
    kept = [d for hh, d in blk3 if hh == h]
    ok = (fresh.get('fresh') == 1 and fresh.get('loads') == 0 and saved and valid
          and back.get('loads') == 1 and back.get('last_loaded') == saved
          and vback['area'] == back['area'] != 82 and vback['clock'][:3] == back['clock'][:3]
          and kept == mine)
    return ok, ('vanilla save -> fresh %s; block %s, minutes %s, slot checksum %s; reloaded: loads %s, '
                'value %s; vanilla build loads it: area %d (modded %d); switched off and saved again: '
                'block kept unchanged %s') % (fresh.get('fresh'), [(hex(x), len(d)) for x, d in blk], saved,
                                            'OK' if valid else 'BAD', back.get('loads'), back.get('last_loaded'),
                                            vback['area'], back['area'], kept == mine)


def p_switch_persist():
    """A switch changed in the game is written to save memory at once and holds after power-off
    (checked at the title screen, before any game is loaded)."""
    import urbz_save, tempfile
    rom, _, _ = build('switch-persist', [os.path.join(TESTS, 'mods', 'npc-visit'),
                                         os.path.join(TESTS, 'mods', 'clock-speed')])
    wait = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'wait.json')
    json.dump([['wait', 60]], open(wait, 'w'))
    sav = play_export(rom, 'switch-persist', ['--city'], wait, pokes=[core_request(rom, 1, 0)])
    rec = urbz_save.switch_record(bytearray(open(sav, 'rb').read()))
    from urbz_code import name_hash
    want = [(name_hash('npc-visit') & 0x7FFF, 1), (name_hash('clock-speed') & 0x7FFF, 0)]
    on_bytes = '0x%08X:%d' % (CODE_BASE + 32 + 28, TABLE_ROW + 1)
    r = ram(rom, 1700, on_bytes, '0x02113B60:2', start=['--sav', sav])
    b = r[on_bytes]
    ok = rec == want and b[0] == 1 and b[TABLE_ROW] == 0 and r['0x02113B60:2'] == b'\x03\x00'
    return ok, 'record in save memory: %s; after power-off at the title: npc-visit on=%d, clock-speed on=%d, ' \
        'clock table %s (original 0300)' % (rec, b[0], b[TABLE_ROW], r['0x02113B60:2'].hex())


def p_mods_page():
    """The Mods button on Options and the Mods page, driven with real touches: switching
    clock-speed off there restores the clock, and the switch holds after power-off."""
    import shutil, tempfile
    rom, _, _ = build('mods-page', [os.path.join(TESTS, 'mods', 'npc-visit'),
                                    os.path.join(TESTS, 'mods', 'clock-speed')])
    script = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'mods.json')
    json.dump([['wait', 30], ['touch', 128, 180, 8], ['wait', 60], ['shot', 'options'],
               ['touch', 61, 120, 8], ['wait', 60], ['shot', 'mods-page'],
               ['touch', 192, 28, 8], ['wait', 60], ['shot', 'clock-speed-off']], open(script, 'w'))
    sav = play_export(rom, 'mods-page', ['--city'], script)
    shots = sorted(glob.glob(os.path.join(KIT, 'verify', 'evidence', '*-play')))[-1]
    for n in ('options', 'mods-page', 'clock-speed-off'):
        shutil.copy(os.path.join(shots, 'play_%s.png' % n), os.path.join(OUT, 'mods-page-%s.png' % n))
    on = '0x%08X:%d' % (CODE_BASE + 32 + 28, TABLE_ROW + 1)
    r = ram(rom, 1, on, '0x02113B60:2', start=['--state', os.path.join(OUT, 'mods-page.dst')])
    after = ram(rom, 1700, on, '0x02113B60:2', start=['--sav', sav])       # power-off, title screen
    ok = (r[on][0] == 1 and r[on][TABLE_ROW] == 0 and r['0x02113B60:2'] == b'\x03\x00'
          and after[on][TABLE_ROW] == 0 and after['0x02113B60:2'] == b'\x03\x00')
    return ok, 'after tapping Options > Mods > clock-speed: npc-visit on=%d, clock-speed on=%d, clock table %s; ' \
        'after power-off: clock-speed on=%d, table %s; screenshots build/proofs/mods-page-*.png' % (
            r[on][0], r[on][TABLE_ROW], r['0x02113B60:2'].hex(), after[on][TABLE_ROW], after['0x02113B60:2'].hex())


# ---------------------------------------------------------------- Phase 5: NPC Life

NPCL_MAGIC = 0x4C43504E          # 'NPCL': mods/npc-life/code/main.c
FOOD_KINDS = 1                   # places.json "food"
KRIS = 45


def npc_life_rom(name, extra=()):
    return build(name, [os.path.join(KIT, 'mods', 'npc-life')] + list(extra))[0]


def sim_plans(region, sim_addr):
    """The live timetables in RAM (sim_t: 36 pointers to the original timetables, then plan[36][168])."""
    so = sim_addr - CODE_BASE + 4 * 36
    return [region[so + 168 * c:so + 168 * (c + 1)] for c in range(36)]


def npcl(region):
    i = region.find(struct.pack('<I', NPCL_MAGIC))
    if i < 0:
        raise RuntimeError('NPC Life state not found')
    return dict(zip('magic attached plans minutes week visits sim'.split(), struct.unpack_from('<7I', region, i)))


def misplaced(plans, tables):
    """(person, slot) where the live timetable differs from the original one in an hour the original
    game does not have them out of town: there they would go missing."""
    return [(c, k) for c in range(36) if tables[c] for k in range(168)
            if tables[c][k] != 82 and plans[c][k] != tables[c][k]]


def orig_timetables():
    import ndspy.rom
    a9 = ndspy.rom.NintendoDSRom.fromFile(os.path.join(PROJ, 'base.nds')).arm9
    out = []
    for c in range(36):
        p = struct.unpack_from('<I', a9, 0x020E4FD8 + 4 * c - 0x02000000)[0]
        out.append(a9[p - 0x02000000:p - 0x02000000 + 168] if p else None)
    return out


def snapshots(rom, start_save, steps, every, ranges, pokes=(), goto=None, pokes_at=None):
    """One emulator run from a save's city state: RAM ranges every `every` frames.
    goto = an area to load first (through the game's own loader, after the pokes);
    pokes_at = {k: [pokes]}: written just before the wait that leads to snapshot k."""
    sys.path.insert(0, os.path.join(KIT, 'verify'))
    import urbz_verify as V
    out = tempfile.mkdtemp(prefix='urbz-snaps-')
    script = []
    for k in range(steps):
        script += [['poke', p] for p in (pokes_at or {}).get(k, [])]
        script += [['wait', every], ['shot', 's%02d' % k]]
    job = {'rom': os.path.abspath(rom), 'out': out, 'tag': 'snap',
           'state': V.city_state(os.path.abspath(rom), None, start_save), 'script': script,
           'snap': list(ranges), 'poke': list(pokes)}
    if goto is not None:
        pts = json.load(open(V.AREAS_JSON))['areas'][goto]['entry_points']
        job['goto'] = (goto, pts[0]['id'] if pts else 0)
    res = V.run_child(job, timeout=3000)
    return [[open(f, 'rb').read() for f in files] for _, files in res['snaps']], out


def p_npc_life_days():
    """Three game days with NPC Life (fast clock: a game minute per tick): the live timetables keep everyone
    where the original game puts them, out-of-town daytime hours become visits, and the routines follow
    the game's week."""
    rom = npc_life_rom('npc-life-days', [os.path.join(TESTS, 'mods', 'fast-clock')])
    snaps, _ = snapshots(rom, 'lobby', 12, 750, ['0x%08X:0x8000' % CODE_BASE, '0x0214112C:6'])
    tables = orig_timetables()
    first, last = npcl(snaps[0][0]), npcl(snaps[-1][0])
    bad = [misplaced(sim_plans(r, first['sim']), tables) for r, _ in snaps]
    plans = sim_plans(snaps[-1][0], first['sim'])
    visits = sum(1 for c in range(36) if tables[c] for k in range(168)
                 if tables[c][k] == 82 and plans[c][k] != 82)
    day0, day1 = struct.unpack_from('<h', snaps[0][1])[0], struct.unpack_from('<h', snaps[-1][1])[0]
    ok = (not any(bad) and visits > 20 and day1 - day0 >= 2 and last['minutes'] >= 2 * 1440
          and last['week'] == day1 // 7)
    return ok, ('%d game minutes followed (day %d -> %d, week %d); people away from where the game puts them: '
                '%d; out-of-town hours turned into visits this week: %d') % (
        last['minutes'], day0, day1, last['week'], sum(len(b) for b in bad), visits)


def walkin_run(rom, pokes=()):
    """From the lobby (Kris's home) at 17:01 Monday: is Kris here at 17:00-18:00, and what the game reads."""
    snaps, out = snapshots(rom, 'lobby', 6, 600, [HEAP_SCAN, '0x0214112C:6', '0x02065924:4'], pokes=pokes)
    res = []
    for mem, clk, lit in snaps:
        res.append({'present': KRIS in people_in(mem), 'hour': clk[2], 'literal': struct.unpack('<I', lit)[0]})
    return res, out


def p_npc_life_stays():
    """Nobody goes missing: at 18:00 Monday the game has Kris on the roof (70), and with NPC Life her live
    timetable says the roof too, so she never turns up in the lobby (her home)."""
    rom = npc_life_rom('npc-life-stays')
    reg = '0x%08X:0x8000' % CODE_BASE
    mem = ram(rom, 1, reg, start=['--from', 'lobby'])[reg]
    live = sim_plans(mem, npcl(mem)['sim'])[KRIS - 31][18 * 7 + 0]
    usual = orig_timetables()[KRIS - 31][18 * 7 + 0]
    res, _ = walkin_run(rom)
    ok = usual == 70 and live == 70 and not any(r['present'] for r in res)
    return ok, 'Kris at 18:00 Monday: the game says area %d, NPC Life says %d; in the lobby: %s' % (
        usual, live, [r['present'] for r in res])


PHOEBE = 54


def p_npc_life_visit():
    """A living city: in an hour the original game has someone out of town, their routine takes them to a
    place they know (a meal, a club, a park), and the game walks them in there. The visit is read from the
    live timetables in RAM; the clock is set to just before it and that area is loaded."""
    rom = npc_life_rom('npc-life-visit')
    reg = '0x%08X:0x8000' % CODE_BASE
    mem = ram(rom, 1, reg, '0x0214112C:6', start=['--from', 'lobby'])
    st = npcl(mem[reg])
    plans, tables = sim_plans(mem[reg], st['sim']), orig_timetables()
    today = struct.unpack_from('<h', mem['0x0214112C:6'])[0]
    visit = next(((c, h, wd, plans[c][h * 7 + wd]) for wd in range(7) for h in range(8, 23) for c in range(36)
                  if tables[c] and tables[c][h * 7 + wd] == 82 and plans[c][h * 7 + wd] != 82
                  and plans[c][(h - 1) * 7 + wd] != plans[c][h * 7 + wd]), None)
    if not visit:
        return False, 'no daytime visit planned this week'
    c, h, wd, area = visit
    day = today // 7 * 7 + wd                                           # that weekday, same week
    _, core = find_magic(rom, 1, CORE_MAGIC, 8)
    pokes = ['0x0214112C=%s%02x3a' % (struct.pack('<h', day).hex(), h - 1),   # the game clock: that day, hh-1:58
             '0x%08X=00000000' % (core + 36)]                           # core: resync minutes
    snaps, out = snapshots(rom, 'lobby', 4, 450, [HEAP_SCAN, '0x0214112C:6'], pokes=pokes, goto=area)
    shot = sorted(glob.glob(os.path.join(out, '*.png')))
    if shot:
        shutil.copy(shot[-1], os.path.join(OUT, 'npc-life-visit.png'))
    present = [31 + c in people_in(m) for m, _ in snaps]
    hours = [clk[2] for _, clk in snaps]
    ok = present[-1] and hours[-1] == h
    return ok, ('person %d at %02d:00 (day %d): the original game has them out of town; NPC Life sends them to '
                'area %d; there, present: %s (hours %s)') % (31 + c, h, day, area, present, hours)


OBJP_MAGIC = 0x504A424F


def p_npc_use_object():
    """People can use the area's objects with the game's own code (Phase 6 groundwork): in Slice O' Life Pizza
    (51) at 17:05, Phoebe (54) is sent to a chair (activity 56) by `npc_goto_object`: she walks there,
    sits down (state 0x11, sitting animation 0x6B) and stays seated, and when we abort the use (stop byte 3) she stands up
    and goes back to wandering (state 0x23)."""
    rom = build('npc-use-object', ['obj-probe'])[0]
    _, probe = find_magic(rom, 1, OBJP_MAGIC, 4)
    pokes = ['0x0214112E=1105',                                          # 17:05: Phoebe's timetable says 51
             '0x%08X=%s' % (probe + 16, struct.pack('<III', PHOEBE, 400, 56).hex()),   # who, ticks, activity
             '0x%08X=04000000' % (probe + 4)]                            # request 4: the whole sequence
    snaps, out = snapshots(rom, 'lobby', 4, 300, ['0x%08X:0x500' % probe], pokes=pokes, goto=51)
    mem = snaps[-1][0]
    n = struct.unpack_from('<I', mem, 1060)[0]
    log = [struct.unpack_from('<IBBBB', mem, 1064 + 8 * k) for k in range(min(n, 16))]
    steps = {st: (t, state, act, anim) for t, st, state, act, anim in reversed(log) if st}
    shot = sorted(glob.glob(os.path.join(out, '*.png')))
    if len(shot) > 1:
        shutil.copy(shot[1], os.path.join(OUT, 'npc-use-object.png'))
    t2, t4 = steps.get(2, (0,))[0], steps.get(4, (1 << 30,))[0]
    sat = any(st == 0 and state == 0x11 and anim == 0x6B and t2 <= t <= t4 for t, st, state, act, anim in log)
    ok = (struct.unpack_from('<i', mem, 28)[0] == 1 and 2 in steps and sat and 5 in steps
          and steps[5][1] == 0x23)
    fmt = lambda k: ('tick %d state %x action %x anim %x' % steps[k]) if k in steps else 'never'
    return ok, ('sent to a chair: %d; started using it: %s; sitting animation 0x6B: %s; after the abort: '
                '%s; build/proofs/npc-use-object.png') % (struct.unpack_from('<i', mem, 28)[0], fmt(2), sat, fmt(5))


NACT_MAGIC = 0x5443414E
USE_SET = {33, 39, 41, 45, 52, 53, 54, 58}       # the people with the game's object animations (sit 0x6B)


def people_states(mem, base=0x0214DE20):
    """{character id: (state, action, anim)} of the people (entity type 7) in a RAM dump."""
    out = {}
    for k in range(0, len(mem) - 0x148, 4):
        t, i = struct.unpack_from('<HH', mem, k + 8)
        if t == 7 and 31 <= i < 80 and struct.unpack_from('<H', mem, k + 0x146)[0] == i:
            out[i] = (mem[k + 0x104], mem[k + 0x105], mem[k + 0xC7])
    return out


def act_run(name, pokes_at=None, steps=12):
    """NPC Life in the Slice O' Life Pizza (51) at 17:05 (Phoebe, Gramma Hattie and 33 there): people's states and the
    behaviour layer's counters every 150 frames."""
    rom = npc_life_rom(name)
    _, nact = find_magic(rom, 1, NACT_MAGIC, 4)
    snaps, out = snapshots(rom, 'lobby', steps, 150, [HEAP_SCAN, '0x%08X:0x40' % nact],
                           pokes=['0x0214112E=1105'], goto=51, pokes_at=pokes_at)
    res = []
    for mem, c in snaps:
        res.append({'people': people_states(mem), 'sent': struct.unpack_from('<I', c, 4)[0],
                    'aborted': struct.unpack_from('<I', c, 12)[0], 'chats': struct.unpack_from('<I', c, 52)[0]})
    return rom, res, out


def p_npc_act():
    """Visible actions (NPC Life, Phase 6): in Slice O' Life Pizza, people act out what they're doing with the
    game's own objects and animations: someone with the object animations sits on a chair (state 0x11,
    anim 0x6B), and two others chat: they face each other and take turns gesturing (our action 0x30 with
    gestures 0x87/0x78/0xDB). Nobody without the sit animation is sent to a chair."""
    rom, res, out = act_run('npc-act')
    sits = sorted({i for r in res for i, (st, ac, an) in r['people'].items() if st == 0x11 and an == 0x6B})
    wrong = sorted({i for r in res for i, (st, ac, an) in r['people'].items() if st in (0x11, 0x26)} - USE_SET)
    talk = [r for r in res if sum(1 for st, ac, an in r['people'].values() if st == 0x23 and ac == 0x30) >= 2]
    gest = sorted({an for r in res for st, ac, an in r['people'].values() if ac == 0x30 and an in (0x87, 0x78, 0xDB)})
    shots = sorted(glob.glob(os.path.join(out, '*.png')))
    if len(shots) > 4:
        shutil.copy(shots[4], os.path.join(OUT, 'npc-act.png'))
    ok = bool(sits) and not wrong and bool(talk) and bool(gest) and res[-1]['chats'] >= 1
    return ok, ('sitting (anim 0x6B): %s; sent to objects without the animations: %s; snapshots with two people '
                'chatting: %d, gestures seen: %s; actions started: %d; build/proofs/npc-act.png') % (
        sits, wrong or 'none', len(talk), ['%02x' % g for g in gest], res[-1]['sent'])


def routine_day(cid, week=0, wd=0):
    """[(minute of the day, area, activity name)] from the routines on the PC (run_test.py day)."""
    out = run([sys.executable, os.path.join(KIT, 'mods', 'npc-life', 'sim', 'run_test.py'), 'day', str(cid),
               str(week), str(wd)])
    rows = []
    for line in out.splitlines()[1:]:
        hm, _, area, act = line.split(None, 3)
        rows.append((int(hm[:2]) * 60 + int(hm[3:]), int(area), act))
    return rows


def p_npc_act_eat():
    """Routines drive object use: Kris's routine has breakfast at home (the Tower Lobby, 66) on Monday of
    week 0 (time from the routines on the PC); at that time NPC Life sends her to the vending machine and
    she eats (state 0x11, animation 0x41: only she has it)."""
    eat = next(((m, a) for m, a, act in routine_day(KRIS) if act == 'eating' and a == 66), None)
    if not eat:
        return False, 'no breakfast at home in Kris\'s routine'
    m = eat[0] - 4                                                      # a few minutes before
    rom = npc_life_rom('npc-act-eat')
    _, core = find_magic(rom, 1, CORE_MAGIC, 8)
    pokes = ['0x0214112E=%02x%02x' % (m // 60, m % 60), '0x%08X=00000000' % (core + 36)]
    snaps, out = snapshots(rom, 'lobby', 16, 150, [HEAP_SCAN], pokes=pokes)
    seen = [people_states(mem).get(KRIS) for mem, in snaps]
    ate = any(s and s[0] == 0x11 and s[2] == 0x41 for s in seen)
    shot = sorted(glob.glob(os.path.join(out, '*.png')))
    if ate:
        k = next(i for i, s in enumerate(seen) if s and s[0] == 0x11 and s[2] == 0x41)
        shutil.copy(shot[k], os.path.join(OUT, 'npc-act-eat.png'))
    return ate, 'breakfast at %02d:%02d in the lobby; Kris (state, action, animation) every 150 frames: %s' % (
        eat[0] // 60, eat[0] % 60, ['%x/%x/%x' % s if s else '-' for s in seen])


def p_npc_act_release():
    """Switching NPC Life off in the game releases everyone acting: nobody stays seated or chatting, and
    they go back to the game's own wandering (state 0x23, actions 7/0x19)."""
    rom = npc_life_rom('npc-act-release')
    off = core_request(rom, 0, 0)
    rom, res, out = act_run('npc-act-release', pokes_at={3: [off]}, steps=6)
    before = res[2]['people']
    acting_before = sorted(i for i, (st, ac, an) in before.items() if st in (0x11, 0x26) or ac == 0x30)
    after = res[-1]['people']
    still = sorted(i for i, (st, ac, an) in after.items() if st in (0x11, 0x26) or ac == 0x30)
    ok = bool(acting_before) and not still and all(st == 0x23 for st, ac, an in after.values())
    return ok, 'acting before the switch: %s; acting 450 frames after it: %s; states after: %s' % (
        acting_before, still or 'nobody', {i: '%x/%x' % (st, ac) for i, (st, ac, an) in after.items()})


def p_npc_body_prototype():
    """Prototype (mod npc-body-proto, off by default): switched on, Kris (45) is drawn with the player's
    female body in her own colours: layered drawing (+0xC5 bit 0x40), the player's body/clothes/hair tables
    in her slots, two palette rows of her own (9-15); switched off again, she gets her own sprite back."""
    rom = build('npc-body-prototype', [os.path.join(TESTS, 'mods', 'npc-body-proto')])[0]
    on, off = core_request(rom, 0, 1), core_request(rom, 0, 0)
    snaps, out = snapshots(rom, 'lobby', 6, 150, [HEAP_SCAN], pokes=['0x0214112E=1205', on], goto=70,
                           pokes_at={4: [off]})
    def kris(mem):
        for k in range(0, len(mem) - 0x148, 4):
            if struct.unpack_from('<HH', mem, k + 8) == (7, KRIS) and struct.unpack_from('<H', mem, k + 0x146)[0] == KRIS:
                e = mem[k:k + 0x148]
                return {'layered': bool(e[0xC5] & 0x40), 'tables': [struct.unpack_from('<I', e, 0xD4 + 12 * j)[0] for j in range(3)],
                        'rows': (e[0xCD], e[0xD9])}
        return None
    states = [kris(m[0]) for m in snaps]
    female = [0x0211E32C, 0x0211DD0C]                      # the player's female body and clothes tables
    during, after = states[3], states[-1]
    ok = (during and during['layered'] and during['tables'][:2] == female and min(during['rows']) >= 9
          and after and not after['layered'] and after['tables'][1:] == [0, 0])
    return ok, 'switched on: %s; switched off: %s (a picture needs melonDS: docs/systems.md)' % (during, after)


def p_npc_anims():
    """New animations for a townsperson (urbz_anims.py): Gramma Hattie (43) has no sit animation; a
    placeholder one (Kris's sit frames in Hattie's colours, made at test time) is built into new assets
    (the game's asset tables are moved to fit them). Sent to a chair, she sits with it: state 0x11,
    animation 0x6B, and the game has loaded the new sheet."""
    work = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'anim-proof')
    run([sys.executable, os.path.join(KIT, 'urbz_anims.py'), 'placeholder', work, '43', 'sit'])
    run([sys.executable, os.path.join(KIT, 'urbz_anims.py'), 'build', work])
    run([sys.executable, os.path.join(KIT, 'urbz_patch.py'), 'build', '--dir', os.path.join(work, 'code')])
    rom = build('npc-anims', ['obj-probe', work])[0]
    _, probe = find_magic(rom, 1, OBJP_MAGIC, 4)
    pokes = ['0x0214112E=1105',                                          # 17:05: Hattie is in area 51
             '0x%08X=%s' % (probe + 16, struct.pack('<III', 43, 400, 56).hex()),
             '0x%08X=04000000' % (probe + 4)]
    first_new = len(json.load(open(os.path.join(PROJ, 'manifest.json')))['entries']) + 1
    ptrs = struct.unpack('<I', ram(rom, 1, '0x02032CA0:4', start=['--from', 'lobby'])['0x02032CA0:4'])[0]
    table = '0x%08X:%d' % (ptrs + 4 * (first_new - 1), 4 * 7)             # the new assets' load slots
    snaps, out = snapshots(rom, 'lobby', 3, 300, ['0x%08X:0x500' % probe, table], pokes=pokes, goto=51)
    mem, loaded = snaps[1]
    n = struct.unpack_from('<I', mem, 1060)[0]
    log = [struct.unpack_from('<IBBBB', mem, 1064 + 8 * k) for k in range(min(n, 16))]
    sat = any(state == 0x11 and anim == 0x6B for t, st, state, act, anim in log)
    gfx = [first_new + k for k in range(7) if struct.unpack_from('<I', loaded, 4 * k)[0]]
    shot = sorted(glob.glob(os.path.join(out, '*.png')))
    if len(shot) > 1:
        shutil.copy(shot[1], os.path.join(OUT, 'npc-anims.png'))
    ok = ptrs != 0x02130654 and sat and bool(gfx)
    return ok, ('asset tables moved: %s; Hattie on the chair with animation 0x6B: %s; new assets the game loaded: '
                '%s (new ones start at %d); build/proofs/npc-anims.png') % (ptrs != 0x02130654, sat, gfx, first_new)


def p_npc_life_off():
    """Switched off in the game: the timetable pointers go back and people follow their usual timetable."""
    rom = npc_life_rom('npc-life-off')
    res, _ = walkin_run(rom, pokes=[core_request(rom, 0, 0)])
    lits = set(r['literal'] for r in res)
    ok = lits == {0x020E4FD8} and not any(r['present'] for r in res)
    return ok, 'switched off at 17:01: schedule pointer %s (original 020e4fd8); Kris in the lobby: %s' % (
        ', '.join('%08x' % x for x in lits), [r['present'] for r in res])


def p_npc_life_reload():
    """Nothing to save: after saving, power-off and Load-an-Urb, the live timetables are exactly the same
    (each week's plan comes from the game's week number), and the save carries no NPC Life data."""
    import urbz_save
    from urbz_code import name_hash
    rom = npc_life_rom('npc-life-reload')
    reg = '0x%08X:0x8000' % CODE_BASE
    before = ram(rom, 1, reg, start=['--from', 'lobby'])[reg]
    sav = play_export(rom, 'npc-life-reload', ['--from', 'lobby'], SAVEGAME)
    buf = open(sav, 'rb').read()
    blk = dict(urbz_save.mod_block(buf[0x20:0x20 + urbz_save.SLOT_SIZE]) or [])
    after = ram(rom, 30, reg, start=['--sav', sav], script=LOADGAME)[reg]
    a, b = npcl(before), npcl(after)
    same = sim_plans(before, a['sim']) == sim_plans(after, b['sim'])
    ok = same and name_hash('npc-life') not in blk and a['week'] == b['week']
    return ok, 'week %d before, %d after loading; live timetables identical: %s; NPC Life data in the save: %s' % (
        a['week'], b['week'], same, name_hash('npc-life') in blk)


def p_npc_life_page():
    """The NPC Life info page, opened with real touches: Options > Mods > npc-life: info."""
    rom = npc_life_rom('npc-life-page')
    script = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'page.json')
    json.dump([['wait', 30], ['touch', 128, 180, 8], ['wait', 60], ['touch', 61, 120, 8], ['wait', 60],
               ['shot', 'mods'], ['touch', 192, 28, 8], ['wait', 60], ['shot', 'info']], open(script, 'w'))
    r = ram(rom, 1, '0x02144CEC:4', start=['--from', 'lobby'], script=script)
    ui = struct.unpack('<I', r['0x02144CEC:4'])[0]
    menu = ram(rom, 1, '0x%08X:12' % ui, start=['--from', 'lobby'], script=script)['0x%08X:12' % ui]
    shots = sorted(glob.glob(os.path.join(KIT, 'verify', 'evidence', '*-ram')))[-1]
    for n in ('mods', 'info'):
        shutil.copy(os.path.join(shots, 'ram_%s.png' % n), os.path.join(OUT, 'npc-life-page-%s.png' % n))
    open_menu = struct.unpack_from('<I', menu, 8)[0]
    return open_menu == 6, 'open menu after the taps: %d (6 = a mod\'s info page); screenshots ' \
        'build/proofs/npc-life-page-*.png' % open_menu


def p_melonds():
    """The NPC Life build in melonDS (stricter than DeSmuME): boots, loads the city save, and the
    Mods page matches DeSmuME's. Skipped (FAIL with a message) if melonDS isn't set up."""
    sys.path.insert(0, os.path.join(KIT, 'verify'))
    import urbz_melon as M
    if not M.available():
        return False, 'melonDS not set up: run verify/melonds_setup.sh (Linux), then rerun this proof'
    rom = npc_life_rom('melonds', [os.path.join(TESTS, 'mods', 'clock-speed')])
    taps = [['wait', 120], ['touch', 128, 180, 8], ['wait', 60], ['touch', 61, 120, 8], ['wait', 90],
            ['shot', 'mods']]
    load = [['wait', 600]] + [['press', 'START'], ['wait', 300]] * 4 + [['wait', 300], ['press', 'DOWN', 10],
            ['wait', 60], ['press', 'A', 10], ['wait', 150], ['touch', 220, 117, 15], ['wait', 600],
            ['shot', 'city']]
    boot = dict(M.run(rom, M.BOOT_SCRIPT))
    _, spread = M.screen_stats(boot['boot-20s'])
    shots = dict(M.run(rom, load + taps, sav=os.path.join(KIT, 'verify', 'saves', 'city.sav')))
    script = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'mods.json')
    json.dump(taps, open(script, 'w'))
    run(VERIFY + ['play', rom, '--city', '--script', script, '--save', os.path.join(OUT, 'melonds-ref.dst')])
    ref = os.path.join(sorted(glob.glob(os.path.join(KIT, 'verify', 'evidence', '*-play')))[-1], 'play_mods.png')
    from PIL import Image
    a = Image.open(shots['mods']).convert('RGB').crop((0, 192, 256, 384))
    b = Image.open(ref).convert('RGB').crop((0, 192, 256, 384))
    same = sum(1 for p, q in zip(a.tobytes()[::3], b.tobytes()[::3]) if abs(p - q) < 24) / (256 * 192)
    for n, f in (('boot', boot['boot-20s']), ('mods', shots['mods'])):
        shutil.copy(f, os.path.join(OUT, 'melonds-%s.png' % n))
    ok = spread > 10 and same > 0.95
    return ok, ('melonDS: top screen after 20 s has detail %.0f (0 = blank); after loading the city save and '
                'tapping Options > Mods, the bottom screen matches DeSmuME %.1f%%; build/proofs/melonds-*.png') % (
        spread, 100 * same)


def p_save_edit():
    """Money and a need edited in a save made later in the game (needs are 8.8 fixed point)."""
    import urbz_save
    src = os.path.join(KIT, 'verify', 'saves', 'lobby.sav')
    dst = os.path.join(OUT, 'edited.sav')
    os.makedirs(OUT, exist_ok=True)
    run([sys.executable, os.path.join(KIT, 'urbz_save.py'), 'set', src, dst, '--money', '4321',
         '--motive', 'hunger=12.5'])
    rom, _, _ = build('vanilla', [])

    def load(sav):
        cmd = VERIFY + ['ram', rom, '--sav', sav, '--script',
                        os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'),
                        '--read', '0x02141124:4', '--read', '0x02141204:8']
        out = {l.split(' = ')[0]: bytes.fromhex(l.split(' = ')[1]) for l in run(cmd).splitlines() if ' = ' in l}
        return (struct.unpack('<i', out['0x02141124:4'])[0], s824(out['0x02141204:8'], 0),
                s824(out['0x02141204:8'], 1))
    # Needs keep decaying while the loaded game runs, so compare with the unedited save loaded the same way.
    m0, h0, y0 = load(src)
    money, hunger, hygiene = load(dst)
    saved = struct.unpack_from('<H', open(src, 'rb').read(), 0x20 + urbz_save.F_MOTIVES)[0] / 256
    want = h0 + 12.5 - saved
    ok = money == 4321 and abs(hunger - want) < 0.1 and abs(hygiene - y0) < 0.01
    return ok, 'edited save: money %d (expect 4321); hunger %.2f (expect %.2f = 12.5 minus the same decay); ' \
        'hygiene %.2f (untouched: %.2f)' % (money, hunger, want, hygiene, y0)


def p_lobby_goto():
    """verify/saves/lobby.sav (first goal done, played without pokes) loads in the Tower Lobby
    with Kris at 30; --goto then loads a street through the game's own area loader."""
    rom, _, _ = build('vanilla', [])
    a = ram(rom, 30, '0x02141FEC:4', '0x0214118C:1', '0x02122794:1', '0x02141940:2', start=['--from', 'lobby'])
    b = ram(rom, 30, '0x02141FEC:4', start=['--from', 'lobby', '--goto', '4'])
    area, kris, var = struct.unpack('<I', a['0x02141FEC:4'])[0], a['0x0214118C:1'][0], a['0x02122794:1'][0]
    street = struct.unpack('<I', b['0x02141FEC:4'])[0]
    goal = a['0x02141940:2']
    return (area, kris, var, street) == (66, 30, 1, 4) and goal == b'\x01\x01', \
        'lobby save: area %d (expect 66), Kris %d (expect 30), variant %d (expect 1), first goal active/complete ' \
        '%s (expect 0101); --goto 4: area %d' % (area, kris, var, goal.hex(), street)


def p_text_accents():
    mod = new_mod('accents')
    os.makedirs(os.path.join(mod, 'text'))
    line = 'café, niño, über, ¿qué? ¡Sí!'
    open(os.path.join(mod, 'text', 'strings.tsv'), 'w', encoding='utf-8').write('ID\ttext\n27\t%s\n' % line)
    rom, log, _ = build('accents', [mod])
    import ndspy.rom, urbz_text
    r = ndspy.rom.NintendoDSRom.fromFile(rom)
    rb = r.files[0]
    o = [struct.unpack_from('<I', rb, 4 * i)[0] for i in (54, 55)]
    s = urbz_text.decode_bank(rb[o[0]:o[1]])[27]
    return urbz_text.escape(s) == line, 'string 27 in the built ROM: %s' % urbz_text.escape(s)


def p_grow_neighbour_pair():
    from urbz_sprites import layout_offsets
    mod = new_mod('grow9195')
    os.makedirs(os.path.join(mod, 'unpacked', '09195'))
    size = os.path.getsize(os.path.join(PROJ, 'unpacked', '09195', '000174.bin'))
    random.seed(3)
    open(os.path.join(mod, 'unpacked', '09195', '000174.bin'), 'wb').write(
        bytes(random.randrange(256) for _ in range(size)))
    rom, log, _ = build('grow9195', [mod])
    import ndspy.rom
    rb = ndspy.rom.NintendoDSRom.fromFile(rom).files[0]
    o = [struct.unpack_from('<I', rb, 4 * i)[0] for i in (9195, 9196, 9197)]
    g, l = rb[o[0]:o[1]], rb[o[1]:o[2]]
    offs = [x for _, x in layout_offsets(l)]
    ok = all((struct.unpack_from('<I', g, x)[0] & 0x70) in (0x60, 0x10, 0x00) for x in offs)
    return ok and 're-pointed' in log, 'layout 09196 points at chunk headers after growth: %s' % ok


def p_catalog_price():
    rom, _, _ = build('cheap-shower', ['cheap-shower'])
    v = struct.unpack('<I', ram(rom, 1, '0x020E9B10:4')['0x020E9B10:4'])[0]
    return v == 99, 'object 200 price in RAM: %d (expect 99; shown in the Catalog as $99)' % v


def p_png_sheets_roundtrip():
    """Unchanged PNGs (screen, simple + composite sprites, font sheets, palette) change nothing;
    one edited glyph rebuilds a font; one edited swatch changes the palette."""
    import urbz_png, urbz_font, urbz_palette
    from PIL import Image
    mod = new_mod('sheets')
    for idx in (10747, 1448, 5650):                       # EA logo screen, composite, simple
        out = os.path.join(mod, 'png', '%05d' % idx)
        urbz_png.export_asset(idx, out)
    os.makedirs(os.path.join(mod, 'font'))
    for slot, asset, base in urbz_font.SLOTS:
        nm = urbz_font._name(slot, asset)
        urbz_font.export_font(open(os.path.join(PROJ, 'assets', '%05d.bin' % asset), 'rb').read(),
                              os.path.join(mod, 'font', nm + '.png'), os.path.join(mod, 'font', nm + '.json'))
    os.makedirs(os.path.join(mod, 'palette'))
    urbz_palette.export_palette(open(os.path.join(PROJ, 'assets', '09160.bin'), 'rb').read(),
                                os.path.join(mod, 'palette', '09160.png'))
    _, _, sha = build('sheets-unchanged', [mod])
    m = json.load(open(os.path.join(PROJ, 'manifest.json')))
    same = sha == m['source_sha1']
    p = os.path.join(mod, 'palette', '09160.png')
    im = Image.open(p).convert('RGB'); im.putpixel((24, 8), (255, 0, 255)); im.save(p)
    f = os.path.join(mod, 'font', urbz_font._name(0, 11547) + '.png')
    j = json.load(open(f[:-4] + '.json')); cw, ch = j['cell']
    im = Image.open(f); r, k = divmod(ord('o') - 0x20, 16); im.putpixel((k * cw, r * ch + 1), 1); im.save(f)
    _, log, _ = build('sheets-edited', [mod])
    ok = same and '1 font(s) rebuilt' in log and '1 palette(s) changed' in log
    return ok, 'unchanged sheets identical: %s; edits: %s' % (same, log.strip().split('\n')[-1][-120:])


def p_object_row():
    """Street objects take their OBJ palette row from a per-kind table (record type 16: 0x020C2828[variant])."""
    rom, _, _ = build('vanilla', [])

    def rows(*pokes):
        b = ram(rom, 30, '0x0215E000:0xC000', pokes=pokes, start=['--from', 'lobby', '--goto', '4'])['0x0215E000:0xC000']
        return sorted((struct.unpack_from('<H', b, i + 0xA)[0], (struct.unpack_from('<I', b, i + 0x90)[0] >> 12) & 15)
                      for i in range(0, len(b) - 0x148, 4) if struct.unpack_from('<I', b, i + 0x4C)[0] == 0x0201DC50)
    a = rows()
    b = rows('0x020C2828=' + '08000000' * 5)
    want = [(v, (7, 5, 3, 7, 2)[v]) for v, _ in a]
    ok = bool(a) and a == want and all(r == 8 for _, r in b) and len(a) == len(b)
    return ok, 'Glasstown type-16 objects (variant, row): %s; with the table set to 8: %s' % (a, b)


def critters(mem, base=0x0214DE20):
    """(address, kind) of the critters (entity type 9: chickens and co.) in a RAM dump that starts at base."""
    return [(base + k, struct.unpack_from('<H', mem, k + 10)[0]) for k in range(0, len(mem) - 0x148, 4)
            if struct.unpack_from('<HH', mem, k + 8)[0] == 9 and struct.unpack_from('<H', mem, k + 10)[0] < 16]


def p_pet_place():
    """A pet you carry home: a Chicken (object 225) written into Pockets (item list 23) is placed in the
    starting home (area 68) with real inputs: Pockets, double-tap it, close the menu, walk 3 steps, A.
    It leaves Pockets and becomes a walking chicken (critter kind 1). Without it, no chicken appears."""
    rom = build('vanilla', [])[0]
    s = [["wait", 60], ["touch", 236, 166, 8], ["wait", 90], ["touch", 84, 75, 8], ["wait", 90],
         ["touch", 164, 36, 8], ["wait", 30], ["touch", 164, 36, 8], ["wait", 90], ["touch", 236, 166, 8], ["wait", 60]]
    s += [["press", "DOWN", 12], ["wait", 20]] * 3 + [["press", "A", 6], ["wait", 400]]
    script = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'place.json')
    json.dump(s, open(script, 'w'))
    reads = ('0x02141338:4', HEAP_SCAN)
    res = {}
    for name, pokes in (('with', ['0x02141338=02', '0x02141892=e1000000']), ('without', [])):
        r = ram(rom, 10, *reads, pokes=pokes, script=script, start=['--city', '--goto', '68'])
        res[name] = (r['0x02141338:4'][0], [k for _, k in critters(r[HEAP_SCAN])])
    ok = res['with'][0] == 1 and 1 in res['with'][1] and 1 not in res['without'][1]
    return ok, 'Pockets count after placing: %d (was 2); critter kinds with: %s, without: %s' % (
        res['with'][0], res['with'][1], res['without'][1])


def place_script(extra=()):
    """Pockets, double-tap the 5th item, close the menu, 3 steps down, A (the starting home, area 68)."""
    s = [["wait", 60], ["touch", 236, 166, 8], ["wait", 90], ["touch", 84, 75, 8], ["wait", 90],
         ["touch", 164, 36, 8], ["wait", 30], ["touch", 164, 36, 8], ["wait", 90], ["touch", 236, 166, 8], ["wait", 60]]
    s += [["press", "DOWN", 12], ["wait", 20]] * 3 + [["press", "A", 6], ["wait", 100]] + list(extra)
    path = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'place.json')
    json.dump(s, open(path, 'w'))
    return path


def pocket_pokes(obj):
    return ['0x02141338=02', '0x02141892=%s' % struct.pack('<HH', obj, 0).hex()]


def p_objects_new():
    """New objects (urbz_objects.py): tests/mods/obj-new adds 386 "Test Kitten" and 389 "Test Puppy"
    (copies of the Chicken) and 390 "Test Chair" (a copy of the Country Class Chair, 136), with new text.
    The seven object tables move into the code region; the catalog loops and shop count follow. In the
    Recreation catalog the new objects are listed with their names (build/proofs/objects-new.png); the
    chair put in Pockets is placed at home (the place check asks about object 136, through code/objects)
    and drawn: an object entity with id 390 and a sprite (+0x8C), like the original chair's."""
    rom = build('objects-new', ['obj-new'])[0]
    cat = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'cat.json')
    json.dump([["wait", 60], ["touch", 56, 128, 8], ["wait", 120], ["touch", 130, 128, 8], ["wait", 120],
               ["touch", 196, 51, 8], ["wait", 40], ["touch", 196, 51, 8], ["wait", 40], ["touch", 98, 51, 8],
               ["wait", 60], ["shot", "catalog"]], open(cat, 'w'))
    cmd = VERIFY + ['ram', rom, '--city', '--frames', '1', '--script', cat, '--read', '0x02014130:4',
                    '--read', '0x0203C6AC:4']
    out = run(cmd)
    vals = dict(l.split(' = ') for l in out.splitlines() if ' = ' in l)
    text = struct.unpack('<I', bytes.fromhex(vals['0x02014130:4'].strip()))[0]
    count = struct.unpack('<I', bytes.fromhex(vals['0x0203C6AC:4'].strip()))[0]
    ev = out.strip().splitlines()[-1].split('evidence: ')[-1]
    shot = glob.glob(os.path.join(ev, '*catalog.png'))
    if shot:
        shutil.copy(shot[0], os.path.join(OUT, 'objects-new.png'))
    rows = ram(rom, 1, '0x%08X:0x28' % (text + 0x14 * 386))['0x%08X:0x28' % (text + 0x14 * 386)]
    r386 = struct.unpack_from('<5I', rows, 0)
    r = ram(rom, 10, '0x02141338:4', HEAP_SCAN, pokes=pocket_pokes(390), script=place_script(),
            start=['--city', '--goto', '68'])
    placed, heap = r['0x02141338:4'][0], r[HEAP_SCAN]
    chairs = [struct.unpack_from('<I', heap, k + 0x8C)[0] for k in range(0, len(heap) - 0x148, 4)
              if struct.unpack_from('<HH', heap, k + 8) == (5, 390) and struct.unpack_from('<H', heap, k + 0x146)[0] == 390]
    ok = (text >= CODE_BASE and count == 392 and r386[0] == 0xDD and r386[2] >= 8311 and placed == 1
          and len(chairs) == 1 and chairs[0] != 0)
    return ok, ('object text table at %08x (moved: %s), shop count %d; row 386: model %d, name string %d, page %d; '
                'chair 390 placed at home: Pockets %d (was 2), object entities with id 390: %d, sprite %s; '
                'build/proofs/objects-new.png') % (
        text, text >= CODE_BASE, count, r386[0], r386[2], r386[3], placed, len(chairs),
        ['%08x' % c for c in chairs])


def p_pets_data():
    """Pets as data (mods/pets: pets.json; urbz_pets.py + code/pets-kit): the Puppy (object 386, from the
    rooster) and the Kitten (389, from the chicken) get critter kinds 7 and 8. Each, placed at home, becomes
    a critter of its own kind; put in the game's pick-up state (state 0x12, action 0x0E), it goes back to
    Pockets as its own object."""
    rom = build('pets', [os.path.join(KIT, 'mods', 'pets')])[0]
    start, res, ok = ['--city', '--goto', '68'], [], True
    for obj, kind in ((386, 7), (389, 8)):
        r = ram(rom, 10, HEAP_SCAN, pokes=pocket_pokes(obj), script=place_script(), start=start)[HEAP_SCAN]
        mine = [a for a, k in critters(r) if k == kind]
        if not mine:
            res.append('%d: no kind-%d critter (kinds %s)' % (obj, kind, [k for _, k in critters(r)]))
            ok = False
            continue
        a = mine[0]
        script = place_script([["poke", "0x%08X=0000" % (a + 0x108)], ["poke", "0x%08X=120E" % (a + 0x104)],
                               ["wait", 60]])
        r2 = ram(rom, 10, HEAP_SCAN, '0x02141338:4', '0x0214188C:12', pokes=pocket_pokes(obj), script=script,
                 start=start)
        slot = struct.unpack_from('<H', r2['0x0214188C:12'], 6)[0]
        i = r2[HEAP_SCAN].find(struct.pack('<I', 0x43544550))
        spawned, picked, n = struct.unpack_from('<III', r2[HEAP_SCAN], i + 4)
        left = [k for _, k in critters(r2[HEAP_SCAN])]
        good = r2['0x02141338:4'][0] == 2 and slot == obj and kind not in left and (spawned, picked, n) == (1, 1, 2)
        ok = ok and good
        res.append('%d -> kind %d -> picked up: Pockets slot 2 = %d, kinds left %s, counters %s' % (
            obj, kind, slot, left, (spawned, picked, n)))
    return ok, '; '.join(res)


def p_mods_split():
    """Pets and new furniture are separate mods (mods/pets: pets.json, 386 and 389-429; mods/more-furniture: 430-511):
    each builds alone and both build together. With more-furniture alone, its armchair (430, a copy of
    the Country Class Chair) put in Pockets is placed at home and drawn; the Furniture catalog page at
    its end: build/proofs/mods-split.png."""
    pets, furn = os.path.join(KIT, 'mods', 'pets'), os.path.join(KIT, 'mods', 'more-furniture')
    reports = {}
    for name, mods in (('split-pets', [pets]), ('split-furniture', [furn]), ('split-both', [pets, furn])):
        log = build(name, mods)[1]
        reports[name] = [l for l in log.splitlines() if l.startswith('objects:')]
    want = {'split-pets': '(386, 389)', 'split-furniture': '(430, 431, 432)', 'split-both': '(386, 389, 430, 431, 432)'}
    builds_ok = all(r and want[n] in r[0] for n, r in reports.items())
    rom = os.path.join(OUT, 'split-furniture.nds')
    cat = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'cat.json')
    json.dump([["wait", 60], ["touch", 56, 128, 8], ["wait", 120], ["touch", 56, 128, 8], ["wait", 120]] +
              [["touch", 196, 51, 8], ["wait", 30]] * 9 + [["touch", 98, 51, 8], ["wait", 60], ["shot", "furniture"]], open(cat, 'w'))
    out = run(VERIFY + ['ram', rom, '--city', '--frames', '1', '--script', cat, '--read', '0x02141124:4'])
    ev = out.strip().splitlines()[-1].split('evidence: ')[-1]
    shot = glob.glob(os.path.join(ev, '*furniture.png'))
    if shot:
        shutil.copy(shot[0], os.path.join(OUT, 'mods-split.png'))
    r = ram(rom, 10, '0x02141338:4', HEAP_SCAN, pokes=pocket_pokes(430), script=place_script(),
            start=['--city', '--goto', '68'])
    placed, heap = r['0x02141338:4'][0], r[HEAP_SCAN]
    chairs = [struct.unpack_from('<I', heap, k + 0x8C)[0] for k in range(0, len(heap) - 0x148, 4)
              if struct.unpack_from('<HH', heap, k + 8) == (5, 430) and struct.unpack_from('<H', heap, k + 0x146)[0] == 430]
    ok = builds_ok and placed == 1 and len(chairs) == 1 and chairs[0] != 0
    return ok, ('builds: %s; more-furniture alone: armchair 430 placed (Pockets %d, was 2), entities %d, sprite %s; '
                'build/proofs/mods-split.png') % (
        '; '.join('%s %s' % (n, r[0][9:40] if r else 'FAILED') for n, r in reports.items()), placed, len(chairs),
        ['%08x' % c for c in chairs])


def p_pets_art(extra=(), name='pets-art'):
    """Pets with their own art (urbz_art.py + urbz_pets.py): a copy of mods/pets where the Kitten has
    placeholder art made at test time (the chicken's frames in orange, with a new palette), built together
    with an urbz_anims mod (Gramma Hattie's placeholder sit) so two mods add art at once. The Kitten's
    critter row points at new art files (numbers after the game's and the anims mod's) and its palette is
    a new file; placed at home it runs around as kind 8 (build/proofs/pets-art.png)."""
    work = tempfile.mkdtemp(prefix='urbz-proof-')
    pets, anims = os.path.join(work, 'pets'), os.path.join(work, 'anim-proof')
    shutil.copytree(os.path.join(KIT, 'mods', 'pets'), pets)
    run([sys.executable, os.path.join(KIT, 'urbz_art.py'), 'placeholder', pets, 'kitten'])
    run([sys.executable, os.path.join(KIT, 'urbz_anims.py'), 'placeholder', anims, '43', 'sit'])
    run([sys.executable, os.path.join(KIT, 'urbz_anims.py'), 'build', anims])
    run([sys.executable, os.path.join(KIT, 'urbz_patch.py'), 'build', '--dir', os.path.join(anims, 'code')])
    n_game0 = len(json.load(open(os.path.join(PROJ, 'manifest.json')))['entries'])
    n_anims0 = len([f for f in os.listdir(os.path.join(anims, 'assets')) if f.endswith('.bin')])
    extra = extra(n_game0 + n_anims0) if callable(extra) else list(extra)
    rom, log, _ = build(name, [anims] + extra + [pets])
    line = [l for l in log.splitlines() if l.startswith('pets:')]
    n_game = len(json.load(open(os.path.join(PROJ, 'manifest.json')))['entries'])
    n_anims = len([f for f in os.listdir(os.path.join(anims, 'assets')) if f.endswith('.bin')])
    lits = ram(rom, 1, '0x02029858:4', '0x0202A824:4', start=['--from', 'lobby'])
    anims_at = struct.unpack('<I', lits['0x02029858:4'])[0]
    pals_at = struct.unpack('<I', lits['0x0202A824:4'])[0]
    rows = ram(rom, 1, '0x%08X:0x28' % (anims_at + 0x28 * 8), '0x%08X:4' % (pals_at + 4 * 8),
               start=['--from', 'lobby'])
    rec = struct.unpack_from('<I', rows['0x%08X:0x28' % (anims_at + 0x28 * 8)], 0)[0]
    pal = struct.unpack('<I', rows['0x%08X:4' % (pals_at + 4 * 8)])[0]
    gfx = struct.unpack('<I', ram(rom, 1, '0x%08X:4' % rec, start=['--from', 'lobby'])['0x%08X:4' % rec])[0]
    shot = os.path.join(work, 'shot.json')
    s = json.load(open(place_script()))
    json.dump(s + [["wait", 80], ["shot", "kitten"]], open(shot, 'w'))
    out = run(VERIFY + ['ram', rom, '--city', '--goto', '68', '--frames', '5', '--script', shot,
                        '--read', HEAP_SCAN] + sum([['--poke', p] for p in pocket_pokes(389)], []))
    heap = bytes.fromhex([l for l in out.splitlines() if ' = ' in l][0].split(' = ')[1].strip())
    kinds = [k for _, k in critters(heap)]
    ev = out.strip().splitlines()[-1].split('evidence: ')[-1]
    pic = glob.glob(os.path.join(ev, '*kitten.png'))
    if pic:
        shutil.copy(pic[0], os.path.join(OUT, name + '.png'))
    first_pet = n_game + n_anims + 1 + len(extra)       # game id of the pets' first new file
    ok = (bool(line) and 'Kitten (kind 8, from chicken, own art)' in line[0] and anims_at >= CODE_BASE
          and gfx >= first_pet and pal >= first_pet and 8 in kinds)
    return ok, ('%s; anims mod files %d; Kitten slot 0 records at %08x, first gfx id %d, palette id %d '
                '(new from %d); placed: critter kinds %s; build/proofs/%s.png') % (
        line[0] if line else 'no pets line', n_anims, rec, gfx, pal, first_pet, kinds, name)


def p_rom_grow():
    """The ROM can grow past the original 32 MB: a test mod adds 40 MB of padding as the first new asset, so
    the pets' and animations' new art files land beyond 64 MB of the ROM. The builder writes a bigger chip
    size into the header; DeSmuME places and draws the Kitten from those files (as in pets-art) and melonDS
    boots the same ROM."""
    def pad(number):                                # numbered after the anims mod's own new files
        d = new_mod('grow-pad')
        os.makedirs(os.path.join(d, 'assets'))
        random.seed(11)
        open(os.path.join(d, 'assets', '%05d.bin' % number), 'wb').write(
            bytes(random.getrandbits(8) for _ in range(1 << 16)) * 640)      # 40 MB
        return [d]
    ok, detail = p_pets_art(extra=pad, name='rom-grow')
    rom = os.path.join(OUT, 'rom-grow.nds')
    h = open(rom, 'rb').read(0x200)
    used = struct.unpack_from('<I', h, 0x80)[0]
    size_ok = used > 64 << 20 and (128 << 10) << h[0x14] >= os.path.getsize(rom) >= used
    melon = ''
    import urbz_melon
    if urbz_melon.available():
        melon = subprocess.run([sys.executable, os.path.join(KIT, 'verify', 'urbz_melon.py'), 'boot', rom],
                               capture_output=True, text=True).stdout
    melon_ok = 'boot: OK' in melon or not urbz_melon.available()
    return ok and size_ok and melon_ok, 'ROM %.1f MB used, header chip size %d MB; melonDS: %s; %s' % (
        used / 2 ** 20, (128 << h[0x14]) >> 10, (melon.strip().splitlines() or ['not installed'])[-1][:60], detail)


# ---------------------------------------------------------------- imports from other Sims DS games

def _sources(*games):
    """The local sources.json entries (urbz_import.py), or None when a game isn't set up here."""
    p = os.path.join(KIT, 'sources.json')
    src = json.load(open(p)) if os.path.exists(p) else {}
    return src if all(g in src and os.path.exists(src[g]) for g in games) else None


def p_import_render():
    """urbz_import.py reads Apartment Pets' 3D dog (GX display list, skeleton, walk animation, textures)
    and renders it at the Urbz camera: the beagle textures resolve by hash, the walk moves its legs (frames
    differ), and the picture has the expected size (~0.41 m tall: ~15 px at 42 px per metre)."""
    if not _sources('aptpets'):
        return None, 'skipped: no aptpets in sources.json (your own copy of The Sims 2: Apartment Pets)'
    import numpy as np
    import urbz_import as I
    g, info = I.find_model('aptpets', 'dog')
    m = I.Model(g, info, {'collie2': 'beagle', 'collie': 'beagle'})
    names = sorted({n.split('/')[-1] for n in m.texture_names})
    a = I.render_model(m, 90, 'walk', 0)
    b = I.render_model(m, 90, 'walk', m.frames('walk') // 2)
    ys = np.nonzero(a[..., 3])[0]
    h = ys.max() - ys.min() + 1 if len(ys) else 0
    moved = int((a[..., 3] != b[..., 3]).sum())
    ok = 'body_beagle.nitro_texture' in names and 12 <= h <= 20 and moved > 20
    return ok, 'textures %s; side view %d px tall; walk frame 0 vs middle: %d pixels differ' % (
        ', '.join(n.replace('.nitro_texture', '') for n in names), h, moved)


def _import_mod():
    d = new_mod('imports')
    json.dump({'objects': [
        {'id': 440, 'like': 136, 'name': 'Green Lounger', 'price': 140, 'page': 3, 'description': 'Imported.',
         'import': {'from': 'aptpets', 'model': 'armchair4'}},
        {'id': 441, 'like': 136, 'name': 'Dog Basket', 'price': 40, 'page': 4, 'description': 'Imported.',
         'import': {'from': 'aptpets', 'model': 'dog_basket'}}]}, open(os.path.join(d, 'objects.json'), 'w'))
    json.dump({'pets': [
        {'name': 'Puppy', 'object': 386, 'from': 'rooster', 'price': 60, 'description': 'A beagle pup.',
         'import': {'from': 'aptpets', 'model': 'dog', 'textures': {'collie2': 'beagle', 'collie': 'beagle'}}},
        {'name': 'Kitten', 'object': 389, 'from': 'chicken', 'price': 45, 'description': 'A kitten.',
         'import': {'from': 'aptpets', 'model': 'cat'}}]}, open(os.path.join(d, 'pets.json'), 'w'))
    return build('imports', [d])


def p_import_furniture():
    """Furniture from Apartment Pets (objects.json "import"): an armchair (440) and a dog basket (441) are
    rendered into new art with their own palettes and icons. In Pockets both show their new icons (model
    numbers 633+, the icon table moved); placed at home, the armchair is an object entity drawn in a palette
    of its own (entity flag 0x20 and its palette table in the code region, through code/objects)
    (build/proofs/import-pockets.png, import-furniture.png)."""
    if not _sources('aptpets'):
        return None, 'skipped: no aptpets in sources.json'
    rom, log, _ = _import_mod()
    line = [l for l in log.splitlines() if l.startswith('objects:')]
    lit = struct.unpack('<I', ram(rom, 1, '0x0204E7B0:4')['0x0204E7B0:4'])[0]
    text = struct.unpack('<I', ram(rom, 1, '0x02014130:4')['0x02014130:4'])[0]
    model = struct.unpack('<I', ram(rom, 1, '0x%08X:4' % (text + 0x14 * 440))['0x%08X:4' % (text + 0x14 * 440)])[0]
    pk = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'pk.json')
    json.dump([["wait", 60], ["touch", 236, 166, 8], ["wait", 90], ["touch", 84, 75, 8], ["wait", 90],
               ["shot", "pockets"]], open(pk, 'w'))
    out = run(VERIFY + ['ram', rom, '--city', '--frames', '1', '--script', pk, '--poke', '0x02141338=03',
                        '--poke', '0x02141892=' + struct.pack('<HHHH', 440, 0, 441, 0).hex()])
    ev = out.strip().splitlines()[-1].split('evidence: ')[-1]
    for f in glob.glob(os.path.join(ev, '*pockets.png')):
        shutil.copy(f, os.path.join(OUT, 'import-pockets.png'))
    sc = place_script([["wait", 30], ["shot", "placed"]])
    out = run(VERIFY + ['ram', rom, '--city', '--goto', '68', '--frames', '1', '--script', sc, '--read', HEAP_SCAN,
                        '--read', '0x02141338:4'] + sum([['--poke', p] for p in pocket_pokes(440)], []))
    vals = dict(l.split(' = ') for l in out.splitlines() if ' = ' in l)
    heap = bytes.fromhex(vals[HEAP_SCAN].strip())
    ev = out.strip().splitlines()[-1].split('evidence: ')[-1]
    for f in glob.glob(os.path.join(ev, '*placed.png')):
        shutil.copy(f, os.path.join(OUT, 'import-furniture.png'))
    ents = [(struct.unpack_from('<I', heap, k + 0xC)[0], struct.unpack_from('<I', heap, k + 0xC8)[0])
            for k in range(0, len(heap) - 0x148, 4)
            if struct.unpack_from('<HH', heap, k + 8) == (5, 440) and struct.unpack_from('<H', heap, k + 0x146)[0] == 440]
    own = [e for e in ents if e[0] & 0x20 and CODE_BASE <= e[1] < CODE_BASE + 0x70000]
    ok = bool(line) and 'own art: 440, 441' in line[0] and lit >= CODE_BASE and model >= 633 and len(own) == 1
    return ok, ('%s; icon table at %08x, object 440 model %d; placed: entities with id 440 %s, own palette %s; '
                'build/proofs/import-pockets.png, import-furniture.png') % (
        line[0] if line else 'no objects line', lit, model, len(ents), bool(own))


def p_import_pet():
    """Pets from Apartment Pets (pets.json "import"): the Puppy is the 3D beagle and the Kitten the cat,
    rendered in every direction and frame the rooster and chicken have, with their walk animations and a
    drop shadow. Placed at home they run around as critter kinds 7 and 8 (build/proofs/import-pet.png)."""
    if not _sources('aptpets'):
        return None, 'skipped: no aptpets in sources.json'
    rom, log, _ = _import_mod()
    line = [l for l in log.splitlines() if l.startswith('pets:')]
    sc = place_script([["wait", 30], ["shot", "pet"]])
    out = run(VERIFY + ['ram', rom, '--city', '--goto', '68', '--frames', '5', '--script', sc, '--read', HEAP_SCAN]
              + sum([['--poke', p] for p in pocket_pokes(386)], []))
    heap = bytes.fromhex([l for l in out.splitlines() if ' = ' in l][0].split(' = ')[1].strip())
    kinds = [k for _, k in critters(heap)]
    ev = out.strip().splitlines()[-1].split('evidence: ')[-1]
    for f in glob.glob(os.path.join(ev, '*pet.png')):
        shutil.copy(f, os.path.join(OUT, 'import-pet.png'))
    ok = bool(line) and 'Puppy (kind 7, from rooster, own art)' in line[0] and 'Kitten (kind 8, from chicken, own art)' \
        in line[0] and 7 in kinds
    return ok, '%s; placed Puppy: critter kinds %s; build/proofs/import-pet.png' % (line[0] if line else 'no pets line', kinds)


def p_pet_walk():
    """Pets walk instead of sliding: the game switches a critter to its walk animation (slot 1) when it
    starts moving and back to stand (slot 0) when it stops, but only for kind 1 (the Chicken); code/pets-kit
    lets every pet pass that test. The Puppy (kind 7, mods/pets) placed at home: calls of critter_play_anim
    from those two places in critter_behaviour, over 900 frames."""
    rom = build('pet-walk', [os.path.join(KIT, 'mods', 'pets')])[0]
    sc = place_script()
    out = run(VERIFY + ['watch', rom, '--city', '--goto', '68', '--script', sc, '--frames', '900',
                        '--hook', 'exec:0x02029804'] + sum([['--poke', p] for p in pocket_pokes(386)], []))
    hits = [h for h in (l.split() for l in out.splitlines()) if len(h) >= 7 and h[0].isdigit() and h[1] == 'exec']
    walk = sum(1 for h in hits if h[4].lower() == '0202a754' and h[6] == '1')
    stand = sum(1 for h in hits if h[4].lower() == '0202a778' and h[6] == '0')
    return walk > 0 and stand > 0, 'walk animation started %d time(s), stand %d time(s)' % (walk, stand)


def p_import_melonds():
    """The imported armchair in melonDS (what Jonathan plays on), with real taps: a game saved at home with
    the chair in Pockets (made in DeSmuME) is loaded in melonDS; Pockets, double-tap the chair, three steps,
    A: the chair stands there, drawn in its own colours. The same steps in DeSmuME give the same picture
    (build/proofs/import-melonds.png)."""
    if not _sources('aptpets'):
        return None, 'skipped: no aptpets in sources.json'
    sys.path.insert(0, os.path.join(KIT, 'verify'))
    import urbz_melon as M
    if not M.available():
        return False, 'melonDS not set up: run verify/melonds_setup.sh (Linux), then rerun this proof'
    rom, _, _ = _import_mod()
    work = tempfile.mkdtemp(prefix='urbz-proof-')
    sav = os.path.join(work, 'home.sav')
    run(VERIFY + ['play', rom, '--city', '--goto', '68', '--script', os.path.join(KIT, 'verify', 'scripts', 'savegame.json'),
                  '--save', os.path.join(work, 'x.dst'), '--export-sav', sav] + sum([['--poke', p] for p in pocket_pokes(440)], []))
    place = json.load(open(place_script([["wait", 30], ["shot", "placed"]])))
    load = [['wait', 600]] + [['press', 'START'], ['wait', 300]] * 4 + [['wait', 300], ['press', 'DOWN', 10],
            ['wait', 60], ['press', 'A', 10], ['wait', 150], ['touch', 220, 117, 15], ['wait', 600], ['shot', 'home']]
    shots = dict(M.run(rom, load + place, sav=sav))
    script = os.path.join(work, 'place.json')
    json.dump(place, open(script, 'w'))
    out = run(VERIFY + ['ram', rom, '--sav', sav, '--script', os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'),
                        '--frames', '1'])
    ref_run = run(VERIFY + ['play', rom, '--sav', sav, '--script', _concat(os.path.join(KIT, 'verify', 'scripts', 'loadgame.json'), script),
                            '--save', os.path.join(work, 'y.dst')])
    ref = glob.glob(os.path.join(sorted(glob.glob(os.path.join(KIT, 'verify', 'evidence', '*-play')))[-1], '*placed.png'))
    from PIL import Image
    a = Image.open(shots['placed']).convert('RGB').crop((0, 0, 256, 192))
    b = Image.open(ref[0]).convert('RGB').crop((0, 0, 256, 192)) if ref else a
    same = sum(1 for p, q in zip(a.tobytes()[::3], b.tobytes()[::3]) if abs(p - q) < 24) / (256 * 192)
    shutil.copy(shots['placed'], os.path.join(OUT, 'import-melonds.png'))
    return bool(ref) and same > 0.9, 'melonDS vs DeSmuME after placing the imported chair: %.1f%% of the top screen the same; ' \
        'build/proofs/import-melonds.png' % (100 * same)


def _concat(*scripts):
    p = os.path.join(tempfile.mkdtemp(prefix='urbz-proof-'), 'all.json')
    json.dump(sum((json.load(open(s)) for s in scripts), []), open(p, 'w'))
    return p


PROOFS = [('vanilla', p_vanilla), ('clock-speed', p_clock_speed), ('hooks-wrap-call', p_hooks_wrap_call),
          ('hooks-thumb', p_hooks_thumb), ('hooks-jump', p_hooks_jump), ('relayout', p_relayout),
          ('needs-decay', p_needs_decay), ('action-effect', p_action_effect), ('lz77', p_lz77_repack),
          ('npc-schedule', p_npc_schedule_hook), ('save-edit', p_save_edit), ('lobby-goto', p_lobby_goto), ('text-accents', p_text_accents),
          ('grow-neighbour', p_grow_neighbour_pair), ('catalog-price', p_catalog_price),
          ('png-sheets', p_png_sheets_roundtrip), ('rom-grow', p_rom_grow), ('import-render', p_import_render), ('import-furniture', p_import_furniture), ('import-pet', p_import_pet), ('pet-walk', p_pet_walk), ('import-melonds', p_import_melonds), ('object-row', p_object_row),
          ('toggle-call', p_toggle_call), ('toggle-data', p_toggle_data),
          ('save-block', p_save_block), ('switch-persist', p_switch_persist),
          ('mods-page', p_mods_page), ('npc-life-days', p_npc_life_days),
          ('npc-life-stays', p_npc_life_stays), ('npc-life-visit', p_npc_life_visit), ('npc-use-object', p_npc_use_object), ('npc-act', p_npc_act),
          ('npc-act-release', p_npc_act_release), ('npc-act-eat', p_npc_act_eat), ('npc-body-prototype', p_npc_body_prototype),
          ('npc-anims', p_npc_anims), ('npc-life-off', p_npc_life_off),
          ('npc-life-reload', p_npc_life_reload), ('npc-life-page', p_npc_life_page), ('pet-place', p_pet_place), ('objects-new', p_objects_new), ('pets-data', p_pets_data), ('pets-art', p_pets_art), ('mods-split', p_mods_split),
          ('melonds', p_melonds)]


def main(argv):
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    if argv and argv[0] == '--list':
        print('\n'.join(n for n, _ in PROOFS))
        return
    sel = [(n, f) for n, f in PROOFS if not argv or n in argv]
    bad = skipped = 0
    for n, f in sel:
        try:
            ok, detail = f()
        except Exception as e:                      # report and carry on
            ok, detail = False, 'error: %s' % str(e).splitlines()[0][:300]
        if ok is None:                              # needs something this machine doesn't have
            skipped += 1
            print('%-16s SKIP  %s' % (n, detail), flush=True)
            continue
        bad += not ok
        print('%-16s %s  %s' % (n, 'PASS' if ok else 'FAIL', detail), flush=True)
    print('%d/%d passed%s' % (len(sel) - bad - skipped, len(sel) - skipped,
                              ', %d skipped' % skipped if skipped else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
