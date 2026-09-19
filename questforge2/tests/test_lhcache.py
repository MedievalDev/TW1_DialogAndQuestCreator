"""The level header cache written by the tool (lhcache.py). The winner of
every case below was measured with the SDK's MeshParamsGen.exe on the same
layout (2026-09-19); there the tool's file was byte for byte the SDK's."""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import tw1_lnd  # noqa: E402
import tw1_wd  # noqa: E402
from questforge2 import export, lhcache, mods, placed  # noqa: E402
from questforge2.tests.test_placed import body  # noqa: E402

BS = chr(92)
ON = ('Minimap.wd', 'Yamalin.wd', 'ShaderFix.wd', 'QuestLimit600.wd')


def _map(tag):
    return body([('MARKER_WHO_' + tag, 1, 5, 5, 5, 0)])


class Rules(unittest.TestCase):
    def setUp(self):
        self.game = tempfile.mkdtemp(prefix='qf2lhc_')
        for sub in ('WDFiles', 'Mods'):
            os.makedirs(os.path.join(self.game, sub))

    def tearDown(self):
        shutil.rmtree(self.game, ignore_errors=True)

    def pack(self, rel, tiles):
        files = {}
        for tile, tag in tiles.items():
            inner = mods.lnd_of_tile(tile)
            files[inner] = tw1_wd.Entry(inner, _map(tag), flags=0x33,
                                        extra_int=20044, guid=b'G' * 16)
        export.pack_archive(os.path.join(self.game, *rel.split('/')), files,
                            log=lambda *a: None, backup=False)

    def winners(self):
        blob, used = lhcache.build(self.game, ON)
        out = {}
        for path, head in lhcache.parse(blob).items():
            names = tw1_lnd.markers(head + bytes(64))
            out[path.split(BS)[1]] = [n[11:] for n in names
                                      if n.startswith('MARKER_WHO_')]
        return out, blob, used

    def test_mods_first_in_alphabet_wins(self):
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL', 'A2': 'RETAIL',
                                        'A3': 'RETAIL'})
        self.pack('Mods/Minimap.wd', {'A1': 'MINIMAP'})
        self.pack('Mods/Yamalin.wd', {'A1': 'YAMALIN'})
        self.pack('Mods/ShaderFix.wd', {'A1': 'SHADER', 'A2': 'SHADER'})
        self.pack('Mods/QuestLimit600.wd', {'A2': 'QLIMIT'})
        self.pack('Mods/SwitchedOff.wd', {'A3': 'OFF'})     # not in ON
        won, blob, used = self.winners()
        self.assertEqual(won, {'Map_A01.lnd': ['MINIMAP'],
                               'Map_A02.lnd': ['QLIMIT'],
                               'Map_A03.lnd': ['RETAIL']})
        self.assertEqual(blob[:12], b'LC' + bytes(2) + bytes([3, 0, 0, 0])
                         + bytes(4))
        self.assertEqual([os.path.basename(f) for _p, f in used],
                         ['Minimap.wd', 'QuestLimit600.wd', 'Levels.wd'])

    def test_wdfiles_first_in_alphabet_wins(self):
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL', 'A2': 'RETAIL'})
        self.pack('WDFiles/Graphics.wd', {'A1': 'GRAPHICS'})
        self.pack('WDFiles/Update16.wd', {'A2': 'UPDATE'})
        self.assertEqual(self.winners()[0], {'Map_A01.lnd': ['GRAPHICS'],
                                             'Map_A02.lnd': ['RETAIL']})

    def test_loose_file_beats_everything(self):
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL', 'A2': 'RETAIL'})
        self.pack('Mods/Minimap.wd', {'A1': 'MINIMAP'})
        os.makedirs(os.path.join(self.game, 'Levels', 'physic'))
        with open(os.path.join(self.game, 'Levels', 'Map_A02.lnd'),
                  'wb') as f:
            f.write(placed.editor_file(_map('LOOSE'), b'L' * 16))
        with open(os.path.join(self.game, 'Levels', 'readme.txt'), 'wb') as f:
            f.write(b'x')
        self.assertEqual(self.winners()[0], {'Map_A01.lnd': ['MINIMAP'],
                                             'Map_A02.lnd': ['LOOSE']})

    def test_head_is_the_body_head(self):
        self.pack('WDFiles/Levels.wd', {'B12': 'RETAIL'})
        blob, _used = lhcache.build(self.game, ())
        full = _map('RETAIL')
        _s, end = tw1_lnd._marker_section(full)
        path = ('Levels' + BS + 'Map_B12.lnd').encode()
        self.assertEqual(blob, b'LC' + bytes(2) + bytes([1, 0, 0, 0])
                         + bytes(4) + bytes([len(path), 0, 0, 0]) + path
                         + full[:end])

    def test_write_and_backup(self):
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL'})
        target = os.path.join(self.game, lhcache.LHC_FILE)
        ok, n, _text = lhcache.write(self.game, ())
        self.assertEqual((ok, n), (True, 1))
        self.assertFalse(os.path.exists(target + '.qf2backup'))
        first = open(target, 'rb').read()
        self.pack('Mods/Minimap.wd', {'A1': 'MINIMAP', 'A2': 'MINIMAP'})
        ok, n, _text = lhcache.write(self.game, ON)
        self.assertEqual((ok, n), (True, 2))
        with open(target + '.qf2backup', 'rb') as f:
            self.assertEqual(f.read(), first)       # kept once
        lhcache.write(self.game, ())
        with open(target + '.qf2backup', 'rb') as f:
            self.assertEqual(f.read(), first)

    def test_nothing_there(self):
        ok, n, text = lhcache.write(self.game, ())
        self.assertEqual((ok, n, text), (False, None, 'no maps found'))
        with self.assertRaises(ValueError):
            lhcache.parse(b'XX' + bytes(10))

    def test_overruled(self):
        mine = os.path.join(self.game, 'Mods', 'Zebra.wd')
        used = [('Levels' + BS + 'Map_A01.lnd',
                 os.path.join(self.game, 'Mods', 'Alpha.wd')),
                ('Levels' + BS + 'Map_A02.lnd', mine),
                ('Levels' + BS + 'Map_A03.lnd',
                 os.path.join(self.game, 'WDFiles', 'Levels.wd'))]
        inners = ['Levels' + BS + 'Map_A01.lnd', 'Levels' + BS + 'Map_A02.lnd',
                  'Levels' + BS + 'physic' + BS + 'Map_A01.phx']
        self.assertEqual(lhcache.overruled(used, mine, inners),
                         [('Levels' + BS + 'Map_A01.lnd', 'Alpha.wd')])


if __name__ == '__main__':
    unittest.main()
