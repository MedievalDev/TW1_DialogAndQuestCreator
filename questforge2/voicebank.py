"""Original voice lines of the game: find similar lines and listen to them.

Search: a dialog line's ``cue`` names an XACT cue; putting an existing cue on
a new line makes the original actor speak it (the subtitle has to match the
recording). ``search`` ranks all voiced lines of the index (7764 cues,
hero = lector 1 with 1820 lines, measured 2026-09-17) by how close their text
is to what the user wants to say.

Listening: the cue is resolved in ``XACT\\win\\Sounds.xsb`` to a wave index of
``UnitTalk.xwb`` (MS-ADPCM mono, about 44.1 kHz). The raw entry is wrapped in
a RIFF header with the MS-ADPCM format block, which Windows plays without an
extra codec. Measured on the Epic Edition: sound bank 2 ms, wave bank header
3 ms, one line under 1 ms. The XACT parsing is taken over from
``QuestForge/tw1_xact.py`` (SoundBank, WaveBank, adpcm_wav).
"""

import difflib
import os
import re
import struct
import tempfile

HERO_LECTOR = 1
MIN_SCORE = 0.25

# -- search -------------------------------------------------------------------

_WORD = re.compile(r"\w+", re.UNICODE)       # "werd's" -> werd, s


def words(text):
    return [w.lower() for w in _WORD.findall(text or '')]


def norm(text):
    return ' '.join(words(text))


def score(query, text, qwords=None, qnorm=None):
    """0..1: how well ``text`` says what ``query`` wants to say.

    Share of the query words that appear in the line (prefix match, so
    "Belohnung" finds "Belohnungen"), mixed with the character similarity of
    the whole sentence; a line that contains the query as a phrase gets a
    bonus, an identical line scores 1."""
    qwords = qwords if qwords is not None else words(query)
    qnorm = qnorm if qnorm is not None else ' '.join(qwords)
    tnorm = norm(text)
    if not qwords or not tnorm:
        return 0.0
    if tnorm == qnorm:
        return 1.0
    twords = tnorm.split()
    hit = 0
    for w in qwords:
        if any(t == w or (len(w) >= 4 and (t.startswith(w) or w.startswith(t))
                          and min(len(t), len(w)) >= 4) for t in twords):
            hit += 1
    cover = hit / len(qwords)
    # extra words in the line count against it: the recording would say more
    extra = max(0, len(twords) - hit) / max(len(twords), 1)
    ratio = difflib.SequenceMatcher(None, qnorm, tnorm).ratio()
    s = 0.4 * cover + 0.35 * ratio + 0.25 * (1 - extra)
    if len(qnorm) >= 4 and qnorm in tnorm:
        s += 0.1 * len(qnorm) / len(tnorm)
    return round(min(s, 0.99), 3)


def search(cues, query, lector=HERO_LECTOR, limit=200):
    """[(score, cue, lector, text, tree)] best first. ``cues`` is the index
    dict cue -> [lector, text, tree]; ``lector`` None = every speaker. An
    empty query lists the speaker's lines in cue order."""
    pool = [(c, v[0], v[1], v[2] if len(v) > 2 else '')
            for c, v in cues.items()
            if lector is None or v[0] == lector]
    q = (query or '').strip()
    if not q:
        return [(0.0, c, lec, txt, tree) for c, lec, txt, tree in
                sorted(pool)][:limit]
    qwords = words(q)
    qnorm = ' '.join(qwords)
    # cheap word filter first, the character ratio only for the candidates
    cand = []
    for c, lec, txt, tree in pool:
        tn = norm(txt)
        if not tn:
            continue
        if any(w[:4] in tn for w in qwords) or difflib.SequenceMatcher(
                None, qnorm, tn).real_quick_ratio() > 0.6:
            cand.append((c, lec, txt, tree))
    out = []
    for c, lec, txt, tree in cand:
        s = score(q, txt, qwords, qnorm)
        if s >= MIN_SCORE:
            out.append((s, c, lec, txt, tree))
    out.sort(key=lambda r: (-r[0], len(r[3]), r[1]))
    return out[:limit]


def speakers(index):
    """[(lector, label, count)] of every voiced speaker, the hero first, then
    by number of lines. Names come from the NPC records of the quest file;
    lectors without an NPC show their number."""
    counts = {}
    for v in index.cues.values():
        counts[v[0]] = counts.get(v[0], 0) + 1
    out = []
    for lec, n in counts.items():
        names = []
        for nid in index.lectors.get(str(lec), []):
            npc = index.npcs.get(str(nid))
            if npc and npc['name'] not in names:
                names.append(npc['name'])
        out.append((lec, ', '.join(names[:2]), n))
    out.sort(key=lambda r: (r[0] != HERO_LECTOR, -r[2], r[0]))
    return out


def tree_quest(tree):
    """'translateDQ_15' -> 15 (None when the tree is not a quest dialog)."""
    m = re.match(r'translateDQ_(\d+)$', tree or '')
    return int(m.group(1)) if m else None


# -- listening ----------------------------------------------------------------

_REGIONS = ('BANKDATA', 'ENTRYMETADATA', 'SEEKTABLES', 'ENTRYNAMES',
            'ENTRYWAVEDATA')
_ADPCM_COEF = ((256, 0), (512, -256), (0, 0), (192, 64), (240, 0),
               (460, -208), (392, -232))


class VoiceError(Exception):
    pass


