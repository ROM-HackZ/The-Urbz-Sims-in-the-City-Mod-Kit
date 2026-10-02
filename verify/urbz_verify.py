#!/usr/bin/env python3
"""Headless emulator checks for Urbz DS builds (py-desmume, no window needed).

  python verify/urbz_verify.py doctor [rom]
      Is this ROM worth testing? Header, boot, and the first screen drawing.
  python verify/urbz_verify.py smoke [rom] [--ref project/base.nds]
      Boot the built ROM and the original side by side with the same button
      presses. Screenshot both, report which screens changed, and flag a hang or crash.
  python verify/urbz_verify.py ram <rom> --frames N [--state file.dst] [--script file.json]
                                   --read ADDR:LEN [--read ...]
      Run (from a savestate, optionally), then dump memory.
  python verify/urbz_verify.py play <rom> --script file.json [--state in.dst] --save out.dst [--heap N]
      Run an input script and save a savestate (used to make test starting points).
      --heap N samples the game's heap every N frames and reports the tightest point.
  python verify/urbz_verify.py trace <rom> --script file.json --name NAME [--state in.dst] [--save out.dst]
      Like play, but records which assets the game loads before each screenshot.
      Saved to verify/traces/NAME.json; the catalog uses these as scene labels.

  python verify/urbz_verify.py city [rom] [--from NAME]
      Boot this build and get into the city (loads verify/saves/city.sav, or plays a new
      game if that file is missing); caches the savestate per ROM (verify/states/cache/).
      Use --city on other commands to start there.
  python verify/urbz_verify.py find <rom> (--state F|--city) --script s.json --test SHOT=COND ...
      Value search: RAM is snapshotted at each shot; keep addresses passing each test
      (eq:N ne:N add:N sub:N range:A-B inc dec same changed any). --size 1|2|4.
  python verify/urbz_verify.py watch <rom> (--state F|--city) --frames N --hook exec:ADDR ...
      Log every exec/read/write of an address (pc, lr, r0, value). --stack adds likely
      callers from the stack; --r0 V keeps only hits where r0 == V.

Start options for ram/play/trace/find/watch: --state F, --city, --sav F (a raw .sav),
--from NAME (like --city, but loads verify/saves/NAME.sav; lobby = first goal done, Tower Lobby),
--poke ADDR=HEXBYTES (write memory before the script; repeatable, for experiments),
--goto AREA[:ENTRY] (EXPERIMENT: load any area through the game's own loader before the script;
  the streets are locked in a real game until the tower chapter is done, see docs/areas.md).
play --export-sav F writes the cartridge save memory at the end of the run.
Savestates contain the game code: for code mods, start from --city, not an old state.

All commands accept --rtc YYYY-MM-DDTHH:MM to set the DS clock (default
2026-01-05T12:00), so runs are repeatable and time-of-day can be tested.

Default rom: build/Urbz Mod.nds. Evidence (screenshots + report.txt) goes to
verify/evidence/<time>-<command>/ and is never deleted automatically.

Input scripts are JSON lists of steps:
  ["wait", frames]  ["press", "A", holdFrames?]  ["touch", x, y, holdFrames?]  ["shot", "name"]
Keys: A B X Y L R START SELECT UP DOWN LEFT RIGHT
"""
import json, os, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
DEFAULT_ROM = os.path.join(KIT, 'build', 'Urbz Mod.nds')
DEFAULT_REF = os.path.join(KIT, 'project', 'base.nds')

# Boot -> legal screens -> EA -> Maxis -> title -> Create-a-Bod.
SMOKE_SCRIPT = []
for i in range(6):
    SMOKE_SCRIPT += [['wait', 300], ['shot', 'step%d' % i], ['press', 'A'], ['press', 'START']]


def evidence_dir(cmd):
    d = os.path.join(HERE, 'evidence', time.strftime('%Y%m%d-%H%M%S') + '-' + cmd)
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------- emulator side

DEFAULT_RTC = '2026-01-05T12:00'   # a Monday at noon; same for every run


def _emu(rom, rtc=None, movie_path=None, sav=None):
    """Open the ROM with a pinned real-time clock so runs are repeatable.

    DeSmuME only fixes the RTC while recording an input movie, so every run
    records a throwaway movie starting at `rtc`, from a blank save or from
    the raw cartridge save `sav` (.sav)."""
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    import desmume.emulator as E
    from datetime import datetime
    emu = E.DeSmuME()
    emu.open(rom)
    emu.volume_set(0)
    t = datetime.fromisoformat(rtc or DEFAULT_RTC)
    date = E.DeSmuME_Date(t.year, t.month, t.day, t.hour, t.minute, t.second, 0)
    emu.movie.record(movie_path or os.devnull, 'urbz_verify', E.StartFrom.START_BLANK, '', date)
    if sav:                       # raw cartridge save (.sav), loaded after the blank start
        if not emu.backup.import_file(sav):
            raise RuntimeError('could not load save file ' + sav)
    return emu


