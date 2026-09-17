"""Record a voice line straight from the microphone (Windows winmm, no extra
library) and play it back.

Format: PCM 16 bit, mono, 44100 Hz. 44100 Hz is the rate of the game's voice
bank (``tw1_adpcm.BANK_RATE`` of the voice pipeline); the pipeline encodes
to MS-ADPCM when it builds the bank. The recording is stored next to the
project in ``<project>_voice/Q<id>_<node>_<line>.wav`` and referenced from
the dialog line as ``line['voice']`` (file name only).

Getting a recording into the game needs the sound bank build (new cue in
Sounds.xsb, wave in UnitTalk.xwb), which the Quest Creator does not do.

winmm is used without callback: a set of buffers is queued, a thread polls
their ``WHDR_DONE`` flag in queue order and requeues them.
"""

import array
import collections
import ctypes
import os
import re
import threading
import time
import wave
from ctypes import wintypes

RATE = 44100
CHANNELS = 1
BITS = 16
BUFFER_SEC = 0.1
BUFFERS = 8
MAX_SECONDS = 120
WAVE_MAPPER = 0xFFFFFFFF
WAVE_FORMAT_PCM = 1
CALLBACK_NULL = 0
WHDR_DONE = 0x00000001


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [('wFormatTag', wintypes.WORD), ('nChannels', wintypes.WORD),
                ('nSamplesPerSec', wintypes.DWORD),
                ('nAvgBytesPerSec', wintypes.DWORD),
                ('nBlockAlign', wintypes.WORD),
                ('wBitsPerSample', wintypes.WORD), ('cbSize', wintypes.WORD)]


class WAVEHDR(ctypes.Structure):
    _fields_ = [('lpData', ctypes.c_void_p),
                ('dwBufferLength', wintypes.DWORD),
                ('dwBytesRecorded', wintypes.DWORD),
                ('dwUser', ctypes.c_size_t), ('dwFlags', wintypes.DWORD),
                ('dwLoops', wintypes.DWORD), ('lpNext', ctypes.c_void_p),
                ('reserved', ctypes.c_size_t)]


class RecorderError(Exception):
    pass


def _winmm():
    try:
        mm = ctypes.WinDLL('winmm')
    except (OSError, AttributeError):
        raise RecorderError('winmm not available')
    h = ctypes.c_void_p
    mm.waveInGetNumDevs.restype = wintypes.UINT
    mm.waveInOpen.argtypes = [ctypes.POINTER(h), wintypes.UINT,
                              ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t,
                              ctypes.c_size_t, wintypes.DWORD]
    for name in ('waveInPrepareHeader', 'waveInUnprepareHeader',
                 'waveInAddBuffer'):
        fn = getattr(mm, name)
        fn.argtypes = [h, ctypes.POINTER(WAVEHDR), wintypes.UINT]
        fn.restype = wintypes.UINT
    for name in ('waveInStart', 'waveInStop', 'waveInReset', 'waveInClose'):
        fn = getattr(mm, name)
        fn.argtypes = [h]
        fn.restype = wintypes.UINT
    mm.waveInOpen.restype = wintypes.UINT
    return mm


def input_devices():
    """Number of recording devices (0 = no microphone)."""
    try:
        return int(_winmm().waveInGetNumDevs())
    except RecorderError:
        return 0


class WAVEINCAPSW(ctypes.Structure):
    _fields_ = [('wMid', wintypes.WORD), ('wPid', wintypes.WORD),
                ('vDriverVersion', wintypes.UINT),
                ('szPname', ctypes.c_wchar * 32), ('dwFormats', wintypes.DWORD),
                ('wChannels', wintypes.WORD), ('wReserved1', wintypes.WORD)]


def device_names():
    """Names of the recording devices in device id order (Windows cuts
    them at 31 characters)."""
    try:
        mm = _winmm()
    except RecorderError:
        return []
    out = []
    for i in range(mm.waveInGetNumDevs()):
        caps = WAVEINCAPSW()
        if mm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)):
            out.append(f'#{i}')
        else:
            out.append(caps.szPname)
    return out


