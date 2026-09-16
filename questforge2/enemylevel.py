"""Enemy levels of the whole world (Quest > Enemy levels).

Wandering animals and enemies are created by the enemy script: ``CreateEnemy``
in the SDK (``Scripts\\Common\\Enemies.ech``) takes the average hero level,
adds a small per-group offset and then clamps the result per creature type to
the minimum and maximum of ``InitializeEnemyLevels``. A grey wolf therefore
stops at level 10 no matter how strong the hero is.

The compiled script ships those 90 pairs as 32 bit immediates, in the order of
the SDK source: every ``IL`` call pushes its arguments right to left, so
``45, 4, 1, 11`` is bandits (type 11, uses markers, 4 to 45). This module finds
that run in the retail script, writes new values into it and packs the result
as ``Mods\\EnemyLevels.wd`` with a FRESH GUID (the engine keys scripts by
GUID; with the retail one it would silently keep the original).

Both shipped variants are patched: ``TwoWorldsEnemies.eco`` (the single player
campaign) and ``TwoWorldsEnemies16.eco`` (the 1.6 and network path).

Only newly created enemies get the new levels, so a new game is needed; units
already in a save keep what they had.
"""

import os
import re
import struct
import time
import zlib

from . import questlimit
from .questlimit import (SEP, build_wd, eco_body, reg_backup, reg_mods,
                         reg_set, wd_entries, wd_read_file)

SOURCE_WD = 'Update16.wd'
FALLBACK_WD = 'Update11-15.wd'
MOD_NAME = 'EnemyLevels.wd'
INNER = (SEP.join(('Scripts', 'Campaigns', 'Missions',
                   'TwoWorldsEnemies.eco')),
         SEP.join(('Scripts', 'Campaigns', 'Missions',
                   'TwoWorldsEnemies16.eco')))
MIN_LEVEL = 1
MAX_LEVEL = 100          # the retail maximum (dragons) and a safe ceiling

