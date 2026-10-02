"""Static analysis: object number -> descriptor (0x020EAF84 + n*0x24) -> actions + motive effect rows.
Writes analysis.json (raw) used by build_table.py."""
import json, struct, re
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from common import *
from up import F, byaddr, starts, func_of, HANDLERS
import bisect
md = Cs(CS_ARCH_ARM, CS_MODE_ARM); md.detail = False
EFFECT = 0x0205DC20
DESC, NDESC = 0x020EAF84, 253
ACTION_TAB = 0x020EA9B0; NACT = 128
SIT_TAB = 0x020F5584       # 12-byte rows; +8 = effect row (used by sit helper 0206be3c, index in r2)
ARCADE_TAB = 0x020C5F80    # 0x20-byte rows; +0xC = effect row (02035e68, index = obj+0x2e)
INV_TAB = 0x020C1CC8       # 12-byte rows {u32 object, u16 ticks, u8 anim, u8 action, u8 row, u8 quality}
HELPERS = {
    0x0206a3f4: 'admire (row 0 room +0.05 at home, else row 1 fun +0.1)',
    0x0206a6a0: 'clean (row 4)',
    0x0206ab4c: 'dance (row 6 alone / row 7 with others)',
    0x0206b42c: 'repair (row 36)',
    0x0206b6d0: 'nap on sofa/bench (row 51)',
    0x0206b90c: 'sleep in bed (row 50)',
    0x0206bba4: 'recline (row 46)',
    0x0206be3c: 'sit (row from sit table 0x020F5584 by sit type)',
    0x0206c1d0: 'skill practice, fun (row 29)',
    0x0206c2b8: 'skill practice (row passed in r3)',
}
def fend(a):
    f = byaddr.get(a)
    if f and f['end'] > a: return f['end']
    i = bisect.bisect_right(starts, a)
    return starts[i] if i < len(starts) else a + 0x400
_cache = {}
def insns(a):
    if a in _cache: return _cache[a]
    e = fend(a)
    code = ARM9[a - 0x02000000:e - 0x02000000]
    out = list(md.disasm(code, a))
    _cache[a] = out
    return out
IMM = re.compile(r'^(r\d+), #(-?0x[0-9a-f]+|-?\d+)$')
def calls(a):
    """BL sites in function a with known immediate r0..r3 (straight-line approximation)."""
    regs = {}
    out = []
    for ins in insns(a):
        m, op = ins.mnemonic, ins.op_str
        if m in ('bl', 'blx') and op.startswith('#'):
            out.append((ins.address, int(op[1:], 16), dict(regs)))
            for r in ('r0', 'r1', 'r2', 'r3', 'r12'): regs.pop(r, None)
            continue
        dst = op.split(',')[0].strip() if op else ''
        mm = IMM.match(op)
        if m in ('mov', 'movs') and mm:
            regs[mm.group(1)] = int(mm.group(2), 0)
        elif m.startswith('mov') and mm:   # conditional move: value uncertain but keep candidate
            regs[mm.group(1)] = int(mm.group(2), 0)
        elif dst in ('r0', 'r1', 'r2', 'r3', 'r12') and not m.startswith(('str', 'cmp', 'tst', 'b', 'push', 'teq', 'cmn')):
            regs.pop(dst, None)
    return out
def closure(roots, maxd=4, maxcallers=25):
    seen, order = set(), []
    todo = [(r, 0) for r in roots if r]
    while todo:
        f, d = todo.pop(0)
        if f in seen: continue
        seen.add(f); order.append(f)
        if d >= maxd or f in HELPERS or f == EFFECT: continue
        for site, t, regs in calls(f):
            nc = len(byaddr.get(t, {}).get('callers', []))
            if t == EFFECT or t in HELPERS or nc <= maxcallers:
                todo.append((t, d + 1))
    return order
