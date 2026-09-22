"""Mouth movement for own voice lines (4.5.0, Marco 2026-09-22: "Lippenbewegung").

``XACT\\win\\LipSync\\data.lipsync`` (measured 2026-09-22, Epic Edition,
7578 entries, 3180091 bytes):

    u32 count
    count x (char[16] cue name, u32 offset, u16 length)    sorted by name
    per cue ``length / 9`` records: u32 start ms, u32 end ms, u8 mouth id

Every entry starts at 0 ms, the last record ends at about 96 % of the cue's
length (median), records last 81 ms in the median, gaps between them are
silence. The 37 ids (0..36) are the phonemes of the tool that made the
file - not documented. Measured over 250 retail lines, the loudest
segments carry 18, 22, 21, 23, 17, 2 (vowels, the mouth open), the
quietest 14, 28, 20, 15, 7 and 0 (0 also the pauses).

An own take has no phoneme alignment. The mouth follows its loudness in
STEP_MS steps: quiet parts get the closed ids, loud parts the open ones,
turn by turn so the mouth does not freeze on one shape, pauses 0.
"""

import array
import math
import struct

NAME_LEN = 16
DIR_ENTRY = NAME_LEN + 6
RECORD = 9
STEP_MS = 80
SILENCE = 0.06                  # share of the loudest step counted as pause
OPEN = (23, 2, 21, 18, 17, 22)  # loud: vowels
MID = (10, 32, 26, 25, 13, 5)
CLOSED = (28, 7, 14, 20, 15)
PAUSE = 0


class LipSyncError(Exception):
    pass


def parse(blob):
    """{cue name: record bytes}, in the order of the file."""
    if len(blob) < 4:
        raise LipSyncError('lipsync file too short')
    n = struct.unpack_from('<I', blob, 0)[0]
    if 4 + n * DIR_ENTRY > len(blob):
        raise LipSyncError('lipsync directory beyond the end')
    out = {}
    for i in range(n):
        o = 4 + i * DIR_ENTRY
        name = blob[o:o + NAME_LEN].split(b'\0')[0].decode('latin-1')
        off, ln = struct.unpack_from('<IH', blob, o + NAME_LEN)
        if off + ln > len(blob):
            raise LipSyncError(f'{name}: data beyond the end')
        out[name] = bytes(blob[off:off + ln])
    return out


def build(entries):
    """The file for {cue name: record bytes}, the names sorted like the
    game's file (a sorted directory may be searched binary)."""
    names = sorted(entries)
    head = struct.pack('<I', len(names))
    off = 4 + len(names) * DIR_ENTRY
    dirs, body = [], []
    for name in names:
        rec = entries[name]
        raw = name.encode('latin-1')
        if len(raw) >= NAME_LEN:
            raise LipSyncError(f'cue name too long: {name}')
        if len(rec) % RECORD or len(rec) > 0xFFFF:
            raise LipSyncError(f'{name}: bad record length {len(rec)}')
        dirs.append(raw.ljust(NAME_LEN, b'\0') + struct.pack('<IH', off,
                                                             len(rec)))
        body.append(rec)
        off += len(rec)
    return head + b''.join(dirs) + b''.join(body)


def records(rec):
    """[(start ms, end ms, id)] of one entry."""
    return [struct.unpack_from('<IIB', rec, k * RECORD)
            for k in range(len(rec) // RECORD)]


def generate(pcm, rate=44100):
    """Record bytes for a take (16 bit mono): one record per STEP_MS of
    speech, merged while the id stays, pauses as id 0."""
    s = array.array('h')
    s.frombytes(pcm[:len(pcm) - len(pcm) % 2])
    step = max(1, rate * STEP_MS // 1000)
    levels = []
    for i in range(0, len(s), step):
        seg = s[i:i + step:2]
        levels.append(math.sqrt(sum(v * v for v in seg) / len(seg))
                      if seg else 0.0)
    top = max(levels) if levels else 0.0
    if top <= 0:
        return b''
    out = []
    turn = 0
    for k, lv in enumerate(levels):
        x = lv / top
        if x < SILENCE:
            mid = PAUSE
        else:
            band = CLOSED if x < 0.3 else (MID if x < 0.6 else OPEN)
            mid = band[turn % len(band)]
            turn += 1
        a = k * STEP_MS
        b = min((k + 1) * STEP_MS, len(s) * 1000 // rate)
        if b <= a:
            break
        if out and out[-1][2] == mid:
            out[-1][1] = b
        else:
            out.append([a, b, mid])
    # the game's entries start at 0 and leave the pauses out after that
    body = [r for i, r in enumerate(out) if i == 0 or r[2] != PAUSE]
    return b''.join(struct.pack('<IIB', a, b, i) for a, b, i in body)
