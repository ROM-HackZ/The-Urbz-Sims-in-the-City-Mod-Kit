import sys, re
src = open('/root/urbz/ghidra/arm9_decomp.c').read()
idx = {m.group(1).lower(): m.start() for m in re.finditer(r'// ==== FUN_([0-9a-fA-F]{8}) @', src)}
keys = sorted(idx.values())
import bisect
for a in sys.argv[1:]:
    s = idx[a.lower().replace('0x','')]
    i = bisect.bisect_right(keys, s)
    e = keys[i] if i < len(keys) else len(src)
    print(src[s:e])
