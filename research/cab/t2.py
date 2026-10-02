from cabprobe import *
emu = emu_open(state='cab.dst')
regs = emu.memory.register_arm9
log = []
def on_spr(a, s):
    r0 = regs.r0
    rec = struct.unpack('<4I', rd(emu, r0, 16)) if 0x02000000 <= r0 < 0x02400000 else None
    log.append(('SPR', V.FRAME[0], hex(r0), rec and [hex(x) for x in rec], hex(regs.r1), hex(regs.r14), [hex(x) for x in V._stack_calls(regs, emu.memory.unsigned, 8)]))
def on_get(a, s):
    log.append(('GET', V.FRAME[0], regs.r0, hex(regs.r14)))
emu.memory.register_exec(0x020ae0c8, on_spr)
emu.memory.register_exec(0x02032CA8, on_get)
seq = [("DOWN","gender"),("RIGHT","gender+"),("DOWN","skin"),("RIGHT","skin+"),("DOWN","hair"),("RIGHT","hair+"),("RIGHT","hair+2"),("DOWN","hcol"),("RIGHT","hcol+")]
for k, n in seq:
    log.append(('MARK', n))
    run(emu, [["press", k], ["wait", 40]], tag='t2')
import collections
seg=None; segs=collections.OrderedDict(); segs['start']=collections.Counter()
cur='start'
for l in log:
    if l[0]=='MARK': cur=l[1]; segs[cur]=collections.Counter(); continue
    if l[0]=='GET': segs[cur][('GET',l[2],l[3])]+=1
    else: segs[cur][('SPR',l[2],tuple(l[3] or ()),l[4],l[5],tuple(l[6]))]+=1
for k,c in segs.items():
    print('==',k)
    for e,n in sorted(c.items(), key=lambda x:str(x[0])): print('  ',n,e)
os._exit(0)
