"""The RPGCompute template: the hero's experience curve and the enemy
values per unit (4.5.0)."""

import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import (data, enemylevel, enemystats, expcurve,  # noqa
                         questlimit, rpgcompute)


def sdk_curve(n):
    """GetExperiencePointsForLevel of the SDK (Unit.ech), recursive."""
    if n < 2:
        return 0
    table = {2: 4, 3: 20, 4: 45, 5: 90, 6: 150}
    if n in table:
        return table[n]
    return 100 + sdk_curve(n - 1) + n * (n + 5)


class Curve(unittest.TestCase):
    def test_same_as_the_script(self):
        for n in range(0, 80):
            self.assertEqual(expcurve.base_points(n), sdk_curve(n), n)
            self.assertEqual(expcurve.points(n), sdk_curve(n), n)

    def test_factor(self):
        self.assertEqual(expcurve.points(10, 150), 1014 * 150 // 100)
        self.assertEqual(expcurve.points(2, 50), 2)
        self.assertEqual(expcurve.to_percent('1.5'), 150)
        self.assertEqual(expcurve.to_percent(0.01), expcurve.MIN_PERCENT)
        self.assertEqual(expcurve.to_percent(99), expcurve.MAX_PERCENT)
        self.assertLess(expcurve.base_points(100) * expcurve.MAX_PERCENT,
                        2 ** 31)


class Template(unittest.TestCase):
    def test_sites(self):
        meta, tpl = rpgcompute.load()
        # the curve: mov edx, imm32 right before imul edx
        s = meta['curve_site']
        self.assertEqual(tpl[s - 1], 0xBA)
        self.assertEqual(tpl[s + 4:s + 6], b'\xf7\xea')
        self.assertEqual(struct.unpack_from('<I', tpl, s)[0],
                         meta['curve_marker'])
        # every number of the table is a mov eax, imm32 followed by push eax
        self.assertEqual(len(meta['table']), len(meta['units']))
        for row in meta['table']:
            self.assertEqual(len(row), len(meta['fields']))
            for off in row:
                self.assertEqual((tpl[off - 1], tpl[off + 4]), (0xB8, 0x50))
        offs = [o for row in meta['table'] for o in row]
        self.assertEqual(len(offs), len(set(offs)))

    def test_write_and_read_back(self):
        stats = {'MO_WOLF_01': {'hp_p': 150, 'xp_a': -30, 'dmg_p': 125},
                 'BANDIT_05': {'phys_a': 20, 'st_p': 80}}
        body = rpgcompute.patch(150, stats, floor=False)
        self.assertEqual(rpgcompute.read(body), (150, stats, False))
        meta, tpl = rpgcompute.load()
        self.assertEqual(struct.unpack_from('<i', body,
                                            meta['active_site'])[0], 1)
        # neutral: the table switched off
        plain = rpgcompute.patch(100, {}, True)
        self.assertEqual(struct.unpack_from('<i', plain,
                                            meta['active_site'])[0], 0)
        self.assertEqual(rpgcompute.read(plain), (100, {}, True))
        self.assertIsNone(rpgcompute.read(body[:-1]))
        broken = bytearray(body)
        broken[100] ^= 1
        self.assertIsNone(rpgcompute.read(bytes(broken)))
        self.assertEqual(expcurve.read_percent(expcurve.patch_body(250)), 250)

    def test_archive_keeps_the_class_id(self):
        inner, body, res, cid = rpgcompute.blob(150, {}, True)
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'T.wd')
        enemylevel.build_mod_archive(path, [(inner, body, res, cid)])
        e = {x['path']: x for x in questlimit.wd_entries(path)}[inner]
        self.assertEqual((e['id'], e['res'], e['flags']),
                         (25, b'RPGCompute', questlimit.ENTRY_FLAGS))
        got = questlimit.eco_body(questlimit.wd_read_file(path, e))
        self.assertEqual(expcurve.read_percent(got), 150)

    def test_units_are_the_windows(self):
        names = {u for e in enemylevel.all_entries() for u in e[6]}
        self.assertEqual(set(rpgcompute.units()), names)


class Values(unittest.TestCase):
    def test_edit(self):
        e = enemystats.edit
        self.assertEqual(e('exp', (100, 0), ('add', -30)), (100, -30))
        self.assertEqual(e('exp', (100, 10), ('pct', 25)), (125, 12))
        self.assertEqual(e('exp', (100, 0), ('set', 5)), (0, 5))
        self.assertEqual(e('dmg', (100, 0), ('add', 25)), (125, 0))
        self.assertEqual(e('dmg', (100, 0), ('pct', 25)), (125, 0))
        self.assertEqual(e('dmg', (100, 0), ('set', 80)), (80, 0))
        self.assertEqual(e('phys', (100, 0), ('add', 20)), (100, 20))
        self.assertEqual(e('strike', (100, 0), ('pct', -25)), (75, 0))
        # health: +n hit points at the level, turned into the base
        per = enemystats.hp_at(100, 6) / 100
        self.assertEqual(e('hp', (100, 0), ('add', 100), 80, 6),
                         (100, round(100 / per)))

    def test_kill_experience(self):
        at = enemystats.exp_at
        self.assertEqual(at((100, 0), 10), 10)
        self.assertEqual(at((150, 5), 10), 20)
        # Marco: worth 10, -30 set: with the floor 0, without it -20
        self.assertEqual(at((100, -30), 10, True), 0)
        self.assertEqual(at((100, -30), 10, False), -20)

    def test_put_keeps_the_table_small(self):
        mods = {}
        enemystats.put(mods, 'U', 'exp', (100, -30))
        enemystats.put(mods, 'U', 'dmg', (125, 0))
        self.assertEqual(mods, {'U': {'xp_a': -30, 'dmg_p': 125}})
        enemystats.put(mods, 'U', 'exp', (100, 0))
        enemystats.put(mods, 'U', 'dmg', (100, 0))
        self.assertEqual(mods, {})

    def test_parse(self):
        p = enemystats.parse_expr
        self.assertEqual(p('-10'), ('add', -10))
        self.assertEqual(p('+25%'), ('pct', 25))
        self.assertEqual(p('-12,5%'), ('pct', -12.5))
        self.assertEqual(p('50'), ('set', 50))
        self.assertIsNone(p('50%'))
        self.assertIsNone(p('abc'))


