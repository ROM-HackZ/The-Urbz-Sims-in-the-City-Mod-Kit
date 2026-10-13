"""Highlights each townsperson's skin colours (urbz_poses.SKIN) in magenta, both views: skin_check.png here."""
import os, sys
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT); sys.path.insert(0, os.path.join(KIT, 'kit'))
import urbz_poses as Q, urbz_anims as A, numpy as np
from PIL import Image, ImageDraw
import urbz_poses as _Q
SK = _Q.SKIN
cells = []
for cid, sk in SK.items():
    for view in ('front', 'back'):
        idx, pal = Q.standing(cid, view)
        a = Q.to_rgba(idx, pal); h = np.array(a)
        m = np.isin(idx, sk)
        h2 = h.copy(); h2[m] = (255, 0, 255, 255)
        b = Q.bbox(idx)
        crop = lambda arr: Image.fromarray(arr).crop((b[0]-2, b[1]-2, b[2]+2, b[3]+2)).resize(((b[2]-b[0]+4)*3, (b[3]-b[1]+4)*3), Image.NEAREST)
        cells.append((cid, view, crop(h), crop(h2)))
W = 4 * 80 * 3 // 2
img = Image.new('RGBA', (len(SK) // 2 * 0 + 8 * 170, ((len(cells) + 3) // 4) * 210), (100, 100, 120, 255))
d = ImageDraw.Draw(img)
for k, (cid, view, a, b) in enumerate(cells):
    x, y = (k % 4) * 340, (k // 4) * 210
    img.alpha_composite(a, (x, y + 12)); img.alpha_composite(b, (x + 160, y + 12))
    d.text((x, y), '%d %s %s' % (cid, A.names()[cid].split()[0], view), fill=(255, 255, 0, 255))
img.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'skin_check.png'))
