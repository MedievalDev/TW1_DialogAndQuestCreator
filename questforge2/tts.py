"""Placeholder voices from the speech synthesis of Windows (4.5.0, Marco
2026-09-22: "mach alle 5, markiere die stimmen als dummy platzhalter").

Two engines, both reached through one PowerShell run per batch, so nothing
goes into the exe:

- OneCore (WinRT ``Windows.Media.SpeechSynthesis``): the voices of the
  Windows settings. A plain German Windows 11 has Microsoft Stefan (male),
  Katja and Hedda (measured 2026-09-22); output 16 kHz mono.
- SAPI 5 (``System.Speech``): the "Desktop" voices (Hedda, Zira) and voices
  of other vendors that register for SAPI; output asked for as 44.1 kHz.

Pitch and speed go through SSML ``<prosody>``; measured with the median
fundamental: Stefan -20 % / 0 / +20 % -> 112 / 126 / 142 Hz, Hedda Desktop
178 / 200 / 222 Hz. So a few voices still give every speaker its own sound.

The result goes through audioin (Media Foundation resamples to 44.1 kHz,
level of the original voices) and is trimmed like a recording. Then it is a
take like any other - but the line carries ``voice_tts``
({'voice', 'text', 'pitch', 'rate'}): it is a PLACEHOLDER, shown as one in
the inspector, the library, the check before the export and the voice
pack. A recording or a loaded file drops the mark; a changed line text
makes the placeholder outdated.
"""

import json
import os
import subprocess
import tempfile
import threading
import time
from xml.sax.saxutils import escape

from . import audioin, recorder

MARK = 'voice_tts'
HERO = 'hero'
PITCHES = (-10, 10, -20, 20, -5, 5, -15, 15)   # NPC speakers step through
LIMIT = 40                                     # +-percent for pitch and rate
TIMEOUT = 45                                   # seconds without an answer
CREATE_NO_WINDOW = 0x08000000

_PS = r'''param([string]$Mode, [string]$Job)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Say($o) {
  [Console]::Out.WriteLine((ConvertTo-Json $o -Compress))
  [Console]::Out.Flush()
}
$onecore = $null; $onecoreErr = ''
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
  $null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
  $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  $onecore = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
} catch { $onecoreErr = $_.Exception.Message }
$sapi = $null; $sapiErr = ''
try {
  Add-Type -AssemblyName System.Speech
  $sapi = New-Object System.Speech.Synthesis.SpeechSynthesizer
} catch { $sapiErr = $_.Exception.Message }
function Await($op, [Type]$t) {
  $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
  $null = $task.Wait(-1)
  $task.Result
}
if ($Mode -eq 'list') {
  if ($onecore) {
    foreach ($v in [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices) {
      Say @{engine = 'onecore'; name = $v.DisplayName; lang = $v.Language; gender = [string]$v.Gender }
    }
  } else { Say @{problem = 'onecore'; text = $onecoreErr } }
  if ($sapi) {
    foreach ($v in $sapi.GetInstalledVoices()) {
      if ($v.Enabled) {
        $i = $v.VoiceInfo
        Say @{engine = 'sapi'; name = $i.Name; lang = $i.Culture.Name; gender = [string]$i.Gender }
      }
    }
  } else { Say @{problem = 'sapi'; text = $sapiErr } }
  exit 0
}
# PowerShell 5 hands a JSON array on as ONE object: no @() around it
$jobs = ConvertFrom-Json (Get-Content -Raw -Encoding UTF8 -LiteralPath $Job)
$fmt = $null
if ($sapi) {
  $fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)
}
$n = 0
foreach ($j in $jobs) {
  try {
    if ($j.engine -eq 'onecore') {
      if (-not $onecore) { throw "OneCore: $onecoreErr" }
      $v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.DisplayName -eq $j.voice } | Select-Object -First 1
      if (-not $v) { throw "voice not installed: $($j.voice)" }
      $onecore.Voice = $v
      $stream = Await ($onecore.SynthesizeSsmlToStreamAsync($j.ssml)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
      $size = [uint32]$stream.Size
      $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
      $null = Await ($reader.LoadAsync($size)) ([uint32])
      $bytes = New-Object byte[] $size
      $reader.ReadBytes($bytes)
      $reader.Dispose()
      $stream.Dispose()
      [System.IO.File]::WriteAllBytes($j.out, $bytes)
    } else {
      if (-not $sapi) { throw "SAPI: $sapiErr" }
      $sapi.SelectVoice($j.voice)
      $sapi.SetOutputToWaveFile($j.out, $fmt)
      try { $sapi.SpeakSsml($j.ssml) } finally { $sapi.SetOutputToNull() }
    }
    Say @{i = $n; ok = $true }
  } catch {
    Say @{i = $n; ok = $false; error = $_.Exception.Message }
  }
  $n++
}
'''


class TTSError(Exception):
    pass


