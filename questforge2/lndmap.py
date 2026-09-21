"""Read terrain height and passability from a .lnd map, write markers into
the map body (3.9.0: markers placed on the map in the tool).

Section walk after the marker block, taken over from the LND viewer
(``LNDTool/Lnd Viewer/tw1_lnd_tool.py`` parse_lnd, read only): skybox
textures, sky states (168 bytes), day/sunrise/sunset, heightmap, edges,
water far LOD, water pools, colour base, textures, one byte, texture
reference and alpha maps, objects, fog reference map, fog descriptions,
flower, stamp and EAX maps, then the passable bit field.

Measured 2026-09-19 on the 108 surface tiles of the game (Levels.wd):
- heightmap 512 x 512 uint16, 64 world units per pixel, row = y / 64
  (not flipped). A marker's z is that value: 97.4 % of 8895 retail markers
  within 16 units when interpolated, 0.8 % stand higher (bridges,
  building floors).
- passable field 1024 rows x 32 uint32 = 1024 x 1024 bits, 32 units per
  bit, row = y / 32, bit = (x / 32) % 32 counted from the lowest bit;
  99.6 % of the retail markers stand on a set bit.

The body is the UNCOMPRESSED map as ``tw1_wd.Entry.data`` holds it.
``tw1_lnd.add_marker`` returns compressed bytes, which must not end up in
an Entry (the packer would compress again; the two stream form is the
trap that once made wdio loop forever).
"""

import struct

import tw1_lnd

TILE_UNITS = 32768


def _u32(d, pos):
    return struct.unpack_from('<I', d, pos)[0]


def _skip_ascii(d, pos, n):
    for _ in range(n):
        pos += 4 + _u32(d, pos)
    return pos


