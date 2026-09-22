"""Own voice lines into the game's sound bank (4.4.0, Marco 2026-09-22).

The engine reads its XACT banks only from ``<game>\\XACT\\win``, not from a
.wd archive, so these files are extended in place (measured for the
campaign, in the game since 08/2026, QuestForge SOUNDBANK.md):

    UnitTalk.xwb     wave bank, ~935 MB: new entries go into the gap behind
                     the metadata, the MS-ADPCM data to the end (tw1_xwb)
    Sounds.xsb       sound bank: one cue per line, checksum and name hash
                     (tw1_xsb)
    sounds.xap.cued  duration per cue name - without it the dialog goes on
                     after exactly one second (XXXDEFAULT = 1.0)
    sounds.xap.info  XACT project file, not read by the game, kept in step
    LipSync\\data.lipsync  mouth movement per cue name (4.5.0, lipsync.py);
                     optional, 4.4.0 left it alone

Cue names follow the game's pattern ``CUE_<lector>_<number>``, counted on
behind the highest number of the same speaker: the engine reads speaker and
number from the name, a name outside the pattern (``CUE_MOD_...``) made the
dialog go on after one second.

Undo without a copy of the 935 MB: before the first change the small files
are copied and of the wave bank only the part in front of the wave data
(header, bank data, metadata and gap, ~210 KB) plus its size are kept.
Restoring writes that part back and cuts the file to its old size.
Everything lives in ``XACT\\win\\QuestCreator``: the record, the base
copies, the encoded lines.

One set of lines per mod archive. Every build restores the base and adds
all sets again, so a set can change or go without touching the others, and
cue names stay what they were (the other mods' dialogs refer to them). When
the files changed behind our back (the campaign installer puts its own
banks in, or its --zurueck the originals), the current files become the new
base and all sets go in again from the encoded lines.
"""

import hashlib
import json
import os
import re
import shutil
import struct
import time
import zipfile

from . import adpcm, audioin, lipsync

XWB = 'UnitTalk.xwb'
SMALL = ('Sounds.xsb', 'sounds.xap.cued', 'sounds.xap.info')
STORE = 'QuestCreator'
RECORD = 'voices.json'
BASE = 'base'
LINES = 'lines'
HEAD = 'UnitTalk.head'
CUE_RE = re.compile(r'^CUE_(\d{4})_(\d{4})$')
RESERVE = 512              # free metadata slots after growing the wave bank
ENCODER = 1                # part of the cache key: bump when encoding changes
BANK = 'UnitTalk'
LIPSYNC = os.path.join('LipSync', 'data.lipsync')   # optional (4.5.0)
PACK_EXT = '.tw1voices'    # voice pack for other players (4.5.0)
PACK_FORMAT = 1


class VoiceError(Exception):
    pass


def _mods():
    import tw1_xap
    import tw1_xsb
    import tw1_xwb
    return tw1_xwb, tw1_xsb, tw1_xap


def xact_dir(game):
    return os.path.join(game, 'XACT', 'win')


def store_dir(game):
    return os.path.join(xact_dir(game), STORE)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _write(path, blob):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.qf2tmp'
    with open(tmp, 'wb') as f:
        f.write(blob)
    os.replace(tmp, path)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def available(game):
    """The game has the four bank files."""
    d = xact_dir(game) if game else ''
    return bool(d) and all(os.path.isfile(os.path.join(d, n))
                           for n in (XWB,) + SMALL)


# ---------------------------------------------------------------------------
# state of the files

def _wave_offset(path):
    xwb, _xsb, _xap = _mods()
    return xwb.Xwb(path).regionen['ENTRYWAVEDATA'][0]


def fingerprint(game):
    """What the files are now: hash of each small file, size and hash of
    the front part of the wave bank."""
    d = xact_dir(game)
    out = {n: _sha(_read(os.path.join(d, n))) for n in SMALL}
    p = os.path.join(d, XWB)
    wo = _wave_offset(p)
    with open(p, 'rb') as f:
        head = f.read(wo)
    out[XWB] = [os.path.getsize(p), _sha(head)]
    lp = os.path.join(d, LIPSYNC)
    if os.path.isfile(lp):
        out[LIPSYNC] = _sha(_read(lp))
    return out


