"""Run object descriptor functions in Unicorn (all calls stubbed) to recover:
  - list_actions (slot +4): the action ids an object offers (union over stub return values / object states)
  - update (slot +0x10): which handler function each action dispatches to.
Writes dispatch.json: {obj: {"actions": [...], "handlers": {action: [called fns]}}}"""
import json, struct, bisect
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_BLOCK, UcError
from unicorn.arm_const import *
from common import ARM9, u32
F = json.load(open('/root/urbz/ghidra/functions_arm9.json'))
STARTS = set(f['addr'] for f in F)
ITCM = open('/root/urbz/itcm.bin', 'rb').read()
DESC = 0x020EAF84
GET_STATE = 0x02069520
OBJ, STATE, SIM, NEEDS, STACK, RET = 0x02380000, 0x02381000, 0x02382000, 0x02383000, 0x023F0000, 0x023FF000

def make():
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0x02000000, 0x400000)
    mu.mem_write(0x02000000, ARM9)
    mu.mem_map(0x01FF8000, 0x8000)
    mu.mem_write(0x01FF8000, ITCM[:0x8000])
    mu.mem_map(0x027C0000, 0x10000)
    return mu

class Run:
    def __init__(self, root, stubval, action=0, objfields=None):
        self.root, self.stubval, self.calls = root, stubval, []
        mu = self.mu = make()
        obj = bytearray(0x100)
        struct.pack_into('<I', obj, 0x24, SIM)
        for off, size, v in (objfields or []):
            obj[off:off + size] = v.to_bytes(size, 'little')
        mu.mem_write(OBJ, bytes(obj))
        st = bytearray(0x40); struct.pack_into('<IH', st, 0, SIM, action)
        mu.mem_write(STATE, bytes(st))
        sim = bytearray(0x148); struct.pack_into('<I', sim, 0x114, NEEDS)
        mu.mem_write(SIM, bytes(sim))
        mu.mem_write(RET, struct.pack('<I', 0xE12FFF1E))   # bx lr (never reached: we stop at RET)
        mu.hook_add(UC_HOOK_BLOCK, self.blk)
    def blk(self, mu, addr, size, ud):
        if addr == self.root or addr == RET: return
        if addr in STARTS or addr == GET_STATE:
            lr = mu.reg_read(UC_ARM_REG_LR)
            if addr == GET_STATE:
                r = STATE
            else:
                self.calls.append(addr)
                r = self.stubval
            mu.reg_write(UC_ARM_REG_R0, r)
            mu.reg_write(UC_ARM_REG_PC, lr)
    def go(self, *args):
        mu = self.mu
        for i, a in enumerate(args): mu.reg_write(UC_ARM_REG_R0 + i, a)
        mu.reg_write(UC_ARM_REG_SP, STACK)
        mu.reg_write(UC_ARM_REG_LR, RET)
        try:
            mu.emu_start(self.root, RET, count=20000)
        except UcError as e:
            self.err = str(e)
        return self

def list_actions(fn):
    acts = []
    for sv in (0, 1, 2, 3, 4):
        for fields in ([], [(0x48, 2, 0x100)], [(0x4a, 1, 1)], [(0x4a, 1, 2), (0x48, 2, 0x6400)]):
            buf = 0x02384000
            r = Run(fn, sv, 0, fields)
            r.mu.mem_write(buf, bytes(16))
            r.go(OBJ, buf)
            b = r.mu.mem_read(buf, 7)
            for x in b:
                if x == 0: break
                if x not in acts: acts.append(x)
    return acts

def handlers(fn, action):
    out = []
    for sv in (0, 1):
        r = Run(fn, sv, action)
        r.go(OBJ)
        for c in r.calls:
            if c not in out: out.append(c)
    return out

if __name__ == '__main__':
    res = {}
    for n in range(253):
        d = DESC + n * 0x24
        lf, up = u32(d + 4), u32(d + 0x10)
        if not (0x02000000 <= lf < 0x020C0000): continue
        acts = list_actions(lf)
        hs = {a: ['%08x' % c for c in handlers(up, a)] for a in acts}
        res[n] = dict(actions=acts, handlers=hs)
    json.dump(res, open('dispatch.json', 'w'), indent=1)
    for n, v in res.items():
        print(n, v['actions'], v['handlers'])