FRAME = [0]      # frames run so far in this child (for hook logs)
PER_FRAME = []   # callbacks(frame) run after every frame
HEAP_TABLE = 0x02142004   # the game's heap handle (NNS expanded heap, 'EXPH')


def heap_stats(mem):
    """(free bytes, largest free block, used bytes) of the game's main heap."""
    u32 = lambda a: struct.unpack('<I', bytes(mem[a:a + 4]))[0]
    h = u32(HEAP_TABLE)
    if not 0x02000000 <= h < 0x02400000 or u32(h) != 0x45585048:     # 'EXPH'
        return None
    out = []
    for off in (0x24, 0x2C):                 # free list head, used list head
        b, n, tot, big = u32(h + off), 0, 0, 0
        while b and n < 200000:
            size = u32(b + 4)
            tot, big, n = tot + size, max(big, size), n + 1
            b = u32(b + 12)
        out.append((tot, big))
    return out[0][0], out[0][1], out[1][0]


def _run_script(emu, script, outdir, tag, loads=None, on_shot=None):
    """Run input steps. If `loads` is a list being filled by a trace hook, each
    shot records the asset IDs used since the previous shot."""
    from desmume.controls import Keys, keymask
    keys = {k: getattr(Keys, 'KEY_' + k) for k in
            'A B X Y L R START SELECT UP DOWN LEFT RIGHT'.split()}
    frame = 0
    shots = []

    def step(n):
        nonlocal frame
        for _ in range(n):
            emu.cycle(with_joystick=False)
            frame += 1
            FRAME[0] = frame
            for cb in PER_FRAME:
                cb(frame)

    for s in script:
        op = s[0]
        if op == 'wait':
            step(int(s[1]))
        elif op == 'press':
            k = keymask(keys[s[1].upper()])
            emu.input.keypad_add_key(k)
            step(int(s[2]) if len(s) > 2 else 6)
            emu.input.keypad_rm_key(k)
            step(10)
        elif op == 'touch':
            emu.input.touch_set_pos(int(s[1]), int(s[2]))
            step(int(s[3]) if len(s) > 3 else 6)
            emu.input.touch_release()
            step(10)
        elif op == 'shot':
            p = os.path.join(outdir, '%s_%s.png' % (tag, s[1]))
            emu.screenshot().save(p)
            if on_shot:
                on_shot(s[1])
            if loads is not None:
                used = sorted(set(loads))
                loads.clear()
                shots.append((s[1], p, frame, used))
            else:
                shots.append((s[1], p, frame))
        else:
            raise ValueError('unknown script step %r' % (s,))
    return shots


