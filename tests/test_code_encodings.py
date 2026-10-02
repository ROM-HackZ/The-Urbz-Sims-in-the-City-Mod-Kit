#!/usr/bin/env python3
"""Unit tests for urbz_code's instruction encodings (no ROM needed).

The game has almost no Thumb code (only SDK BIOS wrappers), so Thumb hook sites
can't be tested in-game; these tests decode every stub with capstone instead.
Run: python tests/test_code_encodings.py
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capstone
import urbz_code as C

ARM = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
THUMB = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)


def one(md, code, addr):
    return list(md.disasm(code, addr))


def target_of(ins):
    return int(ins.op_str.lstrip('#'), 16)


def test_arm_bl_and_blx():
    for site, tgt in ((0x02083DC4, 0x0214DE20), (0x0214DE20, 0x02000800), (0x01FF8C50, 0x0214E000)):
        i = one(ARM, C._arm_branch(site, tgt, True), site)[0]
        assert i.mnemonic == 'bl' and target_of(i) == tgt, (i.mnemonic, i.op_str)
        i = one(ARM, C._arm_branch(site, tgt | 1, True), site)[0]       # Thumb target
        assert i.mnemonic == 'blx' and target_of(i) == tgt, (i.mnemonic, i.op_str)
        i = one(ARM, C._arm_branch(site, tgt, False), site)[0]
        assert i.mnemonic == 'b' and target_of(i) == tgt


def test_thumb_bl_and_blx():
    for site in (0x020B88BC, 0x020B88BE):
        for tgt in (0x0214DE21, 0x0214DE20, 0x0214F000):
            ins = one(THUMB, C._thumb_bl(site, tgt), site)
            assert len(ins) == 1, ins
            i = ins[0]
            if tgt & 1:
                assert i.mnemonic == 'bl' and target_of(i) == tgt & ~1, (i.mnemonic, i.op_str)
            else:
                assert i.mnemonic == 'blx' and target_of(i) == tgt, (i.mnemonic, i.op_str)


def test_thumb_jump_stub():
    """The stub urbz_code writes over a Thumb function entry: bx pc to ARM, then ldr pc."""
    for site in (0x020B88BC, 0x020B88BE):
        half = [0x4778, 0x46C0] if site % 4 == 0 else [0x46C0, 0x4778, 0x46C0]
        stub = struct.pack('<%dH' % len(half), *half) + struct.pack('<II', C.LDR_PC_PC_M4, 0x0214DE20)
        th = one(THUMB, stub[:2 * len(half)], site)
        bx = [i for i in th if i.mnemonic == 'bx'][0]
        arm_at = (bx.address + 4) & ~3                 # bx pc: ARM state at (pc + 4) aligned
        assert arm_at == site + 2 * len(half), (hex(arm_at), hex(site))
        i = one(ARM, stub[2 * len(half):2 * len(half) + 4], arm_at)[0]
        assert i.mnemonic == 'ldr' and 'pc, [pc, #-4]' in i.op_str
        assert struct.unpack_from('<I', stub, 2 * len(half) + 4)[0] == 0x0214DE20


def test_wrap_trampoline():
    t, site, func = 0x0214DE20, 0x02084104, 0x0214DE80
    orig = 0xE92D4FF0                                   # push {r4-r11, lr}
    code = C._wrap_trampoline(t, site, orig, func)
    ins = one(ARM, code[:40], t)
    names = [i.mnemonic for i in ins]
    assert names == ['push', 'mrs', 'push', 'ldr', 'blx', 'pop', 'msr', 'pop', 'push', 'ldr'], names
    assert struct.unpack_from('<I', code, 40)[0] == site + 4
    assert struct.unpack_from('<I', code, 44)[0] == func


def pc_loads(code, at):
    """[(mnemonic, dest reg, literal value)] for every ldr rX, [pc, #imm] in an ARM stub."""
    out = []
    for i in ARM.disasm(code, at):
        if i.mnemonic.startswith('ldr') and '[pc, #' in i.op_str:
            imm = int(i.op_str.split('#')[1].rstrip(']'), 16)
            if '#-' in i.op_str:
                imm = -int(i.op_str.split('#-')[1].rstrip(']'), 16)
            lit = i.address + 8 + imm - at
            out.append((i.mnemonic, i.op_str.split(',')[0], struct.unpack_from('<I', code, lit)[0]))
    return out


def test_switch_call_stub():
    """Chain of 2 mods at one call site: each tests its switch byte, else the original target."""
    at, chain, orig = 0x0214DF10, [(0x0214DE5C, 0x0214F220), (0x0214DEAC, 0x0214F301)], 0x02065890
    code = C._switch_call_stub(at, chain, orig)
    names = [i.mnemonic for i in ARM.disasm(code[:4 * 9], at)]
    assert names == ['ldr', 'ldrb', 'cmp', 'ldrne'] * 2 + ['ldr'], names
    assert pc_loads(code, at) == [('ldr', 'ip', 0x0214DE5C), ('ldrne', 'pc', 0x0214F220),
                                  ('ldr', 'ip', 0x0214DEAC), ('ldrne', 'pc', 0x0214F301),
                                  ('ldr', 'pc', 0x02065890)], pc_loads(code, at)


def test_call_target_decoding():
    """The original target of a BL/BLX, so the off path of a stub goes where the game went."""
    class A9:
        def __init__(self, site, b): self.site, self.b = site, b
        def read(self, addr, n): return self.b[addr - self.site:addr - self.site + n]
    fmap_arm, fmap_thumb = [[0x02000000, 0x03000000, 0]], [[0x02000000, 0x03000000, 1]]
    for site, tgt in ((0x0206665C, 0x02065890), (0x0204C06C, 0x02084104)):
        assert C._call_target(A9(site, C._arm_branch(site, tgt, True)), fmap_arm, site) == tgt
        assert C._call_target(A9(site, C._arm_branch(site, tgt | 1, True)), fmap_arm, site) == tgt | 1
    for site in (0x020B88BC, 0x020B88BE):
        for tgt in (0x0214DE21, 0x0214DE20, 0x020B7C98):
            got = C._call_target(A9(site, C._thumb_bl(site, tgt)), fmap_thumb, site)
            assert got == tgt, (hex(site), hex(tgt), hex(got))


def test_switch_wrap_trampoline():
    t, site, func, on = 0x0214DE20, 0x02084104, 0x0214DE80, 0x0214DE5C
    orig = 0xE92D4FF0
    code = C._switch_wrap_trampoline(t, site, orig, func, on)
    names = [i.mnemonic for i in ARM.disasm(code[:52], t)]
    assert names == ['push', 'mrs', 'push', 'ldr', 'ldrb', 'cmp', 'ldrne', 'blxne', 'pop', 'msr',
                     'pop', 'push', 'ldr'], names
    loads = pc_loads(code, t)
    assert loads[0] == ('ldr', 'r0', on) and loads[1] == ('ldrne', 'ip', func), loads
    assert loads[2] == ('ldr', 'pc', site + 4), loads


def test_switch_jump_stub():
    at, site, func, on = 0x0214DF40, 0x0205DD70, 0x0214F000, 0x0214DE5C
    orig2 = (0xE92D4070, 0xE1A04000)                    # push {r4-r6, lr}; mov r4, r0
    code = C._switch_jump_stub(at, site, orig2, func, on)
    names = [i.mnemonic for i in ARM.disasm(code[:28], at)]
    assert names == ['ldr', 'ldrb', 'cmp', 'ldrne', 'push', 'mov', 'ldr'], names
    assert pc_loads(code, at) == [('ldr', 'ip', on), ('ldrne', 'pc', func), ('ldr', 'pc', site + 8)]


def test_uses_pc():
    assert C._uses_pc(struct.pack('<I', 0xE59F0010), 0x02000000)        # ldr r0, [pc, #16]
    assert C._uses_pc(struct.pack('<I', 0xEB000000), 0x02000000)        # bl
    assert not C._uses_pc(struct.pack('<I', 0xE92D4FF0), 0x02000000)    # push


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok  ' + name)
