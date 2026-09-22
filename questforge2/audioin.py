"""Load a sound file of the user as a voice take (4.4.0, Marco 2026-09-22:
"eigene mp3 oder wave files rein machen, richtig konvertiert fuers game").

Everything Windows can play goes in: WAV of any kind (8/16/24/32 bit,
float, ADPCM), MP3, WMA, M4A/AAC, FLAC. Decoding and the conversion to the
format of the takes (16 bit PCM, mono, 44100 Hz, recorder.RATE) are done by
the Media Foundation of Windows through its Source Reader: asked for that
PCM type it puts the decoder and the audio resampler in by itself. No extra
library, nothing in the exe.

Without Media Foundation (Windows "N" editions without the media pack) a
plain PCM WAV still loads: read with the wave module, mixed to mono and
resampled here (linear, good enough for speech).

Then the level is brought to the one of the original recordings (the
voice pipeline of the campaign, build_soundbank.angleichen): RMS of the
speech 0.30 of full scale, above 0.70 a soft tanh knee instead of hard
clipping, peaks at most 0.985.
"""

import array
import ctypes
import math
import os
import wave
from ctypes import wintypes

from . import recorder

RATE = recorder.RATE
TARGET_RMS = 0.30          # the originals measure 0.33, a little headroom
KNEE = 0.70
CAP = 0.985


class AudioError(Exception):
    pass


# ---------------------------------------------------------------------------
# Media Foundation through ctypes (vtable calls, no comtypes)

class GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [('wFormatTag', wintypes.WORD), ('nChannels', wintypes.WORD),
                ('nSamplesPerSec', wintypes.DWORD),
                ('nAvgBytesPerSec', wintypes.DWORD),
                ('nBlockAlign', wintypes.WORD),
                ('wBitsPerSample', wintypes.WORD), ('cbSize', wintypes.WORD)]


MF_VERSION = 0x00020070
MFSTARTUP_FULL = 0
FIRST_AUDIO_STREAM = 0xFFFFFFFD
ALL_STREAMS = 0xFFFFFFFE
READERF_ENDOFSTREAM = 0x2
COINIT_MULTITHREADED = 0x0
RPC_E_CHANGED_MODE = -2147417850      # 0x80010106

# vtable slots (IUnknown 0-2)
_RELEASE = 2
_READER_SET_SELECTION = 4
_READER_SET_TYPE = 7
_READER_READ = 9
_SAMPLE_CONTIGUOUS = 41              # IMFAttributes 3-32, IMFSample 33-
_BUFFER_LOCK = 3
_BUFFER_UNLOCK = 4


def _method(obj, slot, *argtypes):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    fn = proto(vtbl[0][slot])
    return lambda *a: fn(obj, *a)


def _release(obj):
    if obj:
        _method(obj, _RELEASE)()


def _check(hr, what):
    if hr < 0:
        raise AudioError(f'{what}: 0x{hr & 0xFFFFFFFF:08X}')


def media_foundation_pcm(path):
    """(pcm bytes, 16 bit mono RATE) of any file Windows can decode, through
    the Source Reader. Raises AudioError when Media Foundation is missing or
    the file cannot be read."""
    try:
        mfplat = ctypes.WinDLL('mfplat')
        mfreadwrite = ctypes.WinDLL('mfreadwrite')
        ole32 = ctypes.WinDLL('ole32')
    except OSError as e:
        raise AudioError(f'Media Foundation: {e}')
    hr = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
    com_ok = hr >= 0            # S_OK / S_FALSE: ours to undo
    _check(mfplat.MFStartup(MF_VERSION, MFSTARTUP_FULL), 'MFStartup')
    reader = ctypes.c_void_p()
    mtype = ctypes.c_void_p()
    out = bytearray()
    try:
        mfreadwrite.MFCreateSourceReaderFromURL.argtypes = [
            wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        _check(mfreadwrite.MFCreateSourceReaderFromURL(
            os.path.abspath(path), None, ctypes.byref(reader)),
            'open file')
        sel = _method(reader, _READER_SET_SELECTION, wintypes.DWORD,
                      wintypes.BOOL)
        _check(sel(ALL_STREAMS, False), 'SetStreamSelection')
        _check(sel(FIRST_AUDIO_STREAM, True), 'no audio stream')
        # the wanted output: PCM 16 bit mono RATE; the reader adds the
        # decoder and the resampler
        _check(mfplat.MFCreateMediaType(ctypes.byref(mtype)),
               'MFCreateMediaType')
        wf = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)
        mfplat.MFInitMediaTypeFromWaveFormatEx.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(WAVEFORMATEX), wintypes.UINT]
        _check(mfplat.MFInitMediaTypeFromWaveFormatEx(
            mtype, ctypes.byref(wf), ctypes.sizeof(wf)), 'media type')
        settype = _method(reader, _READER_SET_TYPE, wintypes.DWORD,
                          ctypes.c_void_p, ctypes.c_void_p)
        _check(settype(FIRST_AUDIO_STREAM, None, mtype), 'convert to PCM')
        read = _method(reader, _READER_READ, wintypes.DWORD, wintypes.DWORD,
                       ctypes.POINTER(wintypes.DWORD),
                       ctypes.POINTER(wintypes.DWORD),
                       ctypes.POINTER(ctypes.c_longlong),
                       ctypes.POINTER(ctypes.c_void_p))
        while True:
            index, flags = wintypes.DWORD(), wintypes.DWORD()
            stamp = ctypes.c_longlong()
            sample = ctypes.c_void_p()
            _check(read(FIRST_AUDIO_STREAM, 0, ctypes.byref(index),
                        ctypes.byref(flags), ctypes.byref(stamp),
                        ctypes.byref(sample)), 'ReadSample')
            if sample:
                buf = ctypes.c_void_p()
                try:
                    _check(_method(sample, _SAMPLE_CONTIGUOUS,
                                   ctypes.POINTER(ctypes.c_void_p))(
                        ctypes.byref(buf)), 'buffer')
                    ptr = ctypes.POINTER(ctypes.c_ubyte)()
                    cur, mx = wintypes.DWORD(), wintypes.DWORD()
                    lock = _method(buf, _BUFFER_LOCK,
                                   ctypes.POINTER(ctypes.POINTER(
                                       ctypes.c_ubyte)),
                                   ctypes.POINTER(wintypes.DWORD),
                                   ctypes.POINTER(wintypes.DWORD))
                    _check(lock(ctypes.byref(ptr), ctypes.byref(mx),
                                ctypes.byref(cur)), 'lock')
                    out += ctypes.string_at(ptr, cur.value)
                    _method(buf, _BUFFER_UNLOCK)()
                finally:
                    _release(buf)
                    _release(sample)
            if flags.value & READERF_ENDOFSTREAM:
                break
            if len(out) > RATE * 2 * recorder.MAX_SECONDS * 2:
                raise AudioError('longer than 4 minutes')
    finally:
        _release(mtype)
        _release(reader)
        mfplat.MFShutdown()
        if com_ok:
            ole32.CoUninitialize()
    if len(out) % 2:
        out = out[:-1]
    return bytes(out)


