#!/usr/bin/env python3
"""Put mods' code into the game: place compiled C blobs and apply hooks.

Called by urbz_build.py. Needs no compiler: each code mod ships its compiled
blob (mods/<mod>/code/build/patch.bin + patch.json, made by urbz_patch.py).

Where the code goes
  The game's main program (arm9) loads at 0x02000000. At boot, the SDK start-up
  code copies "autoload" blocks to their RAM addresses, then the heap starts at
  0x0214DE20 (the arena-lo literal at 0x020B7D88). We add one more autoload
  block at 0x0214DE20 holding every mod's blob (and hook trampolines), and move
  the heap start up by that size. See docs/systems.md.

hooks.txt (one per line, # comments)
  call ADDR func     ADDR holds a BL/BLX: make it call func instead.
  jump ADDR func     ADDR is a function's first instruction: replace the whole function.
  wrap ADDR func     Run func (same r0-r3), then the original instruction at ADDR
                     (ARM code only; refused if that instruction uses PC).
  data ADDR hex...   Write bytes, e.g.  data 0x02113B60 01 0F
  u8|u16|u32 ADDR V  Write a number (little-endian).
ADDR may also be a name from code/game.sym (e.g. time_add), or name+offset.
"""
import json, os, struct

CODE_BASE = 0x0214DE20          # end of the game's zero-initialised data (BSS)
ARENA_LO_LITERAL = 0x020B7D88   # OS_GetInitArenaLo(main) returns this word
MODULE_PARAMS = 0x02000ADC
BSS = (0x02121AC0, 0x0214DE20)
HEAP_COMFORT = 128 * 1024       # warn above this (see docs/systems.md, heap budget)
KIT = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(KIT, 'code', 'core')
# Mod table (code/include/mod.h): at CODE_BASE whenever the core is built in.
EVENT_NAMES = ['mod_on_boot', 'mod_on_tick', 'mod_on_minute', 'mod_on_area_enter', 'mod_on_save',
               'mod_on_load', 'mod_on_enable', 'mod_on_disable', 'mod_on_page']
TABLE_MAGIC = 0x43444F4D        # 'MODC'
TABLE_HEADER, TABLE_ROW = 32, 80
MODF_TOGGLE, MODF_EVENTS, MODF_DEFAULT_ON = 1, 2, 4
MAX_SWITCHES = 12               # entries in the switch record (save memory 0x1FE0)


class CodeError(Exception):
    pass


# ---------------------------------------------------------------- inputs

def game_symbols(kit=KIT):
    """code/game.sym: 'name = 0xADDR  # comment' lines (names found by RE)."""
    out = {}
    p = os.path.join(kit, 'code', 'game.sym')
    if os.path.exists(p):
        for line in open(p):
            line = line.split('#', 1)[0].strip()
            if '=' in line:
                k, v = line.split('=', 1)
                out[k.strip()] = int(v.strip(), 0)
    return out


def function_map(kit=KIT):
    """code/functions.json: [[addr, end, thumb], ...] from the Ghidra export."""
    p = os.path.join(kit, 'code', 'functions.json')
    return json.load(open(p)) if os.path.exists(p) else []


def parse_hooks(path, syms):
    hooks = []
    for ln, line in enumerate(open(path, encoding='utf-8-sig'), 1):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        p = line.split()
        where = '%s line %d' % (path, ln)
        kind = p[0].lower()
        if kind not in ('call', 'jump', 'wrap', 'data', 'u8', 'u16', 'u32') or len(p) < 3:
            raise CodeError('%s: expected "call|jump|wrap|data|u8|u16|u32 ADDR ..."' % where)
        addr = _address(p[1], syms, where)
        if kind == 'data':
            try:
                arg = bytes.fromhex(''.join(p[2:]))
            except ValueError:
                raise CodeError('%s: data must be hex bytes' % where)
        elif kind in ('u8', 'u16', 'u32'):
            n = {'u8': 1, 'u16': 2, 'u32': 4}[kind]
            arg = (int(p[2], 0) & ((1 << 8 * n) - 1)).to_bytes(n, 'little')
            kind = 'data'
        else:
            arg = p[2]
        hooks.append((kind, addr, arg, where))
    return hooks


