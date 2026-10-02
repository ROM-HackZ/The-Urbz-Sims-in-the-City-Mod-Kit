import json, struct, sys, os
sys.path.insert(0, '/root/urbz/agentwork/composite')
from urbz_composite import parse_layout, DIMS, TILES
P = '/root/urbz/kit9/project'
m = json.load(open(P + '/manifest.json')); E = m['entries']
refs = json.load(open(P + '/sprite_refs.json'))['gfx']
lay2gfx = {}
for g, v in refs.items():
    for l in v['layouts']: lay2gfx.setdefault(l, []).append(g)
rec = json.load(open(sys.argv[1]))
cache = {}
def ident(hexbytes):
    b = bytes.fromhex(hexbytes)
    if b[:64] in cache: return cache[b[:64]]
    hits = []
    for i, e in enumerate(E):
        if e.get('chunks') or e['size'] < 16: continue
        a = open(P + '/assets/' + e['file'], 'rb').read()
        if b[:len(a)] == a: hits.append('%05d' % i)
    cache[b[:64]] = hits
    return hits
allok = 0; tot = 0
for r in rec:
    ids = ident(r['layout_bytes'])
    r['layout_ids'] = ids
    lay = parse_layout(bytes.fromhex(r['layout_bytes']))
    e = lay.entries[r['frame']]
    base = bytes.fromhex(r['base_attr']); a0, a1, a2 = struct.unpack('<HHH', base[:6])
    hf, vf = (a1 >> 12) & 1, (a1 >> 13) & 1
    px, py = r['pos']
    t = r['tilebase']; pred = []
    for c in e.cells:
        w, h = c.dims
        x = px + (-(w + c.x) if hf else c.x)
        y = py + (-(h + c.y) if vf else c.y)
        pred.append(((y & 0xff) | (c.shape << 14), (x & 0x1ff) | (c.size << 14) | (hf << 12) | (vf << 13), t))
        t += (c.tiles + 1) // 2
    got = []
    for slot, h8, eng in r['oam']:
        g0, g1, g2 = struct.unpack('<HHH', bytes.fromhex(h8)[:6])
        got.append((g0 & 0xc0ff, g1 & 0xf1ff | (g1 & 0x3000), g2 & 0x3ff))
    pm = [(p0, p1, p2) for p0, p1, p2 in pred]
    ok = pm == got
    tot += 1; allok += ok
    print('eng', r['eng'], 'layout', ids, 'gfx', [lay2gfx.get(i) for i in ids], 'frame', r['frame'], 'cells', len(e.cells),
          'flip h/v', hf, vf, 'MATCH' if ok else 'DIFF')
    if not ok:
        print('   pred', [tuple(hex(v) for v in p) for p in pm]); print('   got ', [tuple(hex(v) for v in g) for g in got])
print('%d/%d draw calls match' % (allok, tot))
json.dump(rec, open(sys.argv[1], 'w'))