def child_main(argv):
    """Internal: run one emulator in this process. argv: json job."""
    job = json.loads(argv[0])
    emu = _emu(job['rom'], job.get('rtc'), os.path.join(job['out'], job['tag'] + '.dsm'), job.get('sav'))
    if job.get('state'):
        emu.savestate.load_file(job['state'])
    for pk in job.get('poke') or []:           # RE helper: ADDR=HEXBYTES written before the script
        a, hexb = pk.split('=')
        for i, b in enumerate(bytes.fromhex(hexb)):
            emu.memory.write_byte(int(a, 0) + i, b)
    if job.get('goto'):                        # EXPERIMENT: load an area through the game's state machine
        area, entry = job['goto']
        for addr, val in ((0x027C009C, 0x81), (0x027C00A0, 0), (0x027C00A4, area)):
            for i, b in enumerate(struct.pack('<I', val)):
                emu.memory.write_byte(addr + i, b)
        emu.memory.write_byte(0x02141C28, entry)
        for _ in range(GOTO_FRAMES):
            emu.cycle(with_joystick=False)
        cur = struct.unpack('<I', bytes(emu.memory.unsigned[0x02141FEC:0x02141FF0]))[0]
        if cur != area:
            raise RuntimeError('--goto %d did not load (current area %d)' % (area, cur))
    hooks = []
    if job.get('watch'):
        hooks = _install_watches(emu, job['watch'], stack=job.get('stack'), only_r0=job.get('only_r0'))
    shot_cbs = []
    heap = None
    if job.get('heap'):
        heap = {'samples': 0, 'min_free': None, 'min_largest': None, 'max_used': 0}
        memh = emu.memory.unsigned

        def sample(frame, force=False):
            if frame % job['heap'] and not force:
                return
            st = heap_stats(memh)
            if st is None:
                return                      # heap not created yet (early boot)
            f, big, used = st
            heap['samples'] += 1
            heap['min_free'] = f if heap['min_free'] is None else min(heap['min_free'], f)
            heap['min_largest'] = big if heap['min_largest'] is None else min(heap['min_largest'], big)
            heap['max_used'] = max(heap['max_used'], used)
        PER_FRAME.append(sample)
        shot_cbs.append(lambda n: sample(0, True))
    if job.get('snap'):
        snaps = []
        mem0 = emu.memory.unsigned

        def snap(name):
            files = []
            for k, rng in enumerate(job['snap']):
                a, n = (int(x, 0) for x in rng.split(':'))
                f = os.path.join(job['out'], 'snap_%02d_%s_%d.bin' % (len(snaps), name, k))
                open(f, 'wb').write(bytes(mem0[a:a + n]))
                files.append(f)
            snaps.append((name, files))
        shot_cbs.append(snap)
    loads = []
    if job.get('trace'):
        # 0x02032CA8 = "get asset by game ID" (game ID = file number + 1).
        regs = emu.memory.register_arm9
        n_assets = job['trace']

        def on_get(addr, size):
            gid = regs.r0
            if 1 <= gid <= n_assets:
                loads.append(gid)
        emu.memory.register_exec(0x02032CA8, on_get)
        # Sprite palettes: remember where each decoded frame went in video memory,
        # then at every screenshot read the sprite table (OAM) and palette RAM.
        regs9, mem = emu.memory.register_arm9, emu.memory.unsigned
        writes, cur = [], {}
        emu.memory.register_exec(0x01FF8C50, lambda a, s: cur.update(
            dst=regs9.r1, head=bytes(mem[regs9.r0 - 4:regs9.r0 + 40])))
        emu.memory.register_exec(0x01FF8F68, lambda a, s: writes.append(
            (cur.get('dst'), regs9.r1 - regs9.r0, cur.get('head'))))
        palettes = []

        def on_shot(_name):
            for oam, pal, vram, dispcnt in ((0x07000000, 0x05000200, 0x06400000, 0x04000000),
                                            (0x07000400, 0x05000600, 0x06600000, 0x04001000)):
                dc = struct.unpack('<I', bytes(mem[dispcnt:dispcnt + 4]))[0]
                step = 32 << ((dc >> 20) & 3) if dc & 0x10 else 32
                P = struct.unpack('<256H', bytes(mem[pal:pal + 512]))
                for k in range(128):
                    a0, a1, a2 = struct.unpack('<3H', bytes(mem[oam + k * 8:oam + k * 8 + 6]))
                    if (a0 >> 8) & 3 == 2 or (a0 >> 13) & 1:
                        continue                       # hidden, or 256-colour sprite
                    addr = vram + (a2 & 0x3FF) * step
                    for d, n, head in reversed(writes):
                        if d is not None and head and d <= addr < d + n:
                            bank = a2 >> 12
                            palettes.append((head.hex(), list(P[bank * 16:bank * 16 + 16])))
                            break
        shot_cbs.append(on_shot)
    shots = _run_script(emu, job.get('script', []), job['out'], job['tag'],
                        loads if job.get('trace') else None,
                        (lambda n: [cb(n) for cb in shot_cbs]) if shot_cbs else None)
    result = {'shots': shots}
    if job.get('snap'):
        result['snaps'] = snaps
    if hooks:
        result['watch'] = hooks
    if heap:
        result['heap'] = heap
    if job.get('trace'):
        result['palettes'] = palettes
    if job.get('read'):
        mem = emu.memory.unsigned
        result['reads'] = {a: bytes(mem[int(a.split(':')[0], 0):
                                        int(a.split(':')[0], 0) + int(a.split(':')[1], 0)]).hex()
                           for a in job['read']}
    if job.get('save'):
        emu.savestate.save_file(job['save'])
        result['saved'] = job['save']
    if job.get('export_sav'):
        emu.backup.export_file(job['export_sav'])
        result['exported_sav'] = job['export_sav']
    print('RESULT ' + json.dumps(result), flush=True)
    os._exit(0)          # libdesmume can hang on teardown; we are done