# ---------------------------------------------------------------------------
# PowerShell

def _powershell():
    root = os.environ.get('SystemRoot') or os.environ.get('windir') \
        or 'C:' + os.sep + 'Windows'
    p = os.path.join(root, 'System32', 'WindowsPowerShell', 'v1.0',
                     'powershell.exe')
    return p if os.path.isfile(p) else 'powershell.exe'


def _script():
    """The helper script in the temp folder, written when it differs."""
    p = os.path.join(tempfile.gettempdir(), 'qf2_tts_v1.ps1')
    blob = _PS.encode('utf-8-sig')      # BOM: PowerShell 5 reads UTF-8
    try:
        with open(p, 'rb') as f:
            if f.read() == blob:
                return p
    except OSError:
        pass
    with open(p, 'wb') as f:
        f.write(blob)
    return p


def _run(mode, job=None, on_line=None, cancel=None):
    """Run the helper; ``on_line(dict)`` for every answer line. Stops when
    ``cancel`` (threading.Event) is set or nothing comes for TIMEOUT s."""
    args = [_powershell(), '-NoProfile', '-NonInteractive',
            '-ExecutionPolicy', 'Bypass', '-File', _script(), '-Mode', mode]
    if job:
        args += ['-Job', job]
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL,
                                creationflags=CREATE_NO_WINDOW)
    except OSError as e:
        raise TTSError(f'PowerShell: {e}')
    last = [time.time()]
    stop = threading.Event()

    def watchdog():
        while not stop.wait(0.3):
            if (cancel is not None and cancel.is_set()) or \
                    time.time() - last[0] > TIMEOUT:
                try:
                    proc.kill()
                except OSError:
                    pass
                return
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        for raw in proc.stdout:
            last[0] = time.time()
            text = raw.decode('utf-8', 'replace').strip().lstrip('\ufeff')
            if not text.startswith('{'):
                continue
            try:
                obj = json.loads(text)
            except ValueError:
                continue
            if on_line:
                on_line(obj)
        err = proc.stderr.read().decode('utf-8', 'replace').strip()
        code = proc.wait()
    finally:
        stop.set()
    if cancel is not None and cancel.is_set():
        raise TTSError('cancelled')
    if code and time.time() - last[0] > TIMEOUT:
        raise TTSError('no answer from the speech synthesis')
    return code, err


# ---------------------------------------------------------------------------
# voices

_cache = {}


def voices(refresh=False):
    """[{'id', 'engine', 'name', 'lang', 'gender'}], OneCore first. Asked
    once per session (half a second)."""
    if 'voices' in _cache and not refresh:
        return _cache['voices']
    found, problems = [], []

    def line(o):
        if o.get('engine') and o.get('name'):
            found.append({'id': f"{o['engine']}:{o['name']}",
                          'engine': o['engine'], 'name': o['name'],
                          'lang': o.get('lang') or '',
                          'gender': (o.get('gender') or '').lower()})
        elif o.get('problem'):
            problems.append(f"{o['problem']}: {o.get('text')}")
    code, err = _run('list', on_line=line)
    if not found and (code or err or problems):
        raise TTSError('; '.join(problems) or err or f'exit code {code}')
    seen, out = set(), []
    for v in sorted(found, key=lambda v: (v['engine'] != 'onecore',
                                          v['lang'], v['name'])):
        if v['id'] not in seen:
            seen.add(v['id'])
            out.append(v)
    _cache['voices'] = out
    _cache['problems'] = problems
    return out


def find(voice_list, vid):
    for v in voice_list:
        if v['id'] == vid:
            return v
    return None


def short_name(v):
    name = v['name'].replace('Microsoft ', '')
    return name + (' (SAPI)' if v['engine'] == 'sapi' else '')


def pick(voice_list, lang, gender='male'):
    """The voice for a speaker: the UI language first, then any; the wanted
    gender first."""
    if not voice_list:
        return None

    def rank(v):
        return (not v['lang'].lower().startswith(lang.lower()),
                v['gender'] != gender, v['engine'] != 'onecore', v['name'])
    return sorted(voice_list, key=rank)[0]


def defaults(voice_list, lang, keys, have):
    """Settings for the speaker keys that have none yet: the hero at
    normal pitch, the NPC speakers stepping through PITCHES (counted on
    from the settings already there) so they sound apart."""
    v = pick(voice_list, lang)
    out = {}
    step = sum(1 for k in have if k != HERO)
    for k in keys:
        if k in have:
            continue
        if k == HERO:
            out[k] = {'voice': v['id'] if v else None, 'pitch': 0, 'rate': 0}
        else:
            out[k] = {'voice': v['id'] if v else None,
                      'pitch': PITCHES[step % len(PITCHES)], 'rate': 0}
            step += 1
    return out


# ---------------------------------------------------------------------------
# speaking

def clean(text):
    return ' '.join((text or '').split())