# ---------------------------------------------------------------------------
# fallback: PCM WAV without Media Foundation

def wav_pcm(path):
    """(pcm 16 bit mono RATE) of a PCM WAV with the wave module."""
    try:
        with wave.open(path, 'rb') as w:
            ch, width, rate = w.getnchannels(), w.getsampwidth(), \
                w.getframerate()
            raw = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as e:
        raise AudioError(str(e))
    if width == 1:
        vals = [(b - 128) << 8 for b in raw]
    elif width == 2:
        vals = array.array('h', raw[:len(raw) // 2 * 2]).tolist()
    elif width == 3:
        vals = [int.from_bytes(raw[i:i + 3], 'little', signed=True) >> 8
                for i in range(0, len(raw) - 2, 3)]
    elif width == 4:
        vals = [v >> 16 for v in array.array('i', raw[:len(raw) // 4 * 4])]
    else:
        raise AudioError(f'{width * 8} bit')
    if ch > 1:
        vals = [sum(vals[i:i + ch]) // ch for i in range(0, len(vals), ch)]
    if rate != RATE:
        vals = resample(vals, rate, RATE)
    return array.array('h', vals).tobytes()


def resample(vals, src, dst):
    """Linear interpolation; the fallback only."""
    if not vals:
        return []
    n = int(len(vals) * dst / src)
    step = src / dst
    out = []
    last = len(vals) - 1
    for i in range(n):
        x = i * step
        j = int(x)
        f = x - j
        a = vals[j]
        b = vals[j + 1] if j < last else a
        out.append(int(a + (b - a) * f))
    return out


# ---------------------------------------------------------------------------
# level

def level(pcm):
    """(pcm, note) with the speech at the level of the originals."""
    s = array.array('h', pcm)
    if not s:
        return pcm, {'factor': 1.0, 'limited': 0.0, 'rms': 0.0}
    peak = max(abs(v) for v in s) / 32768.0
    if peak < 1e-4:
        return pcm, {'factor': 1.0, 'limited': 0.0, 'rms': 0.0}
    gate = peak * 0.05 * 32768.0
    loud = [v for v in s if abs(v) > gate]
    rms = math.sqrt(sum(v * v for v in loud) / len(loud)) / 32768.0 \
        if loud else 0.0
    if rms < 1e-4:
        return pcm, {'factor': 1.0, 'limited': 0.0, 'rms': rms}
    factor = TARGET_RMS / rms
    rest = CAP - KNEE
    out = array.array('h')
    over = 0
    for v in s:
        x = v / 32768.0 * factor
        a = abs(x)
        if a > KNEE:
            over += 1
            x = math.copysign(KNEE + rest * math.tanh((a - KNEE) / rest), x)
        x = max(-CAP, min(CAP, x))
        out.append(int(round(x * 32767)))
    return out.tobytes(), {'factor': factor, 'limited': over / len(s),
                           'rms': rms}


def load(path, normalize=True):
    """(pcm 16 bit mono RATE, note) of any sound file. note: 'via' (media
    foundation or wave), 'factor', 'limited' (share of samples above the
    knee)."""
    try:
        pcm = media_foundation_pcm(path)
        via = 'mf'
    except AudioError as e:
        if not path.lower().endswith('.wav'):
            raise
        pcm = wav_pcm(path)
        via = 'wave'
        _ = e
    if len(pcm) < RATE * 2 // 10:
        raise AudioError('shorter than 0.1 s')
    note = {'via': via, 'factor': 1.0, 'limited': 0.0}
    if normalize:
        pcm, lv = level(pcm)
        note.update(lv)
    return pcm, note
