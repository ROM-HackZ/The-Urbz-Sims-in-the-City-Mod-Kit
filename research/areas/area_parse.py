"""Static parser for Urbz DS area tables and area data assets.

Tables in arm9 (vanilla):
  AREA_TABLE   0x020C87E0, 80 x 0x14: {u32 ptr?, u32 name_string, u32 data_asset_gid, u8[4] misc, u32 misc2}
  AREA_GFX     0x020C8E20, 80 x 0x50: 16 u32 asset ids (4 groups of {a,b,0,0}) + u32 x3 assets + u32 byte
Area data asset (raw, no chunks), parsed like FUN_0201279c / FUN_02012820:
  u16 H, u16 n_entry, n_entry x {s16 x, s16 y, u16 id, u16 dir}
  @H: u8 n_sections, u8 variant_to_section[7]
  @H+8: n_sections x {u16 offset, 6 bytes}
  section: {u16 offA, u16 offB, u16 flags, u16 offC} (offsets relative to section start)
           @+8: {u16 n_groups, u16 off[n] rel to +8}
           group: {u16 n, u8 size[n], pad to 4, records...}, record = {u16 type, ...}
"""
import struct, json, os, sys
ARM9 = open('/root/urbz/arm9.bin', 'rb').read()
ASSETS = '/root/urbz/kit9/project/assets'
u32 = lambda a: struct.unpack_from('<I', ARM9, a - 0x02000000)[0]
NAMES = {}

def load_names():
    sys.path.insert(0, '/root/urbz/kit9')
    import urbz_text as T
    return T

def area_table():
    out = []
    for i in range(80):
        ptr, name, gid, misc, misc2 = struct.unpack_from('<IIIII', ARM9, 0x020C87E0 + i * 0x14 - 0x02000000)
        g = struct.unpack_from('<20I', ARM9, 0x020C8E20 + i * 0x50 - 0x02000000)
        out.append(dict(id=i, name_string=name, data_gid=gid, ptr=ptr, misc='%08x' % misc, misc2=misc2,
                        gfx_assets=[x for x in g[:19] if x], gfx_byte=g[19]))
    return out

def parse_group(d, off):
    n = struct.unpack_from('<H', d, off)[0]
    sizes = list(d[off + 2: off + 2 + n])
    p = off + 2 + n
    p = (p + 3) & ~3
    recs = []
    for s in sizes:
        rec = d[p:p + s]
        t = struct.unpack_from('<H', rec, 0)[0]
        r = dict(type=t, size=s, raw=rec.hex())
        if t == 7:
            x, y = struct.unpack_from('<hh', rec, 4)
            r.update(x=x, y=y, char=rec[8], facing=rec[9])
        recs.append(r)
        p += s
    return recs

def parse_section(d, so):
    offA, offB, flags, offC = struct.unpack_from('<4H', d, so)
    ng = struct.unpack_from('<H', d, so + 8)[0]
    groups = []
    for k in range(ng):
        go = struct.unpack_from('<H', d, so + 8 + 2 + 2 * k)[0]
        groups.append(parse_group(d, so + 8 + go))
    # offA / offB lists: u16 count + u16 offsets (rel. to list start); store counts only
    def lst(o):
        if o == 0 or so + o + 2 > len(d):
            return None
        return struct.unpack_from('<H', d, so + o)[0]
    return dict(offset=so, flags=flags, include_base=bool(flags & 1), n_listA=lst(offA), n_listB=lst(offB),
                groups=groups)

def parse_area(gid):
    d = open(os.path.join(ASSETS, '%05d.bin' % (gid - 1)), 'rb').read()
    H, ne = struct.unpack_from('<HH', d, 0)
    entries = [dict(zip(('x', 'y', 'id', 'dir'), struct.unpack_from('<hhHH', d, 4 + 8 * i))) for i in range(ne)]
    nsec = d[H]
    vmap = list(d[H + 1:H + 8])
    secs = []
    for s in range(nsec):
        so = struct.unpack_from('<H', d, H + 8 + 8 * s)[0]
        secs.append(parse_section(d, so))
    return dict(size=len(d), entries=entries, n_sections=nsec, variant_to_section=vmap, sections=secs)

if __name__ == '__main__':
    T = load_names()
    tab = area_table()
    for a in tab[:3] + tab[68:72]:
        p = parse_area(a['data_gid'])
        print(a['id'], a['data_gid'], p['size'], p['entries'], p['n_sections'], p['variant_to_section'])
        for si, s in enumerate(p['sections']):
            print('  sec', si, s['flags'], s['n_listA'], s['n_listB'], [[(r['type'], r.get('char')) for r in g] for g in s['groups']])
