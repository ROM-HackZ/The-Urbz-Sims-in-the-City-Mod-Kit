"""The Urbz DS custom compression (decompressor at ITCM 0x01FF8C50).

A faithful translation of the game's hand-written ARM routine, including its
halfword-output quirks, so decompressed output is byte-exact.

Stream layout:
  u8  dict_len        bytes of dictionary that follow the header (multiple of 4, <= 32)
  u8  escape          literal-prefix value that signals a control code
  u8  off_bits        extra low bits for long match distances
  u8  pfx_bits        bits in a literal's prefix (literal = pfx_bits + (8 - pfx_bits))
  u8  dictionary[dict_len]
  bitstream of 32-bit little-endian words, read MSB first
"""
import struct


class BitReader:
    def __init__(self, data, pos):
        self.data, self.pos = data, pos
        self.buf, self.left = 0, 0          # buf holds `left` unread bits, MSB first

    def bit(self):
        if self.left == 0:
            self.buf = struct.unpack_from('<I', self.data, self.pos)[0]
            self.pos += 4
            self.left = 32
        self.left -= 1
        return (self.buf >> self.left) & 1

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v

    def gamma(self):
        """Unary-prefixed gamma: n one-bits ended by a zero (or capped at 7
        ones, no terminator), then n value bits. Values 1..255."""
        n = 0
        while n < 7 and self.bit() == 1:
            n += 1
        return (1 << n) | self.bits(n)


def decompress(data, start=0, return_consumed=False):
    hdr = struct.unpack_from('<I', data, start)[0]
    dict_len = hdr & 0xFF
    escape = (hdr >> 8) & 0xFF
    off_bits = (hdr >> 16) & 0xFF
    pfx_bits = (hdr >> 24) & 0xFF
    lit_bits = 8 - pfx_bits
    if dict_len == 0 or dict_len % 4 or dict_len > 32 or pfx_bits > 8:
        raise ValueError('not an Urbz-compressed stream')
    table = data[start + 4:start + 4 + dict_len]
    br = BitReader(data, start + 4 + dict_len)

    out = bytearray()
    sl = 0                       # pending low byte (register sl), valid when len(out) odd

    def emit(v):
        nonlocal sl
        if len(out) & 1 == 0:
            sl = v
            out.append(v & 0xFF)
        else:
            # halfword store of (sl + v<<8); the high byte is what lands in memory
            out.append(((sl + (v << 8)) >> 8) & 0xFF)

    def fill(v, n):
        for _ in range(n):
            emit(v & 0xFF)

    while True:
        pfx = br.bits(pfx_bits) if pfx_bits else 0
        if pfx != escape:
            lit = (pfx << lit_bits) | br.bits(lit_bits) if lit_bits else pfx
            emit(lit)
            continue

        g = br.gamma()
        if g >= 2:
            # long match: length g+1, distance from gamma (+off_bits) and a byte
            g2 = br.gamma()
            if g2 == 0xFF:
                break
            hi = g2 - 1
            if off_bits:
                hi = (hi << off_bits) | br.bits(off_bits)
            dist = ((hi << 8) | br.bits(8)) + 1
            copy(out, dist, g + 1, emit, fill)
            continue

        if br.bit() == 0:
            # short match: length 2, 8-bit distance
            dist = br.bits(8) + 1
            copy(out, dist, 2, emit, fill)
            continue

        if br.bit() == 0:
            # escaped literal: emit a literal whose prefix is the escape value,
            # and adopt a new escape value
            new_esc = br.bits(pfx_bits) if pfx_bits else 0
            old = escape
            escape = new_esc
            lit = (old << lit_bits) | br.bits(lit_bits) if lit_bits else old
            emit(lit)
            continue

        # run of one byte value
        g1 = br.gamma()
        run_lo, run_hi = g1, 0
        if g1 >= 0x80:
            run_lo = ((g1 << 1) | br.bit()) & 0xFF
            run_hi = br.gamma() - 1
        gv = br.gamma()
        if gv < 0x20:
            val = table[gv - 1]
        else:
            val = ((gv << 3) | br.bits(3)) & 0xFF
        fill(val, run_lo + 1 + (run_hi << 8))

    consumed = br.pos - start
    return (bytes(out), consumed) if return_consumed else bytes(out)