def _stack_calls(regs, mem, n=24):
    """Likely return addresses on the ARM9 stack (words pointing into game code)."""
    sp = regs.r13
    out = []
    for k in range(64):
        a = sp + 4 * k
        w = struct.unpack('<I', bytes(mem[a:a + 4]))[0]
        if 0x02000800 <= w < 0x02121AC0 and len(out) < n:
            out.append(w)
    return out


def _install_watches(emu, watches, limit=4000, stack=False, only_r0=None):
    """watches: ["exec:ADDR", "read:ADDR[:SIZE]", "write:ADDR[:SIZE]"].
    Logs [frame, kind, addr, pc, lr, r0, value] per hit (first `limit` hits,
    then counts only). Note: block stores (STM) don't trigger write hooks."""
    regs, mem = emu.memory.register_arm9, emu.memory.unsigned
    log = {'hits': [], 'counts': {}}

    def mk(kind, size):
        def cb(addr, sz):
            key = '%s:%08x' % (kind, addr)
            log['counts'][key] = log['counts'].get(key, 0) + 1
            if only_r0 is not None and regs.r0 != only_r0:
                return
            if len(log['hits']) < limit:
                v = int.from_bytes(bytes(mem[addr:addr + size]), 'little') if kind != 'exec' else None
                hit = [FRAME[0], kind, addr, regs.r15, regs.r14, regs.r0, v]
                if stack:
                    hit.append(_stack_calls(regs, mem))
                log['hits'].append(hit)
        return cb
    for w in watches:
        parts = w.split(':')
        kind, addr = parts[0], int(parts[1], 0)
        size = int(parts[2], 0) if len(parts) > 2 else 4
        fn = mk(kind, size)
        if kind == 'exec':
            emu.memory.register_exec(addr, fn)
        elif kind == 'read':
            emu.memory.register_read(addr, fn, size)
        elif kind == 'write':
            emu.memory.register_write(addr, fn, size)
        else:
            raise ValueError('watch kind must be exec, read or write: %s' % w)
    return log


def _check_rom(job):
    if not os.path.exists(job['rom']):
        sys.exit('error: ROM not found: %s (build it first: python urbz_build.py)' % job['rom'])
    if job.get('state') and not os.path.exists(job['state']):
        sys.exit('error: savestate not found: %s' % job['state'])
    if job.get('sav') and not os.path.exists(job['sav']):
        sys.exit('error: save file not found: %s' % job['sav'])


def run_child(job, timeout=600):
    _check_rom(job)
    p = subprocess.run([sys.executable, os.path.abspath(__file__), '_child', json.dumps(job)],
                       capture_output=True, text=True, timeout=timeout)
    for line in p.stdout.splitlines():
        if line.startswith('RESULT '):
            return json.loads(line[7:])
    raise RuntimeError('emulator run failed for %s:\n%s\n%s' % (job['rom'], p.stdout[-2000:], p.stderr[-2000:]))


def run_children(jobs, timeout=600):
    for j in jobs:
        _check_rom(j)
    procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__), '_child', json.dumps(j)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for j in jobs]
    out = []
    for p, j in zip(procs, jobs):
        so, se = p.communicate(timeout=timeout)
        res = next((json.loads(l[7:]) for l in so.splitlines() if l.startswith('RESULT ')), None)
        if res is None:
            raise RuntimeError('emulator run failed for %s:\n%s\n%s' % (j['rom'], so[-2000:], se[-2000:]))
        out.append(res)
    return out


# --------------------------------------------------------------- image helpers

def _img_stats(a_path, b_path):
    from PIL import Image, ImageChops
    a = Image.open(a_path).convert('RGB')
    b = Image.open(b_path).convert('RGB')
    diff = ImageChops.difference(a, b).convert('L').point(lambda v: 255 if v > 24 else 0)
    changed = diff.histogram()[255]
    return changed / (a.width * a.height)


def _blank(p):
    from PIL import Image
    ex = Image.open(p).convert('L').getextrema()
    return ex[1] - ex[0] < 8


