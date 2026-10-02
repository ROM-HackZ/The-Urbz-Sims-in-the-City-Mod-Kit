#!/usr/bin/env python3
"""Build a browsable catalog of every asset: type, size, scene labels, thumbnail.

  python urbz_catalog.py            -> catalog/index.html (open it in a browser)
  python urbz_catalog.py --no-thumbs  (fast, data only)

Types come from static signatures (see urbz_classify.py). Scene labels come
from emulator traces in verify/traces/*.json (made with `urbz_verify.py trace`),
so the catalog gets smarter every time a new area is traced.
Game asset ID = file number + 1 (the game's own numbering, used by its code).
"""
import json, os, sys, time

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from urbz_classify import classify_all
from urbz_gfx import find_screen, render_screen, tiles_preview, render_palette

PROJ = os.path.join(KIT, 'project')
OUT = os.path.join(KIT, 'catalog')


def load_traces():
    labels = {}
    tdir = os.path.join(KIT, 'verify', 'traces')
    if not os.path.isdir(tdir):
        return labels
    for f in sorted(os.listdir(tdir)):
        if not f.endswith('.json'):
            continue
        t = json.load(open(os.path.join(tdir, f)))
        for sc in t['scenes']:
            for gid in sc['game_ids']:
                labels.setdefault(gid - 1, []).append('%s/%s' % (t['name'], sc['shot']))
    return labels


