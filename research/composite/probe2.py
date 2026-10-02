import sys, os, json, struct, collections
sys.path.insert(0, '/root/urbz/kit9/verify')
import urbz_verify as V
rom = '/root/urbz/work/van.nds'
st = V.city_state(rom)
emu = V._emu(rom, None, os.devnull)
emu.savestate.load_file(st)
R = emu.memory.register_arm9
mem = emu.memory.unsigned
a9 = open('/root/urbz/arm9.bin','rb').read()
L = lambda a: struct.unpack_from('<I', a9, a-0x02000000)[0]
ENG = L(0x02067124)
u32 = lambda a: struct.unpack('<I', bytes(mem[a:a+4]))[0]
rec = []; cur = [None]; SEEN=set()
WANT = int(sys.argv[1]) if len(sys.argv) > 1 else 30
def h5534(a, s):
  try:
    _h5534(a,s)
  except Exception as e: print('ERR',e)
def _h5534(a, s):
    SEEN.add(V.FRAME[0])
    if V.FRAME[0] != WANT: return
    sp = R.r13
    p5 = u32(sp) & 0xffff; p6 = u32(sp+4); p7 = u32(sp+8)
    cur[0] = {'eng': mem[ENG], 'layout_ptr': R.r0, 'frame': R.r1, 'flags': R.r2,
              'pos': list(struct.unpack('<ii', bytes(mem[R.r3:R.r3+8]))), 'tilebase': p5,
              'base_attr': bytes(mem[p6:p6+8]).hex(), 'lr': R.r14, 'oam': []}
    rec.append(cur[0])
def h70a8(a, s):
    if V.FRAME[0] != WANT or cur[0] is None: return
    cur[0]['oam'].append((R.r0, bytes(mem[R.r1:R.r1+8]).hex(), mem[ENG]))
emu.memory.register_exec(0x02005534, h5534)
emu.memory.register_exec(0x020670a8, h70a8)
out = '/root/urbz/agentwork/composite/rt'
# grab layout bytes for each ptr after run
V._run_script(emu, [['wait', WANT+1], ['shot', 'f%d' % WANT], ['wait', 1], ['shot', 'f%d_b' % WANT]], out, 'p2')
print("n", len(rec), hex(ENG), sorted(SEEN)[:50])
for r in rec:
    p = r['layout_ptr']; n = struct.unpack('<H', bytes(mem[p+6:p+8]))[0]
    r['layout_head'] = bytes(mem[p:p+64]).hex()
    r['layout_bytes'] = bytes(mem[p:p+0x4000]).hex()
json.dump(rec, open(out + '/calls_f%d.json' % WANT, 'w'))
open(out + '/oam_f%d.bin' % WANT, 'wb').write(bytes(mem[0x07000000:0x07000800]))
open(out + '/objvram_main_f%d.bin' % WANT, 'wb').write(bytes(mem[0x06400000:0x06420000]))
open(out + '/objvram_sub_f%d.bin' % WANT, 'wb').write(bytes(mem[0x06600000:0x06620000]))
open(out + '/pal_f%d.bin' % WANT, 'wb').write(bytes(mem[0x05000000:0x05000800]))
for r in rec:
    print(r['eng'], hex(r['layout_ptr']), r['frame'], r['flags'], r['pos'], hex(r['tilebase']), r['base_attr'], [(o[0], o[1]) for o in r['oam']])
os._exit(0)