def effects_in(funcs, quality):
    res = []
    for f in funcs:
        for site, t, regs in calls(f):
            if t == EFFECT:
                if f in HELPERS and f not in (0x0206c1d0, 0x0206b42c, 0x0206a3f4): continue
                r = regs.get('r1')
                res.append(dict(row=r, site='%08x' % site, func='%08x' % f, via='direct' if r is not None else 'computed'))
            elif t in HELPERS:
                h = HELPERS[t]
                rows = []
                if t == 0x0206a3f4: rows = [0, 1]
                elif t == 0x0206a6a0: rows = [4]
                elif t == 0x0206ab4c: rows = [6, 7]
                elif t == 0x0206b42c: rows = [36]
                elif t == 0x0206b6d0: rows = [51]
                elif t == 0x0206b90c: rows = [50]
                elif t == 0x0206bba4: rows = [46]
                elif t == 0x0206c1d0: rows = [29]
                elif t == 0x0206be3c:
                    k = regs.get('r2')
                    rows = [u32(SIT_TAB + 12 * k + 8)] if k is not None and 0 <= k < 6 else [None]
                    h += ' type %s' % k
                elif t == 0x0206c2b8:
                    rows = [regs.get('r3')]
                res.append(dict(row=rows if len(rows) > 1 else rows[0], site='%08x' % site, func='%08x' % f,
                                via='helper %08x: %s' % (t, h)))
    # dedupe
    seen, out = set(), []
    for e in res:
        k = (e['site'], str(e['row']))
        if k not in seen: seen.add(k); out.append(e)
    return out
def list_actions(a):
    """Heuristic: immediates that reach a strb (directly or after an unconditional b)."""
    ins = insns(a)
    byad = {i.address: k for k, i in enumerate(ins)}
    acts = []
    for k, i in enumerate(ins):
        mm = IMM.match(i.op_str)
        if not (i.mnemonic.startswith('mov') and mm): continue
        reg, v = mm.group(1), int(mm.group(2), 0)
        j, steps = k + 1, 0
        while j < len(ins) and steps < 6:
            x = ins[j]; steps += 1
            if x.mnemonic.startswith('strb') and x.op_str.startswith(reg + ','):
                if 0 < v < NACT and v not in acts: acts.append(v)
                break
            if x.mnemonic == 'b' and x.op_str.startswith('#'):
                t = int(x.op_str[1:], 16)
                if t in byad: j = byad[t]; continue
                break
            if x.op_str.startswith(reg + ',') and not x.mnemonic.startswith(('str', 'cmp', 'tst')): break
            if x.mnemonic in ('bl', 'bx', 'pop'): break
            j += 1
    return acts
def action(i):
    v = u32(ACTION_TAB + 4 * i)
    return dict(id=i, name=text(v >> 16), need=NEEDS[v & 0xffff] if (v & 0xffff) < 8 else None)
def obj_info(n):
    m, d, nm, page, x = [u32(0x020E6D48 + n * 20 + 4 * k) for k in range(5)]
    info = [u32(0x020E8B70 + n * 20 + 4 * k) for k in range(5)]
    return dict(object=n, name=text(nm), name_string=nm, desc_string=d, model=m, catalog_page=page,
                text_field4=x, price=info[0], info=['%x' % v for v in info[1:]])
def main():
    out = []
    for n in range(386):
        o = obj_info(n)
        if n < NDESC:
            d = DESC + n * 0x24
            s = [u32(d + 4 * k) for k in range(8)]
            fl = ARM9[d + 0x20 - 0x02000000:d + 0x24 - 0x02000000]
            o['descriptor'] = '%08x' % d
            o['slots'] = dict(init='%08x' % s[0], list_actions='%08x' % s[1], test='%08x' % s[2], begin='%08x' % s[3],
                              update='%08x' % s[4], end='%08x' % s[5], slot18='%08x' % s[6], in_range='%08x' % s[7])
            o['desc_flags'] = fl.hex(); o['quality_index'] = fl[3]
            o['quality_mult'] = s32(0x020EA998 + 4 * fl[3]) / 16777216 if fl[3] < 6 else None
            if s[1]:
                o['actions'] = [action(i) for i in list_actions(s[1])]
                cl = closure([s[3], s[4]])
                o['effects'] = effects_in(cl, fl[3])
                o['closure'] = ['%08x' % f for f in cl]
        out.append(o)
    json.dump(out, open('analysis.json', 'w'), indent=1)
if __name__ == '__main__':
    main()
