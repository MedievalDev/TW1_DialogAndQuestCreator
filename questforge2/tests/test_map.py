"""Map data (update 5c): DXT1 decoding, PNG, world <-> map pixels, marker
groups, points from game maps and mods."""

import os
import struct
import sys
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import mapdata, mods  # noqa: E402


def dds_dxt1(w, h, blocks):
    head = bytearray(128)
    head[0:4] = b'DDS '
    struct.pack_into('<I', head, 4, 124)
    struct.pack_into('<II', head, 12, h, w)
    head[84:88] = b'DXT1'
    return bytes(head) + b''.join(blocks)


class Decode(unittest.TestCase):
    def test_dxt1_block(self):
        red = 0xF800            # rgb565 pure red
        blue = 0x001F
        # indices: first pixel colour 0, second colour 1, rest colour 0
        bits = 0b01 << 2
        blob = dds_dxt1(4, 4, [struct.pack('<HHI', red, blue, bits)])
        w, h, rgb = mapdata.decode_dxt1(blob)
        self.assertEqual((w, h, len(rgb)), (4, 4, 48))
        self.assertEqual(tuple(rgb[0:3]), (255, 0, 0))
        self.assertEqual(tuple(rgb[3:6]), (0, 0, 255))
        self.assertEqual(tuple(rgb[6:9]), (255, 0, 0))
        with self.assertRaises(ValueError):
            mapdata.decode_dxt1(b'DDS ' + bytes(200))

    def test_png(self):
        png = mapdata.encode_png(2, 1, bytes([1, 2, 3, 4, 5, 6]))
        self.assertTrue(png.startswith(b'\x89PNG'))
        ihdr = png.index(b'IHDR')
        self.assertEqual(struct.unpack('>II', png[ihdr + 4:ihdr + 12]),
                         (2, 1))
        idat = png.index(b'IDAT')
        n = struct.unpack('>I', png[idat - 4:idat])[0]
        raw = zlib.decompress(png[idat + 4:idat + 4 + n])
        self.assertEqual(raw, bytes([0, 1, 2, 3, 4, 5, 6]))


class Coordinates(unittest.TestCase):
    def test_world_to_map(self):
        # E is column 4, row 1 is the top row; world y grows upwards
        self.assertEqual(mapdata.world_to_map('E1', 16384, 16384, 512),
                         (2304.0, 256.0))
        self.assertEqual(mapdata.world_to_map('A2', 0, 0, 64), (0.0, 128.0))
        self.assertEqual(mapdata.world_to_map('F1_1', 0, 32768, 512),
                         (2560.0, 0.0))
        self.assertIsNone(mapdata.world_to_map('Z9', 0, 0))
        tile, x, y = mapdata.map_to_world(
            *mapdata.world_to_map('D8', 19633, 4768, 512), 512)
        self.assertEqual((tile, x, y), ('D8', 19633, 4768))
        self.assertEqual(mapdata.cells_to_world(64, 1), (16384, 256))

    def test_groups(self):
        self.assertEqual(mapdata.group_of('MARKER_QUEST_CREATE_ENEMY'),
                         'quest_enemy')
        self.assertEqual(mapdata.group_of('MARKER_ENEMY_ORC_02'), 'enemy')
        self.assertEqual(mapdata.group_of('MARKER_TELEPORT_DEST_FROMUPPER'),
                         'teleport')
        self.assertEqual(mapdata.group_of('MARKER_GUARD_ROUTE'), 'town')
        self.assertEqual(mapdata.group_of('MARKER_DUMMY'), 'unknown')
        for name in mods.MARKER_NAMES.values():
            self.assertNotEqual(mapdata.group_of(name), 'unknown', name)


class _Idx:
    def __init__(self):
        self.d = {'marker_use': {'Q_Action_Create_Enemy|H6|1': [12]}}
        self.npcs = {'3': {'tile': 'H6', 'marker': 3}}
        self.locations = {'LOC_A': {'name': 'Ort', 'x': 64, 'y': 64,
                                    'tile': 'H6', 'radius': 5, 'type': 16},
                          'LOC_0': {'name': '', 'x': 0, 'y': 0,
                                    'tile': '(null)', 'radius': -1,
                                    'type': 0}}


class Points(unittest.TestCase):
    def test_collect(self):
        retail = {'H6': {'markers': {
            'MARKER_QUEST_CREATE_ENEMY': [[1, 100, 200, 0, 0]],
            'MARKER_QUEST_START': [[3, 300, 400, 0, 0]]}}}
        mod = {'name': 'M.wd', 'tiles': {'H6': {'markers': {
            'MARKER_QUEST_CREATE_ENEMY': [[1, 100, 200, 0, 0],
                                          [2, 500, 600, 0, 0]]},
            'missing': [['MARKER_QUEST_START', 3]]}},
            'locations': {}, 'containers': {}, 'error': None}
        ms = mods.ModSet([{'path': 'M.wd', 'enabled': True}], [mod], retail)
        pts = mapdata.collect(retail, ms, _Idx(), None)
        by = {(p['name'], p['id'], p['mod'] and p['mod']['name']): p
              for p in pts}
        self.assertTrue(by[('MARKER_QUEST_CREATE_ENEMY', 1, None)]['used'])
        self.assertTrue(by[('MARKER_QUEST_START', 3, None)]['used'])
        # the mod repeats marker 1: only its new marker 2 is a mod point
        self.assertIn(('MARKER_QUEST_CREATE_ENEMY', 2, 'M.wd'), by)
        self.assertNotIn(('MARKER_QUEST_CREATE_ENEMY', 1, 'M.wd'), by)
        loc = [p for p in pts if p['group'] == 'locations']
        self.assertEqual(len(loc), 1)
        self.assertEqual((loc[0]['x'], loc[0]['y']), (16384, 16384))


if __name__ == '__main__':
    unittest.main()