def copy(out, dist, length, emit, fill):
    # The ARM routine has fast paths for dist 1 / odd alignment, but they all
    # produce standard overlapping-LZ output.
    for _ in range(length):
        emit(out[-dist])


# ---------------------------------------------------------------- compressor

class BitWriter:
    def __init__(self):
        self.words, self.cur, self.n = [], 0, 0

    def bit(self, b):
        self.cur = (self.cur << 1) | (b & 1)
        self.n += 1
        if self.n == 32:
            self.words.append(self.cur)
            self.cur, self.n = 0, 0

    def bits(self, v, n):
        for i in range(n - 1, -1, -1):
            self.bit((v >> i) & 1)

    def gamma(self, v):
        assert 1 <= v <= 255
        n = v.bit_length() - 1
        for _ in range(n):
            self.bit(1)
        if n < 7:
            self.bit(0)
        self.bits(v, n)                 # low n bits (leading 1 is implicit)

    def getvalue(self):
        words = list(self.words)
        if self.n:
            words.append(self.cur << (32 - self.n))
        return struct.pack('<%dI' % len(words), *words)


def _gbits(v):
    """Bit cost of gamma(v), v in 1..255."""
    n = v.bit_length() - 1
    return 2 * n + (1 if n < 7 else 0)


GBITS = [0] + [_gbits(v) for v in range(1, 256)]
SELF_CHECK_FALLBACKS = 0
MAX_MATCH = 256
CHAIN = 48


def _run_len_cost(total):
    """Bits to encode a run length `total` (>= 2), or None if impossible."""
    if 2 <= total <= 128:
        return GBITS[total - 1]
    t = total - 1
    hi = t >> 8
    if hi > 254:
        return None
    return 14 + 1 + GBITS[hi + 1]


def _candidates(data, off_bits):
    """Per position: list of (length, cost_bits_without_prefix, kind, arg).
    kind: 'm' long match (arg=dist), 's' short match (arg=dist), 'r' run (arg=None)."""
    n = len(data)
    max_hi = (254 << off_bits) - 1
    max_dist = (max_hi << 8) + 256
    head, prev, last2 = {}, [-1] * n, {}
    cands = [None] * n
    run_end = [0] * n                      # length of the run of equal bytes starting at i
    j = n - 1
    while j >= 0:
        run_end[j] = run_end[j + 1] + 1 if j + 1 < n and data[j + 1] == data[j] else 1
        j -= 1
    for i in range(n):
        c = []
        if i + 2 < n:
            j = head.get(data[i:i + 3], -1)
            tries, best = 0, 2
            lim = min(MAX_MATCH, n - i)
            while j >= 0 and tries < CHAIN and best < lim:
                d = i - j
                if d > max_dist:
                    break
                l = 3
                while l < lim and data[j + l] == data[i + l]:
                    l += 1
                if l > best:
                    hi = (d - 1) >> 8
                    dc = GBITS[(hi >> off_bits) + 1] + off_bits + 8
                    for L in range(best + 1, l + 1):
                        c.append((L, GBITS[L - 1] + dc, 'm', d))
                    best = l
                j = prev[j]
                tries += 1
        if i + 1 < n:
            j = last2.get(data[i:i + 2], -1)
            if j >= 0 and i - j <= 256:
                c.append((2, 1 + 1 + 8, 's', i - j))
        r = run_end[i]
        if r >= 2:
            lens = set(range(2, min(r, 9))) | {r, min(r, 128), min(r, 129)}
            k = 16
            while k < r:
                lens.add(k)
                k *= 2
            for L in lens:
                if 2 <= L <= r:
                    lc = _run_len_cost(L)
                    if lc is not None:
                        c.append((L, 3 + lc, 'r', None))       # +value cost added per table
        cands[i] = c
        if i + 2 < n:
            k3 = data[i:i + 3]
            prev[i] = head.get(k3, -1)
            head[k3] = i
        if i + 1 < n:
            last2[data[i:i + 2]] = i
    return cands