WOLF = {'dmg': 80, 'strike': 60, 'weapon': [(100, 100)] + [(0, 0)] * 7,
        'sets': [[(1.0, 40.0), (1.0, 43.0)]]}


class Points(unittest.TestCase):
    """Damage in points and blows a minute (Marco 2026-09-22)."""

    def test_blow_like_the_combat_notes(self):
        # tw1probe research/animations_combat.md 3.6: wolf bite average
        self.assertEqual(enemystats.unit_damage(80, 6), 55)
        self.assertEqual(enemystats.weapon_base(6), 25)
        self.assertEqual([enemystats.blow_at(WOLF, lvl) for lvl in (1, 6, 10)],
                         [22, 80, 196])
        self.assertEqual(enemystats.blow_at(WOLF, 6, 150), 120)
        person = dict(WOLF, weapon=None)
        self.assertIsNone(enemystats.blow_at(person, 6))
        self.assertEqual(enemystats.damage_points(person, 6), 55)

    def test_damage_edits_in_points(self):
        e = enemystats.edit
        self.assertEqual(e('dmg', (100, 0), ('add', 20), WOLF, 6), (125, 0))
        self.assertEqual(e('dmg', (100, 0), ('set', 120), WOLF, 6), (150, 0))
        self.assertEqual(e('dmg', (120, 0), ('pctset', 90), WOLF, 6), (90, 0))
        self.assertEqual(e('dmg', (100, 0), ('pct', 10), WOLF, 6), (110, 0))
        self.assertEqual(enemystats.parse_dmg('150%'), ('pctset', 150))
        self.assertEqual(enemystats.parse_dmg('+10%'), ('pct', 10))
        self.assertEqual(enemystats.parse_dmg('120'), ('set', 120))

    def test_strike_columns(self):
        c = enemystats.strike_column
        self.assertEqual(c([701, 741, 728]), (1.0, 40.0))
        self.assertEqual(c([451, -466, -477, 499, 480]), (1.0, 48.0))
        blows, frames = c([16, 37, 34, 49, 44, 59, 54, 82, 65])
        self.assertAlmostEqual(blows, 1 + .85 + .85 * .6 + .85 * .6 * .3)
        self.assertAlmostEqual(frames, 21 + .85 * 12 + .51 * 10 + .153 * 23)
        self.assertIsNone(c([0]))
        self.assertIsNone(c([]))

    def test_blows_a_minute(self):
        self.assertEqual(enemystats.pause_avg(60), 60)
        self.assertEqual(enemystats.pause_avg(35), 69.5)
        # level 1 strikes with the first column only, 2 and up with both
        self.assertAlmostEqual(enemystats.strike_rates(WOLF, 1, 60)[0],
                               1800 / 100)
        self.assertAlmostEqual(enemystats.strike_rates(WOLF, 6, 60)[0],
                               1800 / 101.5)

    def test_speed_sets_the_pause(self):
        d = enemystats.speed_edit(WOLF, 6, 60, ('pct', 25))
        self.assertEqual(d, 40)
        rate = enemystats.strike_rates(WOLF, 6, d)[0]
        self.assertAlmostEqual(rate, 1800 / 101.5 * 1.25, delta=1)
        # a pause with a random part keeps it (last digit 5 to 9)
        d = enemystats.speed_edit(dict(WOLF, strike=35), 6, 35, ('pct', -20))
        self.assertGreater(d % 10, 4)
        # faster than the animation allows: the shortest pause
        self.assertEqual(enemystats.speed_edit(WOLF, 6, 60, ('set', 500)), 1)
        self.assertIsNone(enemystats.speed_edit(dict(WOLF, sets=[]), 6, 60,
                                                ('set', 20)))


def _game():
    g = data.find_game_dir()
    return g if g and rpgcompute.game_script(g) else None


@unittest.skipIf(_game() is None, 'needs the game')
class Game(unittest.TestCase):
    def test_template_fits_this_game(self):
        self.assertEqual(rpgcompute.usable(_game()), 'ok')

    def test_par_gives_weapons_and_strikes(self):
        src = enemystats.base_par_source(_game(), own=enemylevel.MOD_NAME)
        base = enemystats.read_base(enemystats.load_par(src[0], src[1]),
                                    enemystats.units())
        own = [u for u, b in base.items() if b['weapon'] is not None]
        strikes = [u for u, b in base.items() if b['sets']]
        self.assertGreater(len(own), 100)          # animals and monsters
        self.assertGreater(len(strikes), len(base) - 5)
        people = [b for b in base.values() if b['weapon'] is None]
        # people strike with one set per kind of weapon
        self.assertTrue(any(len(b['sets']) > 1 for b in people))


if __name__ == '__main__':
    unittest.main()
