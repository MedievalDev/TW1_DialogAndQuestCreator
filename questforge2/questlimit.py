"""Quest limit 400 -> 600 (taken over from TW1 Quest Limit Patcher 1.0).

``PQuests.eco`` in ``WDFiles\\Update16.wd`` is compiled with
``eQuestsNum = 400``: valid quest ids are 1 to 399, every id above collapses
to quest 0. The limit sits in 41 immediates of the script VM (29x
``mov eax,400``, 12x ``cmp eax,400``); the other 47 occurrences of 400 are
``[esi+0x190]`` offsets and stay. ``apply`` patches those 41 sites to 600 and
packs the result as ``Mods\\QuestLimit600.wd`` with a FRESH GUID (the engine
keys scripts by GUID and would keep the original with the retail one),
directory flags 0x3b, resource name ``PQuests`` and class id 4, exactly like
the shipped archives, then switches the mod on in the registry. The body is
byte-identical to the SDK build with ``eQuestsNum = 600``; quests above 399
with that limit and a fresh GUID were confirmed in game on 11.09.2026.

Same file name as the stand-alone patcher, so both tools see each other's
result. The limit applies to new games only: a save carries the quest script
and its 400-sized arrays itself.
"""

import hashlib
import os
import random
import re
import shutil
import struct
import subprocess
import time
import zlib

from . import data

SEP = '\\'
SOURCE_WD = 'Update16.wd'
FALLBACK_WD = 'Update11-15.wd'
INNER = SEP.join(('Scripts', 'Campaigns', 'Missions', 'PQuests.eco'))
MOD_NAME = 'QuestLimit600.wd'

OLD_LIMIT = 400
NEW_LIMIT = 600
# Retail Update16 PQuests.eco body, 144 343 bytes. Only this version is proven.
RETAIL_SHA256 = '976b83e3d7c6eb74a61bed8a42d9f6aa100a9d958bda10848d611b23d4e36026'
RETAIL_SITES = 41
# Directory metadata of PQuests.eco in every shipped archive.
ENTRY_FLAGS = 0x3b
ENTRY_RES = b'PQuests'
ENTRY_ID = 4
WD_MAGIC = bytes([0xFF, 0xA1, 0xD0, 0x31, 0x57, 0x44, 0x00, 0x02])
FILETIME_EPOCH = 116444736000000000


# ---------------------------------------------------------------------------
# WD reading (directory only, no full unpack)

def wd_entries(path):
    """Directory of a WD 0x200 archive: list of dicts in archive order."""
    with open(path, 'rb') as f:
        f.seek(-4, 2)
        dir_off = struct.unpack('<I', f.read(4))[0]
        f.seek(-dir_off, 2)
        raw = f.read()
    d = zlib.decompressobj()
    t = d.decompress(raw) + d.flush()
    off = 8
    n = struct.unpack_from('<H', t, off)[0]
    off += 2
    out = []
    for _ in range(n):
        nl = t[off]
        off += 1
        name = t[off:off + nl].decode('latin-1')
        off += nl
        flags, foff, clen, rlen = struct.unpack_from('<BIII', t, off)
        off += 13
        res = kid = guid = None
        if flags & 0x08:
            xl = t[off]
            off += 1
            res = t[off:off + xl]
            off += xl
        if flags & 0x10:
            kid = struct.unpack_from('<I', t, off)[0]
            off += 4
        if flags & 0x20:
            guid = t[off:off + 16]
            off += 16
        out.append({'path': name, 'flags': flags, 'offset': foff,
                    'clen': clen, 'rlen': rlen, 'res': res, 'id': kid,
                    'guid': guid})
    return out


def wd_read_file(path, entry):
    with open(path, 'rb') as f:
        f.seek(entry['offset'])
        raw = f.read(entry['clen'])
    if entry['flags'] & 0x01:
        d = zlib.decompressobj()
        return d.decompress(raw) + d.flush()
    return raw


