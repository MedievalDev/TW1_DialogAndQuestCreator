"""Mods as a third source (update 5b): reading, tile check, dependencies,
writing a quest back into a mod with backup and metadata check."""

import datetime
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tw1_lan  # noqa: E402
import tw1_wd  # noqa: E402
from questforge2 import export, mods, retail  # noqa: E402
from questforge2.model import Project, Quest  # noqa: E402
from questforge2.tests.test_quest_export import (  # noqa: E402
    QTX, _Index, make_quest)

BS = chr(92)
GUID_A = bytes(range(16))
GUID_B = bytes(range(16, 32))


def lnd_body(markers):
    """Minimal map body: header up to the marker section, markers, rest."""
    out = b'LN' + bytes(2)
    out += struct.pack('<I', 3) + 'Map'.encode('utf-16-le')
    out += bytes(20)
    for _ in range(6):
        out += struct.pack('<I', 0)
    out += struct.pack('<II', len(markers), 0)
    for name, ident, x, y, z, angle in markers:
        raw = name.encode('latin-1')
        out += struct.pack('<I', len(raw)) + raw
        out += struct.pack('<Iiii', ident, x, y, z) + bytes([angle]) + bytes(8)
    return out + b'terrain' * 50


def lnd_entry(inner, markers, guid=GUID_A):
    return tw1_wd.Entry(inner, lnd_body(markers), 0x33, b'', 20044, guid)


RETAIL_H6 = [('MARKER_QUEST_TELEPORT', 1, 100, 200, 300, 0),
             ('MARKER_CHEST', 1, 10, 20, 30, 64)]
MOD_QTX = QTX.replace('FC TALK NPC_5\n  REWARD', 'FC TALK NPC_7\n  REWARD') \
    + 'QUEST Q_398 1 3 (null) 0 True\n  FC TALK NPC_5\nEND\n' \
    + 'LOCATION LOC_NEW 1 2 H6 300 10\n'


def pack(path, files):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    export.pack_archive(path, files, log=lambda m: None, backup=False)


def game_with_levels(d):
    """A fake game folder whose Levels.wd has the retail H6 map."""
    game = os.path.join(d, 'game')
    pack(os.path.join(game, 'WDFiles', 'Levels.wd'), {
        'Levels' + BS + 'Map_H06.lnd': lnd_entry(
            'Levels' + BS + 'Map_H06.lnd', RETAIL_H6, GUID_B)})
    return game


def mod_files(markers, qtx=MOD_QTX):
    lan = tw1_lan.build({'translateQ_398': 'Neue Modquest',
                         'translateQ_4': 'Alt'}, [], tw1_lan.build_trees([]))
    return {export.INNER_QTX: qtx.encode('latin-1'),
            'Language' + BS + 'TwoWorldsQuests.lan': lan,
            'Levels' + BS + 'Map_H06.lnd': lnd_entry(
                'Levels' + BS + 'Map_H06.lnd', markers),
            'Parameters' + BS + 'Keep.txt': b'keep me' + bytes([10])}


class Tiles(unittest.TestCase):
    def test_names(self):
        self.assertEqual(mods.tile_of_lnd('Levels' + BS + 'Map_E01.lnd'), 'E1')
        self.assertEqual(mods.tile_of_lnd('Levels' + BS + 'Map_B08_1.lnd'),
                         'B8_1')
        self.assertIsNone(mods.tile_of_lnd('Levels' + BS + 'Net_M_20.lnd'))
        self.assertEqual(mods.lnd_of_tile('F12_1'),
                         'Levels' + BS + 'Map_F12_1.lnd')

    def test_marker_names_cover_index_kinds(self):
        from questforge2 import data
        kinds = {s[0] for s in list(data._FC_MARKERS.values())
                 + list(data._ACTION_MARKERS.values())}
        self.assertEqual(kinds, set(mods.MARKER_NAMES))


class ReadMods(unittest.TestCase):
    def test_retail_markers_and_scan(self):
        with tempfile.TemporaryDirectory() as d:
            game = game_with_levels(d)
            old_root = mods.data.ROOT
            mods.data.ROOT = d
            try:
                tiles = mods.retail_markers(game)
                self.assertEqual(mods.marker_ids(tiles['H6'],
                                                 'MARKER_QUEST_TELEPORT'), {1})
                arch = os.path.join(d, 'Mods', 'Other.wd')
                # the mod dropped the retail chest and added teleport 19
                pack(arch, mod_files([('MARKER_QUEST_TELEPORT', 1, 1, 2, 3, 0),
                                      ('MARKER_QUEST_TELEPORT', 19, 4, 5, 6,
                                       0)]))
                base = mods.qtx_parts(QTX)
                info = mods.load_mod(arch, base, tiles)
                self.assertIsNone(info['error'])
                self.assertEqual(info['quests']['4']['state'], 'changed')
                self.assertEqual(info['quests']['398']['state'], 'new')
                self.assertEqual(info['quests']['398']['title'],
                                 'Neue Modquest')
                self.assertNotIn('12', info['quests'])
                self.assertEqual(info['locations']['LOC_NEW']['tile'], 'H6')
                h6 = info['tiles']['H6']
                self.assertEqual(h6['missing'], [['MARKER_CHEST', 1]])
                self.assertTrue(os.path.isfile(mods._cache_file(arch)))
                # second load comes from the cache
                again = mods.load_mod(arch, base, tiles)
                self.assertEqual(again['quests'], info['quests'])
            finally:
                mods.data.ROOT = old_root


