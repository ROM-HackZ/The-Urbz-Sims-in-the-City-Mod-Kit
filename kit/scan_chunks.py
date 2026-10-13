import struct
from urbzcomp import decompress, lz10_decompress, chunk_codec

FLAGS = (0x60, 0xE0)

def find_chunks(data, step=4):
    """Return [(offset, flags, size, consumed, output)] for every valid
    compressed chunk ([flags|size<<8] header + stream) found in data."""
    found = []
    pos = 0
    while pos + 8 <= len(data):
        h = struct.unpack_from('<I', data, pos)[0]
        flags, size = h & 0xFF, h >> 8
        if flags in FLAGS and 0 < size <= 0x400000:
            try:
                out, used = decompress(data, pos + 4, return_consumed=True)
                if len(out) == size:
                    found.append((pos, flags, size, used, out))
                    pos += 4 + ((used + 3) & ~3)
                    continue
            except Exception:
                pass
        pos += step
    return found


def find_trailing_nested(buf):
    """A nested stream at the END of a decoded chunk: [u16 length][EA stream]
    with no header (e.g. a screen's tile graphics). Returns (pos, L, tiles) or None."""
    found, p = None, 0
    n = len(buf)
    while p + 10 <= n:
        L = struct.unpack_from('<H', buf, p)[0]
        if 8 <= L <= n - p - 2 and n - (p + 2 + L) <= 3:
            dl = buf[p + 2]
            if dl and dl % 4 == 0 and dl <= 32 and buf[p + 5] <= 8:
                try:
                    out, used = decompress(buf, p + 2, return_consumed=True)
                    if L - 3 <= used <= L and len(out) >= 8:
                        found = (p, L, out)
                        break
                except Exception:
                    pass
        p += 2
    return found


def walk_chunks(data):
    """Read an asset as back-to-back chunks of any codec (0 raw, 1 LZ77, 6 EA).
    Returns [(offset, flags, size, slot, decoded)] only if the chunks cover the
    whole asset (up to 3 bytes of padding) AND at least one is compressed;
    otherwise None (then use find_chunks)."""
    pos, out = 0, []
    n = len(data)
    while pos + 4 <= n:
        h = struct.unpack_from('<I', data, pos)[0]
        flags, size = h & 0xFF, h >> 8
        codec = chunk_codec(flags)
        if size == 0 or size > 0x100000:
            return None
        try:
            if codec == 6:
                dec, used = decompress(data, pos + 4, return_consumed=True)
                if len(dec) != size:
                    return None
                slot = 4 + ((used + 3) & ~3)
            elif codec == 1 and flags & 0x0F == 0:
                dec, used = lz10_decompress(data, pos, return_consumed=True)
                slot = (used + 3) & ~3
            elif codec == 0 and flags & 0x0F == 0:
                slot = 4 + ((size + 3) & ~3)
                if pos + 4 + size > n:
                    return None
                dec = bytes(data[pos + 4:pos + 4 + size])
            else:
                return None
        except (ValueError, IndexError, struct.error):
            return None
        out.append((pos, flags, size, slot, dec))
        pos += slot
    if n - pos > 3 or not any(chunk_codec(f) in (1, 6) for _, f, _, _, _ in out):
        return None
    return out


def asset_chunks(data):
    """Best chunk list for an asset: a full walk if it tiles, else the EA scan.
    Returns [(offset, flags, size, slot, decoded)]."""
    w = walk_chunks(data)
    if w is not None:
        return w
    return [(off, fl, size, 4 + ((used + 3) & ~3), dec) for off, fl, size, used, dec in find_chunks(data)]
