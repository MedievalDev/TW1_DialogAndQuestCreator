"""Quest limit 400 -> 600 (questlimit.py) and how the editor uses it."""

import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tw1_wd  # noqa: E402
from questforge2 import data, questlimit, validate  # noqa: E402
from questforge2.tests.test_quest_export import _Index, make_quest  # noqa: E402

MOV = b'\xb8'
CMP = b'\x3d'


def fake_body(limit=400, movs=29, cmps=12, offsets=47):
    """ECO body with the immediates of eQuestsNum and [esi+0x190] offsets
    (8B 86 <imm32>), which must stay untouched."""
    imm = struct.pack('<I', limit)
    parts = [b'ECO\x00' + b'\x90' * 60]
    parts += [MOV + imm + b'\x90' * 7] * movs
    parts += [CMP + imm + b'\x90' * 5] * cmps
    parts += [b'\x8b\x86' + struct.pack('<I', 400) + b'\x90' * 3] * offsets
    return b''.join(parts)


class Patch(unittest.TestCase):
    def test_sites_and_limit(self):
        body = fake_body()
        self.assertEqual(len(questlimit.find_sites(body)), 41)
        self.assertEqual(questlimit.limit_of(body), 400)
        patched, n, verified = questlimit.patch_body(body)
        self.assertEqual(n, 41)
        self.assertFalse(verified)                  # not the retail hash
        self.assertEqual(len(patched), len(body))
        self.assertEqual(questlimit.limit_of(patched), 600)
        # offsets stay 400
        self.assertEqual(patched.count(b'\x8b\x86' + struct.pack('<I', 400)),
                         47)
        self.assertEqual(questlimit.find_sites(patched), [])

    def test_no_sites(self):
        with self.assertRaises(ValueError):
            questlimit.patch_body(b'ECO\x00' + b'\x90' * 100)

    def test_archive_roundtrip(self):
        body = fake_body(600)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'QuestLimit600.wd')
            guid = questlimit.build_wd(body, path)
            e = questlimit.wd_entries(path)
            self.assertEqual(len(e), 1)
            self.assertEqual(e[0]['path'], questlimit.INNER)
            self.assertEqual((e[0]['flags'], e[0]['res'], e[0]['id'],
                              e[0]['guid']),
                             (questlimit.ENTRY_FLAGS, questlimit.ENTRY_RES,
                              questlimit.ENTRY_ID, guid))
            self.assertEqual(questlimit.eco_body(
                questlimit.wd_read_file(path, e[0])), body)
            # the repo's reader agrees
            ents = list(tw1_wd.read(path))
            self.assertEqual(ents[0].data, body)
            # a second archive gets a fresh GUID
            other = questlimit.build_wd(body, os.path.join(d, 'b.wd'))
            self.assertNotEqual(guid, other)


