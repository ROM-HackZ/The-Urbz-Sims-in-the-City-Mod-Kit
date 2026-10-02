#!/usr/bin/env python3
"""Regression proofs: build test mods and check, in the emulator, that each one does
what the docs claim. Every claim in docs/systems.md marked "Proven" has a proof here.

  python tests/proofs.py              run all (about 10-15 minutes)
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


HEAP_SCAN = '0x0214DE20:0x42000'   # code region + the start of the heap (the entity pool moves with the code)


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
    rom, _, _ = build('clock-speed', [os.path.join(KIT, 'mods', 'clock-speed')])
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
    rom, _, _ = build('npc-visit', [os.path.join(KIT, 'mods', 'npc-visit')])
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
    rom, _, _ = build('toggle-call', [os.path.join(KIT, 'mods', 'npc-visit')])
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
    rom, _, _ = build('toggle-data', [os.path.join(KIT, 'mods', 'clock-speed')])
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
    rom, _, _ = build('switch-persist', [os.path.join(KIT, 'mods', 'npc-visit'),
                                         os.path.join(KIT, 'mods', 'clock-speed')])
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
    rom, _, _ = build('mods-page', [os.path.join(KIT, 'mods', 'npc-visit'),
                                    os.path.join(KIT, 'mods', 'clock-speed')])
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
A_SLEEP, A_WORK, A_EAT = 1, 2, 3
KRIS = 45


def npc_life_rom(name, extra=()):
    return build(name, [os.path.join(KIT, 'mods', 'npc-life')] + list(extra))[0]


def sim_people(region, sim_addr):
    """The 36 people in the sim state: [{need, money, act, place, home, work}] (npc_sim.h)."""
    so = sim_addr - CODE_BASE
    out = []
    for c in range(36):
        b = region[so + 8 + 16 * c:so + 24 + 16 * c]
        out.append({'need': list(b[:8]), 'money': struct.unpack_from('<h', b, 8)[0], 'act': b[10],
                    'place': b[11], 'home': b[13], 'work': b[14]})
    return out, struct.unpack_from('<H', region, so + 2)[0]


def npcl(region):
    i = region.find(struct.pack('<I', NPCL_MAGIC))
    if i < 0:
        raise RuntimeError('NPC Life state not found')
    return dict(zip('magic attached ready resets loads saves minutes hours sim'.split(),
                    struct.unpack_from('<9I', region, i)))


def orig_timetables():
    import ndspy.rom
    a9 = ndspy.rom.NintendoDSRom.fromFile(os.path.join(PROJ, 'base.nds')).arm9
    out = []
    for c in range(36):
        p = struct.unpack_from('<I', a9, 0x020E4FD8 + 4 * c - 0x02000000)[0]
        out.append(a9[p - 0x02000000:p - 0x02000000 + 168] if p else None)
    return out


def snapshots(rom, start_save, steps, every, ranges, pokes=(), goto=None):
    """One emulator run from a save's city state: RAM ranges every `every` frames.
    goto = an area to load first (through the game's own loader, after the pokes)."""
    sys.path.insert(0, os.path.join(KIT, 'verify'))
    import urbz_verify as V
    out = tempfile.mkdtemp(prefix='urbz-snaps-')
    script = []
    for k in range(steps):
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
    """Three game days with NPC Life (fast clock: a game minute per tick): needs go up and down,
    money rises at work and falls at meals, people eat at food places, at home or where they are, and
    nobody is ever away from where the original game puts them."""
    rom = npc_life_rom('npc-life-days', [os.path.join(TESTS, 'mods', 'fast-clock')])
    places = json.load(open(os.path.join(KIT, 'mods', 'npc-life', 'places.json')))['places']
    food = {int(a) for a, p in places.items() if 'food' in p['kinds']}
    snaps, _ = snapshots(rom, 'lobby', 30, 300, ['0x%08X:0x8000' % CODE_BASE, '0x0214112C:6'])
    first = npcl(snaps[0][0])
    rows = [sim_people(r, first['sim'])[0] for r, _ in snaps]
    tables = orig_timetables()
    who = [c for c in range(36) if tables[c]]
    swing = sum(1 for c in who if max(r[c]['need'][0] for r in rows) - min(r[c]['need'][0] for r in rows) >= 25
                and max(r[c]['need'][2] for r in rows) - min(r[c]['need'][2] for r in rows) >= 25)
    paid = sum(1 for c in who if any(b[c]['act'] == A_WORK and b[c]['money'] > a[c]['money']
                                     for a, b in zip(rows, rows[1:])))
    spent = sum(1 for c in who if any(b[c]['act'] == A_EAT and b[c]['money'] < a[c]['money']
                                      for a, b in zip(rows, rows[1:])))
    # the sim's hour of the week at each snapshot -> the original timetable slot
    so = first['sim'] - CODE_BASE
    slots = [(lambda c: c // 60 % 24 * 7 + c // 1440)(struct.unpack_from('<H', r, so + 2)[0]) for r, _ in snaps]
    usual = lambda c, k: tables[c][slots[k]]
    meals = [(r[c]['place'], r[c]['home'], usual(c, k)) for k, r in enumerate(rows) for c in who
             if r[c]['act'] == A_EAT]
    good_meals = sum(1 for place, home, u in meals if place in food or place == home or place == u)
    # nobody goes missing: in every snapshot, everyone is where the game puts them, or on a visit in
    # an hour the game has them out of town (82)
    misplaced = sum(1 for k, r in enumerate(rows) for c in who if usual(c, k) != 82 and r[c]['place'] != usual(c, k))
    last = npcl(snaps[-1][0])
    day0, day1 = struct.unpack_from('<h', snaps[0][1])[0], struct.unpack_from('<h', snaps[-1][1])[0]
    ok = (swing >= len(who) * 3 // 4 and paid >= 15 and spent >= 10 and meals and good_meals == len(meals)
          and not misplaced and day1 - day0 >= 2 and last['hours'] >= 60)
    return ok, ('%d game hours simulated (day %d -> %d); hunger and energy both swung 25+ points for %d/%d '
                'people; %d earned at work, %d paid for a meal; %d meals seen, all at food places, home or '
                'where they were anyway: %s; people away from where the game puts them: %d') % (
        last['hours'], day0, day1, swing, len(who), paid, spent, len(meals), good_meals == len(meals), misplaced)


def walkin_run(rom, pokes=()):
    """From the lobby at 17:01, Kris's energy set to 0 in the sim (a precondition): by 18:00 the sim
    sends her home to sleep (the lobby, 66), where her usual timetable says the roof (70)."""
    reg = '0x%08X:0x8000' % CODE_BASE
    sim = npcl(ram(rom, 1, reg, start=['--from', 'lobby'])[reg])['sim']
    energy = '0x%08X=00' % (sim + 8 + (KRIS - 31) * 16 + 2)
    snaps, out = snapshots(rom, 'lobby', 6, 600, [HEAP_SCAN, '0x0214112C:6', '0x02065924:4'],
                           pokes=[energy] + list(pokes))
    res = []
    for mem, clk, lit in snaps:
        people, _ = sim_people(mem, sim)
        res.append({'present': KRIS in people_in(mem), 'hour': clk[2], 'act': people[KRIS - 31]['act'],
                    'place': people[KRIS - 31]['place'], 'literal': struct.unpack('<I', lit)[0]})
    return res, out


def p_npc_life_stays():
    """Nobody goes missing: Kris, exhausted at 17:01, still keeps to the game's own timetable at 18:00
    (the roof, 70): she rests there instead of turning up in the lobby (her home)."""
    rom = npc_life_rom('npc-life-stays')
    res, _ = walkin_run(rom)
    usual = orig_timetables()[KRIS - 31][18 * 7 + 0]
    after = [r for r in res if r['hour'] >= 18]
    ok = usual == 70 and after and not any(r['present'] for r in res) and all(r['place'] == usual for r in after)
    return ok, ('Kris exhausted; her timetable at 18:00 Monday: area %d; the sim keeps her at %s; in the lobby: %s') % (
        usual, sorted(set(r['place'] for r in after)), [r['present'] for r in res])


PHOEBE = 54                      # out of town at midnight going into Tuesday; knows 3 food places


def visit_run(rom, goto=None):
    """Clock set to Monday 23:58 and Phoebe starving (preconditions); RAM after 600 and 1500 frames."""
    reg = '0x%08X:0x8000' % CODE_BASE
    sim = npcl(ram(rom, 1, reg, start=['--from', 'lobby'])[reg])['sim']
    _, core = find_magic(rom, 1, CORE_MAGIC, 8)
    pokes = ['0x0214112E=173A',                                         # game clock 23:58
             '0x%08X=00000000' % (core + 36),                           # core: resync minutes, don't replay
             '0x%08X=%s' % (sim + 2, struct.pack('<H', 23 * 60 + 58).hex()),   # sim clock too
             '0x%08X=00' % (sim + 8 + (PHOEBE - 31) * 16),              # Phoebe's hunger 0,
             '0x%08X=08' % (sim + 8 + (PHOEBE - 31) * 16 + 10)]         # and not eating now (away)
    snaps, out = snapshots(rom, 'lobby', 3, 600, [HEAP_SCAN, '0x0214112C:6'], pokes=pokes, goto=goto)
    res = []
    for mem, clk in snaps:
        people, _ = sim_people(mem, sim)
        res.append({'present': PHOEBE in people_in(mem), 'day': struct.unpack_from('<h', clk)[0], 'hour': clk[2],
                    'act': people[PHOEBE - 31]['act'], 'place': people[PHOEBE - 31]['place']})
    return res, out


def p_npc_life_visit():
    """A living city: in an hour the original game has someone out of town, the sim sends them out (Phoebe,
    starving at midnight, goes to eat) and the game walks them into that place."""
    rom = npc_life_rom('npc-life-visit')
    first, _ = visit_run(rom)
    place = first[-1]['place']
    usual = orig_timetables()[PHOEBE - 31][0 * 7 + 1]                   # Tuesday 00:00
    if place == 82:
        return False, 'Phoebe stayed out of town (sim activity %d)' % first[-1]['act']
    res, out = visit_run(rom, goto=place)
    shot = sorted(glob.glob(os.path.join(out, '*.png')))
    if shot:
        shutil.copy(shot[-1], os.path.join(OUT, 'npc-life-visit.png'))
    ok = usual == 82 and first[-1]['act'] == A_EAT and res[-1]['present'] and res[-1]['hour'] == 0
    return ok, ('Phoebe at Tuesday 00:00 in the original game: area %d (out of town); the sim sends her to eat at '
                '%d; there, she is present: %s (day %d %02d:00)') % (
        usual, place, [r['present'] for r in res], res[-1]['day'], res[-1]['hour'])


OBJP_MAGIC = 0x504A424F


def p_npc_use_object():
    """People can use the area's objects with the game's own code (Phase 6 groundwork): in the Coffee Shop
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


def p_npc_life_off():
    """Switched off in the game: the timetable pointers go back and people follow their usual timetable."""
    rom = npc_life_rom('npc-life-off')
    res, _ = walkin_run(rom, pokes=[core_request(rom, 0, 0)])
    lits = set(r['literal'] for r in res)
    ok = lits == {0x020E4FD8} and not any(r['present'] for r in res)
    return ok, 'switched off at 17:01: schedule pointer %s (original 020e4fd8); Kris in the lobby: %s' % (
        ', '.join('%08x' % x for x in lits), [r['present'] for r in res])


def p_npc_life_save():
    """The simulation is saved with the game and comes back exactly after power-off and Load-an-Urb."""
    import urbz_save
    from urbz_code import name_hash
    rom = npc_life_rom('npc-life-save')
    sav = play_export(rom, 'npc-life-save', ['--from', 'lobby'], SAVEGAME)
    buf = open(sav, 'rb').read()
    blk = dict(urbz_save.mod_block(buf[0x20:0x20 + urbz_save.SLOT_SIZE]) or [])
    saved = blk.get(name_hash('npc-life'))
    reg = '0x%08X:0x8000' % CODE_BASE
    after = ram(rom, 30, reg, start=['--sav', sav], script=LOADGAME)[reg]
    st = npcl(after)
    so = st['sim'] - CODE_BASE
    loaded = after[so:so + len(saved)] if saved else b''
    same_people = saved is not None and loaded[8:] == saved[8:]
    ok = saved is not None and len(saved) == 584 and st['loads'] == 1 and same_people
    return ok, 'mod data in the save: %s bytes; after power-off and loading: loads %d, all 36 people identical: %s' % (
        len(saved) if saved else None, st['loads'], same_people)


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
    rom = npc_life_rom('melonds', [os.path.join(KIT, 'mods', 'clock-speed')])
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


PROOFS = [('vanilla', p_vanilla), ('clock-speed', p_clock_speed), ('hooks-wrap-call', p_hooks_wrap_call),
          ('hooks-thumb', p_hooks_thumb), ('hooks-jump', p_hooks_jump), ('relayout', p_relayout),
          ('needs-decay', p_needs_decay), ('action-effect', p_action_effect), ('lz77', p_lz77_repack),
          ('npc-schedule', p_npc_schedule_hook), ('save-edit', p_save_edit), ('lobby-goto', p_lobby_goto), ('text-accents', p_text_accents),
          ('grow-neighbour', p_grow_neighbour_pair), ('catalog-price', p_catalog_price),
          ('png-sheets', p_png_sheets_roundtrip), ('object-row', p_object_row),
          ('toggle-call', p_toggle_call), ('toggle-data', p_toggle_data),
          ('save-block', p_save_block), ('switch-persist', p_switch_persist),
          ('mods-page', p_mods_page), ('npc-life-days', p_npc_life_days),
          ('npc-life-stays', p_npc_life_stays), ('npc-life-visit', p_npc_life_visit), ('npc-use-object', p_npc_use_object), ('npc-life-off', p_npc_life_off),
          ('npc-life-save', p_npc_life_save), ('npc-life-page', p_npc_life_page), ('melonds', p_melonds)]


def main(argv):
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    if argv and argv[0] == '--list':
        print('\n'.join(n for n, _ in PROOFS))
        return
    sel = [(n, f) for n, f in PROOFS if not argv or n in argv]
    bad = 0
    for n, f in sel:
        try:
            ok, detail = f()
        except Exception as e:                      # report and carry on
            ok, detail = False, 'error: %s' % str(e).splitlines()[0][:300]
        bad += not ok
        print('%-16s %s  %s' % (n, 'PASS' if ok else 'FAIL', detail), flush=True)
    print('%d/%d passed' % (len(sel) - bad, len(sel)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