def load_record(game):
    p = os.path.join(store_dir(game), RECORD)
    try:
        with open(p, encoding='utf-8') as f:
            rec = json.load(f)
        if rec.get('format') == 1:
            return rec
    except (OSError, ValueError):
        pass
    return {'format': 1, 'sets': {}, 'after': None, 'base': None}


def save_record(game, rec):
    blob = json.dumps(rec, indent=1, ensure_ascii=False).encode('utf-8')
    _write(os.path.join(store_dir(game), RECORD), blob)


def ours(game, rec):
    """The files are exactly as our last build left them. Only what the
    record knows counts: a 4.4.0 record has no lip sync file in it."""
    after = rec.get('after')
    if not after:
        return False
    now = fingerprint(game)
    return all(now.get(k) == v for k, v in after.items())


def take_base(game):
    """The files as they are now become the base."""
    xwb, _xsb, _xap = _mods()
    d, bd = xact_dir(game), os.path.join(store_dir(game), BASE)
    os.makedirs(bd, exist_ok=True)
    for n in SMALL:
        shutil.copy2(os.path.join(d, n), os.path.join(bd, n))
    p = os.path.join(d, XWB)
    w = xwb.Xwb(p)
    wo = w.regionen['ENTRYWAVEDATA'][0]
    with open(p, 'rb') as f:
        head = f.read(wo)
    _write(os.path.join(bd, HEAD), head)
    base = {'xwb_size': os.path.getsize(p), 'xwb_count': w.count,
            'head': _sha(head)}
    keep_lipsync(game, base)
    return base


def keep_lipsync(game, base):
    """The lip sync file as it is now goes into the base (a base of 4.4.0
    has none; that version never changed the file)."""
    lp = os.path.join(xact_dir(game), LIPSYNC)
    if base.get('lipsync') or not os.path.isfile(lp):
        return
    blob = _read(lp)
    _write(os.path.join(store_dir(game), BASE, LIPSYNC), blob)
    base['lipsync'] = _sha(blob)


def restore_base(game, base):
    """Write the kept front part back, cut the wave bank to its old size,
    copy the small files back."""
    xwb, _xsb, _xap = _mods()
    d, bd = xact_dir(game), os.path.join(store_dir(game), BASE)
    head = _read(os.path.join(bd, HEAD))
    if _sha(head) != base['head']:
        raise VoiceError('base copy damaged')
    p = os.path.join(d, XWB)
    if os.path.getsize(p) < base['xwb_size']:
        raise VoiceError('wave bank shorter than its base')
    with open(p, 'r+b') as f:
        f.write(head)
        f.truncate(base['xwb_size'])
    w = xwb.Xwb(p)
    if w.count != base['xwb_count'] or w.pruefen():
        raise VoiceError('wave bank not back at its base: '
                         + '; '.join(w.pruefen()))
    for n in SMALL:
        shutil.copy2(os.path.join(bd, n), os.path.join(d, n))
    if base.get('lipsync'):
        blob = _read(os.path.join(bd, LIPSYNC))
        if _sha(blob) != base['lipsync']:
            raise VoiceError('base copy of the lip sync file damaged')
        _write(os.path.join(d, LIPSYNC), blob)


def grow_gap(path, slots, log=print):
    """Rewrite the wave bank with room for ``slots`` more metadata entries
    (the gap of the retail bank holds 71, the campaign used most of them).
    The wave data only moves: playOffset is relative to its region, every
    existing entry stays valid (tw1_xwb.neu_schreiben does the same)."""
    xwb, _xsb, _xap = _mods()
    w = xwb.Xwb(path)
    aus = w.ausrichtung
    mo, ml = w.regionen['ENTRYMETADATA']
    wo, wl = w.regionen['ENTRYWAVEDATA']
    need = os.path.getsize(path) + (slots * xwb.EINTRAG) + (64 << 20)
    if shutil.disk_usage(os.path.dirname(path)).free < need:
        raise VoiceError('not enough free disk space to grow the wave bank')
    new_wo = (mo + ml + slots * xwb.EINTRAG + aus - 1) // aus * aus
    with open(path, 'rb') as q:
        head = bytearray(q.read(wo))
    struct.pack_into('<II', head, 12 + 4 * 8, new_wo, wl)
    head += b'\0' * (new_wo - wo)
    log(('voice_grow', slots, os.path.getsize(path) >> 20))
    tmp = path + '.qf2grow'
    with open(path, 'rb') as q, open(tmp, 'wb') as z:
        z.write(head)
        q.seek(wo)
        rest = wl
        while rest > 0:
            piece = q.read(min(32 << 20, rest))
            if not piece:
                break
            z.write(piece)
            rest -= len(piece)
    grown = xwb.Xwb(tmp)
    if grown.pruefen() or grown.count != w.count or grown.platz() < slots:
        os.remove(tmp)
        raise VoiceError('grown wave bank failed its check')
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# encoding

