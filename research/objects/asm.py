import sys, struct
from capstone import *
from common import *
md = Cs(CS_ARCH_ARM, CS_MODE_ARM); mdt = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
def dis(a, n=40, thumb=False):
    m = mdt if thumb else md
    code = ARM9[a - 0x02000000: a - 0x02000000 + n * 4]
    out = []
    for ins in m.disasm(code, a):
        s = '%08x  %-8s %s' % (ins.address, ins.mnemonic, ins.op_str)
        if 'pc, #' in ins.op_str and ins.mnemonic.startswith('ldr'):
            off = int(ins.op_str.split('#')[-1].rstrip(']'), 0)
            la = (ins.address + (4 if thumb else 8)) + off
            if thumb: la = ((ins.address + 4) & ~3) + off
            s += '   ; =%08x' % u32(la)
        out.append(s)
        if len(out) >= n: break
    return out
if __name__ == '__main__':
    a = int(sys.argv[1], 16); n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    print('\n'.join(dis(a, n, len(sys.argv) > 3)))
