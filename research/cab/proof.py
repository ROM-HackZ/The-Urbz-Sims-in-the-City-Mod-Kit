"""Proof screenshots: Create-a-Bod (from power-on) for vanilla vs mod ROMs.
usage: proof.py out_prefix rom [rom ...]
For each ROM: shot at Create-a-Bod start (male, skin 1, hair 0), then hair style -> 1.
Also records the gfx ids fetched for the preview (get_asset from 0x02001978)."""
from cabprobe import *
from PIL import Image
out = sys.argv[1]
roms = sys.argv[2:]
rows = []
for rom in roms:
    emu = emu_open(rom=rom)
    regs = emu.memory.register_arm9
    seen = []
    emu.memory.register_exec(0x02032CA8, lambda a, s: seen.append(regs.r0 - 1) if regs.r14 == 0x2001978 else None)
    tag = os.path.splitext(os.path.basename(rom))[0]
    sh = run(emu, INTRO + [["wait", 120], ["shot", "start"]], tag=tag)
    g0 = sorted(set(seen[-60:])); seen.clear()
    sh += run(emu, [["press", "DOWN"], ["wait", 30], ["press", "DOWN"], ["wait", 30], ["press", "DOWN"], ["wait", 30],
                    ["press", "RIGHT"], ["wait", 60], ["shot", "hair1"]], tag=tag)
    g1 = sorted(set(seen[-60:]))
    look = rd(emu, 0x02141144, 10).hex(' ')
    print(tag, 'start gfx(files)', g0, '| after hair+1 gfx', g1, '| look', look)
    rows.append([Image.open(p).crop((128, 16, 256, 192)) for _, p, _ in sh if os.path.basename(p).endswith(('start.png', 'hair1.png'))])
    os.system('true')
for i, ims in enumerate(rows):
    for j, im in enumerate(ims): im.save('%s_%d_%d.png' % (out, i, j))
W = Image.new('RGB', (128 * 2 * 2, 176 * 2 * len(rows)))
for r, ims in enumerate(rows):
    for c, im in enumerate(ims):
        W.paste(im.resize((256, 352), Image.NEAREST), (256 * c, 352 * r))
W.save(out + '.png')
print('wrote', out + '.png')
os._exit(0)
