"""Two Worlds 1 .par reader/writer (parameter database).

Format per the reverse-engineered spec in TwStuff\\Par editor\\PAR_FORMAT.md:

  file      : either raw "PAR\\0" data, or two concatenated zlib streams -
              a small wrapper header, then the actual PAR data
  header    : "PAR\\0" | u32 version | u32 listCount | u32 pad
  list      : u32 unk1 | u32 unk2 | u32 entryCount | entries[]
  entry     : dstring name | i8 unk | u16 fieldCount | u16 a | u16 b
              | u8[fieldCount] types | values[]
  types     : 0 i32, 1 f32, 2 u32, 3 dstring,
              4 i32[], 5 f32[], 6 u32[], 7 dstring[]
  array     : u64 lead | u32 count | values[]   - lead 0 means empty, and
              then the count is NOT there either

Field *names* are not stored; they come from the SDK sheets. The mapping is by
LIST, not by field count: every list in the .par is exactly one sheet (608 of
609 in TwoWorlds.par resolve, none mixed). Several sheets share a field count,
so counting fields picks the wrong sheet - see the Par editor's PAR_FORMAT.md.

Values are edited in place and re-serialized; everything the parser does not
understand is carried through byte-for-byte, so a round-trip is lossless.
"""

import struct
import zlib

MAGIC = b'PAR\x00'


def unwrap(blob):
    """Return (par_data, rewrap) for a .par file blob.

    `rewrap(new_par_data)` rebuilds the on-disk form (same stream layout).
    """
    if blob[:4] == MAGIC:
        return blob, (lambda data: data)
    if blob[:1] != b'\x78':
        raise ValueError('not a .par file')
    d1 = zlib.decompressobj()
    head = d1.decompress(blob)
    rest = d1.unused_data
    if not rest:                       # single stream
        return head, (lambda data: zlib.compress(data))
    d2 = zlib.decompressobj()
    par = d2.decompress(rest)
    if par[:4] != MAGIC:
        raise ValueError('second stream is not PAR data')
    return par, (lambda data: zlib.compress(head) + zlib.compress(data))


class Entry:
    __slots__ = ('name', 'unk', 'types', 'values', 'u16a', 'u16b')

    def __init__(self, name, unk, types, values, u16a, u16b):
        self.name = name
        self.unk = unk
        self.types = types
        self.values = values
        self.u16a = u16a
        self.u16b = u16b

    @property
    def field_count(self):
        return len(self.types)


class Par:
    def __init__(self, version, lists, pad=0, trailing=b''):
        self.version = version
        self.lists = lists            # [(unk1, unk2, [Entry])]
        self.pad = pad
        # Bytes behind the last list. TwoWorlds.par has 84 of them (they hold
        # a "--NULL--" record the list structure does not cover). Carried
        # through untouched so a round-trip stays byte-for-byte.
        self.trailing = trailing

    def entries(self):
        for unk1, unk2, ents in self.lists:
            for e in ents:
                yield e


def _rd_str(b, o):
    n = struct.unpack_from('<I', b, o)[0]
    o += 4
    return b[o:o + n].decode('latin-1'), o + n


def _wr_str(s):
    raw = s.encode('latin-1')
    return struct.pack('<I', len(raw)) + raw


def _rd_value(b, o, t):
    if t == 0:
        return struct.unpack_from('<i', b, o)[0], o + 4
    if t == 1:
        return struct.unpack_from('<f', b, o)[0], o + 4
    if t == 2:
        return struct.unpack_from('<I', b, o)[0], o + 4
    if t == 3:
        return _rd_str(b, o)
    if t in (4, 5, 6, 7):
        # Arrays carry a u64 ahead of the count. Zero means empty - and then
        # there is no count either. Reading the count straight away threw the
        # parser off the rails at the first array and it died mid-file.
        if struct.unpack_from('<Q', b, o)[0] == 0:
            return [], o + 8
        o += 8
        n = struct.unpack_from('<I', b, o)[0]
        o += 4
        if t == 7:
            out = []
            for _ in range(n):
                s, o = _rd_str(b, o)
                out.append(s)
            return out, o
        fmt = {4: 'i', 5: 'f', 6: 'I'}[t]
        vals = list(struct.unpack_from(f'<{n}{fmt}', b, o))
        return vals, o + 4 * n
    raise ValueError(f'unknown field type {t}')


def _wr_value(v, t):
    if t == 0:
        return struct.pack('<i', v)
    if t == 1:
        return struct.pack('<f', v)
    if t == 2:
        return struct.pack('<I', v)
    if t == 3:
        return _wr_str(v)
    if t in (4, 5, 6, 7):
        if not v:                       # empty: the lone u64, nothing after it
            return struct.pack('<Q', 0)
        head = struct.pack('<Q', 1) + struct.pack('<I', len(v))
        if t == 7:
            return head + b''.join(_wr_str(s) for s in v)
        fmt = {4: 'i', 5: 'f', 6: 'I'}[t]
        return head + struct.pack(f'<{len(v)}{fmt}', *v)
    raise ValueError(f'unknown field type {t}')


def parse(par_data):
    if par_data[:4] != MAGIC:
        raise ValueError('missing PAR magic')
    version, count, pad = struct.unpack_from('<III', par_data, 4)
    o = 16
    lists = []
    for _ in range(count):
        unk1, unk2, m = struct.unpack_from('<III', par_data, o)
        o += 12
        ents = []
        for _ in range(m):
            name, o = _rd_str(par_data, o)
            unk = par_data[o]; o += 1
            f, a, b = struct.unpack_from('<HHH', par_data, o)
            o += 6
            types = list(par_data[o:o + f]); o += f
            values = []
            for t in types:
                v, o = _rd_value(par_data, o, t)
                values.append(v)
            ents.append(Entry(name, unk, types, values, a, b))
        lists.append((unk1, unk2, ents))
    return Par(version, lists, pad, par_data[o:])


def build(par):
    out = bytearray(MAGIC)
    out += struct.pack('<III', par.version, len(par.lists), par.pad)
    for unk1, unk2, ents in par.lists:
        out += struct.pack('<III', unk1, unk2, len(ents))
        for e in ents:
            out += _wr_str(e.name)
            out += bytes([e.unk])
            out += struct.pack('<HHH', len(e.types), e.u16a, e.u16b)
            out += bytes(e.types)
            for v, t in zip(e.values, e.types):
                out += _wr_value(v, t)
    out += par.trailing
    return bytes(out)
