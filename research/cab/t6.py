"""Screenshots of each shirt style (top screen crops) + which layout entries are decoded."""
from cabprobe import *
from PIL import Image
import collections
emu = emu_open(state='threads.dst')
regs = emu.memory.register_arm9
dec = collections.Counter()
def on_dec(a, s):
    dec[(hex(regs.r0), hex(regs.r14))] += 1
emu.memory.register_exec(0x0202d760, on_dec)
ims = []
for k in range(6):
    dec.clear()
    sh = run(emu, [["press", "RIGHT"], ["wait", 40], ["shot", "style%d" % (k + 1)]], tag='t6')
    print('style', rd(emu, 0x02141148, 1).hex(), sorted(dec.items())[:12])
    ims.append(Image.open(sh[-1][1]).crop((128, 20, 256, 192)))
W = Image.new('RGB', (128 * 6, 172))
for i, im in enumerate(ims): W.paste(im, (128 * i, 0))
W.save('shots/t6_styles.png')
os._exit(0)
