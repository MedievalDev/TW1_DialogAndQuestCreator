"""Kill experience, health, damage, strike pause and resistances per enemy
unit (Quest > Enemy levels, 4.5.0, Marco 2026-09-22: "fuer jeden Gegner XP
einstellbar, oben ein Bulk-Edit: +25 oder -25 %, eine Checkbox, dass man
nicht unter null kann ... dazu Attack Speed, Resistenzen und Schaden").

Every value is kept per unit as percent and amount and computed in the game
by the RPGCompute template (rpgcompute.py) on top of whatever the active
TwoWorlds.par says - a campaign bringing its own par does not undo it:

    value = base * percent / 100 + amount         (as the script: idiv)

- health base (initParamHP, par field 34): the game makes the hit points
  of it, HP = base * (10 + 2 * vitality * (8 + level)) / 100 with an NPC
  vitality of max(9, 6 * level) (SDK Unit.ech);
- strike pause (strikeDelayTicks, 52): ticks between two strikes, 30 a
  second; smaller is faster;
- protections physical / cold / fire / electric (40 to 43): damage after
  armour = d * d / (d + protect);
- damage: a percent of every damage value of the unit's strikes and
  missiles (no amount);
- kill experience: the engine gives the unit's level (times the hero's
  share of the damage, TwoWorlds.exe 0x585D70); the script adds
  level * (percent - 100) / 100 + amount when the hero's hit kills. With
  the floor on a kill is worth at least 0, without it a kill can take
  experience away (Marco: "bringt der Gegner nur 10 und steht -30 da,
  zieht er dem Helden 20 ab").

The window shows values made from the par the game uses without our mod
(an active mod with a par first, else Update16); tw1_par reads it. Besides
the fields above it shows (Marco 2026-09-22: "Schaden auch in Punkten,
Attack Speed"):

- the damage of one blow in points (blow_at): (weapon value of the level +
  unit damage) x the values of the unit's own weapon (Weapon.ech
  GetDamage); people fight with what they carry, for them only the unit's
  share is known;
- blows a minute (strike_rates): the strike animation plus the pause. The
  animations play at a fixed 30 frames a second - no field of the par and
  no script sets their speed - so an edit of the rate sets the pause.
"""

import os
import re

from . import questlimit, rpgcompute
from .questlimit import SEP, wd_entries, wd_read_file

PAR_INNER = SEP.join(('Parameters', 'TwoWorlds.par'))
PAR_ARCHIVES = ('Update16.wd', 'Update11-15.wd', 'Parameters.wd')
UNIT_FIELDS = 65
PAR_FIELDS = {'hp': 34, 'strike': 52, 'phys': 40, 'cold': 41, 'fire': 42,
              'elec': 43}
STATS = ('exp', 'hp', 'dmg', 'strike', 'phys', 'cold', 'fire', 'elec')
# the fields of the template per stat: (percent, amount)
PAIRS = {'exp': ('xp_p', 'xp_a'), 'hp': ('hp_p', 'hp_a'),
         'dmg': ('dmg_p', None), 'strike': ('st_p', 'st_a'),
         'phys': ('phys_p', 'phys_a'), 'cold': ('cold_p', 'cold_a'),
         'fire': ('fire_p', 'fire_a'), 'elec': ('elec_p', 'elec_a')}
NEUTRAL = (100, 0)
LIMIT = 1000000
MIN_VALUE = {'hp': 1, 'strike': 1, 'phys': 0, 'cold': 0, 'fire': 0,
             'elec': 0}


def _tw1_par():
    import tw1_par
    return tw1_par


def _tdiv(a, b):
    """Integer division like the idiv of the script: toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


# ---------------------------------------------------------------------------
# one unit

def get(mods, unit, stat):
    """(percent, amount) of a stat of a unit."""
    p_key, a_key = PAIRS[stat]
    vals = mods.get(unit) or {}
    return (int(vals.get(p_key, 100)),
            int(vals.get(a_key, 0)) if a_key else 0)


def put(mods, unit, stat, pa):
    """Store (percent, amount); neutral fields leave the table."""
    p_key, a_key = PAIRS[stat]
    vals = dict(mods.get(unit) or {})
    p, a = int(pa[0]), int(pa[1])
    p = max(0, min(LIMIT, p))
    a = max(-LIMIT, min(LIMIT, a))
    for key, v, n in ((p_key, p, 100), (a_key, a, 0)):
        if key is None:
            continue
        if v == n:
            vals.pop(key, None)
        else:
            vals[key] = v
    if vals:
        mods[unit] = vals
    else:
        mods.pop(unit, None)


def value(base, pa, stat=None):
    """What the script makes of a par value."""
    v = _tdiv(int(base) * pa[0], 100) + pa[1]
    if stat in MIN_VALUE:
        v = max(MIN_VALUE[stat], v)
    return v


def npc_vitality(level):
    return max(9, 6 * level)


def hp_at(base, level):
    """Hit points of a unit with health base ``base`` at ``level`` (the
    SDK formula, without equipment)."""
    level = max(1, int(level))
    return base * (10 + 2 * npc_vitality(level) * (8 + level)) // 100


def exp_at(pa, level, floor=True):
    """Experience of one kill at ``level``: the engine's level plus the
    script's bonus (not below minus the level with the floor on)."""
    level = max(1, int(level))
    bonus = _tdiv(level * (pa[0] - 100), 100) + pa[1]
    if floor:
        bonus = max(bonus, -level)
    return level + bonus