def encode_take(game, path):
    """(key, blocks) of a take: loaded (any format), levelled like the
    originals, MS-ADPCM, kept in the store by its hash."""
    pcm, _note = audioin.load(path)
    key = _sha(pcm + b'enc%d' % ENCODER)
    p = os.path.join(store_dir(game), LINES, key + '.adpcm')
    if not os.path.isfile(p):
        raw, _blocks = adpcm.encode(pcm)
        _write(p, raw)
    lp = os.path.join(store_dir(game), LINES, key + '.lip')
    if not os.path.isfile(lp):
        _write(lp, lipsync.generate(pcm, adpcm.BANK_RATE))
    return key, os.path.getsize(p) // adpcm.BLOCK


def _encoded(game, key):
    p = os.path.join(store_dir(game), LINES, key + '.adpcm')
    return _read(p) if os.path.isfile(p) else None


def _lip(game, key):
    """The mouth movement of an encoded line (made from the encoded data
    when a pack or an older build brought none)."""
    p = os.path.join(store_dir(game), LINES, key + '.lip')
    if os.path.isfile(p):
        return _read(p)
    raw = _encoded(game, key)
    if raw is None:
        return b''
    rec = lipsync.generate(adpcm.decode(raw), adpcm.BANK_RATE)
    _write(p, rec)
    return rec


# ---------------------------------------------------------------------------
# building

def _number_names(base_names, sets):
    """Keep the cue name of every line that has one (and is free), give the
    others the next number of their speaker."""
    taken = set(base_names)
    top = {}
    for n in base_names:
        m = CUE_RE.match(n)
        if m:
            lec, nr = int(m.group(1)), int(m.group(2))
            top[lec] = max(top.get(lec, 0), nr)
    kept = set()
    for name in sorted(sets):
        for e in sets[name]:
            cue = e.get('cue')
            m = CUE_RE.match(cue or '')
            if m and cue not in taken and cue not in kept \
                    and int(m.group(1)) == e['lector']:
                kept.add(cue)
                top[e['lector']] = max(top.get(e['lector'], 0),
                                       int(m.group(2)))
            else:
                e['cue'] = None
    renamed = []
    for name in sorted(sets):
        for e in sets[name]:
            if e['cue'] is None:
                nr = top.get(e['lector'], 0) + 1
                if nr > 9999:
                    raise VoiceError(f'no cue number left for speaker '
                                     f'{e["lector"]}')
                top[e['lector']] = nr
                e['cue'] = f'CUE_{e["lector"]:04d}_{nr:04d}'
                renamed.append((name, e))
    return renamed