def sprite_thumb(layout_bytes, gfx_chunks, pal=None):
    """Frames side by side if chunks are whole w*h frames, else a tile strip."""
    from PIL import Image
    from urbz_gfx import tiles_to_array
    w, h = layout_bytes[0], layout_bytes[1]
    fb = (w // 8) * (h // 8) * 32
    frames = [c for c in gfx_chunks[:6] if fb and len(c) % fb == 0 and len(c) >= fb]
    if frames and len(frames) == len(gfx_chunks[:6]) and w and h:
        imgs = [tiles_preview(c[:fb], pal, cols=w // 8, max_tiles=fb // 32) for c in frames]
        out = Image.new('RGB', (sum(i.width for i in imgs) + 2 * (len(imgs) - 1), h), (40, 40, 48))
        x = 0
        for im in imgs:
            out.paste(im, (x, 0))
            x += im.width + 2
        return out
    return tiles_preview(gfx_chunks[0], pal, cols=16, max_tiles=128)


def build(thumbs=True):
    t0 = time.time()
    m = json.load(open(os.path.join(PROJ, 'manifest.json')))
    ra = lambda i: open(os.path.join(PROJ, 'assets', '%05d.bin' % i), 'rb').read()
    rc = lambda i, f: open(os.path.join(PROJ, 'unpacked', '%05d' % i, f), 'rb').read()
    print('classifying %d assets...' % len(m['entries']))
    rp = os.path.join(PROJ, 'sprite_refs.json')
    refs = json.load(open(rp))['gfx'] if os.path.exists(rp) else None
    cat = classify_all(m, ra, rc, refs)
    labels = load_traces()
    for i, info in cat.items():
        if i in labels:
            info['seen_in'] = sorted(set(labels[i]))
    os.makedirs(os.path.join(OUT, 'thumbs'), exist_ok=True)
    if thumbs:
        print('rendering thumbnails...')
        done = 0
        for i, info in cat.items():
            p = os.path.join(OUT, 'thumbs', '%05d.png' % i)
            img = None
            try:
                if info['type'] == 'screen':
                    d = rc(i, info['screens'][0])
                    img = render_screen(d)
                elif info['type'] == 'sprite-sheet' and info.get('layouts'):
                    e = m['entries'][i]
                    from urbz_png import captured_palettes
                    from urbz_gfx import bgr555
                    cap = captured_palettes().get(i)
                    pal = [bgr555(v) for v in cap] if cap else None
                    chunks = [rc(i, c['file']) for c in e['chunks'] if (c['flags'] >> 4) & 7 == 6][:6]
                    img = sprite_thumb(ra(info['layouts'][0]), chunks or [rc(i, e['chunks'][0]['file'])], pal)
                    if img is not None and img.height <= 64:      # small sprites: 2x, crisp
                        from PIL import Image
                        img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
                elif info['type'] == 'palette':
                    img = render_palette(ra(i))
                elif info['type'] in ('packed-data', 'packed-multi'):
                    e = m['entries'][i]
                    img = tiles_preview(rc(i, e['chunks'][0]['file']), cols=16, max_tiles=64)
            except Exception as ex:          # a bad preview must never stop the catalog
                info['thumb_error'] = str(ex)[:80]
            if img is not None:
                img.save(p, optimize=True)
                info['thumb'] = 'thumbs/%05d.png' % i
                done += 1
        print('  %d thumbnails' % done)
    rows = [cat[i] for i in sorted(cat)]
    for r, i in zip(rows, sorted(cat)):
        r['n'] = i
    json.dump(rows, open(os.path.join(OUT, 'catalog.json'), 'w'), indent=0)
    write_html(rows)
    print('catalog: %s  (%.0f s)' % (os.path.join(OUT, 'index.html'), time.time() - t0))


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Urbz Asset Catalog</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1f1e1c;--muted:#6b6862;--line:#e3e0da;--accent:#2f6fde;--chip:#eef2fb}
@media (prefers-color-scheme:dark){:root{--bg:#17171a;--card:#212126;--ink:#ecebe8;--muted:#a3a19c;--line:#33333a;--accent:#7aa5ff;--chip:#273049}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;z-index:2}
h1{font-size:16px;margin:0 12px 0 0}
input,select,button{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
button{cursor:pointer}#stats{color:var(--muted);margin-left:auto}
main{padding:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:6px;min-width:0}
.t{height:120px;display:flex;align-items:center;justify-content:center;background:repeating-conic-gradient(#8881 0 25%,#0000 0 50%) 0 0/12px 12px;border-radius:6px;overflow:hidden}
.t img{max-width:100%;max-height:120px;image-rendering:pixelated}
.n{font-weight:600}.m{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.chip{display:inline-block;background:var(--chip);border-radius:6px;padding:1px 6px;font-size:12px;margin:1px 2px 0 0}
nav{display:flex;gap:8px;justify-content:center;padding:0 16px 24px}
</style></head><body>
<header><h1>Urbz Asset Catalog</h1>
<input id="q" placeholder="Search # or scene label" size="22">
<select id="ty"><option value="">All types</option></select>
<label><input type="checkbox" id="seen"> Seen in a trace</label>
<span id="stats"></span></header>
<main id="g"></main>
<nav><button id="prev">Previous</button><span id="pg"></span><button id="next">Next</button></nav>
<script>
const DATA = __DATA__;
const PER = 120; let page = 0, rows = DATA;
const ty = document.getElementById('ty');
[...new Set(DATA.map(r => r.type))].sort().forEach(t => {
  const o = document.createElement('option'); o.value = t;
  o.textContent = t + ' (' + DATA.filter(r => r.type === t).length + ')'; ty.appendChild(o); });
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function card(r){
  const extra = [];
  if (r.gfx !== undefined) extra.push('gfx #' + r.gfx);
  if (r.layouts) extra.push('layouts ' + r.layouts.slice(0,3).map(x=>'#'+x).join(', '));
  if (r.chunks) extra.push(r.chunks + ' chunk' + (r.chunks>1?'s':''));
  return '<div class="c"><div class="t">' + (r.thumb ? '<img loading="lazy" src="' + r.thumb + '" alt="asset ' + r.n + '">' : '<span class="m">no preview</span>') +
    '</div><div class="n">#' + String(r.n).padStart(5,'0') + ' <span class="m">game ID ' + r.id + '</span></div>' +
    '<div class="m">' + esc(r.type) + ' · ' + r.size.toLocaleString() + ' B' + (extra.length ? ' · ' + esc(extra.join(' · ')) : '') + '</div>' +
    (r.seen_in ? '<div>' + r.seen_in.slice(0,4).map(s=>'<span class="chip">'+esc(s)+'</span>').join('') + (r.seen_in.length>4?' +' + (r.seen_in.length-4):'') + '</div>' : '') + '</div>';
}
function apply(){
  const q = document.getElementById('q').value.trim().toLowerCase(), t = ty.value, s = document.getElementById('seen').checked;
  rows = DATA.filter(r => (!t || r.type === t) && (!s || r.seen_in) &&
    (!q || String(r.n).padStart(5,'0').includes(q.replace('#','')) || (r.seen_in||[]).some(x => x.toLowerCase().includes(q))));
  page = 0; draw(); }
function draw(){
  const pages = Math.max(1, Math.ceil(rows.length / PER));
  page = Math.min(page, pages - 1);
  document.getElementById('g').innerHTML = rows.slice(page*PER, page*PER+PER).map(card).join('');
  document.getElementById('pg').textContent = 'Page ' + (page+1) + ' of ' + pages;
  document.getElementById('stats').textContent = rows.length.toLocaleString() + ' of ' + DATA.length.toLocaleString() + ' assets';
}
document.getElementById('q').oninput = apply; ty.onchange = apply; document.getElementById('seen').onchange = apply;
document.getElementById('prev').onclick = () => { if (page > 0) { page--; draw(); scrollTo(0,0); } };
document.getElementById('next').onclick = () => { page++; draw(); scrollTo(0,0); };
draw();
</script></body></html>
'''


def write_html(rows):
    slim = [{k: r[k] for k in ('n', 'id', 'type', 'size', 'chunks', 'thumb', 'seen_in', 'gfx', 'layouts')
             if k in r} for r in rows]
    html = HTML.replace('__DATA__', json.dumps(slim, separators=(',', ':')).replace('</', '<\\/'))
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(html)


if __name__ == '__main__':
    build(thumbs='--no-thumbs' not in sys.argv)