# (type number, name, uses markers, retail min, retail max, group)
# generated from the SDK: Scripts\Common\Enemies.ech, InitializeEnemyLevels
ENTRIES = (
    (11, 'Bandit', 1, 4, 45, 'humans'),
    (12, 'Bandit Archer', 1, 4, 40, 'humans'),
    (5, 'Black Bear', 0, 7, 15, 'animals'),
    (28, 'Black Skeleton', 1, 15, 55, 'undead'),
    (29, 'Black Skeleton Archer', 1, 15, 55, 'undead'),
    (6, 'Brown Bear', 0, 10, 25, 'animals'),
    (4, 'Boar', 0, 2, 8, 'animals'),
    (21, 'Boss Skeleton', 1, 6, 25, 'undead'),
    (14, 'Bro Warrior', 1, 10, 35, 'humans'),
    (2, 'Brown Wolf', 0, 1, 6, 'animals'),
    (53, 'Cyclope', 0, 30, 55, 'demons'),
    (8, 'Daemon 1', 0, 10, 40, 'demons'),
    (9, 'Daemon 2', 0, 25, 60, 'demons'),
    (10, 'Daemon 3', 0, 30, 75, 'demons'),
    (36, 'Dead Knight', 1, 15, 40, 'undead'),
    (31, 'Dragon', 0, 40, 100, 'dragons'),
    (18, 'Dwarf', 0, 6, 15, 'humans'),
    (87, 'Ent', 0, 30, 50, 'animals'),
    (20, 'Ghoul', 0, 6, 30, 'undead'),
    (92, 'Ghost Dwarf Enemy', 0, 6, 15, 'undead'),
    (41, 'Goblin', 1, 6, 15, 'greenskins'),
    (42, 'Goblin Archer', 1, 6, 15, 'greenskins'),
    (43, 'Goblin Mage', 1, 6, 15, 'greenskins'),
    (39, 'Goblin 2', 1, 3, 12, 'greenskins'),
    (40, 'Goblin 2Archer', 1, 3, 12, 'greenskins'),
    (60, 'Golem Flesh', 0, 15, 50, 'demons'),
    (62, 'Golem Steel', 0, 30, 50, 'demons'),
    (63, 'Golem Stone', 0, 30, 50, 'demons'),
    (61, 'Golem Wood', 0, 30, 50, 'demons'),
    (1, 'Gray Wolf', 0, 6, 10, 'animals'),
    (35, 'Hellmaster', 1, 30, 60, 'demons'),
    (57, 'Hideous', 0, 25, 75, 'demons'),
    (24, 'Ice Skeleton', 1, 10, 20, 'undead'),
    (25, 'Ice Skeleton Archer', 1, 10, 20, 'undead'),
    (46, 'Insect Guy', 1, 10, 40, 'dragons'),
    (47, 'Insect Guy Mage', 1, 10, 40, 'dragons'),
    (50, 'Jackal', 1, 15, 40, 'humans'),
    (51, 'Jackal Mage', 1, 15, 40, 'humans'),
    (34, 'Lava Dragon', 0, 40, 100, 'dragons'),
    (59, 'Lizardman', 0, 25, 50, 'dragons'),
    (58, 'Mantis', 0, 25, 50, 'dragons'),
    (44, 'Minion', 1, 40, 50, 'demons'),
    (45, 'Minion Mage', 1, 40, 50, 'demons'),
    (17, 'Mummy', 0, 30, 50, 'undead'),
    (13, 'Necro', 1, 15, 50, 'undead'),
    (16, 'Oficer 04', 1, 25, 50, 'humans'),
    (52, 'Ogr', 0, 15, 60, 'greenskins'),
    (79, 'Orc', 1, 10, 30, 'greenskins'),
    (83, 'Orc 2', 1, 20, 40, 'greenskins'),
    (85, 'Orc 2Archer', 1, 20, 40, 'greenskins'),
    (84, 'Orc 2Chief', 1, 25, 50, 'greenskins'),
    (86, 'Orc 2Shaman', 1, 20, 30, 'greenskins'),
    (81, 'Orc Archer', 1, 10, 30, 'greenskins'),
    (80, 'Orc Chief', 1, 20, 40, 'greenskins'),
    (82, 'Orc Shaman', 1, 10, 30, 'greenskins'),
    (68, 'Raptor 1', 0, 3, 8, 'animals'),
    (69, 'Raptor 2', 0, 8, 15, 'animals'),
    (70, 'Raptor 3', 0, 15, 20, 'animals'),
    (71, 'Raptor 4', 0, 20, 25, 'animals'),
    (26, 'Red Skeleton', 1, 18, 25, 'undead'),
    (27, 'Red Skeleton Archer', 1, 18, 25, 'undead'),
    (37, 'Scorpio', 0, 20, 40, 'other'),
    (48, 'Sea Guy', 1, 15, 30, 'dragons'),
    (49, 'Sea Guy Mage', 1, 15, 30, 'dragons'),
    (22, 'Skeleton', 1, 5, 10, 'undead'),
    (23, 'Skeleton Archer', 1, 5, 15, 'undead'),
    (75, 'Snow Orc', 1, 15, 25, 'greenskins'),
    (77, 'Snow Orc Archer', 1, 15, 25, 'greenskins'),
    (76, 'Snow Orc Chief', 1, 20, 30, 'greenskins'),
    (78, 'Snow Orc Shaman', 1, 15, 25, 'greenskins'),
    (15, 'Soldier 04', 1, 10, 15, 'humans'),
    (38, 'Spider', 0, 10, 30, 'animals'),
    (33, 'Stone Dragon', 0, 40, 90, 'dragons'),
    (66, 'Undead Bear', 0, 15, 20, 'undead'),
    (67, 'Undead Reptile', 0, 10, 15, 'undead'),
    (64, 'Undead Wolf', 0, 8, 12, 'undead'),
    (72, 'Vyvern 1', 0, 15, 19, 'dragons'),
    (73, 'Vyvern 2', 0, 19, 25, 'dragons'),
    (74, 'Vyvern 3', 0, 25, 30, 'dragons'),
    (30, 'Vyvern 4', 0, 30, 35, 'dragons'),
    (7, 'White Bear', 0, 20, 25, 'animals'),
    (3, 'White Wolf', 0, 10, 15, 'animals'),
    (19, 'Yeti', 0, 25, 40, 'animals'),
    (54, 'Zombie 1', 0, 5, 10, 'undead'),
    (55, 'Zombie 2', 0, 10, 20, 'undead'),
    (56, 'Zombie 3', 0, 20, 30, 'undead'),
    (88, 'Dragonfly', 0, 10, 10, 'animals'),
    (89, 'Deadmeat', 0, 15, 20, 'undead'),
    (90, 'Khan', 0, 20, 20, 'humans'),
    (91, 'Skull', 0, 20, 20, 'undead'),
)

GROUPS = ('animals', 'greenskins', 'humans', 'undead', 'demons', 'dragons',
          'other')


def entry(type_num):
    for e in ENTRIES:
        if e[0] == type_num:
            return e
    return None


def retail_values():
    return {e[0]: (e[3], e[4]) for e in ENTRIES}


# ---------------------------------------------------------------------------
# finding the table in a compiled script

def _immediates(body):
    out = []
    for m in re.finditer(rb'[\xb8\x68]', body):
        off = m.start()
        if off + 5 <= len(body):
            out.append((off, struct.unpack_from('<I', body, off + 1)[0]))
    return out