def _apply(game, rec, log=print):
    """Base -> base plus every line of every set. The files must be at the
    base when this is called."""
    xwb, xsb, xap = _mods()
    d = xact_dir(game)
    sets = rec['sets']
    # lines whose encoded data is gone cannot go in again
    for name in list(sets):
        keep = []
        for e in sets[name]:
            if _encoded(game, e['key']) is None:
                log(('voice_lost', name, e['take']))
            else:
                keep.append(e)
        sets[name] = keep
    x = xsb.Xsb(_read(os.path.join(d, 'Sounds.xsb')))
    if BANK not in x.baenke:
        raise VoiceError('Sounds.xsb has no UnitTalk bank')
    bank = x.baenke.index(BANK)
    for name, e in _number_names(x.namen, sets):
        log(('voice_newcue', name, e['cue'], e['take']))
    flat = [(name, e) for name in sorted(sets) for e in sets[name]]
    if not flat:
        return 0
    p = os.path.join(d, XWB)
    w = xwb.Xwb(p)
    problems = w.pruefen()
    if problems:
        raise VoiceError('wave bank: ' + '; '.join(problems))
    base_count = w.count
    if w.platz() < len(flat):
        grow_gap(p, len(flat) + RESERVE, log)
        rec['base'] = take_base(game)
        w = xwb.Xwb(p)
    fmt = adpcm.format_word()
    new = []
    for _name, e in flat:
        raw = _encoded(game, e['key'])
        new.append((raw, fmt, len(raw) // adpcm.BLOCK))
    idx = w.anhaengen(new)
    cued = xap.Xap(_read(os.path.join(d, 'sounds.xap.cued')))
    info = xap.Xap(_read(os.path.join(d, 'sounds.xap.info')))
    try:
        info_ok = len(info._kinder(info.wave_liste())) == base_count
    except (KeyError, IndexError, StopIteration):
        info_ok = False
    if not info_ok:
        log(('voice_noinfo',))
    for (_name, e), i, (raw, _f, blocks) in zip(flat, idx, new):
        x.cue_anlegen(e['cue'], i, bank=bank)
        seconds = blocks * adpcm.SAMPLES / adpcm.BANK_RATE
        cued.dauer_anlegen(e['cue'], seconds)
        if info_ok:
            lec, nr = CUE_RE.match(e['cue']).groups()
            info.wave_anlegen(i, f'WAV_{lec}_{nr}', prl=blocks *
                              adpcm.SAMPLES * 2, srate=adpcm.BANK_RATE)
            info.snd_anlegen(f'SND_{lec}_{nr}', f'WAV_{lec}_{nr}')
        e['wave'] = i
        e['seconds'] = round(seconds, 3)
    new_xsb = x.bauen()
    check = xsb.Xsb(new_xsb)
    durations = xap.Xap(cued.bauen()).dauern()
    for _name, e in flat:
        if check.wave_of(e['cue']) != (BANK, e['wave']) \
                or abs(durations.get(e['cue'], -1) - e['seconds']) > 0.01:
            raise VoiceError(f'check failed for {e["cue"]}')
    _write(os.path.join(d, 'Sounds.xsb'), new_xsb)
    _write(os.path.join(d, 'sounds.xap.cued'), cued.bauen())
    if info_ok:
        _write(os.path.join(d, 'sounds.xap.info'), info.bauen())
    _apply_lipsync(game, rec, flat, log)
    return len(flat)


def _apply_lipsync(game, rec, flat, log):
    """Mouth movement for the new cues (4.5.0). The file must be at its
    base; without one nothing happens (the voices still speak)."""
    lp = os.path.join(xact_dir(game), LIPSYNC)
    if not os.path.isfile(lp) or not rec.get('base', {}).get('lipsync'):
        return
    try:
        entries = lipsync.parse(_read(lp))
    except lipsync.LipSyncError as e:
        log(('voice_nolip', str(e)))
        return
    for _name, e in flat:
        entries[e['cue']] = _lip(game, e['key'])
    blob = lipsync.build(entries)
    check = lipsync.parse(blob)
    for _name, e in flat:
        if check.get(e['cue']) != entries[e['cue']]:
            raise VoiceError(f"lip sync check failed for {e['cue']}")
    _write(lp, blob)


def _prepare(game, rec, log):
    """Bring the files to the base: ours -> restore it; changed behind our
    back or first time -> the current files are the base."""
    if ours(game, rec) and rec.get('base'):
        restore_base(game, rec['base'])
        keep_lipsync(game, rec['base'])
        log(('voice_restored',))
    else:
        if rec.get('after'):
            log(('voice_changed',))
        rec['base'] = take_base(game)


def build(game, set_name, lines, log=print, partial_quests=None):
    """Put the lines of one mod archive into the game.

    lines: [{'take': file name, 'path': take file, 'lector': speaker,
    'quest': quest id}]. partial_quests: the quest ids of an "export this
    quest"; the set's lines of other quests stay. Returns {take: cue}."""
    if not available(game):
        raise VoiceError('no XACT bank files in the game folder')
    rec = load_record(game)
    old = {(e['take'], e['lector']): e for e in rec['sets'].get(set_name, [])}
    fresh = []
    for ln in lines:
        key, blocks = encode_take(game, ln['path'])
        prev = old.get((ln['take'], ln['lector']))
        fresh.append({'take': ln['take'], 'key': key, 'lector': ln['lector'],
                      'quest': ln.get('quest'), 'blocks': blocks,
                      'cue': prev['cue'] if prev else None,
                      'tts': bool(ln.get('tts')),
                      'text': ln.get('text', '')})
    if partial_quests is not None:
        fresh += [e for e in rec['sets'].get(set_name, [])
                  if e.get('quest') not in partial_quests]
    if fresh:
        rec['sets'][set_name] = fresh
    else:
        rec['sets'].pop(set_name, None)
    _prepare(game, rec, log)
    n = _apply(game, rec, log)
    rec['after'] = fingerprint(game)
    save_record(game, rec)
    log(('voice_built', len(rec['sets'].get(set_name, [])), n))
    return {e['take']: e['cue'] for e in rec['sets'].get(set_name, [])}


def remove(game, set_name=None, log=print):
    """Take the lines of one set (None: all) out of the game again."""
    rec = load_record(game)
    if not rec.get('after'):
        return 0
    if not ours(game, rec):
        raise VoiceError('changed')
    restore_base(game, rec['base'])
    gone = 0
    if set_name is None:
        gone = sum(len(v) for v in rec['sets'].values())
        rec['sets'] = {}
    else:
        gone = len(rec['sets'].pop(set_name, []))
    _apply(game, rec, log)
    rec['after'] = fingerprint(game)
    save_record(game, rec)
    log(('voice_removed', gone))
    return gone


def status(game):
    """{'sets': {name: count}, 'ours': bool} for the window."""
    rec = load_record(game)
    try:
        mine = ours(game, rec) if rec.get('after') else False
    except Exception:
        mine = False
    return {'sets': {k: len(v) for k, v in rec['sets'].items()},
            'ours': mine, 'built': bool(rec.get('after'))}


# ---------------------------------------------------------------------------
# the project side

def project_lines(project, recorder_voice_path):
    """[{'take', 'path', 'lector', 'quest', 'tts', 'text'}] of every line
    with a take ('tts': a placeholder, 4.5.0), and
    [(quest id, take)] of those whose file is missing. A speaker without a
    lector (NPCs taken over from multiplayer quests) speaks as lector 0,
    the same number its dialog lines get in the tree (graph_to_tree)."""
    out, skipped = [], []
    for q in project.quests:
        for node in q.graph.get('nodes', {}).values():
            if node.get('type') not in ('npc', 'player'):
                continue
            if node['type'] == 'player':
                lector = 1
            else:
                spk = q.speaker(node.get('speaker'))
                lector = (spk.get('lector') if spk else None) or 0
            for ln in node.get('lines') or []:
                if not ln.get('voice'):
                    continue
                path = recorder_voice_path(project, ln)
                if not path or not os.path.isfile(path):
                    skipped.append((q.id, ln['voice']))
                    continue
                out.append({'take': ln['voice'], 'path': path,
                            'lector': int(lector), 'quest': q.id,
                            'tts': bool(ln.get('voice_tts')),
                            'text': ln.get('text', '')})
    return out, skipped


# ---------------------------------------------------------------------------
# voice pack: the voices of one mod for other players (4.5.0)
#
# The engine reads its banks only from XACT\win, so the voices cannot travel
# inside the .wd. A pack carries the encoded lines of one set and the cue
# names the dialogs of that .wd refer to; installing it puts them into the
# receiver's bank under the same names (the same way as an own export, so
# "take own voices out of the game" removes it again).

def pack_name(set_name):
    return os.path.splitext(set_name)[0] + PACK_EXT


def set_entries(game, set_name):
    """The lines of one set as the last build left them ([] if none)."""
    return list(load_record(game)['sets'].get(set_name) or [])


def write_pack(game, set_name, path, tool='', takes=None):
    """Write the set's lines as a pack (zip: manifest.json and
    lines/<key>.adpcm). ``takes``: only these take names. Returns the
    manifest."""
    entries = set_entries(game, set_name)
    if takes is not None:
        entries = [e for e in entries if e['take'] in takes]
    if not entries:
        raise VoiceError('no voices of this mod in the game')
    lines = []
    tmp = path + '.qf2tmp'
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            done = set()
            for e in entries:
                raw = _encoded(game, e['key'])
                if raw is None:
                    raise VoiceError(f"{e['take']}: encoded line missing, "
                                     f"export the mod again")
                if e['key'] not in done:
                    z.writestr(f"lines/{e['key']}.adpcm", raw)
                    z.writestr(f"lines/{e['key']}.lip", _lip(game, e['key']))
                    done.add(e['key'])
                lines.append({'cue': e['cue'], 'lector': e['lector'],
                              'take': e['take'], 'key': e['key'],
                              'blocks': e['blocks'],
                              'seconds': e.get('seconds'),
                              'quest': e.get('quest'),
                              'tts': bool(e.get('tts')),
                              'text': e.get('text', ''), 'sha': _sha(raw)})
            man = {'format': PACK_FORMAT, 'mod': set_name, 'tool': tool,
                   'created': time.strftime('%Y-%m-%d %H:%M'),
                   'lines': lines}
            z.writestr('manifest.json', json.dumps(man, indent=1,
                                                   ensure_ascii=False))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return man


def read_pack(path):
    """The manifest of a pack, checked for its shape."""
    try:
        with zipfile.ZipFile(path) as z:
            man = json.loads(z.read('manifest.json').decode('utf-8'))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        raise VoiceError(f'not a voice pack: {e}')
    if man.get('format') != PACK_FORMAT or not man.get('mod') \
            or not isinstance(man.get('lines'), list):
        raise VoiceError('unknown voice pack format')
    for ln in man['lines']:
        if not CUE_RE.match(ln.get('cue') or '') or \
                not re.match(r'^[0-9a-f]{64}$', ln.get('key') or ''):
            raise VoiceError('voice pack damaged')
    return man


def install_pack(game, path, log=print):
    """Put a pack into the game. Returns {'mod', 'n', 'tts', 'moved':
    [(cue in the pack, cue it got)]} - a moved cue was taken here already
    (another campaign or mod), the dialog of the mod still asks for the
    old name."""
    if not available(game):
        raise VoiceError('no XACT bank files in the game folder')
    man = read_pack(path)
    with zipfile.ZipFile(path) as z:
        for ln in man['lines']:
            raw = z.read(f"lines/{ln['key']}.adpcm")
            if _sha(raw) != ln['sha'] or len(raw) != ln['blocks'] * \
                    adpcm.BLOCK:
                raise VoiceError(f"voice pack damaged: {ln['cue']}")
            p = os.path.join(store_dir(game), LINES, ln['key'] + '.adpcm')
            if not os.path.isfile(p):
                _write(p, raw)
            try:
                lip = z.read(f"lines/{ln['key']}.lip")
            except KeyError:             # made here from the audio then
                lip = None
            if lip is not None and len(lip) % lipsync.RECORD == 0:
                _write(os.path.join(store_dir(game), LINES,
                                    ln['key'] + '.lip'), lip)
    entries = [{'take': ln['take'], 'key': ln['key'],
                'lector': int(ln['lector']), 'quest': ln.get('quest'),
                'blocks': ln['blocks'], 'cue': ln['cue'],
                'tts': bool(ln.get('tts')), 'text': ln.get('text', '')}
               for ln in man['lines']]
    wanted = {id(e): e['cue'] for e in entries}
    rec = load_record(game)
    rec['sets'][man['mod']] = entries
    _prepare(game, rec, log)
    n = _apply(game, rec, log)
    rec['after'] = fingerprint(game)
    save_record(game, rec)
    got = rec['sets'].get(man['mod'], [])
    moved = [(wanted[id(e)], e['cue']) for e in got
             if wanted.get(id(e), e['cue']) != e['cue']]
    log(('voice_built', len(got), n))
    return {'mod': man['mod'], 'n': len(got), 'moved': moved,
            'tts': sum(1 for e in got if e.get('tts'))}