def eco_body(raw):
    """ECO body: naked, or two-stream file (header record + body)."""
    if raw[:4] == b'ECO' + bytes(1):
        return raw
    if raw[:2] == b'\x78\x9c':
        d = zlib.decompressobj()
        d.decompress(raw)
        rest = d.unused_data
        return zlib.decompress(rest) if rest[:2] == b'\x78\x9c' else rest
    raise ValueError('unknown .eco layout')


def pquests_in(wd_path):
    for e in wd_entries(wd_path):
        if e['path'].lower().endswith('pquests.eco'):
            return e
    return None


# ---------------------------------------------------------------------------
# patching

SITE_RE = re.compile(rb'[\xb8\x3d]' + re.escape(struct.pack('<I', OLD_LIMIT)))


def find_sites(body):
    return [m.start() + 1 for m in SITE_RE.finditer(body)]


def patch_body(body):
    """(patched body, site count, verified); verified = retail Update16."""
    verified = hashlib.sha256(body).hexdigest() == RETAIL_SHA256
    sites = find_sites(body)
    if verified and len(sites) != RETAIL_SITES:
        raise ValueError(f'expected {RETAIL_SITES} sites, found {len(sites)}')
    if not sites:
        raise ValueError('no eQuestsNum immediates found')
    out = bytearray(body)
    for s in sites:
        out[s:s + 4] = struct.pack('<I', NEW_LIMIT)
    return bytes(out), len(sites), verified


def limit_of(body):
    """400, 600 or None: what a PQuests body counts with."""
    for limit in (OLD_LIMIT, NEW_LIMIT):
        pat = re.compile(rb'[\xb8\x3d]' + re.escape(struct.pack('<I', limit)))
        if len(pat.findall(body)) >= 12:
            return limit
    return None


def build_wd(body, out_path, guid=None):
    """One-file WD 0x200 archive with PQuests.eco, metadata like retail."""
    guid = guid or random.randbytes(16)
    head = zlib.compress(WD_MAGIC + random.randbytes(16))
    blob = zlib.compress(body)
    offset = len(head)
    filetime = int(time.time() * 10000000) + FILETIME_EPOCH
    path = INNER.encode('ascii')
    tab = struct.pack('<QH', filetime, 1)
    tab += bytes([len(path)]) + path
    tab += struct.pack('<BIII', ENTRY_FLAGS, offset, len(blob), len(body))
    tab += bytes([len(ENTRY_RES)]) + ENTRY_RES
    tab += struct.pack('<I', ENTRY_ID)
    tab += guid
    cdir = zlib.compress(tab)
    with open(out_path, 'wb') as f:
        f.write(head)
        f.write(blob)
        f.write(cdir)
        f.write(struct.pack('<I', len(cdir) + 4))
    return guid


# ---------------------------------------------------------------------------
# registry

def reg_mods():
    """{archive name: DWORD} of the game's mod switches."""
    out = {}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, data.REG_MODS) as k:
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = val
                i += 1
    except (OSError, ImportError):
        pass
    return out


def reg_set(name, value):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, data.REG_MODS) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))


def backup_dir():
    return os.path.join(data.ROOT, 'backup')


def reg_backup():
    """Export the Mods key before any change; path or None."""
    d = backup_dir()
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, time.strftime('mods_%Y-%m-%d_%H-%M-%S.reg'))
    try:
        subprocess.run(['reg', 'export', 'HKCU' + SEP + data.REG_MODS, out,
                        '/y'], capture_output=True, creationflags=0x08000000)
    except Exception:            # no reg.exe: go on without backup
        return None
    return out if os.path.exists(out) else None


# ---------------------------------------------------------------------------
# state

