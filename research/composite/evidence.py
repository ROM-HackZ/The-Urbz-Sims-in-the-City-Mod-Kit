import json, struct, sys
sys.path.insert(0, '/root/urbz/agentwork/composite')
from urbz_composite import frames, compose_frame, parse_layout
from PIL import Image
rt = '/root/urbz/agentwork/composite/rt/'
rec = json.load(open(rt + 'calls_f31.json'))
vram = {0: open(rt + 'objvram_main_f31.bin', 'rb').read(), 1: open(rt + 'objvram_sub_f31.bin', 'rb').read()}
palram = open(rt + 'pal_f31.bin', 'rb').read()
refs = json.load(open('/root/urbz/kit9/project/sprite_refs.json'))['gfx']
l2g = {l: g for g, v in refs.items() for l in v['layouts']}
def pal16(eng, n):
    base = (0x200 if eng == 0 else 0x600) + n * 32
    out = []
    for i in range(16):
        v = struct.unpack_from('<H', palram, base + 2 * i)[0]
        out.append(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31))
    return out
okc = totc = 0
for r in rec:
    l = r['layout_ids'][0]; g = l2g[l]
    e, ch = frames(g, l)[r['frame']]
    t = r['tilebase']; p = 0
    for c in e.cells:
        n = c.tiles * 32
        got = vram[r['eng']][t * 64:t * 64 + n]
        totc += 1; okc += got == ch[p:p + n]
        p += n; t += (c.tiles + 1) // 2
print('VRAM tile bytes match ROM chunk (re-spaced to 64-byte cells): %d/%d cells' % (okc, totc))
# Render the player (first 3 engine-0 calls share one position) from ROM data with runtime palettes
shot = Image.open(rt + 'p2_f31.png').convert('RGBA')
canvas = Image.new('RGBA', (256, 192), (0, 0, 0, 0))
for r in rec[:6]:
    if r['eng'] != 0: continue
    l = r['layout_ids'][0]; g = l2g[l]
    e, ch = frames(g, l)[r['frame']]
    a1 = struct.unpack_from('<H', bytes.fromhex(r['base_attr']), 2)[0]
    palno = struct.unpack_from('<H', bytes.fromhex(r['oam'][0][1]), 4)[0] >> 12
    im = compose_frame(e, ch, pal16(0, palno))
    im.save(rt + 'part_%s_%s_f%d.png' % (g, l, r['frame']))
    x, y = e.x, e.y
    if a1 & 0x1000:
        im = im.transpose(Image.FLIP_LEFT_RIGHT); x = -(e.x + e.w)
    canvas.alpha_composite(im, (r['pos'][0] + x, r['pos'][1] + y)) if 0 <= r['pos'][0] + x and 0 <= r['pos'][1] + y else None
# crop around player
box = (100, 60, 160, 140)
crop = shot.crop(box)
mine = canvas.crop(box)
bg = Image.new('RGBA', mine.size, (255, 0, 255, 255)); bg.alpha_composite(mine)
over = crop.copy(); over.alpha_composite(mine)
W = crop.size[0]
sheet = Image.new('RGBA', (W * 3 + 8, crop.size[1]), (255, 255, 255, 255))
sheet.paste(crop, (0, 0)); sheet.paste(bg, (W + 4, 0)); sheet.paste(over, (2 * W + 8, 0))
sheet = sheet.resize((sheet.size[0] * 4, sheet.size[1] * 4), Image.NEAREST)
sheet.save(rt + 'player_compare.png')
# pixel agreement: where our render is opaque, compare with the screenshot
sp, mp = crop.load(), mine.load(); same = opq = 0
for yy in range(crop.size[1]):
    for xx in range(crop.size[0]):
        if mp[xx, yy][3]:
            opq += 1; same += max(abs(a-b) for a,b in zip(sp[xx, yy][:3], mp[xx, yy][:3])) <= 8
print('player pixels: %d/%d of our opaque pixels equal the emulator screenshot' % (same, opq))

def best(shotpath):
    s = Image.open(shotpath).convert('RGBA').load()
    cp = canvas.load(); res = []
    pts = [(x, y, cp[x, y][:3]) for x in range(256) for y in range(192) if cp[x, y][3]]
    for dx in range(-8, 9):
        for dy in range(-8, 9):
            n = sum(1 for x, y, c in pts if 0 <= x+dx < 256 and 0 <= y+dy < 192 and max(abs(a-b) for a,b in zip(s[x+dx, y+dy][:3], c)) <= 8)
            res.append((n, dx, dy))
    return max(res), len(pts)
for sp in ('p2_f31.png', 'p2_f31_b.png'):
    print(sp, 'best (matches, dx, dy), opaque px:', best(rt + sp))
print('sample colours', [(Image.open(rt+'p2_f31.png').convert('RGB').getpixel((x,y)), canvas.getpixel((x,y))) for x,y in [(125,85),(128,100),(127,125)]])
