#!/usr/bin/env python3
"""Edit the game's text (dialogue, menus, item and place names).

All 8,311 strings live in one Huffman-compressed bank: asset 00054 (game ID 55).
The game decodes a string by ID with the routine in ITCM at 0x01FF85C4 into a
1,024-byte buffer, so a string can be up to 1,023 bytes.

  python urbz_text.py find "sitting around"          search all strings
  python urbz_text.py show 5870 5871                 print strings by ID
  python urbz_text.py edit <mod> 5870 [5871 ...]     copy strings into a mod to edit
  python urbz_text.py export [file.tsv]              write every string (default project/text/strings.tsv)

A mod's text lives in mods/<mod>/text/strings.tsv: one string per line,
"ID<TAB>text". Edit the text column in any editor (keep the ID and the tab).
Accented letters (é, ñ, ü, ...) can be typed directly; they map to the game's font
codes. Escapes: \\n = new line, \\t = tab, \\\\ = backslash, \\xNN = a raw byte. Placeholders the game fills in: @1 @2 @3 (names),
@hh @mm @ss @am (clock). Keep them where the original has them.
The builder re-encodes the bank only when a mod changes text.
"""
import heapq, itertools, json, os, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
TEXT_ASSET = 54
MAX_LEN = 1023
MAX_NEW = 2000                      # new strings a mod may add after the game's (IDs 8311 and up)


# ---------------------------------------------------------------- bank codec