def _address(text, syms, where):
    """0x02000000, a game.sym name, or name+offset."""
    name, _, off = text.partition('+')
    try:
        base = int(name, 0)
    except ValueError:
        if name not in syms:
            raise CodeError('%s: unknown address or game symbol "%s"' % (where, name))
        base = syms[name]
    try:
        return base + (int(off, 0) if off else 0)
    except ValueError:
        raise CodeError('%s: bad offset in "%s"' % (where, text))


def mod_info(md):
    """mod.json with defaults (every field is optional)."""
    p = os.path.join(md, 'mod.json')
    try:
        info = json.load(open(p, encoding='utf-8-sig')) if os.path.exists(p) else {}
    except ValueError as e:
        raise CodeError('%s is not valid JSON: %s' % (p, e))
    name = os.path.basename(os.path.normpath(md))
    code = os.path.isdir(os.path.join(md, 'code'))
    out = {'name': info.get('name', name), 'version': str(info.get('version', '')),
           'author': info.get('author', ''), 'description': info.get('description', ''),
           'toggle': bool(info.get('toggle', code)), 'default': bool(info.get('default', True)),
           'conflicts': list(info.get('conflicts', [])), 'save_bytes': int(info.get('save_bytes', 0))}
    if not 0 <= out['save_bytes'] <= 0xFFFF:
        raise CodeError('%s: save_bytes must be 0..65535' % p)
    return out


SAVE_BUDGET = 1024              # bytes of mod data per save slot we plan for (docs/systems.md)


def check_mod_set(mod_dirs):
    """Conflicts and save space for a set of enabled mods. -> warning lines; raises CodeError."""
    infos = [(os.path.basename(os.path.normpath(d)), mod_info(d)) for d in mod_dirs]
    names = {n for n, _ in infos}
    for n, info in infos:
        clash = [c for c in info['conflicts'] if c in names and c != n]
        if clash:
            raise CodeError('mod "%s" conflicts with %s (see its mod.json); turn one of them off'
                            % (n, ', '.join('"%s"' % c for c in clash)))
    total = sum(info['save_bytes'] + 6 for _, info in infos if info['save_bytes'])
    out = []
    if total:
        total += 10
        if total > SAVE_BUDGET:
            out.append('warning: mods ask for %d bytes of save space per slot; the planned budget is '
                       '%d (a save that runs out keeps the game\'s data and skips mod data)'
                       % (total, SAVE_BUDGET))
    return out


def name_hash(name):
    """FNV-1a (32-bit) of the mod's folder name: how saves and the switch record know a mod."""
    h = 0x811C9DC5
    for b in name.encode('utf-8'):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h or 1


def load_code_mods(mod_dirs, syms):
    """-> list of dicts for mods that have a code/ folder (or are a code folder: the core)."""
    mods = []
    for md in mod_dirs:
        cdir = os.path.join(md, 'code')
        if not os.path.isdir(cdir):
            if not os.path.exists(os.path.join(md, 'hooks.txt')):
                continue
            cdir = md
        name = os.path.basename(os.path.normpath(md))
        m = {'name': name, 'blob': b'', 'relocs': [], 'symbols': {}, 'bss': 0, 'hooks': [],
             'meta': mod_info(md)}
        hp = os.path.join(cdir, 'hooks.txt')
        if os.path.exists(hp):
            m['hooks'] = parse_hooks(hp, syms)
        bp, jp = os.path.join(cdir, 'build', 'patch.bin'), os.path.join(cdir, 'build', 'patch.json')
        if os.path.exists(bp):
            if not os.path.exists(jp):
                raise CodeError('mod "%s": code/build/patch.json is missing; rebuild with '
                                'python urbz_patch.py build %s' % (name, name))
            info = json.load(open(jp))
            m.update(blob=open(bp, 'rb').read(), relocs=info['relocs'],
                     symbols=info['symbols'], bss=info.get('bss', 0))
            stale = _stale_sources(cdir, info)
            if stale:
                print('warning: mod "%s": %s changed since the last code build; '
                      'run: python urbz_patch.py build %s' % (name, ', '.join(stale), name))
        elif any(f.endswith(('.c', '.s', '.S')) for f in os.listdir(cdir)):
            raise CodeError('mod "%s" has C/assembly source but no compiled code/build/patch.bin; '
                            'run: python urbz_patch.py build %s' % (name, name))
        m['events'] = [m['symbols'].get(e) for e in EVENT_NAMES]
        if m['blob'] or m['hooks']:
            mods.append(m)
    return mods