LEVEL_CEILING = 200      # sanity check while searching, not a game limit


def _match_at(imms, start):
    """Try to read the whole table beginning at immediate ``start``.
    The anchor is the run of type numbers and marker flags, never the levels
    themselves, so a script that was already changed is still found."""
    out, j = [], start
    for num, _name, mark, _lo, _hi, _grp in ENTRIES:
        width = 4 if mark else 3
        if j + width > len(imms):
            return None
        vals = [v for _, v in imms[j:j + width]]
        if vals[-1] != num or (mark and vals[-2] != mark):
            return None
        hi, lo = vals[0], vals[1]
        if not (0 < lo <= hi <= LEVEL_CEILING):
            return None
        out.append((num, imms[j + 1][0], imms[j][0]))
        j += width
    return out


def locate(body):
    """[(type number, offset of min, offset of max)] in table order.
    Raises ValueError when the script does not carry the known table."""
    imms = _immediates(body)
    first = ENTRIES[0]
    width = 4 if first[2] else 3
    for start in range(len(imms)):
        vals = [v for _, v in imms[start:start + width]]
        if len(vals) < width or vals[-1] != first[0]:
            continue
        hit = _match_at(imms, start)
        if hit:
            return hit
    raise ValueError('enemy level table not found')


def read_levels(body):
    """{type number: (min, max)} of a compiled script."""
    out = {}
    for num, off_lo, off_hi in locate(body):
        out[num] = (struct.unpack_from('<I', body, off_lo + 1)[0],
                    struct.unpack_from('<I', body, off_hi + 1)[0])
    return out


def patch_body(body, values):
    """Write {type: (min, max)} into a copy of the script."""
    out = bytearray(body)
    n = 0
    for num, off_lo, off_hi in locate(body):
        if num not in values:
            continue
        lo, hi = values[num]
        lo = max(MIN_LEVEL, min(MAX_LEVEL, int(lo)))
        hi = max(lo, min(MAX_LEVEL, int(hi)))
        struct.pack_into('<I', out, off_lo + 1, lo)
        struct.pack_into('<I', out, off_hi + 1, hi)
        n += 1
    return bytes(out), n


# ---------------------------------------------------------------------------
# archive with both scripts

def build_mod_archive(out_path, blobs):
    """blobs: [(inner path, body, resource name)] -> one WD archive with a
    fresh GUID per entry."""
    import random
    head = zlib.compress(questlimit.WD_MAGIC + random.randbytes(16))
    parts, dir_rows, offset = [head], [], len(head)
    guids = {}
    for inner, body, res in blobs:
        data = zlib.compress(body)
        parts.append(data)
        guid = random.randbytes(16)
        guids[inner] = guid
        row = bytes([len(inner)]) + inner.encode('ascii')
        row += struct.pack('<BIII', questlimit.ENTRY_FLAGS, offset, len(data),
                           len(body))
        row += bytes([len(res)]) + res
        row += struct.pack('<I', questlimit.ENTRY_ID)
        row += guid
        dir_rows.append(row)
        offset += len(data)
    filetime = int(time.time() * 10000000) + questlimit.FILETIME_EPOCH
    tab = struct.pack('<QH', filetime, len(dir_rows)) + b''.join(dir_rows)
    cdir = zlib.compress(tab)
    with open(out_path, 'wb') as f:
        for p in parts:
            f.write(p)
        f.write(cdir)
        f.write(struct.pack('<I', len(cdir) + 4))
    return guids


# ---------------------------------------------------------------------------
# state