def decode_bank(a):
    tab = struct.unpack_from('<I', a, 0)[0]
    tree = struct.unpack_from('<%dH' % ((tab - 4) // 2), a, 4)
    first = struct.unpack_from('<I', a, tab)[0]
    n = (first - tab) // 4
    offs = struct.unpack_from('<%dI' % n, a, tab)
    out = []
    for o in offs:
        p, byte, bit, s = o + 1, a[o], 0, bytearray()
        while True:
            node = 0x100
            while node >= 0x100:
                node = tree[2 * (node - 0x100) + ((byte >> bit) & 1)]
                bit += 1
                if bit == 8:
                    byte = a[p] if p < len(a) else 0
                    p += 1
                    bit = 0
            if node == 0:
                break
            s.append(node)
            if len(s) > MAX_LEN:
                raise ValueError('string %d does not terminate' % len(out))
        out.append(bytes(s))
    return out


def encode_bank(strings):
    """Strings (bytes, no NULs) -> bank bytes in the game's format."""
    freq = {}
    for s in strings:
        for b in s:
            freq[b] = freq.get(b, 0) + 1
    freq[0] = freq.get(0, 0) + len(strings)              # one terminator per string
    if len(freq) < 2:
        freq[0x20] = freq.get(0x20, 0) + 1
    tie = itertools.count()
    heap = [(f, next(tie), ('leaf', b)) for b, f in freq.items()]
    heapq.heapify(heap)
    while len(heap) > 1:
        f1, _, a = heapq.heappop(heap)
        f2, _, b = heapq.heappop(heap)
        heapq.heappush(heap, (f1 + f2, next(tie), ('node', a, b)))
    root = heap[0][2]
    # Number internal nodes breadth-first from 0x100 (the game starts at 0x100).
    order, queue = [], [root]
    while queue:
        nd = queue.pop(0)
        if nd[0] == 'node':
            order.append(nd)
            queue += [nd[1], nd[2]]
    num = {id(nd): 0x100 + k for k, nd in enumerate(order)}
    if 0x100 + len(order) > 0xFFFF:
        raise ValueError('too many symbols')
    tree = []
    codes = {}
    for nd in order:
        for child in (nd[1], nd[2]):
            tree.append(child[1] if child[0] == 'leaf' else num[id(child)])

    def walk(nd, code, length):
        if nd[0] == 'leaf':
            codes[nd[1]] = (code, length)
        else:
            walk(nd[1], code, length + 1)                  # bit 0 -> first child
            walk(nd[2], code | (1 << length), length + 1)   # bit 1 -> second child
    walk(root, 0, 0)

    tab = 4 + 2 * len(tree)
    tab = (tab + 3) & ~3
    data_start = tab + 4 * len(strings)
    blobs, offs, pos = [], [], data_start
    for s in strings:
        acc, nbits = 0, 0
        for b in bytes(s) + b'\0':
            c, l = codes[b]
            acc |= c << nbits
            nbits += l
        blob = acc.to_bytes((nbits + 7) // 8 or 1, 'little')
        offs.append(pos)
        blobs.append(blob)
        pos += len(blob)
    out = bytearray(struct.pack('<I', tab))
    out += struct.pack('<%dH' % len(tree), *tree)
    out += b'\0' * (tab - len(out))
    out += struct.pack('<%dI' % len(offs), *offs)
    for b in blobs:
        out += b
    out += b'\0' * (4 + (-len(out) % 4))       # the decoder reads one byte ahead
    return bytes(out)


# ---------------------------------------------------------------- TSV escaping

# The game's fonts (urbz_font.py) put Western-European letters at 0x7B-0xB8. In the TSV
# they appear as the real characters; \xNN still works for any byte.
CODEPAGE = dict(zip(range(0x7B, 0xB9),
                    '\u00a9\u0153\u00a1\u00bf\u00c0'      # 7B-7F  © œ ¡ ¿ À
                    'ÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑ'                 # 80-8F
                    'ÒÓÔÕÖØÙÚÜßàáâãäå'                 # 90-9F
                    'æçèéêëìíîïñòóôõö'                 # A0-AF
                    'øùúûüºª\u2026\u2122'))             # B0-B8  … ™
UNICODE = {v: k for k, v in CODEPAGE.items()}

def escape(s):
    o = []
    for b in s:
        if b == 0x5C:
            o.append('\\\\')
        elif b == 0x0A:
            o.append('\\n')
        elif b == 0x09:
            o.append('\\t')
        elif 0x20 <= b < 0x7B:
            o.append(chr(b))
        elif b in CODEPAGE:
            o.append(CODEPAGE[b])
        else:
            o.append('\\x%02X' % b)
    return ''.join(o)


def unescape(t, where=''):
    o = bytearray()
    i = 0
    while i < len(t):
        c = t[i]
        if c == '\\' and i + 1 < len(t):
            n = t[i + 1]
            if n == 'n':
                o.append(10); i += 2; continue
            if n == 't':
                o.append(9); i += 2; continue
            if n == '\\':
                o.append(0x5C); i += 2; continue
            if n in 'xX' and i + 3 < len(t) + 1:
                try:
                    o.append(int(t[i + 2:i + 4], 16)); i += 4; continue
                except ValueError:
                    pass
            raise ValueError('%sunknown escape "\\%s"' % (where, n))
        if c in UNICODE:
            o.append(UNICODE[c])
        elif ord(c) > 0x7E or ord(c) < 0x20:
            raise ValueError('%scharacter %r is not in the game font (it has ASCII and %s); '
                             'add it with urbz_font.py and use a \\xNN escape'
                             % (where, c, ''.join(CODEPAGE.values())))
        else:
            o.append(ord(c))
        i += 1
    if 0 in o:
        raise ValueError('%stext cannot contain \\x00' % where)
    return bytes(o)


def read_tsv(path):
    """-> {id: bytes}. Lines: ID<TAB>text. Blank lines and # comments are ignored."""
    out = {}
    for ln, line in enumerate(open(path, encoding='utf-8-sig'), 1):
        line = line.rstrip('\r\n')
        if not line.strip() or line.startswith('#'):
            continue
        if '\t' not in line:
            raise ValueError('%s line %d: expected "ID<TAB>text"' % (path, ln))
        sid, text = line.split('\t', 1)
        if sid.strip().lower() == 'id':
            continue
        try:
            sid = int(sid)
        except ValueError:
            raise ValueError('%s line %d: "%s" is not a string ID' % (path, ln, sid))
        out[sid] = unescape(text, '%s line %d: ' % (path, ln))
    return out


# ---------------------------------------------------------------- project glue

def project_strings(proj):
    m = json.load(open(os.path.join(proj, 'manifest.json')))
    a = open(os.path.join(proj, 'assets', m['entries'][TEXT_ASSET]['file']), 'rb').read()
    return decode_bank(a)


def build_text_asset(proj, overlay):
    """If enabled mods edit text, return the new bank bytes; else None."""
    rel = 'text/strings.tsv'
    paths = [p for name, p in _mod_text_files(overlay)]
    if not paths:
        return None
    strings = project_strings(proj)
    n_game = len(strings)
    edits = {}
    for name, p in _mod_text_files(overlay):
        for sid, s in read_tsv(p).items():
            if not 0 <= sid < n_game + MAX_NEW:
                raise ValueError('mod "%s": string ID %d is out of range (0-%d are the game\'s; new '
                                 'strings may use %d-%d)' % (name, sid, n_game - 1, n_game,
                                                             n_game + MAX_NEW - 1))
            if len(s) > MAX_LEN:
                raise ValueError('mod "%s": string %d is %d bytes; the game buffer holds %d'
                                 % (name, sid, len(s), MAX_LEN))
            edits[sid] = s
    if all(i < n_game and strings[i] == s for i, s in edits.items()):
        return None
    if edits and max(edits) >= n_game:                # new strings go after the game's (gaps stay empty)
        strings += [b''] * (max(edits) + 1 - n_game)
    for i, s in edits.items():
        strings[i] = s
    bank = encode_bank(strings)
    assert decode_bank(bank) == strings, 'text bank self-check failed'
    return bank


def _mod_text_files(overlay):
    out = []
    for md in overlay.mod_dirs:
        p = os.path.join(md, 'text', 'strings.tsv')
        if os.path.exists(p):
            out.append((os.path.basename(os.path.normpath(md)), p))
    return out


def export(proj, path):
    strings = project_strings(proj)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# The Urbz DS text, read-only reference. To change a line, copy it into a\n'
                '# mod with: python urbz_text.py edit <mod> <ID>   (see urbz_text.py --help)\n')
        f.write('ID\ttext\n')
        for i, s in enumerate(strings):
            f.write('%d\t%s\n' % (i, escape(s)))
    return len(strings)


def main(argv):
    proj = os.path.join(KIT, 'project')
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == 'find':
        if not args:
            sys.exit('usage: urbz_text.py find "words"')
        q = args[0].lower()
        hits = [(i, s) for i, s in enumerate(project_strings(proj)) if q in s.decode('latin-1').lower()]
        for i, s in hits[:200]:
            print('%5d  %s' % (i, escape(s)))
        print('(%d match%s)' % (len(hits), '' if len(hits) == 1 else 'es'))
    elif cmd == 'show':
        S = project_strings(proj)
        for a in args:
            print('%5d  %s' % (int(a), escape(S[int(a)])))
    elif cmd == 'export':
        path = args[0] if args else os.path.join(proj, 'text', 'strings.tsv')
        print('wrote %d strings to %s' % (export(proj, path), path))
    elif cmd == 'edit':
        if len(args) < 2:
            sys.exit('usage: urbz_text.py edit <mod> <ID> [<ID> ...]')
        md = os.path.join(KIT, 'mods', args[0])
        if not os.path.isdir(md):
            sys.exit('error: no mod named "%s" (create it: python urbz_mod.py new %s)' % (args[0], args[0]))
        S = project_strings(proj)
        path = os.path.join(md, 'text', 'strings.tsv')
        have = read_tsv(path) if os.path.exists(path) else {}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = 0
        with open(path, 'a', encoding='utf-8', newline='\n') as f:
            if not have and os.path.getsize(path) == 0:
                f.write('ID\ttext\n')
            for a in args[1:]:
                i = int(a)
                if not 0 <= i < len(S):
                    sys.exit('error: string IDs run from 0 to %d' % (len(S) - 1))
                if i in have:
                    print('already in the mod: %d' % i)
                    continue
                f.write('%d\t%s\n' % (i, escape(S[i])))
                new += 1
        print('added %d line(s) to %s; edit the text after the tab' % (new, path))
    else:
        sys.exit('unknown command %s. Run: python urbz_text.py help' % cmd)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except BrokenPipeError:          # e.g. piped into `head`
        pass
