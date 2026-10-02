import json, struct, bisect, sys
from common import *
F = json.load(open('/root/urbz/ghidra/functions_arm9.json'))
F.sort(key=lambda f: f['addr'])
starts = [f['addr'] for f in F]
byaddr = {f['addr']: f for f in F}
def func_of(a):
    i = bisect.bisect_right(starts, a) - 1
    return F[i]['addr'] if i >= 0 else None
# literal index: value -> list of literal addrs
LIT = {}
for o in range(0, len(ARM9) - 3, 4):
    v = struct.unpack_from('<I', ARM9, o)[0]
    if 0x02000000 <= v < 0x02400000:
        LIT.setdefault(v & ~1, []).append(0x02000000 + o)
HANDLERS = {u32(0x020C2308 + 4 * t) & ~1: t for t in range(1, 38)}
def parents(f):
    out = []
    for c in byaddr.get(f, {}).get('callers', []):
        out.append(('call', c, func_of(c)))
    for l in LIT.get(f, []):
        out.append(('ptr', l, func_of(l)))
    return out
def tree(f, depth=0, seen=None, maxd=6):
    seen = seen if seen is not None else set()
    tag = ' [record type %d handler]' % HANDLERS[f] if f in HANDLERS else ''
    if f in seen:
        return
    seen.add(f)
    for kind, at, pf in parents(f):
        t2 = ' [rec %d]' % HANDLERS[pf] if pf in HANDLERS else ''
        print('  ' * depth + '<- %s at %08x in %s%s' % (kind, at, ('%08x' % pf) if pf else '?', t2))
        if pf and depth < maxd and pf not in HANDLERS:
            tree(pf, depth + 1, seen, maxd)
if __name__ == '__main__':
    for x in sys.argv[1:]:
        f = int(x, 16)
        print('== %08x' % f, '[rec %d]' % HANDLERS[f] if f in HANDLERS else '')
        tree(f, 0, set(), int(sys.argv[0] and 3))
