import json, struct, bisect, sys
from common import *
F = json.load(open('/root/urbz/ghidra/functions_arm9.json'))
F.sort(key=lambda f: f['addr'])
starts = [f['addr'] for f in F]
def func_of(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0: return F[i]["addr"]
    return None
def refs(val, lo=None, hi=None):
    out = []
    for o in range(0, len(ARM9) - 3, 4):
        v = struct.unpack_from('<I', ARM9, o)[0]
        if (lo is not None and lo <= v < hi) or v == val:
            a = 0x02000000 + o
            out.append((a, v, func_of(a)))
    return out
if __name__ == '__main__':
    for x in sys.argv[1:]:
        if ':' in x:
            lo, hi = [int(y, 16) for y in x.split(':')]
            r = refs(None, lo, hi)
        else:
            r = refs(int(x, 16))
        for a, v, f in r:
            print('%s: lit at %08x = %08x in func %s' % (x, a, v, '%08x' % f if f else None))