class Dependencies(unittest.TestCase):
    def _set(self, *mod_markers, choice=None):
        retail_tiles = {'H6': {'markers': mods._plain_markers(
            {'MARKER_QUEST_TELEPORT': [(1, (0, 0, 0, 0))],
             'MARKER_CHEST': [(1, (0, 0, 0, 0))]})}}
        infos, entries = [], []
        for i, marks in enumerate(mod_markers):
            rec = {'inner': 'Levels' + BS + 'Map_H06.lnd',
                   'markers': mods._plain_markers(marks)}
            rec['missing'] = mods.missing_markers(retail_tiles['H6'], rec)
            infos.append({'name': f'M{i}.wd', 'path': f'M{i}.wd',
                          'quests': {}, 'tiles': {'H6': rec}, 'error': None})
            entries.append({'path': f'M{i}.wd', 'enabled': True})
        return mods.ModSet(entries, infos, retail_tiles, choice or {})

    def test_marker_only_in_mod(self):
        p = Project('P')
        p.quests.append(make_quest())      # NPC_TELEPORT marker 19 on H6
        full = {'MARKER_QUEST_TELEPORT': [(1, (0, 0, 0, 0)),
                                          (19, (0, 0, 0, 0))],
                'MARKER_CHEST': [(1, (0, 0, 0, 0))]}
        deps = mods.dependencies(p, self._set(full))
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]['status'], 'ok')
        self.assertEqual(deps[0]['mod'], 'M0.wd')
        self.assertEqual(deps[0]['uses'], [(390, 'Q_Action_Teleport', 19)])
        rows = self._set(full).marker_rows('Q_Action_Teleport', 'H6')
        self.assertEqual([(r[0], r[2] and r[2]['name']) for r in rows],
                         [(1, None), (19, 'M0.wd')])

    def test_red_tile_and_conflict(self):
        p = Project('P')
        p.quests.append(make_quest())
        red = {'MARKER_QUEST_TELEPORT': [(19, (0, 0, 0, 0))]}
        deps = mods.dependencies(p, self._set(red))
        self.assertEqual(deps[0]['status'], 'missing')
        self.assertIn(['MARKER_CHEST', 1], deps[0]['missing'])
        full = {'MARKER_QUEST_TELEPORT': [(1, (0, 0, 0, 0)),
                                          (19, (0, 0, 0, 0))],
                'MARKER_CHEST': [(1, (0, 0, 0, 0))]}
        two = self._set(full, full)
        self.assertEqual(mods.dependencies(p, two)[0]['status'], 'conflict')
        self.assertEqual(two.tile_conflicts(), {'H6': ['M0.wd', 'M1.wd']})
        chosen = self._set(full, full, choice={'H6': 'M1.wd'})
        dep = mods.dependencies(p, chosen)[0]
        self.assertEqual((dep['status'], dep['mod']), ('ok', 'M1.wd'))

    def test_no_dependency_for_retail_marker(self):
        p = Project('P')
        q = make_quest()
        for n in q.graph['nodes'].values():
            if n.get('verb') == 'NPC_TELEPORT':
                n['args']['marker'] = 1
        p.quests.append(q)
        full = {'MARKER_QUEST_TELEPORT': [(1, (0, 0, 0, 0))]}
        self.assertEqual(mods.dependencies(p, self._set(full)), [])


