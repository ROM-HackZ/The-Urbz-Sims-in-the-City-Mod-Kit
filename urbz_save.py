#!/usr/bin/env python3
"""Read and edit The Urbz DS save files (8 KB EEPROM, .sav as written by emulators).

  python urbz_save.py info game.sav                   header, both slots, clock, money, needs
  python urbz_save.py set game.sav out.sav [--slot 1|2] [--money N] [--motive NAME=0..100 ...]
                                           [--clock HH:MM]  (time of day; the day stays)
  python urbz_save.py fix game.sav out.sav            recompute checksums (after editing by hand)

Layout (see docs/systems.md):
  0x0000  0x20-byte header: "URBZ0010" ...; u16 at 0x1E makes the u16 sum of the header 0
  0x0020  slot 1, 0xFE0 bytes;  0x1000  slot 2, 0xFE0 bytes
          each slot is a bit/nibble/byte stream (about 2.5 KB used early in the game); the
          u16 at slot+0xFDE makes the u16 sum of the slot 0. A slot that doesn't sum to 0 is empty.
Known slot fields (offsets inside a slot): +0x05 clock (u16 day, u8 hour, minute, second,
tick), +0x0B money (24-bit, little-endian), +0x8E u16[8] needs (8.8 fixed point, 0-100).
"""
import struct, sys

HEADER, SLOT_SIZE = 0x20, 0xFE0
SLOTS = (0x20, 0x1000)
MOTIVES = ['hunger', 'hygiene', 'energy', 'social', 'comfort', 'bladder', 'fun', 'room']
F_CLOCK, F_MONEY, F_MOTIVES = 0x05, 0x0B, 0x8E   # needs: u16, value * 256