# ---------------------------------------------------------------------------
# input: "+10", "-10", "+25%", "-12,5%", "50", "=50"

_EXPR = re.compile(r'^\s*([+-]|=)?\s*(\d+(?:[.,]\d+)?)\s*(%)?\s*$')


def parse_expr(text):
    """('add', n) | ('pct', p) | ('set', n), None for anything else. A sign
    means "change by", a bare number "set to"; % makes it a percentage."""
    m = _EXPR.match(text or '')
    if not m:
        return None
    sign, num, pct = m.groups()
    n = float(num.replace(',', '.'))
    if pct:
        if sign in (None, '='):
            return None          # "50%" alone is not meant as a value
        return ('pct', n if sign == '+' else -n)
    if sign in ('+', '-'):
        return ('add', n if sign == '+' else -n)
    return ('set', n)


_PCT_SET = re.compile(r'^\s*=?\s*(\d+(?:[.,]\d+)?)\s*%\s*$')


def parse_dmg(text):
    """parse_expr, and a percent alone ("150%") setting the damage
    percent: ('pctset', 150)."""
    m = _PCT_SET.match(text or '')
    if m:
        return ('pctset', float(m.group(1).replace(',', '.')))
    return parse_expr(text)


def apply_expr(value_now, expr, lo=None, hi=None):
    """A plain number after an edit (levels)."""
    kind, n = expr
    if kind == 'add':
        out = value_now + n
    elif kind == 'pct':
        out = value_now * (100 + n) / 100
    else:
        out = n
    out = int(round(out))
    if lo is not None:
        out = max(lo, out)
    if hi is not None:
        out = min(hi, out)
    return out


def edit(stat, pa, expr, base=None, level=None):
    """(percent, amount) of a unit after an edit of what the window shows.

    - "+n" / "-n": the value shown goes up or down by n (for the health:
      n hit points at ``level``, turned back into the base);
    - "+p%" / "-p%": the value scales, percent and amount alike;
    - "n": the value becomes n for every unit (percent 0, amount n).
    The damage is kept as a percent: points ("+10", "120") are turned into
    it with the damage of the unit at ``level`` (``base`` is then the dict
    of read_base)."""
    p, a = pa
    kind, n = expr
    if stat == 'dmg':
        if kind == 'pctset':
            p = n
        elif kind == 'pct':
            p = p * (100 + n) / 100
        else:
            pts = damage_points(base, level) if isinstance(base, dict) else 0
            if pts:
                n = n * 100.0 / pts
            p = p + n if kind == 'add' else n
        return (max(0, int(round(p))), 0)
    if kind == 'pct':
        f = (100 + n) / 100
        return (int(round(p * f)), int(round(a * f)))
    if stat == 'hp' and level:
        per = hp_at(100, level) / 100.0         # hit points per base point
        n = n / per
    if kind == 'add':
        return (p, int(round(a + n)))
    return (0, int(round(n)))


def span(values):
    """'12' or '4-45' for a list of numbers (floats rounded)."""
    values = [int(round(v)) for v in values]
    if not values:
        return ''
    lo, hi = min(values), max(values)
    return str(lo) if lo == hi else f'{lo}–{hi}'


# ---------------------------------------------------------------------------
# damage in points and blows a minute (what the window shows)

UNIT_ANIMS = 13           # $uArmedUnitAnimationsID: the animation set
UNIT_WEAPON = 29          # $defaultWeaponID: a monster's own weapon
UNIT_DAMAGE = 35          # initParamDamage
ANIM_FIELDS = 218         # UnitsAnimations
STRIKE_COLUMNS = (119, 120, 121, 122)     # anStrike0 to 3
WEAPON_DAMAGE = range(27, 43, 2)          # wpDam<type>Min, Max after it
COMBO = (85, 60, 30)      # % an NPC goes on with the 2nd, 3rd, 4th blow
TICKS = 30                # game ticks and animation frames a second
MAX_DELAY = 3000