class State:
    """Where the enemy scripts come from and which levels they carry."""

    def __init__(self, game):
        self.game = game
        self.mods_dir = os.path.join(game, 'Mods') if game else None
        self.mod_path = os.path.join(self.mods_dir, MOD_NAME) if game else None
        self.source = None
        self.sources = {}        # inner path -> (archive, entry)
        self.mod_present = False
        self.mod_active = False
        self.values = {}         # what the game will use
        self.mod_values = {}
        self.others = []         # other mods shipping an enemy script
        self.error = None
        if game:
            self.read()

    def read(self):
        wdfiles = os.path.join(self.game, 'WDFiles')
        for name in (SOURCE_WD, FALLBACK_WD):
            p = os.path.join(wdfiles, name)
            if not os.path.exists(p):
                continue
            try:
                ents = {e['path']: e for e in wd_entries(p)}
            except Exception:
                continue
            for inner in INNER:
                if inner in ents and inner not in self.sources:
                    self.sources[inner] = (p, ents[inner])
            if self.sources:
                self.source = p
                break
        if INNER[0] not in self.sources:
            self.error = 'nosource'
            return
        try:
            self.values = read_levels(self.retail_body(INNER[0]))
        except Exception as e:
            self.error = str(e)
            return
        switches = reg_mods()
        self.mod_present = os.path.isfile(self.mod_path)
        self.mod_active = bool(switches.get(MOD_NAME, 0))
        if self.mod_present:
            try:
                ents = {e['path']: e for e in wd_entries(self.mod_path)}
                e = ents.get(INNER[0])
                if e:
                    self.mod_values = read_levels(
                        eco_body(wd_read_file(self.mod_path, e)))
            except Exception:
                self.mod_values = {}
        if self.mod_present and self.mod_active and self.mod_values:
            self.values = dict(self.mod_values)
        if not os.path.isdir(self.mods_dir):
            return
        for f in sorted(os.listdir(self.mods_dir)):
            if not f.lower().endswith('.wd') or f == MOD_NAME:
                continue
            try:
                paths = {e['path'] for e in wd_entries(
                    os.path.join(self.mods_dir, f))}
            except Exception:
                continue
            if paths & set(INNER):
                self.others.append((f, bool(switches.get(f, 0))))

    def retail_body(self, inner):
        arc, e = self.sources[inner]
        return eco_body(wd_read_file(arc, e))

    @property
    def changed(self):
        return self.values != retail_values()


def apply(game, values, log=print):
    """Write Mods\\EnemyLevels.wd with the given {type: (min, max)}."""
    st = State(game)
    if st.error:
        raise RuntimeError(st.error)
    blobs = []
    for inner in INNER:
        if inner not in st.sources:
            continue
        body = st.retail_body(inner)
        patched, n = patch_body(body, values)
        arc, e = st.sources[inner]
        blobs.append((inner, patched, e['res'] or b'Enemies Script'))
        log(('patched', inner.rsplit(SEP, 1)[-1], n,
             os.path.basename(arc)))
    if not blobs:
        raise RuntimeError('nosource')
    bak = reg_backup()
    if bak:
        log(('regbackup', bak))
    if os.path.exists(st.mod_path):
        import shutil
        old = st.mod_path + time.strftime('.vor_%Y-%m-%d_%H-%M-%S')
        shutil.move(st.mod_path, old)
        log(('oldmod', os.path.basename(old)))
    os.makedirs(st.mods_dir, exist_ok=True)
    tmp = st.mod_path + '.neu'
    guids = build_mod_archive(tmp, blobs)
    back = {e['path']: e for e in wd_entries(tmp)}
    for inner, body, res in blobs:
        e = back.get(inner)
        if (e is None or eco_body(wd_read_file(tmp, e)) != body
                or e['guid'] != guids[inner] or e['res'] != res
                or e['flags'] != questlimit.ENTRY_FLAGS
                or e['id'] != questlimit.ENTRY_ID):
            os.remove(tmp)
            raise RuntimeError('archive differs after writing')
    os.replace(tmp, st.mod_path)
    reg_set(MOD_NAME, 1)
    log(('written', MOD_NAME, len(blobs),
         guids[INNER[0]].hex()))
    for name, active in st.others:
        if active:
            log(('otheractive', name))
    return len(blobs)


def remove(game, log=print):
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


# ---------------------------------------------------------------------------
# presets

def preset_follow_hero(values, types=None):
    """No cap: the creature keeps the hero's level (max 100)."""
    out = dict(values)
    for num, _n, _m, lo, hi, _g in ENTRIES:
        if types is None or num in types:
            out[num] = (MIN_LEVEL, MAX_LEVEL)
    return out


def preset_add(values, plus, types=None):
    """Raise the maximum (and the minimum with it) by ``plus``."""
    out = dict(values)
    for num, _n, _m, lo, hi, _g in ENTRIES:
        if types is None or num in types:
            cur_lo, cur_hi = out.get(num, (lo, hi))
            out[num] = (min(MAX_LEVEL, cur_lo + plus),
                        min(MAX_LEVEL, cur_hi + plus))
    return out


def preset_scale(values, factor, types=None):
    out = dict(values)
    for num, _n, _m, lo, hi, _g in ENTRIES:
        if types is None or num in types:
            cur_lo, cur_hi = out.get(num, (lo, hi))
            out[num] = (max(MIN_LEVEL, min(MAX_LEVEL, round(cur_lo * factor))),
                        max(MIN_LEVEL, min(MAX_LEVEL, round(cur_hi * factor))))
    return out


def preset_retail(values, types=None):
    out = dict(values)
    for num, _n, _m, lo, hi, _g in ENTRIES:
        if types is None or num in types:
            out[num] = (lo, hi)
    return out