class _SoundBank:
    """Sounds.xsb: cue name -> (bank name, wave index) for simple cues."""

    def __init__(self, path):
        d = self.data = open(path, 'rb').read()
        if d[:4] != b'SDBK':
            raise VoiceError(f'not an XACT sound bank: {path}')
        self.n_simple = struct.unpack_from('<H', d, 19)[0]
        n_total = struct.unpack_from('<H', d, 25)[0]
        n_banks = d[27]
        self.simple_off, _complex, names_off = struct.unpack_from('<III', d,
                                                                  36)
        banks_off = struct.unpack_from('<I', d, 60)[0]
        self.banks = [d[banks_off + i * 64:banks_off + i * 64 + 64]
                      .split(b'\0')[0].decode('latin-1')
                      for i in range(n_banks)]
        self.index, o = {}, names_off
        for i in range(n_total):
            e = d.index(b'\0', o)
            self.index[d[o:e].decode('latin-1')] = i
            o = e + 1

    def wave(self, cue):
        i = self.index.get(cue)
        if i is None or i >= self.n_simple:
            return None
        o = struct.unpack_from('<I', self.data, self.simple_off + i * 5 + 1)[0]
        if self.data[o] & 1:                  # clips, not used for speech
            return None
        track, bank = struct.unpack_from('<HB', self.data, o + 9)
        return self.banks[bank], track


class _WaveBank:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            head = f.read(52)
            if head[:4] != b'WBND':
                raise VoiceError(f'not an XACT wave bank: {path}')
            reg = {n: struct.unpack_from('<II', head, 12 + i * 8)
                   for i, n in enumerate(_REGIONS)}
            f.seek(reg['BANKDATA'][0])
            bd = f.read(reg['BANKDATA'][1])
            self.count = struct.unpack_from('<I', bd, 4)[0]
            self.entry_size = struct.unpack_from('<I', bd, 72)[0]
            f.seek(reg['ENTRYMETADATA'][0])
            self.meta = f.read(reg['ENTRYMETADATA'][1])
            self.data_off = reg['ENTRYWAVEDATA'][0]

    def entry(self, i):
        o = i * self.entry_size
        _fd, fmt, po, pl = struct.unpack_from('<IIII', self.meta, o)
        return fmt, po, pl

    def wav(self, i):
        fmt, po, pl = self.entry(i)
        tag, channels = fmt & 0x3, (fmt >> 2) & 0x7
        rate, align = (fmt >> 5) & 0x3FFFF, (fmt >> 23) & 0xFF
        if tag != 2:
            raise VoiceError(f'wave {i}: format {tag} is not ADPCM')
        with open(self.path, 'rb') as f:
            f.seek(self.data_off + po)
            raw = f.read(pl)
        return adpcm_wav(raw, rate, align, channels)


def adpcm_wav(raw, rate, align_field, channels=1):
    """Raw XACT ADPCM -> playable .wav bytes. XACT stores the block size
    shortened: nBlockAlign = (field + 22) * channels (48 -> 70 bytes,
    128 samples per block)."""
    block = (align_field + 22) * channels
    spb = (block - 7 * channels) * 8 // (4 * channels) + 2
    fmt = struct.pack('<HHIIHH', 2, channels, rate, rate * block // spb,
                      block, 4)
    fmt += struct.pack('<HHH', 32, spb, len(_ADPCM_COEF))
    for a, b in _ADPCM_COEF:
        fmt += struct.pack('<hh', a, b)
    fact = struct.pack('<I', len(raw) // block * spb)
    data = raw[:len(raw) // block * block]
    return (b'RIFF' + struct.pack('<I', 4 + 8 + len(fmt) + 8 + len(fact)
                                  + 8 + len(data)) + b'WAVE'
            + b'fmt ' + struct.pack('<I', len(fmt)) + fmt
            + b'fact' + struct.pack('<I', len(fact)) + fact
            + b'data' + struct.pack('<I', len(data)) + data)


class OriginalVoices:
    """Lazy access to the game's speech bank."""

    def __init__(self, game_dir):
        self.game_dir = game_dir
        self._sb = None
        self._wb = None

    def available(self):
        d = os.path.join(self.game_dir or '', 'XACT', 'win')
        return (os.path.isfile(os.path.join(d, 'Sounds.xsb'))
                and os.path.isfile(os.path.join(d, 'UnitTalk.xwb')))

    def _open(self):
        if self._sb is None:
            if not self.available():
                raise VoiceError('XACT\\win\\Sounds.xsb / UnitTalk.xwb '
                                 'not found in the game folder')
            d = os.path.join(self.game_dir, 'XACT', 'win')
            self._sb = _SoundBank(os.path.join(d, 'Sounds.xsb'))
            self._wb = _WaveBank(os.path.join(d, 'UnitTalk.xwb'))

    def wav_bytes(self, cue):
        self._open()
        w = self._sb.wave(cue)
        if w is None or w[0] != 'UnitTalk':
            raise VoiceError(f'{cue}: no speech recording in UnitTalk.xwb')
        if not 0 <= w[1] < self._wb.count:
            raise VoiceError(f'{cue}: wave {w[1]} outside the bank')
        return self._wb.wav(w[1])

    def play(self, cue):
        """Play asynchronously; returns the temporary file."""
        path = os.path.join(tempfile.gettempdir(), 'qf2_cue_preview.wav')
        data = self.wav_bytes(cue)
        from . import recorder
        recorder.stop_playing()
        with open(path, 'wb') as f:
            f.write(data)
        recorder.play(path)
        return path