class Terrain:
    """Heightmap and passable field of one map body."""

    def __init__(self, body):
        d = body
        _start, pos = tw1_lnd._marker_section(d)
        n = _u32(d, pos)
        pos = _skip_ascii(d, pos + 8, n)                 # skybox textures
        n = _u32(d, pos)
        pos += 8 + n * 168                              # sky states
        pos += 12                                       # day, sunrise, sunset
        self.hw, self.hh = struct.unpack_from('<II', d, pos)
        pos += 8
        # a view on bytes instead of a tuple of Python ints (8 MB a tile)
        self.heights = memoryview(bytes(
            d[pos:pos + self.hw * self.hh * 2])).cast('H')
        pos += self.hw * self.hh * 2
        for _ in range(2):                              # vertical/horiz. edges
            pos += 4 + _u32(d, pos) * 2
        w, h = struct.unpack_from('<II', d, pos)        # water far LOD
        pos += 8 + w * h * 2
        n = _u32(d, pos)                                # water pools
        pos += 8
        for _ in range(n):
            pos += 4 + 4 + 4 + 2 + 4 + 4 + 88 + 4 + 4 + 8 + 4 + 4 + 16 + 4
            pos = _skip_ascii(d, pos, 2)
            pos += 8
        w, h = struct.unpack_from('<II', d, pos)        # colour base
        pos += 8 + w * h * 4
        n = _u32(d, pos)                                # textures and stamps
        pos = _skip_ascii(d, pos + 8, n)
        pos += 1
        for _ in range(2):                              # tex ref, tex alpha
            w, h = struct.unpack_from('<II', d, pos)
            pos += 8 + w * h * 4
        n = _u32(d, pos)                                # objects
        pos += 8
        for _ in range(n):
            pos += 4 + _u32(d, pos) + 8 + 12 + 3
        w, h = struct.unpack_from('<II', d, pos)        # fog reference map
        pos += 8 + w * h * 2
        n = _u32(d, pos)                                # fog descriptions
        pos += 8 + n * 12
        for size in (21, 16, 1):                        # flower, stamp, EAX
            w, h = struct.unpack_from('<II', d, pos)
            pos += 8 + w * h * size
        pw, ph, _w2 = struct.unpack_from('<III', d, pos)
        pos += 12
        # the same field as bytes: bit x of row y is bit (x % 8) of byte
        # y * 128 + x // 8, lowest bit first - a 1 bit image for drawing
        self.pass_raw = bytes(d[pos:pos + pw * ph * 4])
        self.pass_words = memoryview(self.pass_raw).cast('I')
        self.pass_per_row = (pw * ph) // 1024 if pw * ph else 0

    def height(self, x, y):
        """Terrain height at world x/y inside the tile, interpolated."""
        w, h = self.hw, self.hh
        fx = min(max(x / 64.0, 0.0), w - 1.001)
        fy = min(max(y / 64.0, 0.0), h - 1.001)
        x0, y0 = int(fx), int(fy)
        ax, ay = fx - x0, fy - y0
        v = self.heights
        return int(round(v[y0 * w + x0] * (1 - ax) * (1 - ay)
                         + v[y0 * w + x0 + 1] * ax * (1 - ay)
                         + v[(y0 + 1) * w + x0] * (1 - ax) * ay
                         + v[(y0 + 1) * w + x0 + 1] * ax * ay))

    def passable(self, x, y):
        """True when the ground at world x/y is walkable (no tree, rock,
        wall); None when the map has no field."""
        if not self.pass_per_row:
            return None
        bx = min(max(int(x) * 1024 // TILE_UNITS, 0), 1023)
        by = min(max(int(y) * 1024 // TILE_UNITS, 0), 1023)
        word = self.pass_words[by * self.pass_per_row + bx // 32]
        return bool((word >> (bx % 32)) & 1)

    def blocked_mask(self, size):
        """size x size bytes, 1 where the ground is blocked (for drawing).
        Row 0 is y = 0 of the tile."""
        out = bytearray(size * size)
        if not self.pass_per_row:
            return out
        for r in range(size):
            by = r * 1024 // size
            base = by * self.pass_per_row
            for c in range(size):
                bx = c * 1024 // size
                if not (self.pass_words[base + bx // 32] >> (bx % 32)) & 1:
                    out[r * size + c] = 1
        return out


def _marker_entries(body):
    """(start, end, [(name, id, raw bytes)]) of the marker block."""
    start, end = tw1_lnd._marker_section(body)
    pos, out = start + 8, []
    for _ in range(_u32(body, start)):
        name, p2 = tw1_lnd._ascii(body, pos)
        stop = tw1_lnd._entry_end(body, p2)
        out.append((name, _u32(body, p2), body[pos:stop]))
        pos = stop
    return start, end, out


def _game_order(entries):
    """The order the game's maps have, measured 2026-09-21 on all 160 maps
    of Levels.wd without an exception: one block per marker type, the types
    sorted without case, the numbers ascending inside a block (every
    editor map as well). Up to 4.2.0 placed markers were appended at the
    end, a second block of their type. That this alone breaks a marker in
    the game is NOT measured - Kunibert's missing giver had another cause
    (export.insert_npc) - the order is kept like the game's as a
    precaution (4.2.1)."""
    return sorted(entries, key=lambda e: (e[0].lower(), e[1]))


def sort_markers(body):
    """``body`` with its marker block in the game's order (the same bytes
    when it already is, as every map of the game and the editor)."""
    start, end, ents = _marker_entries(body)
    ordered = _game_order(ents)
    if ordered == ents:
        return body
    return body[:start + 8] + b''.join(e[2] for e in ordered) + body[end:]


def add_markers(body, markers):
    """The uncompressed map body with ``markers`` added:
    [(name, ident, x, y, z, angle)], each in the block of its type (see
    _game_order). Everything outside the marker block stays byte for
    byte."""
    if not markers:
        return body
    start, end, ents = _marker_entries(body)
    for name, ident, x, y, z, angle in markers:
        raw = name.encode('latin-1')
        ents.append((name, int(ident), struct.pack('<I', len(raw)) + raw
                     + struct.pack('<Iiii', int(ident), int(x), int(y), int(z))
                     + bytes([int(angle) & 0xFF]) + b'\x00' * 8))
    return (body[:start] + struct.pack('<I', len(ents))
            + body[start + 4:start + 8]
            + b''.join(e[2] for e in _game_order(ents)) + body[end:])
