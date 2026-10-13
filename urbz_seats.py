"""Extra seats (and other objects) in the game's places: a mod's "seats.json" adds object records to areas, so
chairs and sofas that are only drawn into a place's background become real seats townspeople can use.

  {"areas": {"42": [{"object": 156, "x": 220, "y": 330, "facing": 1, "note": "front sofa"}, ...]}}

The objects are the game's own (156 Invisible Love Seat, 134 Invisible Park Bench, ... docs/objects.md); the
records go into the area's base group (section 0, group 0), which every version of the place spawns when it
loads. Made at build time from your game's area files into the hidden generated mod build/new-seats (nothing
from the game is committed).

Area data (docs/areas.md): u16 H, u16 n_entry, entries; @H u8 n_sections, u8 variant_to_section[7];
@H+8 n_sections x {u16 offset, 6 bytes}; section {u16 offA, u16 offB, u16 flags, u16 offC} @+8 {u16 n_groups,
u16 off[] (from +8)}; group {u16 n, u8 size[n], pad to 4, records}. Object record (type 5, 16 bytes):
{u16 5, u16 0, s16 x, s16 y, u16 object, u8 facing, u8 0, u32 0 (3 zero bytes), u8 0xFF}.
"""
import json, os, shutil, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
AREA_TABLE = 0x020C87E0


class SeatsError(Exception):
    pass


def area_file(area):
    """The area's data asset: file number in project/assets."""
    import urbz_anims as A
    gid = struct.unpack_from('<I', A.arm9(), AREA_TABLE + area * 0x14 + 8 - 0x02000000)[0]
    return gid - 1


def object_record(obj, x, y, facing):
    return struct.pack('<HHhhHBB', 5, 0, x, y, obj, facing, 0) + b'\0\0\0\xff'


def records(d):
    """[(section, group, [record bytes])] of an area file."""
    H = struct.unpack_from('<H', d, 0)[0]
    out = []
    for s in range(d[H]):
        so = struct.unpack_from('<H', d, H + 8 + 8 * s)[0]
        for k in range(struct.unpack_from('<H', d, so + 8)[0]):
            go = so + 8 + struct.unpack_from('<H', d, so + 10 + 2 * k)[0]
            n = struct.unpack_from('<H', d, go)[0]
            p, recs = (go + 2 + n + 3) & ~3, []
            for sz in d[go + 2:go + 2 + n]:
                recs.append(d[p:p + sz])
                p += sz
            out.append((s, k, recs))
    return out


def add_records(d, new):
    """The area file with the records `new` (bytes each) added to section 0's group 0."""
    H = struct.unpack_from('<H', d, 0)[0]
    so = struct.unpack_from('<H', d, H + 8)[0]
    go = so + 8 + struct.unpack_from('<H', d, so + 10)[0]
    n = struct.unpack_from('<H', d, go)[0]
    sizes = list(d[go + 2:go + 2 + n])
    p = (go + 2 + n + 3) & ~3
    end = p + sum(sizes)
    old = d[p:end]
    sizes += [len(r) for r in new]
    if len(sizes) > 255 or any(s > 255 for s in sizes):
        raise SeatsError('too many records in one group')
    head = struct.pack('<H', len(sizes)) + bytes(sizes)
    head += b'\0' * (((go + len(head) + 3) & ~3) - (go + len(head)))
    group = head + old + b''.join(new)
    delta = len(group) - (end - go)
    out = bytearray(d[:go] + group + d[end:])
    # everything after the group moved by delta: section 0's lists and later groups, later sections
    offA, offB, flags, offC = struct.unpack_from('<4H', out, so)
    g0 = go - so
    struct.pack_into('<4H', out, so, *[o + delta if o and o > g0 else o for o in (offA, offB)], flags,
                     offC + delta if offC and offC > g0 else offC)
    ng = struct.unpack_from('<H', out, so + 8)[0]
    for k in range(1, ng):
        o = struct.unpack_from('<H', out, so + 10 + 2 * k)[0]
        struct.pack_into('<H', out, so + 10 + 2 * k, o + delta)
    for s in range(1, out[H]):
        o = struct.unpack_from('<H', out, H + 8 + 8 * s)[0]
        if o > so:
            struct.pack_into('<H', out, H + 8 + 8 * s, o + delta)
    if len(out) > 0x2000:
        raise SeatsError('area file over 8 KB (the game parses it into an 8 KB buffer)')
    return bytes(out)


def seats_mod(proj, mod_dirs, out_dir):
    """Mods' seats.json -> the hidden mod out_dir (area files with the extra records). (dirs, log line)."""
    want = {}
    for m in mod_dirs:
        p = os.path.join(m, 'seats.json')
        if os.path.exists(p):
            for area, items in json.load(open(p)).get('areas', {}).items():
                want.setdefault(int(area), []).extend(items)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    if not want:
        return None, ''
    os.makedirs(os.path.join(out_dir, 'assets'))
    n = 0
    for area, items in sorted(want.items()):
        f = area_file(area)
        d = open(os.path.join(proj, 'assets', '%05d.bin' % f), 'rb').read()
        new = [object_record(int(i['object']), int(i['x']), int(i['y']), int(i.get('facing', 3))) for i in items]
        open(os.path.join(out_dir, 'assets', '%05d.bin' % f), 'wb').write(add_records(d, new))
        n += len(new)
    json.dump({'name': 'new-seats', 'description': 'Kit: extra seats in places (seats.json)', 'toggle': False,
               'hidden': True}, open(os.path.join(out_dir, 'mod.json'), 'w'), indent=1)
    return [out_dir], 'seats: %d object(s) added in %d place(s)' % (n, len(want))


if __name__ == '__main__':
    import urbz_anims as A
    for area in [int(a) for a in sys.argv[1:]] or [42]:
        d = A.asset(area_file(area))
        for s, k, recs in records(d):
            for r in recs:
                t, _, x, y = struct.unpack_from('<HHhh', r)
                if t == 5:
                    print(area, 'section', s, 'group', k, 'object', struct.unpack_from('<H', r, 8)[0], 'at', x, y,
                          'facing', r[10])
