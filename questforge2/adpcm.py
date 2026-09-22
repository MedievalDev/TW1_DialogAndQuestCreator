"""MS-ADPCM for the game's voice bank, in plain Python (4.4.0).

The same encoder as the campaign's voice pipeline (QuestForge tw1_adpcm,
in the game since 08/2026), without numpy: UnitTalk.xwb keeps speech as
MS-ADPCM mono, 44100 Hz, blocks of 70 bytes = 128 samples (XACT alignment
field 48: nBlockAlign = (48 + 22) * channels).

Block header, 7 bytes: u8 predictor 0..6, i16 delta, i16 the SECOND sample
in time, i16 the FIRST; then 4 bit codes, high nibble first. The encoder
only picks which of the seven fixed coefficient pairs a block uses (the one
with the smallest prediction error) and the start delta (mean error / 2,
measured best on campaign lines).
"""

import array
import struct

COEF = [(256, 0), (512, -256), (0, 0), (192, 64),
        (240, 0), (460, -208), (392, -232)]
ADAPT = [230, 230, 230, 230, 307, 409, 512, 614,
         768, 614, 512, 409, 307, 230, 230, 230]
DELTA_MIN = 16
BLOCK = 70
SAMPLES = 128
ALIGN_FIELD = 48
BANK_RATE = 44100


def _predictor(x):
    if len(x) < 3:
        return 0
    best, best_err = 0, None
    for p, (c1, c2) in enumerate(COEF):
        err = 0
        for i in range(2, len(x)):
            d = x[i] - (c1 * x[i - 1] + c2 * x[i - 2]) // 256
            err += d * d
        if best_err is None or err < best_err:
            best, best_err = p, err
    return best


def _delta_start(x, p):
    if len(x) < 3:
        return DELTA_MIN
    c1, c2 = COEF[p]
    total = 0
    for i in range(2, len(x)):
        total += abs(x[i] - (c1 * x[i - 1] + c2 * x[i - 2]) // 256)
    return max(DELTA_MIN, int(total / (len(x) - 2) / 2) or DELTA_MIN)


def encode_block(x):
    """128 samples (ints) -> 70 bytes."""
    p = _predictor(x)
    c1, c2 = COEF[p]
    delta = _delta_start(x, p)
    s2, s1 = int(x[0]), int(x[1])          # s1 is the second one in time
    out = bytearray(struct.pack('<Bhhh', p, delta, s1, s2))
    nib = []
    for i in range(2, len(x)):
        pred = (s1 * c1 + s2 * c2) // 256
        n = int(round((x[i] - pred) / delta))
        n = 7 if n > 7 else (-8 if n < -8 else n)
        new = pred + n * delta
        new = 32767 if new > 32767 else (-32768 if new < -32768 else new)
        s2, s1 = s1, new
        delta = max(DELTA_MIN, (ADAPT[n & 0xF] * delta) // 256)
        nib.append(n & 0xF)
    for i in range(0, len(nib), 2):
        out.append((nib[i] << 4) | nib[i + 1])
    return bytes(out)


def decode_block(b):
    """70 bytes -> 128 samples, for the self check."""
    p, delta, s1, s2 = struct.unpack_from('<Bhhh', b, 0)
    c1, c2 = COEF[p]
    out = [s2, s1]
    for byte in b[7:]:
        for n in ((byte >> 4) & 0xF, byte & 0xF):
            v = n - 16 if n > 7 else n
            pred = (s1 * c1 + s2 * c2) // 256
            new = pred + v * delta
            new = 32767 if new > 32767 else (-32768 if new < -32768 else new)
            s2, s1 = s1, new
            delta = max(DELTA_MIN, (ADAPT[n] * delta) // 256)
            out.append(new)
    return out


def encode(pcm):
    """16 bit mono PCM bytes at BANK_RATE -> (raw ADPCM, block count). The
    last block is filled up with the last sample, like the originals."""
    x = array.array('h', pcm[:len(pcm) // 2 * 2]).tolist()
    rest = (-len(x)) % SAMPLES
    if rest:
        x += [x[-1] if x else 0] * rest
    raw = bytearray()
    for i in range(0, len(x), SAMPLES):
        raw += encode_block(x[i:i + SAMPLES])
    return bytes(raw), len(x) // SAMPLES


def decode(raw):
    out = []
    for i in range(0, len(raw) - BLOCK + 1, BLOCK):
        out += decode_block(raw[i:i + BLOCK])
    return array.array('h', out).tobytes()


def format_word(rate=BANK_RATE, channels=1, align=ALIGN_FIELD):
    """MINIWAVEFORMAT of the wave bank metadata (ADPCM = 2)."""
    return (2 | (channels & 0x7) << 2 | (rate & 0x3FFFF) << 5
            | (align & 0xFF) << 23)