class State:
    """What the game will run with at its next start."""

    def __init__(self, game):
        self.game = game
        self.mods_dir = os.path.join(game, 'Mods') if game else None
        self.mod_path = os.path.join(self.mods_dir, MOD_NAME) if game else None
        self.source = None           # retail archive carrying PQuests.eco
        self.source_verified = False
        self.mod_present = False
        self.mod_active = False
        self.mod_limit = None
        self.others = []             # (name, limit, active) other PQuests mods
        self.error = None
        if game:
            self.read()

    def read(self):
        wdfiles = os.path.join(self.game, 'WDFiles')
        for name in (SOURCE_WD, FALLBACK_WD):
            p = os.path.join(wdfiles, name)
            try:
                if os.path.exists(p) and pquests_in(p):
                    self.source = p
                    break
            except Exception:
                continue
        if not self.source:
            self.error = 'nosource'
            return
        try:
            body = eco_body(wd_read_file(self.source, pquests_in(self.source)))
            self.source_verified = (hashlib.sha256(body).hexdigest()
                                    == RETAIL_SHA256)
        except Exception as e:
            self.error = f'unreadable: {e}'
            return
        switches = reg_mods()
        self.mod_present = os.path.exists(self.mod_path)
        self.mod_active = bool(switches.get(MOD_NAME, 0))
        if self.mod_present:
            try:
                e = pquests_in(self.mod_path)
                self.mod_limit = (limit_of(eco_body(wd_read_file(
                    self.mod_path, e))) if e else None)
            except Exception:
                self.mod_limit = None
        if not os.path.isdir(self.mods_dir):
            return
        for f in sorted(os.listdir(self.mods_dir)):
            if not f.lower().endswith('.wd') or f == MOD_NAME:
                continue
            p = os.path.join(self.mods_dir, f)
            try:
                e = pquests_in(p)
            except Exception:
                continue
            if e:
                try:
                    lim = limit_of(eco_body(wd_read_file(p, e)))
                except Exception:
                    lim = None
                self.others.append((f, lim, bool(switches.get(f, 0))))

    @property
    def effective(self):
        """Our mod, else another active quest-script mod, else retail."""
        if self.mod_present and self.mod_active and self.mod_limit:
            return self.mod_limit
        for _name, lim, active in self.others:
            if active and lim:
                return lim
        return OLD_LIMIT

    @property
    def effective_source(self):
        if self.mod_present and self.mod_active and self.mod_limit:
            return MOD_NAME
        for name, lim, active in self.others:
            if active and lim:
                return name
        return os.path.basename(self.source) if self.source else ''


def effective_limit(game):
    """Limit for the editor; retail 400 when anything cannot be read."""
    if not game:
        return OLD_LIMIT
    try:
        return State(game).effective
    except Exception:
        return OLD_LIMIT


def apply(game, log=print):
    """Build Mods\\QuestLimit600.wd from the retail script and switch it on.
    ``log`` receives tuples (kind, ...)."""
    st = State(game)
    if st.error:
        raise RuntimeError(st.error)
    e = pquests_in(st.source)
    body = eco_body(wd_read_file(st.source, e))
    patched, n, verified = patch_body(body)
    log(('source', os.path.basename(st.source), len(body), verified))
    log(('sites', n))
    bak = reg_backup()
    if bak:
        log(('regbackup', bak))
    if os.path.exists(st.mod_path):
        old = st.mod_path + time.strftime('.vor_%Y-%m-%d_%H-%M-%S')
        shutil.move(st.mod_path, old)
        log(('oldmod', os.path.basename(old)))
    os.makedirs(st.mods_dir, exist_ok=True)
    tmp = st.mod_path + '.neu'
    guid = build_wd(patched, tmp)
    # read back before it counts
    chk = wd_entries(tmp)[0]
    back = eco_body(wd_read_file(tmp, chk))
    if back != patched or (chk['flags'], chk['res'], chk['id'],
                           chk['guid']) != (ENTRY_FLAGS, ENTRY_RES, ENTRY_ID,
                                            guid):
        os.remove(tmp)
        raise RuntimeError('archive differs after writing')
    os.replace(tmp, st.mod_path)
    reg_set(MOD_NAME, 1)
    log(('written', MOD_NAME, guid.hex()))
    for name, _lim, active in st.others:
        if active:
            log(('otheractive', name))
    return n


def remove(game, log=print):
    """Delete Mods\\QuestLimit600.wd and switch it off."""
    st = State(game)
    bak = reg_backup()
    if bak:
        log(('regbackup', bak))
    if st.mod_present:
        os.remove(st.mod_path)
        log(('removed', MOD_NAME))
    if MOD_NAME in reg_mods():
        reg_set(MOD_NAME, 0)
        log(('switchedoff', MOD_NAME))