def _value_cost(b, tidx):
    i = tidx.get(b)
    return GBITS[i + 1] if i is not None and i < 31 else GBITS[32 + (b >> 3)] + 3


def _optimal(data, cands, pfx_bits, off_bits, table):
    """DP over (position, escape). Returns (bits, initial_escape, ops)."""
    n = len(data)
    INF = 1 << 60
    lit_bits = 8 - pfx_bits
    E = 1 << pfx_bits
    tidx = {}
    for k, b in enumerate(table):
        tidx.setdefault(b, k)
    plain = pfx_bits + lit_bits
    escaped = 2 * pfx_bits + 3 + lit_bits
    cost = [[INF] * E for _ in range(n + 1)]
    back = [[None] * E for _ in range(n + 1)]
    for e in range(E):
        cost[0][e] = 0
    for i in range(n):
        row = cost[i]
        b = data[i]
        p = b >> lit_bits if pfx_bits else 0
        vcost = _value_cost(b, tidx)
        nxt = cost[i + 1]
        bnx = back[i + 1]
        best_e = min(range(E), key=row.__getitem__)
        for e in range(E):
            c0 = row[e]
            if c0 >= INF:
                continue
            if p != e:
                if pfx_bits:
                    v = c0 + plain
                    if v < nxt[e]:
                        nxt[e] = v
                        bnx[e] = (i, e, 'l', None)
            else:
                v = c0 + escaped
                for e2 in range(E):
                    if v < nxt[e2]:
                        nxt[e2] = v
                        bnx[e2] = (i, e, 'x', e2)
            for L, oc, kind, arg in cands[i]:
                v = c0 + pfx_bits + oc + (vcost if kind == 'r' else 0)
                tgt = cost[i + L]
                if v < tgt[e]:
                    tgt[e] = v
                    back[i + L][e] = (i, e, kind, (L, arg))
    end_bits = pfx_bits + GBITS[2] + GBITS[255]
    e = min(range(E), key=cost[n].__getitem__)
    total = cost[n][e] + end_bits
    ops = []
    i = n
    while i > 0:
        pi, pe, kind, arg = back[i][e]
        ops.append((pi, pe, kind, arg))
        i, e = pi, pe
    ops.reverse()
    init_esc = ops[0][1] if ops else 0
    return total, init_esc, ops


def _emit(data, pfx_bits, off_bits, table, init_esc, ops):
    w = BitWriter()
    lit_bits = 8 - pfx_bits
    mask = (1 << lit_bits) - 1
    tidx = {}
    for k, b in enumerate(table):
        tidx.setdefault(b, k)
    esc = init_esc
    for pos, e, kind, arg in ops:
        assert e == esc
        b = data[pos]
        if kind == 'l':
            w.bits(b >> lit_bits, pfx_bits)
            w.bits(b & mask, lit_bits)
            continue
        w.bits(esc, pfx_bits)
        if kind == 'x':                   # escaped literal (prefix == esc), switch escape
            w.gamma(1); w.bit(1); w.bit(0)
            w.bits(arg, pfx_bits)
            w.bits(b & mask, lit_bits)
            esc = arg
        elif kind == 's':
            L, d = arg
            w.gamma(1); w.bit(0); w.bits(d - 1, 8)
        elif kind == 'm':
            L, d = arg
            hi, lo = (d - 1) >> 8, (d - 1) & 0xFF
            w.gamma(L - 1)
            w.gamma((hi >> off_bits) + 1)
            if off_bits:
                w.bits(hi & ((1 << off_bits) - 1), off_bits)
            w.bits(lo, 8)
        elif kind == 'r':
            L, _ = arg
            w.gamma(1); w.bit(1); w.bit(1)
            if L <= 128:
                w.gamma(L - 1)
            else:
                t = L - 1
                lo, hi = t & 0xFF, t >> 8
                w.gamma(128 + (lo >> 1)); w.bit(lo & 1); w.gamma(hi + 1)
            k = tidx.get(b)
            if k is not None and k < 31:
                w.gamma(k + 1)
            else:
                w.gamma(32 + (b >> 3)); w.bits(b & 7, 3)
    w.bits(esc, pfx_bits)
    w.gamma(2)
    w.gamma(255)
    return w.getvalue()


