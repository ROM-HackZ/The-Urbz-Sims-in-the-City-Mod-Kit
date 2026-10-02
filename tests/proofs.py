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
import json, os, random, shutil, struct, subprocess, sys, tempfile

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
    pool = ram(rom, 300, '0x0215E000:0xC000')['0x0215E000:0xC000']
    found = [i for i in range(0, len(pool) - 0x148, 4)          # entity: +8 type, +0xA and +0x146 id
             if struct.unpack_from('<HH', pool, i + 8) == (7, 31)
             and struct.unpack_from('<H', pool, i + 0x146)[0] == 31]
    return answered > 0 and bool(found), \
        'schedule hook answered %d time(s); Bayou Boo (type 7, id 31) in the entity pool: %s' % (
            answered, bool(found))


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
          ('png-sheets', p_png_sheets_roundtrip), ('object-row', p_object_row)]


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