class WriteMod(unittest.TestCase):
    def _quest_from(self, arch):
        text, _lans = mods.quest_sources(arch)
        block = mods.qtx_parts(text)['quests'][398]
        q = Quest(398, 'Neue Modquest')
        retail.import_block(q, block)
        return q

    def test_write_into_archive(self):
        with tempfile.TemporaryDirectory() as d:
            game = game_with_levels(d)
            arch = os.path.join(d, 'Mods', 'Other.wd')
            pack(arch, mod_files(RETAIL_H6))
            before = {e.path: e.meta() for e in mods.wd_directory(arch)}
            template = mods.metadata_template(game)
            self.assertEqual(mods.metadata_problems(arch, template), [])
            q = self._quest_from(arch)
            q.title = 'Umbenannt'
            master = tw1_lan.build({}, [], tw1_lan.build_trees([]))
            logs = []
            day = datetime.date(2026, 9, 16)
            res = mods.write_quest(arch, q, _Index(), master, game,
                                   logs.append, today=day)
            self.assertEqual(res['backup'], arch + '.bak-2026-09-16')
            self.assertTrue(os.path.isfile(res['backup']))
            self.assertEqual(mods.list_backups(arch), [res['backup']])
            after = {e.path: e.meta() for e in mods.wd_directory(arch)}
            for inner in ('Levels' + BS + 'Map_H06.lnd',
                          'Parameters' + BS + 'Keep.txt'):
                self.assertEqual(after[inner], before[inner])
            ents = {e.path: e.data for e in tw1_wd.read(arch)}
            tr = tw1_lan.read(ents['Language' + BS + 'TwoWorldsQuests.lan'])[0]
            self.assertEqual(tr['translateQ_398'], 'Umbenannt')
            self.assertEqual(ents[export.INNER_QTX].count(b'QUEST Q_398 '), 1)
            self.assertEqual(mods.metadata_problems(arch, template), [])
            # a second write the same day keeps the first backup
            q.title = 'Noch einmal'
            res2 = mods.write_quest(arch, q, _Index(), master, game,
                                    logs.append, today=day)
            self.assertIsNone(res2['backup'])
            # restore brings the state before the first write back
            keep = mods.restore_backup(arch, res['backup'])
            self.assertTrue(os.path.isfile(keep))
            ents = {e.path: e.data for e in tw1_wd.read(arch)}
            tr = tw1_lan.read(ents['Language' + BS + 'TwoWorldsQuests.lan'])[0]
            self.assertEqual(tr['translateQ_398'], 'Neue Modquest')

    def test_write_into_folder(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, 'FolderMod')
            files = mod_files(RETAIL_H6)
            for inner, blob in files.items():
                dest = os.path.join(folder, *inner.split(BS))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as f:
                    f.write(export.staged_blob(blob)
                            if isinstance(blob, tw1_wd.Entry) else blob)
            q = self._quest_from(folder)
            q.title = 'Ordner'
            master = tw1_lan.build({}, [], tw1_lan.build_trees([]))
            res = mods.write_quest(folder, q, _Index(), master, None,
                                   lambda m: None,
                                   today=datetime.date(2026, 9, 16))
            self.assertTrue(os.path.isfile(os.path.join(
                res['backup'], 'Scripts', 'Quests', 'TwoWorldsQuests.qtx')))
            got = mods.read_files(folder)
            tr = tw1_lan.read(got['Language' + BS + 'TwoWorldsQuests.lan'])[0]
            self.assertEqual(tr['translateQ_398'], 'Ordner')
            # the staged map keeps its metadata header
            flags, _res, class_id, guid, body = mods.file_entry(open(
                os.path.join(folder, 'Levels', 'Map_H06.lnd'), 'rb').read())
            self.assertEqual((flags, class_id, guid), (0x33, 20044, GUID_A))

    def test_dependency_entries_packed_with_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            arch = os.path.join(d, 'Mods', 'Other.wd')
            marks = RETAIL_H6 + [('MARKER_QUEST_TELEPORT', 19, 1, 1, 1, 0)]
            pack(arch, mod_files(marks))
            deps = [{'status': 'ok', 'path': arch, 'mod': 'Other.wd',
                     'inner': 'Levels' + BS + 'Map_H06.lnd'}]
            entries = mods.dependency_entries(deps, lambda m: None)
            target = os.path.join(d, 'Mods', 'Own.wd')
            pack(target, entries)
            got = {e.path: e for e in mods.wd_directory(target)}
            e = got['Levels' + BS + 'Map_H06.lnd']
            self.assertEqual((e.flags, e.class_id, e.guid),
                             (0x33, 20044, GUID_A))
            self.assertEqual(mods.wd_data(target, e), lnd_body(marks))


class ProjectFile(unittest.TestCase):
    def test_mods_round_trip(self):
        p = Project('P')
        plain = p.to_json()
        self.assertNotIn('"mods"', plain)
        p.mods = [{'path': 'C:/x/A.wd', 'enabled': False}]
        p.mod_tiles = {'H6': 'A.wd'}
        again = Project.from_json(p.to_json())
        self.assertEqual(again.mods, p.mods)
        self.assertEqual(again.mod_tiles, p.mod_tiles)
        self.assertEqual(again.to_json(), p.to_json())

    def test_old_project_saves_identical(self):
        """A quest without links (projects before 2.8.0) keeps its bytes."""
        p = Project('Old')
        p.quests.append(make_quest())
        text = p.to_json()
        self.assertNotIn('"links"', text)
        self.assertEqual(Project.from_json(text).to_json(), text)
        q = p.quests[0]
        snap = q.snapshot()
        q.links.append({'type': 'TAKE', 'event': 'TAKE', 'quest': 4})
        self.assertIn('"links"', p.to_json())
        q.restore(snap)
        self.assertEqual(q.links, [])


if __name__ == '__main__':
    unittest.main()