def compress(data, flags=None, effort=2):
    """Compress bytes into an Urbz stream (optimal parse, verified by decoding).
    effort 2 = full parameter search; 1 = fewer combinations (big inputs).
    If flags is given, prepend the 4-byte chunk header (flags | len << 8)."""
    data = bytes(data)
    if not data:
        return compress_fast(data, flags)
    from collections import Counter
    common = [b for b, _ in Counter(data).most_common(32)]
    if effort < 2 or len(data) > 32768:
        dict_sizes, pfx_set = (8,), (1, 2)
    else:
        dict_sizes, pfx_set = (4, 8, 16, 32), (0, 1, 2, 3)
    best = None
    for off_bits in ((0,) if len(data) <= 65024 else (0, 1, 2)):
        cands = _candidates(data, off_bits)
        for tl in dict_sizes:
            table = bytes((common + [0] * 32)[:tl])
            for pfx_bits in pfx_set:
                bits, esc, ops = _optimal(data, cands, pfx_bits, off_bits, table)
                size = 4 + tl + ((bits + 31) // 32) * 4
                if best is None or size < best[0]:
                    best = (size, pfx_bits, off_bits, table, esc, ops)
    size, pfx_bits, off_bits, table, esc, ops = best
    body = _emit(data, pfx_bits, off_bits, table, esc, ops)
    stream = struct.pack('<BBBB', len(table), esc, off_bits, pfx_bits) + table + body
    if decompress(stream) != data:          # never ship a stream the game can't read back
        global SELF_CHECK_FALLBACKS
        SELF_CHECK_FALLBACKS += 1
        import sys
        print('urbzcomp: optimal encoder self-check failed; using the greedy encoder',
              file=sys.stderr)
        return compress_fast(data, flags)
    if flags is not None:
        stream = struct.pack('<I', (flags & 0xFF) | (len(data) << 8)) + stream
    return stream


# ---- fast greedy encoder (kept for bulk checks and as a fallback) ----

def _find_matches(data, max_dist, chain_limit=48):
    n = len(data)
    head, prev = {}, [-1] * n
    last2 = {}
    ins = 0

    def index_to(upto):
        nonlocal ins
        while ins < upto:
            if ins + 2 < n:
                k = data[ins:ins + 3]
                prev[ins] = head.get(k, -1)
                head[k] = ins
            if ins + 1 < n:
                last2[data[ins:ins + 2]] = ins
            ins += 1

    def longest(i):
        index_to(i)
        if i + 2 >= n:
            return 0, 0
        best_len, best_dist = 0, 0
        limit = min(MAX_MATCH, n - i)
        j, tries = head.get(data[i:i + 3], -1), 0
        while j >= 0 and tries < chain_limit:
            d = i - j
            if d > max_dist:
                break
            l = 3
            while l < limit and data[j + l] == data[i + l]:
                l += 1
            if l > best_len:
                best_len, best_dist = l, d
                if l == limit:
                    break
            j, tries = prev[j], tries + 1
        return best_len, best_dist

    ops, i = [], 0
    while i < n:
        l, d = longest(i)
        if l >= 3:
            l2, d2 = longest(i + 1) if i + 1 < n else (0, 0)
            if l2 > l + 1:
                ops.append(('lit', data[i]))
                i += 1
                l, d = l2, d2
            ops.append(('match', d, l))
            i += l
            continue
        index_to(i)
        if i + 1 < n:
            j = last2.get(data[i:i + 2], -1)
            if j >= 0 and i - j <= 256:
                ops.append(('match', i - j, 2))
                i += 2
                continue
        ops.append(('lit', data[i]))
        i += 1
    return ops


def _encode_greedy(ops, pfx_bits, escape, off_bits):
    w = BitWriter()
    lit_bits = 8 - pfx_bits
    esc = escape
    for op in ops:
        if op[0] == 'lit':
            b = op[1]
            pfx = b >> lit_bits if lit_bits < 8 else 0
            if pfx_bits and pfx != esc:
                w.bits(pfx, pfx_bits)
                w.bits(b & ((1 << lit_bits) - 1), lit_bits)
            else:
                w.bits(esc, pfx_bits)
                w.gamma(1); w.bit(1); w.bit(0)
                w.bits(esc, pfx_bits)
                w.bits(b & ((1 << lit_bits) - 1), lit_bits)
        else:
            _, dist, length = op
            w.bits(esc, pfx_bits)
            if length == 2:
                w.gamma(1); w.bit(0); w.bits(dist - 1, 8)
            else:
                d = dist - 1
                hi, lo = d >> 8, d & 0xFF
                w.gamma(length - 1)
                w.gamma((hi >> off_bits) + 1)
                if off_bits:
                    w.bits(hi & ((1 << off_bits) - 1), off_bits)
                w.bits(lo, 8)
    w.bits(esc, pfx_bits)
    w.gamma(2)
    w.gamma(255)
    return w.getvalue()


def compress_fast(data, flags=None):
    """Greedy encoder: quick, ~7% bigger than the game's own files."""
    data = bytes(data)
    best = None
    for off_bits in ((0,) if len(data) <= 65024 else (0, 1, 2)):
        max_hi = (254 << off_bits) - 1
        ops = _find_matches(data, (max_hi << 8) + 256)
        hist = [0] * 256
        for op in ops:
            if op[0] == 'lit':
                hist[op[1]] += 1
        for pfx_bits in (0, 1, 2, 3):
            lit_bits = 8 - pfx_bits
            if pfx_bits == 0:
                esc = 0
            else:
                counts = [0] * (1 << pfx_bits)
                for b in range(256):
                    counts[b >> lit_bits] += hist[b]
                esc = min(range(len(counts)), key=counts.__getitem__)
            table = bytes(4)
            stream = struct.pack('<BBBB', 4, esc, off_bits, pfx_bits) + table + \
                _encode_greedy(ops, pfx_bits, esc, off_bits)
            if best is None or len(stream) < len(best):
                best = stream
    if flags is not None:
        best = struct.pack('<I', (flags & 0xFF) | (len(data) << 8)) + best
    return best


# ------------------------------------------------------------ 16-bit delta
# Chunks with flags 0xE0 are delta-encoded halfwords; after decompressing,
# the game runs x[i] += x[i-1] over the buffer (FUN_0202d928).

DELTA_FLAG = 0x80


def undelta16(b):
    n = len(b) // 2
    v = list(struct.unpack_from('<%dH' % n, b))
    for i in range(1, n):
        v[i] = (v[i] + v[i - 1]) & 0xFFFF
    return struct.pack('<%dH' % n, *v) + bytes(b[n * 2:])


def delta16(b):
    n = len(b) // 2
    v = struct.unpack_from('<%dH' % n, b)
    out = [v[0]] if n else []
    out += [(v[i] - v[i - 1]) & 0xFFFF for i in range(1, n)]
    return struct.pack('<%dH' % n, *out) + bytes(b[n * 2:])


def unpack_chunk(flags, raw):
    """Decompressed bytes -> what the game actually uses."""
    return undelta16(raw) if flags & DELTA_FLAG else raw


# ------------------------------------------------- other chunk codecs
# Chunk header flags bits 4-6 pick the codec (FUN_0202d760): 0 = stored raw,
# 1 = Nintendo BIOS LZ77 (the chunk header doubles as the LZ77 header),
# 6 = EA bitstream. Codecs 2/3/4 are supported by the game but unused here.

def lz10_decompress(data, pos=0, return_consumed=False):
    """BIOS LZ77 (type 0x10). data[pos] is the 4-byte header."""
    h = struct.unpack_from('<I', data, pos)[0]
    if h & 0xF0 != 0x10:
        raise ValueError('not LZ77')
    size = h >> 8
    out = bytearray()
    i = pos + 4
    while len(out) < size:
        flags = data[i]
        i += 1
        for b in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> b):
                x = (data[i] << 8) | data[i + 1]
                i += 2
                n, disp = (x >> 12) + 3, (x & 0xFFF) + 1
                if disp > len(out):
                    raise ValueError('bad LZ77 back-reference')
                for _ in range(n):
                    out.append(out[-disp])
            else:
                out.append(data[i])
                i += 1
    out = bytes(out[:size])
    return (out, i - pos) if return_consumed else out