def _contact(pairs, out_path):
    from PIL import Image, ImageDraw
    if not pairs:
        return
    w, h = Image.open(pairs[0][1]).size
    sheet = Image.new('RGB', (w * len(pairs), h * 2 + 16), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (name, a, b) in enumerate(pairs):
        sheet.paste(Image.open(b), (i * w, 16))
        sheet.paste(Image.open(a), (i * w, 16 + h))
        d.text((i * w + 4, 2), name, fill='black')
    sheet.save(out_path)


# --------------------------------------------------------------- commands

def header_check(rom):
    with open(rom, 'rb') as f:
        hdr = f.read(0x200)
    code = hdr[0xC:0x10].decode('ascii', 'replace')
    title = hdr[0:12].rstrip(b'\0').decode('ascii', 'replace')
    return code, title


def cmd_doctor(args):
    rom = args[0] if args else DEFAULT_ROM
    if not os.path.exists(rom):
        sys.exit('DOCTOR FAIL: %s not found (build first: python urbz_build.py)' % rom)
    code, title = header_check(rom)
    print('header: %s / %s' % (title, code))
    if code != 'ASIE':
        sys.exit('DOCTOR FAIL: not The Urbz DS (USA), game code %s' % code)
    out = evidence_dir('doctor')
    res = run_child({'rom': os.path.abspath(rom), 'out': out, 'tag': 'rom',
                     'script': [['wait', 60], ['shot', 'boot60'], ['wait', 300], ['shot', 'boot360']]})
    shots = {n: p for n, p, _ in res['shots']}
    if _blank(shots['boot60']) and _blank(shots['boot360']):
        sys.exit('DOCTOR FAIL: screen still blank after 360 frames (likely a crash on boot). Evidence: ' + out)
    print('DOCTOR OK: boots and draws. Evidence: ' + out)


def cmd_smoke(args):
    rom = DEFAULT_ROM
    ref = DEFAULT_REF
    rest = list(args)
    if rest and not rest[0].startswith('--'):
        rom = rest.pop(0)
    if '--ref' in rest:
        ref = rest[rest.index('--ref') + 1]
    for p in (rom, ref):
        if not os.path.exists(p):
            sys.exit('SMOKE FAIL: %s not found' % p)
    out = evidence_dir('smoke')
    print('running %s and reference %s side by side (about a minute)...' % (os.path.basename(rom), os.path.basename(ref)))
    r_rom, r_ref = run_children([
        {'rom': os.path.abspath(rom), 'out': out, 'tag': 'build', 'script': SMOKE_SCRIPT,
         'rtc': _opt(rest, '--rtc')},
        {'rom': os.path.abspath(ref), 'out': out, 'tag': 'orig', 'script': SMOKE_SCRIPT,
         'rtc': _opt(rest, '--rtc')}])
    lines, pairs = [], []
    build_shots = r_rom['shots']
    blanks = 0
    for (name, a, fa), (_, b, _) in zip(build_shots, r_ref['shots']):
        frac = _img_stats(a, b)
        blanks += _blank(a) and not _blank(b)
        lines.append('%-7s frame %5d  %5.1f%% of pixels differ from original' % (name, fa, frac * 100))
        pairs.append((name, a, b))
    # A frozen game produces identical consecutive screenshots while the original changes.
    frozen = all(_img_stats(build_shots[i][1], build_shots[i + 1][1]) == 0
                 for i in range(len(build_shots) - 1))
    _contact(pairs, os.path.join(out, 'compare.png'))
    last = _img_stats(build_shots[-1][1], r_ref['shots'][-1][1])
    verdict = 'PASS'
    notes = []
    if frozen:
        verdict = 'FAIL'
        notes.append('every screenshot is identical: the game looks frozen')
    if blanks:
        verdict = 'FAIL'
        notes.append('%d screen(s) are blank where the original draws something' % blanks)
    if last > 0.6:
        notes.append('the final screen differs a lot from the original (expected only if your mod changes it)')
    report = ['SMOKE %s' % verdict, 'rom: ' + rom, 'ref: ' + ref, ''] + lines + [''] + notes + \
             ['', 'top row = original, bottom row = your build: compare.png']
    open(os.path.join(out, 'report.txt'), 'w').write('\n'.join(report) + '\n')
    print('\n'.join(report))
    print('evidence: ' + out)
    if verdict != 'PASS':
        sys.exit(1)


def _opt(args, name, default=None, many=False):
    vals = [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]
    return vals if many else (vals[-1] if vals else default)


def cmd_ram(args):
    if not args:
        sys.exit('usage: urbz_verify.py ram <rom> --frames N [--state f.dst] [--script s.json] --read ADDR:LEN ...')
    rom = args[0]
    frames = int(_opt(args, '--frames', '0'))
    script = json.load(open(_opt(args, '--script'))) if _opt(args, '--script') else []
    script = script + [['wait', frames]] if frames else script
    reads = _opt(args, '--read', many=True)
    out = evidence_dir('ram')
    res = run_child(dict(_start(args, rom), out=out, tag='ram', script=script, read=reads))
    report = []
    for k, v in res.get('reads', {}).items():
        report.append('%s = %s' % (k, v))
    open(os.path.join(out, 'report.txt'), 'w').write('\n'.join(report) + '\n')
    print('\n'.join(report))
    print('evidence: ' + out)


def cmd_play(args):
    if not args or '--script' not in args or '--save' not in args:
        sys.exit('usage: urbz_verify.py play <rom> --script s.json [--state in.dst] --save out.dst')
    rom = args[0]
    out = evidence_dir('play')
    job = dict(_start(args, rom), out=out, tag='play', script=json.load(open(_opt(args, '--script'))),
               save=os.path.abspath(_opt(args, '--save')))
    if _opt(args, '--export-sav'):
        job['export_sav'] = os.path.abspath(_opt(args, '--export-sav'))
    if _opt(args, '--heap'):
        job['heap'] = int(_opt(args, '--heap'))
    res = run_child(job)
    if 'heap' in res:
        h = res['heap']
        print('heap: lowest free %d KB, smallest largest-free-block %d KB, most used %d KB (%d samples)'
              % (h['min_free'] // 1024, h['min_largest'] // 1024, h['max_used'] // 1024, h['samples']))
    print('saved state: %s  (screens in %s)' % (res['saved'], out))


def cmd_trace(args):
    if not args or '--script' not in args or '--name' not in args:
        sys.exit('usage: urbz_verify.py trace <rom> --script s.json --name scene-set '
                 '[--state in.dst] [--save out.dst] [--rtc ISO]')
    rom = args[0]
    name = _opt(args, '--name')
    out = evidence_dir('trace-' + name)
    job = dict(_start(args, rom), out=out, tag='trace',
               script=json.load(open(_opt(args, '--script'))), trace=20000)
    if _opt(args, '--save'):
        job['save'] = os.path.abspath(_opt(args, '--save'))
    res = run_child(job)
    scenes = [{'shot': s[0], 'frame': s[2], 'game_ids': s[3],
               'files': ['%05d.bin' % (g - 1) for g in s[3]],
               'image': os.path.relpath(s[1], KIT)} for s in res['shots']]
    tdir = os.path.join(HERE, 'traces')
    os.makedirs(tdir, exist_ok=True)
    tpath = os.path.join(tdir, name + '.json')
    json.dump({'name': name, 'rom': os.path.basename(rom), 'scenes': scenes}, open(tpath, 'w'), indent=1)
    n_pal = save_palettes(name, res.get('palettes', []))
    if n_pal:
        print('sprite palettes captured for %d asset(s)' % n_pal)
    for s in scenes:
        print('%-20s %4d assets used' % (s['shot'], len(s['game_ids'])))
    print('trace saved: %s  (screens in %s)' % (tpath, out))


# --------------------------------------------------------------- starting points

STATE_CACHE = os.path.join(HERE, 'states', 'cache')
NEWGAME = os.path.join(HERE, 'scripts', 'newgame.json')


def _sha1(path):
    import hashlib
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


CITY_SAV = os.path.join(HERE, 'saves', 'city.sav')
GOTO_FRAMES = 400
AREAS_JSON = os.path.join(os.path.dirname(HERE), 'docs', 'data', 'areas.json')
LOADGAME = os.path.join(HERE, 'scripts', 'loadgame.json')


def city_state(rom, rtc=None, save=None):
    """Savestate of THIS build in the city, cached per ROM hash. Savestates hold all
    of RAM including code, so a state made with another build would silently run
    that build's code instead.

    Fast path: boot with verify/saves/city.sav (a game saved in the city) and load
    it (about 2,000 frames). Without that file: play a new game (about 7,000 frames)."""
    sav = os.path.join(HERE, 'saves', save + '.sav') if save else CITY_SAV
    if save and not os.path.exists(sav):
        sys.exit('error: no save named %s (files in verify/saves/: %s)' % (save, ', '.join(
            f[:-4] for f in sorted(os.listdir(os.path.join(HERE, 'saves'))) if f.endswith('.sav'))))
    fast = os.path.exists(sav)
    tag = '%s-%s%s' % (_sha1(rom)[:12], (rtc or DEFAULT_RTC).replace(':', ''),
                       ('-' + save if save else '-sav') if fast else '')
    path = os.path.join(STATE_CACHE, tag + '.dst')
    if os.path.exists(path):
        return path
    os.makedirs(STATE_CACHE, exist_ok=True)
    out = evidence_dir('city')
    job = {'rom': os.path.abspath(rom), 'out': out, 'tag': 'city', 'rtc': rtc, 'save': path + '.tmp'}
    if fast:
        print('booting %s and loading the saved city game (about 10 s)...' % os.path.basename(rom))
        script = json.load(open(LOADGAME))
        if save:                                   # a later save opens with a goal pop-up; close it
            script += [['press', 'B'], ['wait', 60], ['shot', 'popup-closed']]
        job.update(script=script, sav=sav)
    else:
        print('cold-booting %s into the city via a new game (about 2 minutes)...' % os.path.basename(rom))
        job.update(script=json.load(open(NEWGAME)))
    run_child(job)
    os.replace(path + '.tmp', path)
    return path


def _start(args, rom):
    """Common start options: --state F, --city (cached city state for this ROM),
    --sav F (boot with a save file), --rtc ISO."""
    rtc = _opt(args, '--rtc')
    job = {'rom': os.path.abspath(rom), 'rtc': rtc}
    if '--city' in args or _opt(args, '--from'):
        job['state'] = city_state(rom, rtc, _opt(args, '--from'))
    elif _opt(args, '--state'):
        job['state'] = os.path.abspath(_opt(args, '--state'))
        if os.path.exists(job['state']) and not _state_matches(job['state'], rom):
            print('warning: %s was not made with this ROM; savestates contain the game code, '
                  'so code mods will not run from it (use --city)' % os.path.basename(job['state']))
    if _opt(args, '--sav'):
        job['sav'] = os.path.abspath(_opt(args, '--sav'))
    if _opt(args, '--poke'):
        job['poke'] = _opt(args, '--poke', many=True)
    if _opt(args, '--goto'):
        a, _, e = _opt(args, '--goto').partition(':')
        if not e:
            pts = json.load(open(AREAS_JSON))['areas'][int(a)]['entry_points']
            e = pts[0]['id'] if pts else 0
        job['goto'] = (int(a), int(e))
    return job


def _state_matches(state, rom):
    """A savestate holds the game code. One made with another build is fine
    unless this ROM's code (arm9/arm7) differs from the original game's."""
    if os.path.basename(state).startswith(_sha1(rom)[:12]) or not os.path.exists(DEFAULT_REF):
        return True
    return _code_bytes(rom) == _code_bytes(DEFAULT_REF)


def _code_bytes(path):
    with open(path, 'rb') as f:
        h = f.read(0x200)
        out = b''
        for off in (0x20, 0x30):
            o, _, _, n = struct.unpack_from('<4I', h, off)
            f.seek(o)
            out += f.read(n)
    return out


def cmd_city(args):
    rom = args[0] if args and not args[0].startswith('--') else DEFAULT_ROM
    print('city state: ' + city_state(rom, _opt(args, '--rtc'), _opt(args, '--from')))


# --------------------------------------------------------------- reverse-engineering helpers

def _parse_cond(c):
    if ':' in c:
        k, v = c.split(':', 1)
        if k == 'range':
            lo, hi = (int(x, 0) for x in v.split('-'))
            return lambda prev, cur: lo <= cur <= hi
        n = int(v, 0)
        return {'eq': lambda p, c: c == n, 'ne': lambda p, c: c != n,
                'add': lambda p, c: c == p + n, 'sub': lambda p, c: c == p - n}[k]
    return {'inc': lambda p, c: c > p, 'dec': lambda p, c: c < p, 'same': lambda p, c: c == p,
            'changed': lambda p, c: c != p, 'any': lambda p, c: True}[c]


def cmd_find(args):
    """Cheat-engine style search: snapshot RAM at every 'shot' in the script and
    keep addresses whose values pass each shot's test."""
    if not args or '--script' not in args:
        sys.exit('usage: urbz_verify.py find <rom> (--state F|--city|--sav F) --script s.json '
                 '--test SHOT=COND [--test ...] [--size 1|2|4] [--range ADDR:LEN]\n'
                 'COND: eq:N ne:N add:N sub:N range:A-B inc dec same changed any')
    rom = args[0]
    size = int(_opt(args, '--size', '4'))
    rng = _opt(args, '--range', '0x02000000:0x400000')
    tests = {}
    for t in _opt(args, '--test', many=True):
        name, cond = t.split('=', 1)
        tests.setdefault(name, []).append(_parse_cond(cond))
    out = evidence_dir('find')
    res = run_child(dict(_start(args, rom), out=out, tag='find',
                         script=json.load(open(_opt(args, '--script'))), snap=[rng]))
    base = int(rng.split(':')[0], 0)
    fmt = {1: 'B', 2: 'H', 4: 'I'}[size]
    import array
    vals = []
    for name, files in res['snaps']:
        a = array.array(fmt)
        a.frombytes(open(files[0], 'rb').read())
        vals.append((name, a))
    cand = range(len(vals[0][1]))
    for i, (name, a) in enumerate(vals):
        conds = tests.get(name, [])
        if not conds:
            continue
        prev = vals[i - 1][1] if i else a
        cand = [k for k in cand if all(c(prev[k], a[k]) for c in conds)]
    lines = ['%d candidate(s) (size %d)' % (len(cand), size),
             'address    ' + ' '.join('%10s' % n[:10] for n, _ in vals)]
    for k in list(cand)[:200]:
        lines.append('%08x   ' % (base + k * size) + ' '.join('%10d' % a[k] for _, a in vals))
    open(os.path.join(out, 'report.txt'), 'w').write('\n'.join(lines) + '\n')
    for name, files in res['snaps']:
        for f in files:
            os.remove(f)
    print('\n'.join(lines[:60]))
    print('evidence: ' + out)


def cmd_watch(args):
    """Run a script with exec/read/write hooks and log who touches what."""
    if not args or '--hook' not in args:
        sys.exit('usage: urbz_verify.py watch <rom> (--state F|--city|--sav F) [--script s.json] '
                 '[--frames N] --hook exec:ADDR|read:ADDR[:SIZE]|write:ADDR[:SIZE] [--hook ...] '
                 '[--stack] [--r0 VALUE]')
    rom = args[0]
    script = json.load(open(_opt(args, '--script'))) if _opt(args, '--script') else []
    if _opt(args, '--frames'):
        script = script + [['wait', int(_opt(args, '--frames'))]]
    out = evidence_dir('watch')
    res = run_child(dict(_start(args, rom), out=out, tag='watch', script=script,
                         watch=_opt(args, '--hook', many=True), stack='--stack' in args,
                         only_r0=int(_opt(args, '--r0'), 0) if _opt(args, '--r0') else None))
    w = res['watch']
    lines = ['%-20s %d hits' % (k, n) for k, n in sorted(w['counts'].items())]
    import collections
    who = collections.Counter((h[1], h[3], h[4]) for h in w['hits'])
    lines += ['', 'who (first %d hits):  kind   pc        lr        count' % len(w['hits'])]
    lines += ['                      %-5s  %08x  %08x  %d' % (k, pc, lr, n)
              for (k, pc, lr), n in who.most_common(40)]
    lines.append('')
    lines.append(' frame  kind   addr      pc        lr        r0        value')
    for h in w['hits']:
        f, kind, addr, pc, lr, r0, v = h[:7]
        lines.append('%6d  %-5s  %08x  %08x  %08x  %08x  %s' % (f, kind, addr, pc, lr, r0,
                                                              '' if v is None else v))
        if len(h) > 7:
            lines.append('        stack: ' + ' '.join('%08x' % x for x in h[7]))
    open(os.path.join(out, 'report.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:80]))
    print('evidence: ' + out)


def save_palettes(name, found):
    """Map captured (stream head, 16 colours) pairs to asset numbers using the
    project, and write verify/palettes/NAME.json = {asset: [16 BGR555 colours]}."""
    if not found:
        return 0
    import bisect, collections
    proj = os.path.join(KIT, 'project')
    m = json.load(open(os.path.join(proj, 'manifest.json')))
    blobs = [open(os.path.join(proj, 'assets', e['file']), 'rb').read() for e in m['entries']]
    big = b''.join(blobs)
    starts, p = [], 0
    for b in blobs:
        starts.append(p)
        p += len(b)
    votes = collections.defaultdict(collections.Counter)
    for head, cols in found:
        i = big.find(bytes.fromhex(head))
        if i >= 0:
            votes[bisect.bisect_right(starts, i) - 1][tuple(cols)] += 1
    out = {'%05d' % a: list(c.most_common(1)[0][0]) for a, c in votes.items()}
    pdir = os.path.join(HERE, 'palettes')
    os.makedirs(pdir, exist_ok=True)
    json.dump(out, open(os.path.join(pdir, name + '.json'), 'w'), indent=0)
    return len(out)


def main(argv):
    if argv and argv[0] == '_child':
        return child_main(argv[1:])
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmds = {'doctor': cmd_doctor, 'smoke': cmd_smoke, 'ram': cmd_ram, 'play': cmd_play,
            'trace': cmd_trace, 'city': cmd_city, 'find': cmd_find, 'watch': cmd_watch}
    if argv[0] not in cmds:
        sys.exit('unknown command %s. Run: python verify/urbz_verify.py help' % argv[0])
    cmds[argv[0]](argv[1:])


if __name__ == '__main__':
    main(sys.argv[1:])