def _stale_sources(cdir, info):
    import hashlib
    out = []
    for f, sha in info.get('sources', {}).items():
        p = os.path.join(cdir, f)
        if not os.path.exists(p) or hashlib.sha1(open(p, 'rb').read()).hexdigest() != sha:
            out.append(f)
    return out


# ---------------------------------------------------------------- encodings

def _arm_branch(site, target, link):
    """B/BL/BLX from ARM code at site to target (bit 0 set = Thumb target)."""
    if target & 1:
        if not link:
            raise CodeError('an ARM B cannot switch to Thumb at %08x' % site)
        off = (target & ~1) - (site + 8)
        return struct.pack('<I', 0xFA000000 | ((off >> 1) & 1) << 24 | (off >> 2) & 0xFFFFFF)
    off = target - (site + 8)
    if off & 3 or not -(1 << 25) <= off < (1 << 25):
        raise CodeError('branch from %08x to %08x is out of range' % (site, target))
    return struct.pack('<I', (0xEB if link else 0xEA) << 24 | (off >> 2) & 0xFFFFFF)


def _thumb_bl(site, target):
    """BL (to Thumb) or BLX (to ARM) pair at Thumb site."""
    if target & 1:
        off = (target & ~1) - (site + 4)
        lo = 0xF800
    else:
        off = target - ((site + 4) & ~3)
        lo = 0xE800
    if not -(1 << 22) <= off < (1 << 22):
        raise CodeError('Thumb call from %08x to %08x is out of range' % (site, target))
    return struct.pack('<HH', 0xF000 | (off >> 12) & 0x7FF, lo | (off >> 1) & 0x7FF)


def _is_arm_call(w):
    return (w >> 24) == 0xEB or (w >> 25) == 0x7D


def _is_thumb_call(h1, h2):
    return (h1 & 0xF800) == 0xF000 and (h2 & 0xE800) == 0xE800


LDR_PC_PC_M4 = 0xE51FF004       # ldr pc, [pc, #-4]


def _wrap_trampoline(t, site, orig, func):
    """Run func with the caller's r0-r3 (flags preserved), then the moved
    instruction, then continue after the hook site."""
    words = [0xE92D500F,        # stmfd sp!, {r0-r3, r12, lr}
             0xE10FC000,        # mrs   r12, cpsr
             0xE92D5000,        # stmfd sp!, {r12, lr}
             0xE59FC018,        # ldr   r12, [pc, #24]   -> func
             0xE12FFF3C,        # blx   r12
             0xE8BD5000,        # ldmfd sp!, {r12, lr}
             0xE128F00C,        # msr   cpsr_f, r12
             0xE8BD500F,        # ldmfd sp!, {r0-r3, r12, lr}
             orig,              # the instruction we replaced
             LDR_PC_PC_M4,      # back to site + 4
             site + 4,
             func]
    return struct.pack('<12I', *words)


def _uses_pc(code, addr):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.detail = True
    for i in md.disasm(code, addr):
        r, w = i.regs_access()
        names = {i.reg_name(x) for x in r + w}
        return 'pc' in names or i.group(capstone.CS_GRP_JUMP) or i.group(capstone.CS_GRP_CALL)
    return True                 # undecodable: refuse


# ---------------------------------------------------------------- arm9 image