def lz10_compress(raw):
    """Optimal-parse BIOS LZ77 encoder (type 0x10 header included).
    Never uses distance 1, so the output is also safe for the BIOS VRAM decoder."""
    raw = bytes(raw)
    n = len(raw)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    choice = [None] * (n + 1)
    cost[0] = 0
    head, prev = {}, [-1] * n
    for i in range(n):
        c = cost[i]
        if c + 9 < cost[i + 1]:
            cost[i + 1] = c + 9
            choice[i + 1] = (i, 0, 0)
        if i + 2 < n:
            j, tries, best = head.get(raw[i:i + 3], -1), 0, 2
            lim = min(18, n - i)
            while j >= 0 and tries < 64 and best < lim:
                d = i - j
                if d > 4096:
                    break
                if d >= 2:
                    l = 3
                    while l < lim and raw[j + l] == raw[i + l]:
                        l += 1
                    for L in range(best + 1, l + 1):
                        if c + 17 < cost[i + L]:
                            cost[i + L] = c + 17
                            choice[i + L] = (i, L, d)
                    best = max(best, l)
                j = prev[j]
                tries += 1
            k = raw[i:i + 3]
            prev[i] = head.get(k, -1)
            head[k] = i
    toks = []
    i = n
    while i > 0:
        pi, L, d = choice[i]
        toks.append((pi, L, d))
        i = pi
    toks.reverse()
    out = bytearray(struct.pack('<I', 0x10 | (n << 8)))
    for g in range(0, len(toks), 8):
        group = toks[g:g + 8]
        flag = 0
        body = bytearray()
        for k, (pos, L, d) in enumerate(group):
            if L:
                flag |= 0x80 >> k
                x = ((L - 3) << 12) | (d - 1)
                body += bytes((x >> 8, x & 0xFF))
            else:
                body.append(raw[pos])
        out.append(flag)
        out += body
    while len(out) % 4:
        out.append(0)
    return bytes(out)


def chunk_codec(flags):
    return (flags >> 4) & 7


def pack_chunk(flags, content):
    """Inverse of unpack_chunk, then encode with the chunk's own codec and header."""
    raw = delta16(content) if flags & DELTA_FLAG else content
    codec = chunk_codec(flags)
    if codec == 6:
        return compress(raw, flags=flags)
    if codec == 1:
        packed = lz10_compress(raw)
        packed = bytes([(packed[0] & 0x0F) | (flags & 0xF0)]) + packed[1:]
        if lz10_decompress(packed) != raw:
            raise AssertionError('LZ77 self-check failed')
        return packed
    if codec == 0:
        return struct.pack('<I', (flags & 0xFF) | (len(raw) << 8)) + raw
    raise ValueError('chunk codec %d is not supported for re-packing' % codec)
