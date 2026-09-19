"""Editor maps into the project (editormaps.py) and the .phx in the export."""

import os
import shutil
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from questforge2 import editormaps, mods  # noqa: E402

BS = chr(92)


def _editor_lnd(guid=b'G' * 16):
    """An editor export: metadata stream (flags 0x31, class id 20044, GUID)
    + compressed body, like Map_E01s.lnd from TwoWorldsEditorFix.exe."""
    head = bytes([0xFF, 0xA1, 0xD0, 0x31]) + (20044).to_bytes(4, 'little') + guid
    return zlib.compress(head) + zlib.compress(b'LND body')


class Names(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(editormaps.parse_name('Map_E01s.lnd'), ('E1', 'E01', 'lnd', 's'))
        self.assertEqual(editormaps.parse_name('Map_F01_1s.phx'), ('F1_1', 'F01_1', 'phx', 's'))
        self.assertEqual(editormaps.parse_name('Map_F01m.lnd'), ('F1', 'F01', 'lnd', 'm'))
        self.assertEqual(editormaps.parse_name('map_h06.LND'), ('H6', 'H06', 'lnd', ''))
        self.assertEqual(editormaps.parse_name('Map_E1s.lnd')[1], 'E01')
        self.assertIsNone(editormaps.parse_name('Map_E01s.bmp'))
        self.assertIsNone(editormaps.parse_name('TwoWorlds.par'))
        self.assertEqual(editormaps.inner_path('F01_1', 'phx'),
                         f'Levels{BS}physic{BS}Map_F01_1.phx')
        self.assertEqual(editormaps.inner_path('E01', 'lnd'), f'Levels{BS}Map_E01.lnd')


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, 'Levels')          # editor layout
        os.makedirs(os.path.join(self.src, 'physic'))
        with open(os.path.join(self.src, 'Map_E01s.lnd'), 'wb') as f:
            f.write(_editor_lnd())
        with open(os.path.join(self.src, 'physic', 'Map_E01s.phx'), 'wb') as f:
            f.write(b'PHYSICS')
        with open(os.path.join(self.src, 'Map_D08s.lnd'), 'wb') as f:
            f.write(_editor_lnd())
        with open(os.path.join(self.src, 'notes.txt'), 'w') as f:
            f.write('x')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_partner_found_and_copied(self):
        items, skipped = editormaps.plan_import([
            os.path.join(self.src, 'Map_E01s.lnd'),
            os.path.join(self.src, 'Map_D08s.lnd'),
            os.path.join(self.src, 'notes.txt')])
        self.assertEqual([r['tile'] for r in items], ['D8', 'E1'])
        e1 = items[1]
        self.assertTrue(e1['phx'].endswith(os.path.join('physic', 'Map_E01s.phx')))
        self.assertIsNone(items[0]['phx'])                 # D08 has none
        self.assertEqual(len(skipped), 1)
        dest = os.path.join(self.tmp, 'proj_levels')
        done = editormaps.import_maps(items, dest)
        self.assertEqual(sorted(x[1] for x in done), sorted([
            f'Levels{BS}Map_D08.lnd', f'Levels{BS}Map_E01.lnd',
            f'Levels{BS}physic{BS}Map_E01.phx']))
        have = {tl: (l, p) for tl, l, p, _t in editormaps.present(dest)}
        self.assertEqual(have, {'D8': (True, False), 'E1': (True, True)})

    def test_phx_alone_finds_lnd(self):
        items, _ = editormaps.plan_import([os.path.join(self.src, 'physic', 'Map_E01s.phx')])
        self.assertTrue(items[0]['lnd'].endswith('Map_E01s.lnd'))

    def test_dependency_entries_pack_phx(self):
        dest = os.path.join(self.tmp, 'proj_levels')
        items, _ = editormaps.plan_import([os.path.join(self.src, 'Map_E01s.lnd')])
        editormaps.import_maps(items, dest)
        dep = [{'status': 'ok', 'path': dest, 'inner': f'Levels{BS}Map_E01.lnd',
                'mod': 'proj_levels', 'tile': 'E1'}]
        out = mods.dependency_entries(dep, log=lambda *a: None)
        lnd = out[f'Levels{BS}Map_E01.lnd']
        self.assertEqual((lnd.flags, lnd.extra_int, lnd.guid), (0x31, 20044, b'G' * 16))
        self.assertEqual(lnd.data, b'LND body')
        phx = out[f'Levels{BS}physic{BS}Map_E01.phx']
        self.assertEqual((phx.flags, phx.data), (0x00, b'PHYSICS'))


class Ticks(unittest.TestCase):
    def test_tick_found(self):
        class Q:
            extra = {'markers_todo': [
                {'name': 'MARKER_QUEST_START', 'num': 507, 'tile': 'E1', 'done': False},
                {'name': 'MARKER_QUEST_START', 'num': 508, 'tile': 'E1', 'done': False},
                {'name': 'MARKER_QUEST_START', 'num': 1, 'tile': 'E1', 'done': False}]}
        info = {'tiles': {'E1': {'markers': {'MARKER_QUEST_START': [[507, 0.0, 0.0, 0.0]]}}}, 'error': None}
        ms = mods.ModSet([{'path': 'x', 'enabled': True}], [info],
                         {'E1': {'markers': {'MARKER_QUEST_START': [[1, 0.0, 0.0, 0.0]]}}})
        self.assertEqual(editormaps.tick_found([Q], ms), 2)
        self.assertEqual([x['done'] for x in Q.extra['markers_todo']], [True, False, True])


class Real(unittest.TestCase):
    """The editor files on this PC, if there are any (read only)."""

    def test_real_exports(self):
        lnd = os.path.join(editormaps.EDITOR_LEVELS, 'Map_E01s.lnd')
        if not os.path.isfile(lnd):
            self.skipTest('no editor export on this PC')
        items, _ = editormaps.plan_import([lnd])
        self.assertTrue(items[0]['phx'], 'physic\\Map_E01s.phx not found')
        with open(lnd, 'rb') as f:
            flags, _res, cid, guid, body = mods.file_entry(f.read())
        self.assertEqual((flags, cid), (0x31, 20044))
        self.assertTrue(body)


if __name__ == '__main__':
    unittest.main()