class Arm9:
    """The game's code sections, addressable by RAM address."""

    def __init__(self, data):
        import ndspy.code
        self.mcf = ndspy.code.MainCodeFile(data, 0x02000000, MODULE_PARAMS)
        self.patched = []           # (start, end, who)

    def locate(self, addr, n):
        for s in self.mcf.sections:
            if s.ramAddress <= addr and addr + n <= s.ramAddress + len(s.data):
                return s, addr - s.ramAddress
        if BSS[0] <= addr < BSS[1]:
            raise CodeError('%08x is in the game\'s zeroed data (BSS), not code' % addr)
        raise CodeError('%08x is not inside the game\'s code' % addr)

    def read(self, addr, n):
        s, o = self.locate(addr, n)
        return bytes(s.data[o:o + n])

    def write(self, addr, b, who):
        for a0, a1, w in self.patched:
            if addr < a1 and a0 < addr + len(b):
                raise CodeError('%s and %s both patch %08x' % (w, who, max(a0, addr)))
        s, o = self.locate(addr, len(b))
        d = bytearray(s.data)
        d[o:o + len(b)] = b
        s.data = bytes(d)
        self.patched.append((addr, addr + len(b), who))

    def reserve(self, addr, n, who):
        """Claim bytes the core will write at runtime (switchable data hooks)."""
        self.locate(addr, n)
        for a0, a1, w in self.patched:
            if addr < a1 and a0 < addr + n:
                raise CodeError('%s and %s both patch %08x' % (w, who, max(a0, addr)))
        self.patched.append((addr, addr + n, who))

    def add_section(self, data, ram, bss):
        import ndspy.code
        self.mcf.sections.append(ndspy.code.MainCodeFile.Section(data, ram, bss, implicit=False))

    def save(self):
        return self.mcf.save(compress=False)


def _mode_at(fmap, addr):
    import bisect
    keys = [f[0] for f in fmap]
    i = bisect.bisect_right(keys, addr) - 1
    if i >= 0 and fmap[i][0] <= addr < fmap[i][1]:
        return fmap[i]
    return None


def _call_target(a9, fmap, site):
    """Where the BL/BLX at site goes (bit 0 set = Thumb)."""
    fn = _mode_at(fmap, site)
    if fn and fn[2]:
        h1, h2 = struct.unpack('<HH', a9.read(site, 4))
        off = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
        off -= (1 << 23) if off & (1 << 22) else 0
        if (h2 & 0xF800) == 0xF800:
            return (site + 4 + off) | 1
        return ((site + 4) & ~3) + off
    w = struct.unpack('<I', a9.read(site, 4))[0]
    off = (w & 0xFFFFFF) << 2
    off -= (1 << 26) if off & (1 << 25) else 0
    if (w >> 25) == 0x7D:                       # BLX imm: to Thumb, H bit = half-word
        return (site + 8 + off + ((w >> 23) & 2)) | 1
    return site + 8 + off


def _ldr_pc_rel(cond, rd, at, lit):
    """ldr<cond> rd, [pc, #lit - (at + 8)] (lit after at)."""
    off = lit - (at + 8)
    if not 0 <= off < 4096:
        raise CodeError('internal: literal out of range')
    return (cond << 28) | 0x059F0000 | (rd << 12) | off


AL, NE = 0xE, 0x1


def _switch_call_stub(at, chain, orig):
    """At a call site: the first switched-on mod in chain [(on_addr, func)] gets the call,
    else the original target. Uses r12 and the flags only (both free at a call)."""
    k = len(chain)
    n_ins = 4 * k + 1
    lit = at + 4 * n_ins
    words = []
    for i, (on, func) in enumerate(chain):
        on_lit, fn_lit = lit + 8 * i, lit + 8 * i + 4
        words += [_ldr_pc_rel(AL, 12, at + 4 * len(words), on_lit),
                  0xE5DCC000,                 # ldrb r12, [r12]
                  0xE35C0000]                 # cmp  r12, #0
        words.append(_ldr_pc_rel(NE, 15, at + 4 * len(words), fn_lit))
    words.append(_ldr_pc_rel(AL, 15, at + 4 * len(words), lit + 8 * k))
    for on, func in chain:
        words += [on, func]
    words.append(orig)
    return struct.pack('<%dI' % len(words), *words)


