from up import *
D0, ND = 0x020EAF84, 253
def desc_slot(litaddr):
    if D0 <= litaddr < D0 + ND * 0x24:
        n, off = divmod(litaddr - D0, 0x24)
        return n, off
    return None
INV = 0x020C1CC8
def roots(f, depth=0, seen=None, maxd=6):
    seen = set() if seen is None else seen
    out = set()
    if f in seen or depth > maxd: return out
    seen.add(f)
    if f in HANDLERS: out.add('rec%d' % HANDLERS[f]); return out
    if f == 0x0200be50: out.add('entity_common_update(0200be50)'); return out
    ps = parents(f)
    if not ps: out.add('top:%08x' % f)
    for kind, at, pf in ps:
        ds = desc_slot(at) if kind == 'ptr' else None
        if ds:
            out.add('obj%d+%x' % ds); continue
        if pf is None or not (0x02000000 <= at < 0x020C0000) and kind == 'ptr':
            out.add('data@%08x' % at); continue
        out |= roots(pf, depth + 1, seen, maxd)
    return out
if __name__ == '__main__':
    cs = byaddr[0x0205DC20]['callers']
    for f in sorted(set(func_of(c) for c in cs)):
        r = sorted(roots(f))
        print('%08x' % f, ' '.join(r[:30]), '...' if len(r) > 30 else '')
