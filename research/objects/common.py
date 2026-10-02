import struct, sys, json
sys.path.insert(0, '/root/urbz/kit9')
ARM9 = open('/root/urbz/arm9.bin', 'rb').read()
def u32(a): return struct.unpack_from('<I', ARM9, a - 0x02000000)[0]
def s32(a): return struct.unpack_from('<i', ARM9, a - 0x02000000)[0]
def u16(a): return struct.unpack_from('<H', ARM9, a - 0x02000000)[0]
_S = None
def text(i):
    global _S
    if _S is None:
        import urbz_text as T
        _S = T.decode_bank(open('/root/urbz/kit9/project/assets/00054.bin', 'rb').read())
    try: return _S[i].decode('latin-1')
    except Exception: return None
NEEDS = ['hunger', 'hygiene', 'energy', 'social', 'comfort', 'bladder', 'fun', 'room']
def effect_row(r):
    return [s32(0x020CEED4 + r * 32 + 4 * i) / 16777216 for i in range(8)]
def effect_str(r):
    v = effect_row(r)
    return ', '.join('%s %+.3f' % (NEEDS[i], x) for i, x in enumerate(v) if x) or '(none)'
