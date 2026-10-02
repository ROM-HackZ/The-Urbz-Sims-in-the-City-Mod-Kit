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


def test_uses_pc():
    assert C._uses_pc(struct.pack('<I', 0xE59F0010), 0x02000000)        # ldr r0, [pc, #16]
    assert C._uses_pc(struct.pack('<I', 0xEB000000), 0x02000000)        # bl
    assert not C._uses_pc(struct.pack('<I', 0xE92D4FF0), 0x02000000)    # push


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok  ' + name)
