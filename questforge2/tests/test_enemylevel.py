"""Enemy levels: finding the table, patching, the mod archive (2.6.0)."""

import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import enemylevel, questlimit  # noqa: E402


def fake_script(values=None):
    """A body that carries the level table the way the compiled script does:
    every IL call pushes its arguments right to left as 32 bit immediates."""
    values = values or enemylevel.retail_values()
    out = bytearray(b'ECO\x00' + b'\x90' * 40)
    for num, _name, mark, lo, hi, _grp in enemylevel.ENTRIES:
        cur = values.get(num, (lo, hi))
        args = [cur[1], cur[0], mark, num] if mark else [cur[1], cur[0], num]
        for a in args:
            out += b'\xb8' + struct.pack('<I', a)
            out += b'\x90' * 3          # some code between the pushes
        out += b'\xe8' + b'\x00' * 4    # call
    out += b'\x90' * 20
    return bytes(out)


class Table(unittest.TestCase):
    def test_entries(self):
        self.assertEqual(len(enemylevel.ENTRIES), 90)
        self.assertEqual(enemylevel.entry(11)[1], 'Bandit')
        self.assertEqual(enemylevel.retail_values()[1], (6, 10))   # grey wolf
        self.assertEqual(enemylevel.retail_values()[31], (40, 100))  # dragon
        groups = {e[5] for e in enemylevel.ENTRIES}
        self.assertTrue(groups <= set(enemylevel.GROUPS))

    def test_locate_and_read(self):
        body = fake_script()
        found = enemylevel.locate(body)
        self.assertEqual(len(found), 90)
        self.assertEqual([f[0] for f in found],
                         [e[0] for e in enemylevel.ENTRIES])
        self.assertEqual(enemylevel.read_levels(body),
                         enemylevel.retail_values())

    def test_patch(self):
        body = fake_script()
        values = dict(enemylevel.retail_values())
        values[1] = (20, 60)            # grey wolf
        patched, n = enemylevel.patch_body(body, values)
        self.assertEqual(n, 90)
        self.assertEqual(len(patched), len(body))
        self.assertEqual(enemylevel.read_levels(patched)[1], (20, 60))
        # everything else untouched
        rest = enemylevel.read_levels(patched)
        del rest[1]
        ref = enemylevel.retail_values()
        del ref[1]
        self.assertEqual(rest, ref)

    def test_patch_clamps(self):
        body = fake_script()
        values = {1: (0, 500), 2: (80, 5)}
        patched, _ = enemylevel.patch_body(body, values)
        read = enemylevel.read_levels(patched)
        self.assertEqual(read[1], (enemylevel.MIN_LEVEL, enemylevel.MAX_LEVEL))
        self.assertEqual(read[2], (80, 80))     # max pulled up to the minimum

    def test_unknown_script(self):
        with self.assertRaises(ValueError):
            enemylevel.locate(b'ECO\x00' + b'\x90' * 200)


class Presets(unittest.TestCase):
    def test_presets(self):
        v = enemylevel.retail_values()
        hero = enemylevel.preset_follow_hero(v)
        self.assertEqual(hero[1], (1, 100))
        plus = enemylevel.preset_add(v, 10, {1})
        self.assertEqual(plus[1], (16, 20))
        self.assertEqual(plus[2], v[2])          # other types untouched
        scale = enemylevel.preset_scale(v, 2.0, {1})
        self.assertEqual(scale[1], (12, 20))
        self.assertEqual(enemylevel.preset_retail(scale, {1})[1], v[1])
        # the ceiling holds
        self.assertEqual(enemylevel.preset_add(v, 90, {31})[31], (100, 100))


class Mod(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = self.tmp.name
        os.makedirs(os.path.join(self.game, 'WDFiles'))
        os.makedirs(os.path.join(self.game, 'Mods'))
        body = fake_script()
        blobs = [(inner, body, b'Enemies Script')
                 for inner in enemylevel.INNER]
        enemylevel.build_mod_archive(
            os.path.join(self.game, 'WDFiles', 'Update16.wd'), blobs)
        self.reg = {}
        self._saved = (questlimit.reg_mods, questlimit.reg_set,
                       questlimit.reg_backup)
        questlimit.reg_mods = lambda: dict(self.reg)
        questlimit.reg_set = lambda n, v: self.reg.__setitem__(n, v)
        questlimit.reg_backup = lambda: None
        enemylevel.reg_mods = questlimit.reg_mods
        enemylevel.reg_set = questlimit.reg_set
        enemylevel.reg_backup = questlimit.reg_backup

    def tearDown(self):
        (questlimit.reg_mods, questlimit.reg_set,
         questlimit.reg_backup) = self._saved
        enemylevel.reg_mods = questlimit.reg_mods
        enemylevel.reg_set = questlimit.reg_set
        enemylevel.reg_backup = questlimit.reg_backup
        self.tmp.cleanup()

    def test_apply_and_remove(self):
        st = enemylevel.State(self.game)
        self.assertIsNone(st.error)
        self.assertEqual(len(st.sources), 2)
        self.assertFalse(st.changed)
        values = dict(st.values)
        values[1] = (30, 60)
        logs = []
        self.assertEqual(enemylevel.apply(self.game, values, logs.append), 2)
        mod = os.path.join(self.game, 'Mods', enemylevel.MOD_NAME)
        self.assertTrue(os.path.isfile(mod))
        self.assertEqual(self.reg[enemylevel.MOD_NAME], 1)
        ents = {e['path']: e for e in questlimit.wd_entries(mod)}
        self.assertEqual(set(ents), set(enemylevel.INNER))
        guids = {e['guid'] for e in ents.values()}
        self.assertEqual(len(guids), 2)          # a fresh GUID per entry
        src = {e['guid'] for e in questlimit.wd_entries(
            os.path.join(self.game, 'WDFiles', 'Update16.wd'))}
        self.assertFalse(guids & src)
        for e in ents.values():
            self.assertEqual((e['flags'], e['id']),
                             (questlimit.ENTRY_FLAGS, questlimit.ENTRY_ID))
        st = enemylevel.State(self.game)
        self.assertEqual(st.values[1], (30, 60))
        self.assertTrue(st.changed)
        self.assertTrue(st.mod_present and st.mod_active)
        # switched off: the original values count again
        self.reg[enemylevel.MOD_NAME] = 0
        self.assertEqual(enemylevel.State(self.game).values[1],
                         enemylevel.retail_values()[1])
        self.reg[enemylevel.MOD_NAME] = 1
        enemylevel.remove(self.game, logs.append)
        self.assertFalse(os.path.exists(mod))
        self.assertEqual(self.reg[enemylevel.MOD_NAME], 0)
        self.assertFalse(enemylevel.State(self.game).changed)

    def test_other_mod_seen(self):
        body = fake_script()
        enemylevel.build_mod_archive(
            os.path.join(self.game, 'Mods', 'Other.wd'),
            [(enemylevel.INNER[0], body, b'Enemies Script')])
        self.reg['Other.wd'] = 1
        self.assertEqual(enemylevel.State(self.game).others,
                         [('Other.wd', True)])


if __name__ == '__main__':
    unittest.main()