def _switch_wrap_trampoline(t, site, orig, func, on):
    """Like _wrap_trampoline, but only calls func while the mod's switch byte is on."""
    words = [0xE92D500F,        # stmfd sp!, {r0-r3, r12, lr}
             0xE10FC000,        # mrs   r12, cpsr
             0xE92D5000,        # stmfd sp!, {r12, lr}
             0xE59F0024,        # ldr   r0, [pc, #36]   -> on
             0xE5D00000,        # ldrb  r0, [r0]
             0xE3500000,        # cmp   r0, #0
             0x159FC01C,        # ldrne r12, [pc, #28]  -> func
             0x112FFF3C,        # blxne r12
             0xE8BD5000,        # ldmfd sp!, {r12, lr}
             0xE128F00C,        # msr   cpsr_f, r12
             0xE8BD500F,        # ldmfd sp!, {r0-r3, r12, lr}
             orig,              # the instruction we replaced
             LDR_PC_PC_M4,      # back to site + 4
             site + 4,
             on,
             func]
    return struct.pack('<16I', *words)


def _switch_jump_stub(at, site, orig2, func, on):
    """A replaced ARM function: func while on, else the 2 moved instructions and the rest."""
    words = [_ldr_pc_rel(AL, 12, at, at + 28),
             0xE5DCC000, 0xE35C0000,
             _ldr_pc_rel(NE, 15, at + 12, at + 32),
             orig2[0], orig2[1],
             _ldr_pc_rel(AL, 15, at + 24, at + 36),
             on, func, site + 8]
    return struct.pack('<10I', *words)


WRAP_SIZE, SWITCH_WRAP_SIZE, SWITCH_JUMP_SIZE = 48, 64, 40


def _branches_to(a9, fn, addr):
    """Does any branch inside function fn jump to addr?"""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.detail = True
    for i in md.disasm(a9.read(fn[0], fn[1] - fn[0]), fn[0]):
        if i.group(capstone.CS_GRP_JUMP) and i.op_str.startswith('#') and \
                int(i.op_str[1:], 16) == addr:
            return True
    return False