class GameDir(unittest.TestCase):
    """apply / remove / State on a fake game folder; the registry is
    replaced by a dict so the real mod switches stay untouched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = self.tmp.name
        os.makedirs(os.path.join(self.game, 'WDFiles'))
        os.makedirs(os.path.join(self.game, 'Mods'))
        self.src_guid = questlimit.build_wd(
            fake_body(400), os.path.join(self.game, 'WDFiles', 'Update16.wd'))
        self.reg = {}
        self._saved = (questlimit.reg_mods, questlimit.reg_set,
                       questlimit.reg_backup)
        questlimit.reg_mods = lambda: dict(self.reg)
        questlimit.reg_set = lambda name, v: self.reg.__setitem__(name, v)
        questlimit.reg_backup = lambda: None

    def tearDown(self):
        (questlimit.reg_mods, questlimit.reg_set,
         questlimit.reg_backup) = self._saved
        self.tmp.cleanup()

    def test_apply_and_remove(self):
        st = questlimit.State(self.game)
        self.assertIsNone(st.error)
        self.assertEqual(st.effective, 400)
        self.assertFalse(st.source_verified)
        logs = []
        self.assertEqual(questlimit.apply(self.game, logs.append), 41)
        mod = os.path.join(self.game, 'Mods', questlimit.MOD_NAME)
        self.assertTrue(os.path.isfile(mod))
        self.assertEqual(self.reg[questlimit.MOD_NAME], 1)
        entry = questlimit.pquests_in(mod)
        self.assertNotEqual(entry['guid'], self.src_guid)
        st = questlimit.State(self.game)
        self.assertEqual((st.mod_present, st.mod_active, st.mod_limit),
                         (True, True, 600))
        self.assertEqual(st.effective, 600)
        self.assertEqual(questlimit.effective_limit(self.game), 600)
        self.assertIn('written', [m[0] for m in logs])
        # switched off: back to 400 although the file is there
        self.reg[questlimit.MOD_NAME] = 0
        self.assertEqual(questlimit.State(self.game).effective, 400)
        # applying again keeps the old file as a backup
        self.reg[questlimit.MOD_NAME] = 1
        questlimit.apply(self.game, logs.append)
        self.assertIn('oldmod', [m[0] for m in logs])
        questlimit.remove(self.game, logs.append)
        self.assertFalse(os.path.exists(mod))
        self.assertEqual(self.reg[questlimit.MOD_NAME], 0)
        self.assertEqual(questlimit.State(self.game).effective, 400)

    def test_other_mod_with_limit(self):
        # e.g. QuestMigrate.wd: its own quest script with 600
        questlimit.build_wd(fake_body(600),
                            os.path.join(self.game, 'Mods', 'Other.wd'))
        self.assertEqual(questlimit.State(self.game).effective, 400)
        self.reg['Other.wd'] = 1
        st = questlimit.State(self.game)
        self.assertEqual(st.others, [('Other.wd', 600, True)])
        self.assertEqual(st.effective, 600)
        self.assertEqual(st.effective_source, 'Other.wd')

    def test_missing_game_parts(self):
        self.assertEqual(questlimit.effective_limit(None), 400)
        with tempfile.TemporaryDirectory() as d:
            st = questlimit.State(d)
            self.assertEqual(st.error, 'nosource')
            self.assertEqual(questlimit.effective_limit(d), 400)


class EditorUse(unittest.TestCase):
    def test_max_id_and_free_ids(self):
        self.assertEqual(data.max_quest_id(), 399)
        self.assertEqual(data.max_quest_id(400), 399)
        self.assertEqual(data.max_quest_id(600), 599)
        idx = data.Index({'quests': {'381': {}}, 'npcs': {}, 'groups': {},
                          'locations': {}, 'objects': {}, 'tiles': [],
                          'markers': {}, 'cues': {}, 'lectors': {}})
        self.assertEqual(idx.free_ids()[0], 382)
        self.assertEqual(idx.free_ids()[-1], 399)
        idx.quest_limit = 600
        self.assertEqual(idx.free_ids()[-1], 599)
        self.assertEqual(len(idx.free_ids()), 599 - 381)

    def _keys(self, qid, limit):
        idx = _Index()
        idx.quest_limit = limit
        E, W = validate.validate_quest(make_quest(qid), idx)
        return ' '.join(m for m, _ in E), ' '.join(m for m, _ in W)

    def test_validation(self):
        e, w = self._keys(390, 400)
        self.assertNotIn('val.id', e)
        self.assertNotIn('warn.id.limit600', w)
        e, w = self._keys(450, 400)
        self.assertIn('val.id.limit', e)
        e, w = self._keys(450, 600)
        self.assertNotIn('val.id', e)
        self.assertIn('warn.id.limit600', w)
        e, w = self._keys(600, 600)
        self.assertIn('val.id.limit', e)
        e, w = self._keys(380, 600)
        self.assertIn('val.id.range', e)


if __name__ == '__main__':
    unittest.main()