def peak(pcm):
    """Loudest sample of 16-bit little-endian PCM as 0..1."""
    if len(pcm) < 2:
        return 0.0
    a = array.array('h')
    a.frombytes(pcm[:len(pcm) - len(pcm) % 2])
    return max(abs(min(a)), abs(max(a))) / 32768.0


class Recorder:
    """start() -> (while recording: seconds, level) -> stop() -> pcm."""

    def __init__(self, rate=RATE, device=None):
        self.rate = rate
        self.device = device             # None = Windows default device
        self.chunks = []
        self.level = 0.0
        self.error = None
        self._stop = threading.Event()
        self._thread = None

    @property
    def seconds(self):
        return sum(len(c) for c in self.chunks) / (self.rate * 2)

    def start(self):
        mm = _winmm()
        if not mm.waveInGetNumDevs():
            raise RecorderError('no recording device')
        fmt = WAVEFORMATEX(WAVE_FORMAT_PCM, CHANNELS, self.rate,
                           self.rate * CHANNELS * BITS // 8,
                           CHANNELS * BITS // 8, BITS, 0)
        handle = ctypes.c_void_p()
        dev = WAVE_MAPPER if self.device is None else int(self.device)
        res = mm.waveInOpen(ctypes.byref(handle), dev,
                            ctypes.byref(fmt), 0, 0, CALLBACK_NULL)
        if res:
            raise RecorderError(f'waveInOpen failed ({res}); microphone '
                                f'blocked in the Windows privacy settings?')
        size = int(self.rate * BUFFER_SEC) * 2
        bufs, hdrs = [], []
        for _ in range(BUFFERS):
            buf = ctypes.create_string_buffer(size)
            hdr = WAVEHDR(ctypes.cast(buf, ctypes.c_void_p), size, 0, 0, 0,
                          0, None, 0)
            bufs.append(buf)
            hdrs.append(hdr)
            mm.waveInPrepareHeader(handle, ctypes.byref(hdr),
                                   ctypes.sizeof(WAVEHDR))
            mm.waveInAddBuffer(handle, ctypes.byref(hdr),
                               ctypes.sizeof(WAVEHDR))
        self._mm, self._h, self._bufs, self._hdrs = mm, handle, bufs, hdrs
        self.chunks = []
        self._stop.clear()
        if mm.waveInStart(handle):
            self._close()
            raise RecorderError('waveInStart failed')
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _take(self, i):
        hdr, buf = self._hdrs[i], self._bufs[i]
        data = ctypes.string_at(buf, hdr.dwBytesRecorded)
        self.chunks.append(data)
        self.level = peak(data)
        return data

    def _run(self):
        mm, h = self._mm, self._h
        order = collections.deque(range(len(self._hdrs)))
        size = ctypes.sizeof(WAVEHDR)
        try:
            while not self._stop.is_set():
                if self.seconds >= MAX_SECONDS:
                    break
                progressed = False
                while order and self._hdrs[order[0]].dwFlags & WHDR_DONE:
                    i = order.popleft()
                    self._take(i)
                    hdr = self._hdrs[i]
                    mm.waveInUnprepareHeader(h, ctypes.byref(hdr), size)
                    hdr.dwFlags = 0
                    hdr.dwBytesRecorded = 0
                    mm.waveInPrepareHeader(h, ctypes.byref(hdr), size)
                    mm.waveInAddBuffer(h, ctypes.byref(hdr), size)
                    order.append(i)
                    progressed = True
                if not progressed:
                    time.sleep(0.02)
            mm.waveInStop(h)
            mm.waveInReset(h)          # returns the partly filled buffers
            deadline = time.time() + 1
            while order and time.time() < deadline:
                if self._hdrs[order[0]].dwFlags & WHDR_DONE:
                    self._take(order.popleft())
                else:
                    time.sleep(0.01)
        except Exception as e:         # reported by stop()
            self.error = e
        finally:
            self._close()

    def _close(self):
        size = ctypes.sizeof(WAVEHDR)
        for hdr in self._hdrs:
            self._mm.waveInUnprepareHeader(self._h, ctypes.byref(hdr), size)
        self._mm.waveInClose(self._h)

    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def stop(self):
        """Stop and return the recorded PCM bytes."""
        self._stop.set()
        if self._thread:
            self._thread.join(3)
        if self.error:
            raise RecorderError(str(self.error))
        return b''.join(self.chunks)


def write_wav(path, pcm, rate=RATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with wave.open(tmp, 'wb') as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(BITS // 8)
        w.setframerate(rate)
        w.writeframes(pcm)
    os.replace(tmp, path)
    return path


def duration(path):
    try:
        with wave.open(path, 'rb') as w:
            return w.getnframes() / float(w.getframerate())
    except (OSError, wave.Error, EOFError):
        return None


def play(path):
    import winsound
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)


def stop_playing():
    try:
        import winsound
        winsound.PlaySound(None, 0)
    except (ImportError, RuntimeError):
        pass


def voice_dir(project):
    """``<project>_voice`` next to the project file (None when unsaved)."""
    if project is None or not project.path:
        return None
    return os.path.splitext(project.path)[0] + '_voice'


def voice_name(quest, nid, index):
    safe = re.sub(r'[^A-Za-z0-9_-]+', '', str(nid))
    return f'Q{quest.id}_{safe}_{index}.wav'


def voice_refs(quests, skip=None):
    """File names referenced by dialog lines (``skip``: one line object
    left out)."""
    out = set()
    for q in quests:
        for node in q.graph.get('nodes', {}).values():
            for ln in node.get('lines') or []:
                if ln is not skip and ln.get('voice'):
                    out.add(ln['voice'])
    return out


def take_name(project, quests, quest, nid, index, line):
    """File name for a new take of ``line``: its own file again when no
    other line uses it, else ``Q<id>_<node>_<line>.wav`` or, when that one
    is taken (lines moved, node copied) or already on disk, with ``_2``,
    ``_3`` ... so no other take gets overwritten."""
    others = voice_refs(quests, skip=line)
    own = line.get('voice')
    if own and own not in others:
        return own
    d = voice_dir(project)
    base = voice_name(quest, nid, index)[:-4]
    name, n = base + '.wav', 1
    while name in others or (d and os.path.exists(os.path.join(d, name))):
        n += 1
        name = f'{base}_{n}.wav'
    return name


def copy_takes(old_dir, new_dir, names):
    """Save as: bring the referenced takes along. Returns the count."""
    import shutil
    if not old_dir or not new_dir or os.path.normcase(
            os.path.abspath(old_dir)) == os.path.normcase(
            os.path.abspath(new_dir)):
        return 0
    n = 0
    for name in sorted(names):
        src = os.path.join(old_dir, name)
        dst = os.path.join(new_dir, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            os.makedirs(new_dir, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
            orig = original_path(src)
            if os.path.isfile(orig):
                os.makedirs(os.path.dirname(original_path(dst)),
                            exist_ok=True)
                shutil.copy2(orig, original_path(dst))
    return n


def voice_path(project, line):
    d = voice_dir(project)
    if not d or not line.get('voice'):
        return None
    return os.path.join(d, line['voice'])


# -- editing and the library (3.6.0) ------------------------------------------

ORIG_DIR = '_original'           # untrimmed takes, inside <project>_voice
SILENCE = 0.04                   # share of the loudest window counted as speech
PAD = 0.08                       # seconds kept before and after the speech


def read_wav(path):
    """(pcm bytes 16-bit mono, rate). Other formats raise ValueError."""
    with wave.open(path, 'rb') as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f'{os.path.basename(path)}: not 16-bit mono')
        return w.readframes(w.getnframes()), w.getframerate()


def samples(pcm):
    a = array.array('h')
    a.frombytes(pcm[:len(pcm) - len(pcm) % 2])
    return a


def peaks(pcm, n):
    """``n`` values 0..1, the loudest sample of each slice (waveform)."""
    a = samples(pcm)
    if not a or n <= 0:
        return [0.0] * max(n, 0)
    step = len(a) / n
    out = []
    for i in range(n):
        s = a[int(i * step):max(int((i + 1) * step), int(i * step) + 1)]
        out.append(max(abs(min(s)), abs(max(s))) / 32768.0 if s else 0.0)
    return out


def detect_trim(pcm, rate, silence=SILENCE, pad=PAD):
    """(start, end) in seconds around the speech: 10 ms windows, a window
    counts as speech above ``silence`` times the loudest window; ``pad``
    seconds stay on both sides. The whole take when nothing is found."""
    a = samples(pcm)
    total = len(a) / float(rate) if rate else 0.0
    win = max(1, rate // 100)
    levels = []
    for i in range(0, len(a), win):
        s = a[i:i + win]
        levels.append(max(abs(min(s)), abs(max(s))) if s else 0)
    top = max(levels) if levels else 0
    if top == 0:
        return 0.0, total
    loud = [i for i, v in enumerate(levels) if v >= top * silence]
    start = max(0.0, loud[0] * win / rate - pad)
    end = min(total, (loud[-1] + 1) * win / rate + pad)
    return round(start, 3), round(end, 3)


def cut(pcm, rate, start, end):
    """The part between ``start`` and ``end`` seconds."""
    i = max(0, int(start * rate)) * 2
    j = min(len(pcm), int(end * rate) * 2)
    return pcm[i:max(i, j)]


def original_path(path):
    d, name = os.path.split(path)
    return os.path.join(d, ORIG_DIR, name)


def trim_file(path, start, end):
    """Cut the take in place. The first cut keeps the untrimmed take in
    ``_original`` so it can be restored. Returns the new length."""
    pcm, rate = read_wav(path)
    part = cut(pcm, rate, start, end)
    if len(part) < rate // 10 * 2:
        raise ValueError('less than 0.1 s left')
    backup = original_path(path)
    if not os.path.exists(backup):
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        with open(path, 'rb') as src, open(backup, 'wb') as dst:
            dst.write(src.read())
    write_wav(path, part, rate)
    return len(part) / (2.0 * rate)


def drop_original(path):
    try:
        os.remove(original_path(path))
    except OSError:
        pass


def restore_original(path):
    backup = original_path(path)
    if not os.path.isfile(backup):
        return False
    os.replace(backup, path)
    return True


def library(project, quests):
    """Every take of the project: [{'name', 'path', 'exists', 'seconds',
    'mtime', 'trimmed', 'uses': [(quest, nid, index, text)]}], files on disk
    and names referenced by lines (missing files included), sorted by name."""
    d = voice_dir(project)
    items = {}
    if d and os.path.isdir(d):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if name.lower().endswith('.wav') and os.path.isfile(p):
                items[name] = {'name': name, 'path': p, 'exists': True,
                               'uses': []}
    for q in quests:
        for nid, node in q.graph.get('nodes', {}).items():
            for i, ln in enumerate(node.get('lines') or []):
                name = ln.get('voice')
                if not name:
                    continue
                it = items.setdefault(name, {
                    'name': name, 'path': os.path.join(d, name) if d else None,
                    'exists': False, 'uses': []})
                it['uses'].append((q, nid, i, ln.get('text', '')))
    for it in items.values():
        if it['exists']:
            it['seconds'] = duration(it['path'])
            it['mtime'] = os.path.getmtime(it['path'])
            it['trimmed'] = os.path.isfile(original_path(it['path']))
        else:
            it['seconds'] = it['mtime'] = None
            it['trimmed'] = False
    return [items[k] for k in sorted(items, key=str.lower)]
