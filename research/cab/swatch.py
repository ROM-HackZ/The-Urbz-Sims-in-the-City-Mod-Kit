#!/usr/bin/env python3
"""Render the player colour tables (assets 11543 'A' = skin/hair/shoes and 11542 'B' = clothes,
file numbers) as a labelled swatch PNG, and reproduce the game's two player palette rows
(FUN_02083538) for a given look.

usage: swatch.py [project_dir] [out.png]
       python3 -c "import swatch; print(swatch.player_palettes(look_bytes))"
"""
import struct, sys, os
from PIL import Image, ImageDraw
PROJ = sys.argv[1] if len(sys.argv) > 1 else '/root/urbz/kit9/project'

def load(f, proj=PROJ):
    return list(struct.unpack('<256H', open(os.path.join(proj, 'assets', '%05d.bin' % f), 'rb').read()))

def rgb(c):
    return ((c & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, ((c >> 10) & 31) * 255 // 31)

def cols(P, byte_off, n):
    i = byte_off // 2
    return P[i:i + n]

def skin(A, s):      return cols(A, 2 + s * 0x20, 5)
def skin_dark(A, s): return cols(A, 2 + (s + 8) * 0x20, 3)
def hair(A, h):      return cols(A, 0xC + h * 0x20, 5)
def shoes(A, k):     return cols(A, 0x16 + k * 0x20, 4)
def cloth3(B, c):    return cols(B, (2 + c * 0x20) if c < 16 else (8 + (c - 16) * 0x20), 3)
def cloth4(B, c):    return cols(B, (0x10 + c * 0x20) if c < 16 else (0x18 + (c - 16) * 0x20), 4)

def player_palettes(look, proj=PROJ):
    """look = 10+ bytes at 0x02141144: gender, skin, hair, haircol, style, shirt, over, sleeve,
    pants, shoes. Returns (row_skin_hair[16], row_clothes[16]) exactly as FUN_02083538 builds them."""
    A, B = load(11543, proj), load(11542, proj)
    g, s, _, hc, st, sh, ov, sl, pa, so = look[:10]
    r1 = [A[0]] + skin(A, s) + hair(A, hc) + shoes(A, so)[:4] + [A[15]]
    shirt3 = cloth3(B, sh)
    # (game quirk: 4-shade shirt = shirt3 pointer + 7 or 8 colours, test is shirt < 15 not < 16)
    i3 = ((2 + sh * 0x20) if sh < 16 else (8 + (sh - 16) * 0x20)) // 2
    shirt4 = B[i3 + (7 if sh < 15 else 8): i3 + (7 if sh < 15 else 8) + 4]
    X, Y, Z = shirt3, cloth4(B, ov), cloth4(B, ov)
    sk = skin(A, s)[:4]
    if g == 0:
        Z, Y = {0: (cloth4(B, sl), Y), 1: (cloth4(B, sl), shirt4), 2: (sk, Y), 3: (sk, shirt4),
                4: (Z, Y), 5: (shirt4, shirt4)}[st]
    else:
        if st == 0: Z = sk
        elif st == 2: Y, Z = shirt4, shirt4
        elif st == 3: Y, Z = shirt4, sk
        elif st == 4: X = skin_dark(A, s)
        elif st == 5: X, Z = skin_dark(A, s), sk
    r2 = [B[0]] + list(X) + list(Y) + list(Z) + list(cloth4(B, pa))
    return r1, r2

def main():
    out = sys.argv[2] if len(sys.argv) > 2 else '/root/urbz/agentwork/cab/player_colours.png'
    A, B = load(11543), load(11542)
    S = 14
    img = Image.new('RGB', (40 * S, 50 * S), (40, 40, 40))
    d = ImageDraw.Draw(img)
    y = 0
    def row(label, cl):
        nonlocal y
        d.text((2, y * S + 2), label, fill=(255, 255, 255))
        for i, c in enumerate(cl):
            d.rectangle([(10 + i) * S, y * S, (11 + i) * S - 2, (y + 1) * S - 2], fill=rgb(c))
        y += 1
    for s in range(6): row('skin %d' % s, list(skin(A, s)) + [0] + list(skin_dark(A, s)))
    for h in range(10): row('hair col %d' % h, hair(A, h))
    for k in range(16): row('shoes %d' % k, shoes(A, k))
    for c in range(32): pass
    img2 = Image.new('RGB', (40 * S, 34 * S), (40, 40, 40)); d2 = ImageDraw.Draw(img2)
    for c in range(32):
        d2.text((2, c * S + 2), 'cloth %d' % c, fill=(255, 255, 255))
        for i, col in enumerate(list(cloth3(B, c)) + [0] + list(cloth4(B, c))):
            d2.rectangle([(10 + i) * S, c * S, (11 + i) * S - 2, (c + 1) * S - 2], fill=rgb(col))
    W = Image.new('RGB', (80 * S, 50 * S), (40, 40, 40)); W.paste(img, (0, 0)); W.paste(img2, (40 * S, 0))
    W.save(out)
    print('wrote', out)

if __name__ == '__main__':
    main()