def _int(v):
    return v if isinstance(v, int) else 0


def weapon_base(level):
    """The weapon value of a level (Equipment.ech CalculateDamageFromLevel,
    NEW_BALANCING)."""
    q = (max(1, int(level)) - 1) // 3 * 3
    if q == 0:
        return 10
    return (5 + (q - 1) * 3) * (20 + q) // 10


def unit_damage(init, level):
    """eParamDamage of an NPC: init x strength x (2 + level / 5) / 100,
    strength 5 + 3 x level (Unit.ech)."""
    level = max(1, int(level))
    return int(init) * ((5 + 3 * level) * (2 + level // 5)) // 100


def blow_at(base, level, percent=100):
    """Average damage of one blow at ``level`` before armour: per damage
    type (weapon value + unit damage) x (min + max) / 2 of the unit's own
    weapon / 100 (Weapon.ech GetDamage, Unit.ech InitMissile), times the
    percent of the mod. The own weapon is taken at the unit's level (the
    engine sets it; not measured). None for units without an own weapon:
    people fight with what they carry."""
    w = base.get('weapon')
    if w is None:
        return None
    s = unit_damage(base.get('dmg', 0), level)
    ks = [(lo + hi) / 2.0 for lo, hi in w]
    if any(ks):
        wb = weapon_base(level)
        total = sum(int((wb + s) * k) // 100 for k in ks)
    else:
        total = s            # no values: the unit damage alone (InitMissile)
    return _tdiv(int(total) * int(percent), 100)


def damage_points(base, level):
    """The points an edit of the damage refers to: a blow, for people the
    unit's share."""
    if not base:
        return 0
    got = blow_at(base, level)
    return got if got is not None else unit_damage(base.get('dmg', 0), level)


def strike_column(arr):
    """(blows, frames) of one anStrike column, expected over the chances an
    NPC goes on with the next blow (Unit.ech GetNextSequenceDirectFight-
    Action); None for an empty column. A column is [start, end 1, hit 1,
    end 2, hit 2 ...], negative numbers are further events."""
    if not isinstance(arr, list) or len(arr) < 3 \
            or not isinstance(arr[0], int):
        return None
    rest = [v for v in arr[1:] if isinstance(v, int) and v >= 0]
    blows = frames = 0.0
    reach, last = 1.0, arr[0]
    for i, end in enumerate(rest[0::2]):
        if end <= last or i > len(COMBO):
            break
        if i:
            reach *= COMBO[i - 1] / 100.0
        blows += reach
        frames += reach * (end - last)
        last = end
    return (blows, frames) if blows else None


def _ref(par, ident):
    """(list, entry) an id of the par points at (list << 16 | index)."""
    if not isinstance(ident, int) or ident <= 0:
        return None
    li, ix = ident >> 16, ident & 0xFFFF
    if li >= len(par.lists):
        return None
    ents = par.lists[li][2]
    return (li, ents[ix]) if ix < len(ents) else None


def _strikes(entry):
    if entry.field_count != ANIM_FIELDS:
        return []
    return [c for c in (strike_column(entry.values[k])
                        for k in STRIKE_COLUMNS) if c]


def anim_sets(par, ident):
    """[[(blows, frames) per anStrike column] per animation set] a unit
    strikes with: its own set, or when that has no strikes (people, whose
    set comes with the weapon) every set of the same list that has."""
    got = _ref(par, ident)
    if got is None:
        return []
    li, entry = got
    own = _strikes(entry)
    if own:
        return [own]
    return [c for c in (_strikes(e) for e in par.lists[li][2]) if c]


def weapon_damage(par, ident):
    """[(min, max)] per damage type of a unit's own weapon, None for none."""
    got = _ref(par, ident)
    if got is None or got[1].field_count <= WEAPON_DAMAGE[-1] + 1:
        return None
    v = got[1].values
    out = [(v[i], v[i + 1]) for i in WEAPON_DAMAGE]
    if not all(isinstance(a, int) and isinstance(b, int) for a, b in out):
        return None
    return out


def pause_avg(delay):
    """Ticks an NPC waits after a strike on average: the pause, plus
    Rand(2 x pause) when it ends in 5 to 9 (OnEndDirectFightAction)."""
    d = max(0, int(delay))
    return d + (d - 0.5 if d % 10 > 4 else 0)


def _cycle(cols, level):
    """Average (blows, frames) of a set at ``level``: the column is
    Rand(min(level, columns)) (SelectDirectFightStrikeAnim)."""
    m = max(1, min(max(1, int(level)), len(cols)))
    return (sum(c[0] for c in cols[:m]) / m, sum(c[1] for c in cols[:m]) / m)


def strike_rates(base, level, delay):
    """Blows a minute per animation set (people: one per kind of weapon) at
    ``level`` with a pause of ``delay`` ticks."""
    out = []
    for cols in base.get('sets') or ():
        blows, frames = _cycle(cols, level)
        out.append(blows * 60 * TICKS / (frames + pause_avg(delay)))
    return out


def delay_for(base, level, rate, like):
    """The pause that comes nearest to ``rate`` blows a minute (over the
    sets on average); it keeps whether the pause ``like`` has a random
    part. None when the unit has no strikes or the rate is not positive."""
    sets = base.get('sets') or ()
    if not sets or rate <= 0:
        return None
    cyc = [_cycle(cols, level) for cols in sets]
    blows = sum(c[0] for c in cyc) / len(cyc)
    frames = sum(c[1] for c in cyc) / len(cyc)
    want = blows * 60 * TICKS / rate - frames
    rnd = int(like) % 10 > 4
    best = None
    for centre in (want, (want + 0.5) / 2):
        centre = max(1, min(MAX_DELAY, int(round(centre))))
        for d in range(max(1, centre - 12), min(MAX_DELAY, centre + 12) + 1):
            if (d % 10 > 4) != rnd:
                continue
            err = abs(pause_avg(d) - want)
            if best is None or err < best[0]:
                best = (err, d)
    return best[1]


def speed_edit(base, level, delay, expr):
    """The pause after an edit of the blows a minute, None if it cannot
    be done (no strikes, a rate of 0 or less)."""
    rates = strike_rates(base, level, delay)
    if not rates:
        return None
    cur = sum(rates) / len(rates)
    kind, n = expr
    if kind == 'add':
        want = cur + n
    elif kind == 'pct':
        want = cur * (100 + n) / 100
    else:
        want = n
    return delay_for(base, level, want, delay)


# ---------------------------------------------------------------------------
# the par (for showing what the values come to)

def unit_entries(par):
    """{unit name: Entry} of the Units sheet (65 fields, first one wins)."""
    out = {}
    for e in par.entries():
        if e.field_count == UNIT_FIELDS and e.name not in out \
                and all(e.types[i] == 0 for i in PAR_FIELDS.values()):
            out[e.name] = e
    return out


def read_base(par, units):
    """{unit: {stat: par value, 'dmg': initParamDamage, 'weapon': own
    weapon (weapon_damage), 'sets': strikes (anim_sets)}} for the units the
    par knows."""
    ents = unit_entries(par)
    out = {}
    sets, weapons = {}, {}
    for u in units:
        e = ents.get(u)
        if e is None:
            continue
        b = {k: e.values[i] for k, i in PAR_FIELDS.items()}
        b['dmg'] = _int(e.values[UNIT_DAMAGE])
        w, a = e.values[UNIT_WEAPON], e.values[UNIT_ANIMS]
        if w not in weapons:
            weapons[w] = weapon_damage(par, w)
        if a not in sets:
            sets[a] = anim_sets(par, a)
        b['weapon'], b['sets'] = weapons[w], sets[a]
        out[u] = b
    return out


def _entry(path, inner):
    for e in wd_entries(path):
        if e['path'].lower() == inner.lower():
            return e
    return None


def base_par_source(game, own=None):
    """(archive, entry, label) of the par the game uses besides our mod: a
    switched on mod that ships one, else the newest game archive."""
    mods_dir = os.path.join(game, 'Mods')
    switches = questlimit.reg_mods()
    if os.path.isdir(mods_dir):
        for f in sorted(os.listdir(mods_dir)):
            if not f.lower().endswith('.wd') or f == own \
                    or not switches.get(f, 0):
                continue
            p = os.path.join(mods_dir, f)
            try:
                e = _entry(p, PAR_INNER)
            except Exception:
                continue
            if e is not None:
                return p, e, f
    for name in PAR_ARCHIVES:
        p = os.path.join(game, 'WDFiles', name)
        if not os.path.exists(p):
            continue
        e = _entry(p, PAR_INNER)
        if e is not None:
            return p, e, name
    return None


def load_par(path, entry):
    tw1_par = _tw1_par()
    data, _rewrap = tw1_par.unwrap(wd_read_file(path, entry))
    return tw1_par.parse(data)


def units():
    """The units of the template, in its order."""
    return rpgcompute.units()
