"""Two Worlds 1 single-player savegame reader/writer.

Layout of a `NNNNNN.TwoWorldsSave` (decoded 2026-07, verified byte-exact):

    "RGMH"            magic
    u32  1            version
    u32  0x2028       payload-header offset (points at the u32 below)
    u32  4
    u32  0
    u32  pngLen       length of the embedded PNG thumbnail
    GUID (16 bytes)   + a fixed-size UTF-16 title field, up to 0x2028
  @0x2028:
    u32  pngLen       (again) + PNG bytes
    <preview>         ~91 bytes: an UNCOMPRESSED copy of the payload head
                      (SV header, save name, TwoWorlds.par GUID) so the game
                      can list the save without inflating 6 MB
    zlib stream       the real payload (level 6), to EOF

There is no length field or checksum anywhere in the header, so editing the
payload and re-deflating at level 6 reproduces a file the game accepts (the
uncompressed preview must be kept in sync, which `repack` does).

The payload itself begins:
    "SV\x01"  dstring version ("1.6")  UTF-16 save name
    GUID of the loaded TwoWorlds.par   (content fingerprint)
    sections … (per-tile level state, world objects, quest state)

`title` is the human-readable save label shown in the load list; it lives in
three places (the header field, the preview, and the payload) plus the
sibling `_files_.txt`, all updated by `write_title`.
"""

import os
import re
import struct
import zlib

MAGIC = b'RGMH'
PAYLOAD_OFFSET = 0x2028
_ZLIB_LEVEL = 6


class SaveError(Exception):
    pass


class Save:
    __slots__ = ('raw', 'png', 'preview', 'payload', 'zlib_off')

    def __init__(self, raw):
        if raw[:4] != MAGIC:
            raise SaveError('not a TwoWorldsSave (bad magic)')
        png_len = struct.unpack_from('<I', raw, PAYLOAD_OFFSET)[0]
        png_start = PAYLOAD_OFFSET + 4
        png_end = png_start + png_len
        z = raw.find(b'\x78\x9c', png_end)
        if z < 0:
            raise SaveError('no zlib stream found')
        d = zlib.decompressobj()
        payload = d.decompress(raw[z:])
        payload += d.flush()
        if d.unused_data:
            raise SaveError('trailing data after payload')
        self.raw = raw
        self.png = raw[png_start:png_end]
        self.preview = raw[png_end:z]      # uncompressed payload-head copy
        self.payload = payload
        self.zlib_off = z

    # -- titles ---------------------------------------------------------

    @property
    def header_label(self):
        """The generic label in the fixed header field (usually 'Two
        Worlds') - not the per-save name shown in the load list."""
        buf = self.raw[0x28:PAYLOAD_OFFSET]
        end = buf.find(b'\x00\x00\x00')
        if end % 2:
            end += 1
        return buf[:end].decode('utf-16-le', 'replace').rstrip('\x00')

    @property
    def title(self):
        """The per-save label ('Thalmont 7.53:38') stored in the payload as
        a dstring16 (u32 charCount + UTF-16), mirrored in the preview."""
        # It follows the "SV\x01" + version dstring; the name is the first
        # run of UTF-16 printable characters, prefixed by a u32 charCount.
        m = re.search(rb'([ -~]\x00){3,}', self.preview)
        if not m:
            return ''
        start = m.start()
        cnt = struct.unpack_from('<I', self.preview, start - 4)[0]
        return self.preview[start:start + cnt * 2].decode('utf-16-le',
                                                          'replace')

    def with_title(self, new_title):
        """Return raw bytes with the per-save label changed everywhere it
        occurs (preview + payload). The dstring16 length prefix is updated,
        so the new title may be any length."""
        old = self.title
        pat = struct.pack('<I', len(old)) + old.encode('utf-16-le')
        repl = struct.pack('<I', len(new_title)) + new_title.encode('utf-16-le')
        preview = bytes(self.preview).replace(pat, repl, 1)
        payload = self.payload.replace(pat, repl, 1)
        return self.repack(payload=payload, preview=preview)

    # -- (re)assembly ---------------------------------------------------

    def repack(self, payload=None, preview=None):
        payload = self.payload if payload is None else payload
        preview = self.preview if preview is None else preview
        out = bytearray(self.raw[:PAYLOAD_OFFSET + 4])
        out += self.png
        out += preview
        out += zlib.compress(payload, _ZLIB_LEVEL)
        return bytes(out)


def read(path):
    with open(path, 'rb') as f:
        return Save(f.read())


def find_save_dir():
    """The active single-player save folder.

    The game writes to `%USERPROFILE%\\Saved Games\\Two Worlds Saves\\`
    with the NNNNNN.TwoWorldsSave files sitting DIRECTLY in it (there is no
    _files_.txt there - the load-list label comes from inside each save).
    An old `Documents\\TwoWorlds files\\Players\\<name>\\Single\\` layout may
    also exist but is not what the retail game loads.
    """
    cand = os.path.join(os.path.expanduser('~'), 'Saved Games',
                        'Two Worlds Saves')
    return cand if os.path.isdir(cand) else None


def _files_path(save_path):
    return os.path.join(os.path.dirname(save_path), '_files_.txt')


def load_index(save_path):
    """Return {filename: label} from the sibling _files_.txt."""
    path = _files_path(save_path)
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding='latin-1'):
            m = re.match(r'(\S+)\s*->\s*(.*)', line.strip())
            if m:
                out[m.group(1)] = m.group(2)
    return out


def write_index(save_path, index):
    lines = [f'{k}\t->\t{v}' for k, v in index.items()]
    with open(_files_path(save_path), 'w', encoding='latin-1') as f:
        f.write('\n'.join(lines) + '\n')


def next_slot(folder):
    """Lowest unused NNNNNN.TwoWorldsSave number in a save folder."""
    used = set()
    for f in os.listdir(folder):
        m = re.fullmatch(r'(\d{6})\.TwoWorldsSave', f)
        if m:
            used.add(int(m.group(1)))
    n = 0
    while n in used:
        n += 1
    return f'{n:06d}.TwoWorldsSave'