def u16sum(b):
    return sum(struct.unpack('<%dH' % (len(b) // 2), b)) & 0xFFFF


def fix_block(buf, start, size):
    struct.pack_into('<H', buf, start + size - 2, 0)
    struct.pack_into('<H', buf, start + size - 2, -u16sum(buf[start:start + size]) & 0xFFFF)


def slot_valid(buf, n):
    s = SLOTS[n]
    return u16sum(buf[s:s + SLOT_SIZE]) == 0 and any(buf[s:s + SLOT_SIZE - 2])


def mod_block(slot):
    """The mod core's block after the game's data: [(hash, data)] or None.
    'MODS', u8 version 1, u8 0, then {u32 hash, u16 length, data} ..., then u32 0."""
    data = bytes(slot[:SLOT_SIZE - 2])
    i = data.find(b'MODS\x01\x00')
    while i >= 0:
        q, out = i + 6, []
        while q + 4 <= len(data):
            h = struct.unpack_from('<I', data, q)[0]
            if h == 0:
                return out
            if q + 6 > len(data):
                break
            n = struct.unpack_from('<H', data, q + 4)[0]
            if q + 6 + n > len(data):
                break
            out.append((h, data[q + 6:q + 6 + n]))
            q += 6 + n
        i = data.find(b'MODS\x01\x00', i + 1)
    return None


def switch_record(buf):
    """The in-game mod switches (save memory 0x1FE0): [(hash15, on)] or None."""
    r = bytes(buf[0x1FE0:0x2000])
    if r[:4] != b'MODS' or r[4] != 1 or r[5] > 12:
        return None
    if sum(r[8:]) & 0xFFFF != struct.unpack_from('<H', r, 6)[0]:
        return None
    return [(e & 0x7FFF, e >> 15) for e in struct.unpack_from('<%dH' % r[5], r, 8)]


def _mod_names():
    import os
    from urbz_code import name_hash
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mods')
    names = os.listdir(root) if os.path.isdir(root) else []
    return {name_hash(n): n for n in names}


def load(path):
    buf = bytearray(open(path, 'rb').read())
    if len(buf) < 0x2000:
        sys.exit('error: %s is %d bytes; expected an 8 KB save' % (path, len(buf)))
    return buf


def info(path):
    buf = load(path)
    hdr_ok = buf[:8] == b'URBZ0010' and u16sum(buf[:HEADER]) == 0
    print('%s: header %s' % (path, 'OK' if hdr_ok else 'missing/invalid (blank save?)'))
    for n, s in enumerate(SLOTS):
        if not slot_valid(buf, n):
            print('slot %d: empty' % (n + 1))
            continue
        day, h, m, sec = struct.unpack_from('<HBBB', buf, s + F_CLOCK)
        money = int.from_bytes(buf[s + F_MONEY:s + F_MONEY + 3], 'little')
        mot = [v / 256 for v in struct.unpack_from('<8H', buf, s + F_MOTIVES)]
        used = len(bytes(buf[s:s + SLOT_SIZE - 2]).rstrip(b'\0'))
        print('slot %d: day %d %02d:%02d:%02d  money %d  (about %d of %d bytes used)'
              % (n + 1, day, h, m, sec, money, used, SLOT_SIZE))
        print('        needs: ' + ', '.join('%s %.1f' % (k, v) for k, v in zip(MOTIVES, mot)))
        blk = mod_block(buf[s:s + SLOT_SIZE])
        if blk is not None:
            names = _mod_names()
            print('        mod data: ' + (', '.join('%s %d bytes' % (names.get(h, '%08x' % h), len(d))
                                                 for h, d in blk) or 'none'))
    rec = switch_record(buf)
    if rec is not None:
        names = {h & 0x7FFF: n for h, n in _mod_names().items()}
        print('mod switches: ' + (', '.join('%s %s' % (names.get(h, '%04x' % h), 'on' if on else 'off')
                                            for h, on in rec) or 'none saved'))


def main(argv):
    if len(argv) < 2 or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd = argv[0]
    if cmd == 'info':
        info(argv[1])
        return
    if len(argv) < 3:
        sys.exit('usage: urbz_save.py %s in.sav out.sav ...' % cmd)
    buf = load(argv[1])
    out = argv[2]
    rest = argv[3:]
    if cmd == 'set':
        slot = 1
        i = 0
        while i < len(rest):
            k = rest[i]
            v = rest[i + 1] if i + 1 < len(rest) else None
            if v is None:
                sys.exit('error: %s needs a value' % k)
            if k == '--slot':
                slot = int(v)
                if slot not in (1, 2):
                    sys.exit('error: --slot is 1 or 2')
            i += 2
        s = SLOTS[slot - 1]
        if not slot_valid(buf, slot - 1):
            sys.exit('error: slot %d is empty' % slot)
        i = 0
        while i < len(rest):
            k, v = rest[i], rest[i + 1]
            if k == '--money':
                if not 0 <= int(v) < 1 << 24:
                    sys.exit('error: money is saved in 24 bits (0-16777215)')
                buf[s + F_MONEY:s + F_MONEY + 3] = int(v).to_bytes(3, 'little')
            elif k == '--motive':
                name, val = v.split('=')
                if name not in MOTIVES:
                    sys.exit('error: motive is one of ' + ', '.join(MOTIVES))
                val = float(val)
                if not 0 <= val <= 100:
                    sys.exit('error: motive values are 0-100')
                struct.pack_into('<H', buf, s + F_MOTIVES + 2 * MOTIVES.index(name), round(val * 256))
            elif k == '--clock':
                h, _, m = v.partition(':')
                if not (0 <= int(h) < 24 and 0 <= int(m or 0) < 60):
                    sys.exit('error: --clock is HH:MM (00:00-23:59)')
                buf[s + F_CLOCK + 2] = int(h)
                buf[s + F_CLOCK + 3] = int(m or 0)
                buf[s + F_CLOCK + 4] = 0                     # seconds
            elif k != '--slot':
                sys.exit('error: unknown option ' + k)
            i += 2
        fix_block(buf, s, SLOT_SIZE)
    elif cmd == 'fix':
        fix_block(buf, 0, HEADER)
        for n, s in enumerate(SLOTS):
            if any(buf[s:s + SLOT_SIZE - 2]):
                fix_block(buf, s, SLOT_SIZE)
    else:
        sys.exit('unknown command ' + cmd)
    open(out, 'wb').write(buf)
    print('wrote ' + out)
    info(out)


if __name__ == '__main__':
    main(sys.argv[1:])
