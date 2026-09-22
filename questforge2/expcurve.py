"""Experience the hero needs per level (4.5.0, Marco 2026-09-22: "ganz oben
fuer den Player needed EXP per Level einstellen ueber einen Multiplikator").

The game asks the script ``RPGCompute`` how many experience points a level
needs (SDK ``Scripts\\RPGCompute\\Unit.ech``, ``GetExperiencePointsForLevel``,
called by the engine for the level up and by the character screen): levels
2 to 6 from a table (4, 20, 45, 90, 150), then ``100 + previous + n * (n +
5)``. The numbers are totals: level 10 needs 1014 points, level 30 14134.

A factor cannot go into the shipped script by changing constants (``n * (n
+ 5)`` has none to turn), so the RPGCompute template (rpgcompute.py,
tools/build_rpgcompute.py) wraps it:

    GetExperiencePointsForLevel(n) = BaseExperience(n) * PERCENT / 100

and the tool writes PERCENT there. The same script carries the values of
the enemies (enemystats.py) and goes into ``Mods\\EnemyLevels.wd``.
"""

from . import rpgcompute

MIN_PERCENT = 10
MAX_PERCENT = 1000
TABLE = {2: 4, 3: 20, 4: 45, 5: 90, 6: 150}
EXAMPLE_LEVELS = (5, 10, 20, 30)
INNER = rpgcompute.INNER


# ---------------------------------------------------------------------------
# the curve (the same arithmetic as the script)

def base_points(level):
    """Experience points level ``level`` needs in total, as the game has
    it."""
    if level < 2:
        return 0
    if level in TABLE:
        return TABLE[level]
    total = TABLE[6]
    for n in range(7, level + 1):
        total = 100 + total + n * (n + 5)
    return total


def points(level, percent=100):
    """With the factor: 32 bit product divided by 100 like the script
    (``imul`` keeps the low 32 bits, ``idiv`` truncates)."""
    prod = base_points(level) * int(percent)
    prod = (prod + 2 ** 31) % 2 ** 32 - 2 ** 31
    q = abs(prod) // 100
    return q if prod >= 0 else -q


def clamp(percent):
    return max(MIN_PERCENT, min(MAX_PERCENT, int(round(percent))))


def to_percent(factor):
    return clamp(float(factor) * 100)


# ---------------------------------------------------------------------------
# the template (rpgcompute.py)

def patch_body(percent):
    return rpgcompute.patch(curve=clamp(percent))


def read_percent(body):
    got = rpgcompute.read(body)
    return got[0] if got else None


def usable(game):
    return rpgcompute.usable(game)
