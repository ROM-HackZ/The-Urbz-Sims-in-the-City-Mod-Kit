#!/usr/bin/env python3
"""Dump the player look -> sprite part tables of The Urbz DS (USA) from arm9.bin.

City player (FUN_0208327c, called with the look struct at game_state+0x24 = 0x02141144):
  slot 0 'body'  : 0x020F75E0[gender]                 -> anim table
  slot 1 'part1' : 0x020F75D8[gender]                 -> anim table
  slot 2 'hair'  : 0x020F75D0[gender] -> [hair style]  -> anim table
  slot 3 'part3' : 0x020F75C8[gender]                 -> anim table
  anim table = u32[196] indexed by entity+0xC7 (animation), each -> 5 sprite records
  (one per facing direction) or 0 (part not drawn in that animation).
  sprite record = {u32 gfx game id, u32 layout game id, u32 palette id (0), u32 param}
Create-a-Bod preview (FUN_02045f30):
  slot 0: 0x0211CD9C[gender], slot 1: 0x0211CDA4[gender], slot 2: 0x0211CDAC[gender] -> [hair]
  each -> 5 records (all 5 identical: front view only).
Game ids = file number + 1.

usage: dump_parts.py [arm9.bin] [--anims]
"""
import struct, sys, collections
A9 = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else '/root/urbz/arm9.bin'
a = open(A9, 'rb').read()
BASE = 0x02000000
u = lambda x: struct.unpack_from('<I', a, x - BASE)[0]
NANIM = 196
HAIRS = 4

def recs(p):
    return [struct.unpack_from('<4I', a, p - BASE + 16 * d) for d in range(5)]

def anim_table(t):
    out = []
    for k in range(NANIM):
        p = u(t + 4 * k)
        out.append((k, p, recs(p) if p else None))
    return out

def summary(name, t, show):
    rows = anim_table(t)
    ids = collections.Counter()
    for k, p, r in rows:
        if r:
            for g, l, pal, prm in r:
                ids[(g, l)] += 1
    used = sum(1 for _, p, _ in rows if p)
    print('  %-12s table 0x%08X  anims with this part: %d/%d  distinct gfx/layout pairs: %d' % (name, t, used, NANIM, len(ids)))
    if show:
        for k, p, r in rows:
            if r:
                print('     anim %3d -> 0x%08X  ' % (k, p) + ' '.join('%d/%d' % (g - 1, l - 1) for g, l, _, _ in r))
    return rows

def main():
    show = '--anims' in sys.argv
    print('City player parts (file numbers gfx/layout; 5 directions per anim)')
    for g in range(2):
        print('gender %d (%s)' % (g, 'male' if g == 0 else 'female'))
        summary('slot0 body', u(0x020F75E0 + 4 * g), show)
        summary('slot1', u(0x020F75D8 + 4 * g), show)
        ht = u(0x020F75D0 + 4 * g)
        for h in range(HAIRS):
            rows = summary('slot2 hair%d' % h, u(ht + 4 * h), show)
            k, p, r = next(x for x in rows if x[2])
            print('     e.g. anim %d: %s' % (k, ' '.join('%05d/%05d' % (gg - 1, l - 1) for gg, l, _, _ in r)))
        summary('slot3', u(0x020F75C8 + 4 * g), show)
    print('\nCreate-a-Bod preview parts')
    for g in range(2):
        b0 = u(0x0211CD9C + 4 * g); b1 = u(0x0211CDA4 + 4 * g); ht = u(0x0211CDAC + 4 * g)
        r0 = recs(b0)[0]; r1 = recs(b1)[0]
        hs = [recs(u(ht + 4 * h))[0] for h in range(HAIRS)]
        print('gender %d: slot0 0x%08X gfx %05d lay %05d | slot1 0x%08X gfx %05d lay %05d' % (
            g, b0, r0[0] - 1, r0[1] - 1, b1, r1[0] - 1, r1[1] - 1))
        for h in range(HAIRS):
            print('   hair %d: ptr @0x%08X = 0x%08X gfx %05d lay %05d' % (h, ht + 4 * h, u(ht + 4 * h), hs[h][0] - 1, hs[h][1] - 1))

if __name__ == '__main__':
    main()