def ssml(text, lang, pitch=0, rate=0):
    body = escape(clean(text), {"'": '&apos;', '"': '&quot;'})
    attrs = []
    if pitch:
        attrs.append(f"pitch='{int(pitch):+d}%'")
    if rate:
        attrs.append(f"rate='{int(rate):+d}%'")
    if attrs:
        body = f"<prosody {' '.join(attrs)}>{body}</prosody>"
    return ("<speak version='1.0' "
            "xmlns='http://www.w3.org/2001/10/synthesis' "
            f"xml:lang='{escape(lang or 'en-US')}'>{body}</speak>")


def synthesize(jobs, progress=None, cancel=None):
    """jobs: [{'voice': voice dict, 'pitch', 'rate', 'text'}]. Returns
    [(pcm or None, error or None)] in the same order; pcm is a take: 16 bit
    mono 44.1 kHz, levelled like the originals, silence cut off.
    ``progress(done, total)`` from the worker thread."""
    tmp = tempfile.mkdtemp(prefix='qf2_tts_')
    spec = []
    for i, j in enumerate(jobs):
        v = j['voice']
        spec.append({'engine': v['engine'], 'voice': v['name'],
                     'ssml': ssml(j['text'], v['lang'], j.get('pitch', 0),
                                  j.get('rate', 0)),
                     'out': os.path.join(tmp, f'{i}.wav')})
    job = os.path.join(tmp, 'jobs.json')
    with open(job, 'w', encoding='utf-8') as f:
        json.dump(spec, f)           # ASCII only: no code page trouble
    answers = {}

    def line(o):
        if 'i' in o:
            answers[int(o['i'])] = o
            if progress:
                progress(len(answers), len(jobs))
    try:
        try:
            _code, err = _run('speak', job, line, cancel)
        except TTSError as e:            # cancelled: keep what is there
            err = str(e)
        out = []
        for i in range(len(jobs)):
            a = answers.get(i)
            if not a or not a.get('ok'):
                out.append((None, (a or {}).get('error') or err
                            or 'no answer'))
                continue
            try:
                pcm, _note = audioin.load(spec[i]['out'])
            except (audioin.AudioError, OSError) as e:
                out.append((None, str(e)))
                continue
            start, end = recorder.detect_trim(pcm, audioin.RATE)
            pcm = recorder.cut(pcm, audioin.RATE, start, end) or pcm
            out.append((pcm, None))
        return out
    finally:
        for n in os.listdir(tmp):
            try:
                os.remove(os.path.join(tmp, n))
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# the mark on the line

def mark(line, voice_id, pitch, rate):
    line[MARK] = {'voice': voice_id, 'text': clean(line.get('text')),
                  'pitch': int(pitch), 'rate': int(rate)}


def unmark(line):
    line.pop(MARK, None)


def is_placeholder(line):
    return bool(line.get('voice') and line.get(MARK))


def outdated(line):
    """The line text changed after the placeholder was spoken."""
    m = line.get(MARK)
    return bool(m) and clean(m.get('text')).lower() != \
        clean(line.get('text')).lower()


def speaker_key(node):
    if node.get('type') == 'player':
        return HERO
    return str(node.get('speaker'))


def voiced_node(node):
    """NPC lines and the hero's single answers. The hero's choices stay
    silent like in the game (none of the 1524 retail choice points has a
    recording)."""
    if node.get('type') == 'npc':
        return True
    return node.get('type') == 'player' and node.get('kind') != 'question'


def todo(quests, take_exists, renew_outdated=True, renew_all=False):
    """[(quest, nid, index, line, speaker key, reason)] of the lines that
    get a placeholder now; reason 'new', 'outdated' or 'renew'. Lines with
    an original cue or an own take are left alone. ``take_exists(line)``
    tells whether the line's take file is there."""
    out = []
    for q in quests:
        for nid, node in q.graph.get('nodes', {}).items():
            if not voiced_node(node):
                continue
            for i, ln in enumerate(node.get('lines') or []):
                if not clean(ln.get('text')):
                    continue
                if ln.get('voice'):
                    if not ln.get(MARK):
                        continue                 # own recording or file
                    if not take_exists(ln):
                        reason = 'new'
                    elif outdated(ln) and (renew_outdated or renew_all):
                        reason = 'outdated'
                    elif renew_all:
                        reason = 'renew'
                    else:
                        continue
                elif ln.get('cue'):
                    continue                     # the original actor speaks
                else:
                    reason = 'new'
                out.append((q, nid, i, ln, speaker_key(node), reason))
    return out


def placeholders(quests):
    """[(quest, nid, index, line)] of every line speaking a placeholder."""
    out = []
    for q in quests:
        for nid, node in q.graph.get('nodes', {}).items():
            for i, ln in enumerate(node.get('lines') or []):
                if is_placeholder(ln):
                    out.append((q, nid, i, ln))
    return out