def apply_code(arm9_data, mods, fmap, core=None):
    """-> (new arm9 bytes, report lines). Raises CodeError on any problem.

    core: the mod core (load_code_mods of CORE_DIR). It is built in when any mod can be
    switched in-game or uses events; then the mod table sits at CODE_BASE and switchable
    mods' hooks go through stubs that test their switch byte (code/include/mod.h)."""
    a9 = Arm9(arm9_data)
    report = []
    for m in mods:
        m.setdefault('meta', {'toggle': False, 'default': True, 'version': '', 'save_bytes': 0})
        m.setdefault('events', [None] * len(EVENT_NAMES))
    use_core = core is not None and any(m['meta']['toggle'] or any(m['events']) for m in mods)
    switchable = [m for m in mods if use_core and m['meta']['toggle']]
    if len(switchable) > MAX_SWITCHES:
        report.append('warning: %d switchable mods; the switch record keeps %d (the rest always '
                      'start at their default)' % (len(switchable), MAX_SWITCHES))
    placed = ([core] if use_core else []) + mods

    # 1. Plan the region: [mod table] [patch data] [stubs + trampolines] [core] [mods].
    region = bytearray(TABLE_HEADER + TABLE_ROW * len(mods) if use_core else 0)
    row_addr = {id(m): CODE_BASE + TABLE_HEADER + TABLE_ROW * i for i, m in enumerate(mods)}
    patches = {id(m): [] for m in mods}             # [(addr, orig, new, desc_addr)]
    for m in switchable:
        for kind, addr, arg, where in m['hooks']:
            if kind == 'data':
                patches[id(m)].append([addr, arg])
    for m in switchable:
        for pt in patches[id(m)]:
            pt.append(CODE_BASE + len(region))      # descriptor {addr, len, orig*, mod*}
            region += bytes(16)
    for m in switchable:
        for pt in patches[id(m)]:
            addr, new = pt[0], pt[1]
            orig = a9.read(addr, len(new))
            pt.append(CODE_BASE + len(region))
            region += orig + bytes(-len(orig) % 4)
            pt.append(CODE_BASE + len(region))
            region += new + bytes(-len(new) % 4)
            o = pt[2] - CODE_BASE
            struct.pack_into('<4I', region, o, addr, len(new), pt[3], pt[4])
    # call sites: group switchable mods' call hooks per address (a chain)
    call_sites = {}
    for m in switchable:
        for kind, addr, arg, where in m['hooks']:
            if kind == 'call':
                call_sites.setdefault(addr, []).append((m, arg, where))
    stub_at = {}
    for addr, chain in call_sites.items():
        stub_at[addr] = CODE_BASE + len(region)
        region += bytes(4 * (4 * len(chain) + 1) + 4 * (2 * len(chain) + 1))
    tramp_at = {}
    for m in placed:
        for h in m['hooks']:
            kind = h[0]
            if kind == 'wrap':
                tramp_at[(id(m), h[1])] = CODE_BASE + len(region)
                region += bytes(SWITCH_WRAP_SIZE if m in switchable else WRAP_SIZE)
            elif kind == 'jump' and m in switchable:
                fn = _mode_at(fmap, h[1])
                if fn and fn[2]:
                    raise CodeError('%s: a jump hook on Thumb code can\'t be switched in-game; '
                                    'set "toggle": false in mod.json' % h[3])
                tramp_at[(id(m), h[1])] = CODE_BASE + len(region)
                region += bytes(SWITCH_JUMP_SIZE)
    for m in placed:
        if not m['blob']:
            m['base'] = None
            continue
        while len(region) % 8:
            region.append(0)
        m['base'] = CODE_BASE + len(region)
        blob = bytearray(m['blob'])
        for off in m['relocs']:
            v = struct.unpack_from('<I', blob, off)[0]
            struct.pack_into('<I', blob, off, v + m['base'])
        region += blob + bytes(m['bss'])

    def resolve(m, name, where):
        if name not in m['symbols']:
            raise CodeError('%s: "%s" is not a function in mod "%s" (rebuild it, or check the '
                            'name)' % (where, name, m['name']))
        return m['base'] + m['symbols'][name]

    # 2. Hooks.
    for addr, chain in call_sites.items():
        fn = _mode_at(fmap, addr)
        thumb = bool(fn and fn[2])
        if thumb:
            h1, h2 = struct.unpack('<HH', a9.read(addr, 4))
            ok = _is_thumb_call(h1, h2)
        else:
            ok = _is_arm_call(struct.unpack('<I', a9.read(addr, 4))[0])
        if not ok:
            raise CodeError('%s: %08x is not a call (BL) instruction' % (chain[0][2], addr))
        orig = _call_target(a9, fmap, addr)
        links = []
        for m, arg, where in chain:
            if m['base'] is None:
                raise CodeError('%s: "call" needs compiled code; run python urbz_patch.py build %s'
                                % (where, m['name']))
            links.append((row_addr[id(m)] + 28, resolve(m, arg, where)))
        st = stub_at[addr]
        o = st - CODE_BASE
        stub = _switch_call_stub(st, links, orig)
        region[o:o + len(stub)] = stub
        who = ' + '.join('%s (%s)' % (m['name'], w) for m, _, w in chain)
        a9.write(addr, _thumb_bl(addr, st) if thumb else _arm_branch(addr, st, True), who)
    for m in placed:
        sw = m in switchable
        for kind, addr, arg, where in m['hooks']:
            who = '%s (%s)' % (m['name'], where)
            if kind == 'data':
                if sw:
                    a9.reserve(addr, len(arg), who)     # the core writes it at boot / when switched
                else:
                    a9.write(addr, arg, who)
                continue
            if sw and kind == 'call':
                continue                                 # done above (stub chain)
            if m['base'] is None:
                raise CodeError('%s: "%s" needs compiled code; run python urbz_patch.py build %s'
                                % (where, kind, m['name']))
            target = resolve(m, arg, where)
            fn = _mode_at(fmap, addr)
            thumb = bool(fn and fn[2])
            if kind == 'call':
                if thumb:
                    h1, h2 = struct.unpack('<HH', a9.read(addr, 4))
                    if not _is_thumb_call(h1, h2):
                        raise CodeError('%s: %08x is not a call (BL) instruction' % (where, addr))
                    a9.write(addr, _thumb_bl(addr, target), who)
                else:
                    w = struct.unpack('<I', a9.read(addr, 4))[0]
                    if not _is_arm_call(w):
                        raise CodeError('%s: %08x is not a call (BL) instruction' % (where, addr))
                    a9.write(addr, _arm_branch(addr, target, True), who)
            elif kind == 'jump':
                if not fn or fn[0] != addr:
                    raise CodeError('%s: %08x is not the start of a known function' % (where, addr))
                if sw:
                    st = tramp_at[(id(m), addr)]
                    orig2 = struct.unpack('<2I', a9.read(addr, 8))
                    for k in range(2):
                        if _uses_pc(a9.read(addr + 4 * k, 4), addr + 4 * k):
                            raise CodeError('%s: the function at %08x starts with an instruction '
                                            'that uses PC, so it can\'t be switched off; set '
                                            '"toggle": false in mod.json' % (where, addr))
                    if _branches_to(a9, fn, addr + 4):
                        raise CodeError('%s: the function at %08x branches back to its 2nd '
                                        'instruction, so it can\'t be switched off; set "toggle": '
                                        'false in mod.json' % (where, addr))
                    o = st - CODE_BASE
                    region[o:o + SWITCH_JUMP_SIZE] = _switch_jump_stub(
                        st, addr, orig2, target, row_addr[id(m)] + 28)
                    target = st
                if thumb:
                    # bx pc must sit 2 bytes before a word-aligned ARM ldr pc,[pc,#-4].
                    half = [0x4778, 0x46C0] if addr % 4 == 0 else [0x46C0, 0x4778, 0x46C0]
                    stub = struct.pack('<%dH' % len(half), *half) + \
                        struct.pack('<II', LDR_PC_PC_M4, target)
                else:
                    stub = struct.pack('<II', LDR_PC_PC_M4, target)
                if fn[1] - addr < len(stub):
                    raise CodeError('%s: function at %08x is too small to replace' % (where, addr))
                a9.write(addr, stub, who)
            elif kind == 'wrap':
                if thumb:
                    raise CodeError('%s: wrap only works in ARM code; %08x is Thumb' % (where, addr))
                orig = a9.read(addr, 4)
                if _uses_pc(orig, addr):
                    raise CodeError('%s: the instruction at %08x uses PC (a branch or literal '
                                    'load); wrap the next instruction or use call' % (where, addr))
                t = tramp_at[(id(m), addr)]
                o = t - CODE_BASE
                ow = struct.unpack('<I', orig)[0]
                if sw:
                    region[o:o + SWITCH_WRAP_SIZE] = _switch_wrap_trampoline(
                        t, addr, ow, target, row_addr[id(m)] + 28)
                else:
                    region[o:o + WRAP_SIZE] = _wrap_trampoline(t, addr, ow, target)
                a9.write(addr, _arm_branch(addr, t, False), who)
        n = len(m['blob']) + m['bss']
        report.append('%s %s: %d hook(s)%s%s' % (
            'mod core' if m is core else 'code mod', m['name'], len(m['hooks']),
            ', %d bytes at %08x' % (n, m['base']) if m['base'] else '',
            ', switchable in-game' if sw else ''))

    # 3. The mod table.
    if use_core:
        struct.pack_into('<IHHI', region, 0, TABLE_MAGIC, 1, len(mods), TABLE_ROW)
        for i, m in enumerate(mods):
            meta = m['meta']
            o = row_addr[id(m)] - CODE_BASE
            name = m['name'].encode('ascii', 'replace')[:15]
            ver = meta.get('version', '').encode('ascii', 'replace')[:7]
            sw = m in switchable
            flags = (MODF_TOGGLE if sw else 0) | (MODF_EVENTS if any(m['events']) else 0) | \
                (MODF_DEFAULT_ON if meta['default'] else 0)
            on = 1 if (not sw or meta['default']) else 0
            pl = patches[id(m)]
            ev = [(m['base'] + v) if v is not None and m['base'] is not None else 0
                  for v in m['events']]
            struct.pack_into('<16s8sIBBBBHHI9II', region, o, name, ver, name_hash(m['name']),
                             on, flags, i, 0, meta.get('save_bytes', 0), len(pl),
                             pl[0][2] if pl else 0, *ev, 0)
        report.append('mod table at %08x: %d mod(s), %d switchable' % (
            CODE_BASE, len(mods), len(switchable)))

    # 4. New autoload section + move the heap up.
    # At boot the section's bytes sit inside the game's BSS (from about
    # 0x02123700) and are copied out before BSS is cleared; past ~160 KB the
    # copy would overlap its own destination.
    if len(region) > 160 * 1024:
        raise CodeError('code mods total %d KB; the limit is 160 KB' % (len(region) // 1024))
    if len(region) > HEAP_COMFORT:
        report.append('warning: code mods take %d KB from the game heap (measured headroom in '
                      'the city is about 1.4 MB; see docs/systems.md)' % (len(region) // 1024))
    if region:
        while len(region) % 32:
            region.append(0)
        lit = struct.unpack('<I', a9.read(ARENA_LO_LITERAL, 4))[0]
        if lit != CODE_BASE:
            raise CodeError('unexpected heap-start literal %08x (is this the USA ROM?)' % lit)
        data = bytes(region).rstrip(b'\0')
        data += bytes(-len(data) % 4)
        a9.add_section(data, CODE_BASE, len(region) - len(data))
        a9.write(ARENA_LO_LITERAL, struct.pack('<I', CODE_BASE + len(region)), 'heap start')
        report.append('code region %08x-%08x (%d bytes); heap now starts at %08x'
                      % (CODE_BASE, CODE_BASE + len(region), len(region), CODE_BASE + len(region)))
    return a9.save(), report


# ---------------------------------------------------------------- ROM image

def put_arm9(img, arm9):
    """Write a new arm9 into the cartridge image. If it no longer fits before
    arm7, move arm7 + file-name table + FAT + banner to the end of the image."""
    off, entry, load, size = struct.unpack_from('<4I', img, 0x20)
    footer = bytes(img[off + size:off + size + 12])
    has_footer = struct.unpack_from('<I', footer)[0] == 0xDEC00621
    need = len(arm9) + (12 if has_footer else 0)
    arm7_off = struct.unpack_from('<I', img, 0x30)[0]
    if off + need > arm7_off:
        fnt, fat, banner = (struct.unpack_from('<I', img, x)[0] for x in (0x40, 0x48, 0x68))
        fat_size = struct.unpack_from('<I', img, 0x4C)[0]
        ver = struct.unpack_from('<H', img, banner)[0]
        bsize = {1: 0x840, 2: 0x940, 3: 0xA40}.get(ver, 0x23C0)
        blk_start, blk_end = arm7_off, max(banner + bsize, fat + fat_size)
        used = struct.unpack_from('<I', img, 0x80)[0]
        new = (used + 0x1FF) & ~0x1FF
        delta = new - blk_start
        block = bytes(img[blk_start:blk_end])
        end = new + len(block)
        cap = img[0x14]
        while (0x20000 << cap) < end:
            cap += 1
        if (0x20000 << cap) > len(img):
            img += b'\xff' * ((0x20000 << cap) - len(img))
            img[0x14] = cap
        img[new:end] = block
        img[blk_start:blk_end] = b'\xff' * (blk_end - blk_start)
        for x in (0x30, 0x40, 0x48, 0x68):
            struct.pack_into('<I', img, x, struct.unpack_from('<I', img, x)[0] + delta)
        struct.pack_into('<I', img, 0x80, end)
        if off + need > new:
            raise CodeError('the game code grew too large for the cartridge layout')
    old_end = off + size + (12 if has_footer else 0)
    img[off:off + len(arm9)] = arm9
    if has_footer:
        img[off + len(arm9):off + len(arm9) + 12] = footer
    if off + need < old_end:
        img[off + need:old_end] = b'\xff' * (old_end - off - need)
    struct.pack_into('<I', img, 0x2C, len(arm9))
    return img


def apply_to_image(img, mod_dirs, kit=KIT):
    """Builder entry point. Returns report lines (empty if no code mods)."""
    syms = game_symbols(kit)
    mods = load_code_mods(mod_dirs, syms)
    if not mods:
        return []
    core = load_code_mods([os.path.join(kit, 'code', 'core')], syms)
    if not core or not core[0]['blob']:
        raise CodeError('the mod core (code/core) is not compiled; run: python urbz_patch.py '
                        'build --dir code/core')
    off, _, _, size = struct.unpack_from('<4I', img, 0x20)
    arm9, report = apply_code(bytes(img[off:off + size]), mods, function_map(kit), core[0])
    put_arm9(img, arm9)
    return report
