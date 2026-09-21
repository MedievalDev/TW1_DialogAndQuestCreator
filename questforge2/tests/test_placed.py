"""Markers placed on the map in the tool (lndmap.py, placed.py, placewin.py
without the window): a synthetic .lnd body with the section chain the
Terrain reader walks, height and passable lookups, appending markers, the
editor file form and the levels folder round trip."""

import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import tw1_lnd  # noqa: E402
from questforge2 import editormaps, lndmap, mods, placed  # noqa: E402
from questforge2.model import Project  # noqa: E402
from questforge2.tests.test_mpmerge import RETAIL_TILES, mp_quest  # noqa: E402

BS = chr(92)
NUL = bytes(1)
START, OBJ = 'MARKER_QUEST_START', 'MARKER_QUEST_CREATE_OBJECT'


def _ascii(s):
    return struct.pack('<I', len(s)) + s


def body(markers=(), blocked=()):
    """A map body: name, 6 neighbours, the markers, then every section up
    to the passable field. Heightmap 4 x 4 with height 100 * x + 1000 * y,
    passable everywhere except the 32-unit cells in ``blocked``."""
    d = b'LND0'
    d += struct.pack('<I', 3) + 'E01'.encode('utf-16-le') + NUL * 20
    for _ in range(6):
        d += _ascii(b'')
    d += struct.pack('<II', len(markers), 0)
    for name, ident, x, y, z, angle in markers:
        d += (_ascii(name.encode()) + struct.pack('<Iiii', ident, x, y, z)
              + bytes([angle]) + NUL * 8)
    d += struct.pack('<II', 0, 0)                 # skybox textures
    d += struct.pack('<II', 0, 0)                 # sky states
    d += NUL * 12                                 # day, sunrise, sunset
    d += struct.pack('<II', 4, 4)
    d += struct.pack('<16H', *[100 * x + 1000 * y for y in range(4)
                               for x in range(4)])
    d += struct.pack('<I', 0) * 2                 # edges
    d += struct.pack('<II', 0, 0)                 # water far LOD
    d += struct.pack('<II', 0, 0)                 # pools
    d += struct.pack('<II', 0, 0)                 # colour base
    d += struct.pack('<II', 0, 0)                 # textures
    d += NUL
    d += struct.pack('<II', 0, 0) * 2             # tex ref, tex alpha
    d += struct.pack('<II', 0, 0)                 # objects
    d += struct.pack('<II', 0, 0)                 # fog reference
    d += struct.pack('<II', 0, 0)                 # fog descriptions
    d += struct.pack('<II', 0, 0) * 3             # flower, stamp, EAX
    words = [0xFFFFFFFF] * 32768
    for bx, by in blocked:
        words[by * 32 + bx // 32] &= ~(1 << (bx % 32))
    d += struct.pack('<III', 32, 1024, 0) + struct.pack('<32768I', *words)
    return d


class TerrainRead(unittest.TestCase):
    def test_height_interpolated(self):
        t = lndmap.Terrain(body())
        self.assertEqual((t.hw, t.hh), (4, 4))
        self.assertEqual(t.height(0, 0), 0)
        self.assertEqual(t.height(64, 64), 1100)
        self.assertEqual(t.height(32, 0), 50)
        self.assertEqual(t.height(96, 128), 2150)
        self.assertEqual(t.height(-50, 99999), t.height(0, 64 * 2.999))

    def test_passable_and_mask(self):
        cells = [(5, 7)] + [(bx, by) for bx in range(4) for by in range(4)]
        t = lndmap.Terrain(body(blocked=cells))
        self.assertTrue(t.passable(0, 200))
        self.assertFalse(t.passable(170, 230))       # cell 5, 7
        self.assertTrue(t.passable(192, 230))
        self.assertFalse(t.passable(10, 10))         # cells 0..3
        m = t.blocked_mask(256)
        self.assertEqual(m[0], 1)                    # row 0 col 0 -> cell 0,0
        self.assertEqual(m[1 * 256 + 0], 0)          # row 1 -> cell y 4
        self.assertEqual(sum(m), 1)

    def test_no_field(self):
        d = body()
        cut = d[:len(d) - 32768 * 4 - 12] + struct.pack('<III', 0, 0, 0)
        t = lndmap.Terrain(cut)
        self.assertIsNone(t.passable(5, 5))
        self.assertEqual(sum(t.blocked_mask(8)), 0)


class AddMarkers(unittest.TestCase):
    def test_append_keeps_rest(self):
        base = body([(START, 3, 10, 20, 30, 0)])
        new = lndmap.add_markers(base, [(START, 508, 100, 200, 300, 90),
                                        (OBJ, 1, 1, 2, 3, 0)])
        got = tw1_lnd.markers_full(new)
        self.assertEqual(got[START], [(3, (10, 20, 30, 0)),
                                      (508, (100, 200, 300, 90))])
        self.assertEqual(got[OBJ], [(1, (1, 2, 3, 0))])
        start, end = tw1_lnd._marker_section(base)
        _s2, end2 = tw1_lnd._marker_section(new)
        self.assertEqual(new[:start], base[:start])
        self.assertEqual(new[end2:], base[end:])
        self.assertEqual(lndmap.Terrain(new).height(64, 64), 1100)
        self.assertEqual(lndmap.add_markers(base, []), base)

    @staticmethod
    def _order(d):
        start, _end = tw1_lnd._marker_section(d)
        pos, out = start + 8, []
        for _ in range(struct.unpack_from('<I', d, start)[0]):
            name, p2 = tw1_lnd._ascii(d, pos)
            out.append((name, struct.unpack_from('<I', d, p2)[0]))
            pos = tw1_lnd._entry_end(d, p2)
        return out

    def test_into_the_block_of_its_type(self):
        # 4.2.1: the game's maps have one block per type (measured on all
        # 160); appended markers formed a second block
        base = body([('MARKER_CHEST', 5, 0, 0, 0, 0), (OBJ, 3, 0, 0, 0, 0),
                     (START, 3, 0, 0, 0, 0), ('MARKER_SLEEP', 1, 0, 0, 0, 0)])
        new = lndmap.add_markers(base, [(START, 508, 1, 2, 3, 0),
                                        (OBJ, 1, 4, 5, 6, 0),
                                        ('MARKER_Q_KNEEL', 2, 7, 8, 9, 0)])
        self.assertEqual(self._order(new), [
            ('MARKER_CHEST', 5), ('MARKER_Q_KNEEL', 2), (OBJ, 1), (OBJ, 3),
            (START, 3), (START, 508), ('MARKER_SLEEP', 1)])
        self.assertEqual(tw1_lnd.markers_full(new)[START][1],
                         (508, (1, 2, 3, 0)))
        self.assertEqual(lndmap.sort_markers(new), new)

    def test_sort_repairs_an_appended_map(self):
        # what 3.9.0 to 4.2.0 wrote: the placed markers at the end
        bad = body([(OBJ, 3, 0, 0, 0, 0), (START, 3, 0, 0, 0, 0),
                    (START, 508, 1, 2, 3, 0), (OBJ, 1, 4, 5, 6, 0)])
        good = lndmap.sort_markers(bad)
        self.assertEqual(self._order(good), [(OBJ, 1), (OBJ, 3), (START, 3),
                                             (START, 508)])
        self.assertEqual(len(good), len(bad))
        self.assertEqual({k: sorted(v) for k, v in tw1_lnd.markers_full(good).items()},
                         {k: sorted(v) for k, v in tw1_lnd.markers_full(bad).items()})
        self.assertEqual(lndmap.Terrain(good).height(64, 64), 1100)

    def test_game_maps_already_in_order(self):
        from questforge2 import data, lhcache
        try:
            game = data.find_game_dir()
        except Exception:
            game = None
        wd = os.path.join(game or '', 'WDFiles', 'Levels.wd')
        if not os.path.isfile(wd):
            self.skipTest('game not installed')
        ent = next(e for e in mods.wd_directory(wd)
                   if e.path.lower().endswith('map_levelheaders.lhc'))
        heads = lhcache.parse(mods.wd_data(wd, ent))
        self.assertEqual(len(heads), 160)
        for path, head in heads.items():
            self.assertEqual(lndmap.sort_markers(head), head, path)


class MarkerText(unittest.TestCase):
    """A marker may carry a text behind its angle (Dream Worlds Map_E03,
    marker 323 "Engine.Draw3DObjects"); a fixed 8 byte tail broke there."""

    def _with_text(self):
        plain = body([(START, 1, 1, 2, 3, 0), (OBJ, 2, 4, 5, 6, 7)])
        start, _end = tw1_lnd._marker_section(plain)
        first = start + 8 + 4 + len(START) + 17      # first marker's tail
        text = b'Engine.Draw3DObjects'
        return (plain[:first] + struct.pack('<I', len(text)) + text
                + plain[first + 4:]), plain

    def test_read_past_the_text(self):
        d, plain = self._with_text()
        self.assertEqual(tw1_lnd.markers_full(d),
                         {START: [(1, (1, 2, 3, 0))], OBJ: [(2, (4, 5, 6, 7))]})
        _s, end = tw1_lnd._marker_section(d)
        _s, end_plain = tw1_lnd._marker_section(plain)
        self.assertEqual(end, end_plain + 20)
        self.assertEqual(lndmap.Terrain(d).height(64, 64), 1100)

    def test_edit_behind_the_text(self):
        d, _plain = self._with_text()
        new = lndmap.add_markers(d, [(START, 9, 7, 7, 7, 0)])
        self.assertEqual(tw1_lnd.markers(new), {START: {1, 9}, OBJ: {2}})
        moved, old = tw1_lnd.move_marker(d, OBJ, 2, dz=10)
        self.assertEqual(old, (4, 5, 6))
        self.assertEqual(tw1_lnd.markers_full(moved)[OBJ], [(2, (4, 5, 16, 7))])

    def test_dream_worlds_if_installed(self):
        import glob
        from questforge2 import data
        game = data.find_game_dir() if hasattr(data, 'find_game_dir') else None
        hits = glob.glob(os.path.join(game or '', 'Mods', 'Dream Worlds*.wd'))
        if not hits:
            self.skipTest('Dream Worlds not installed')
        n = 0
        for e in mods.wd_directory(hits[0]):
            if e.path.lower().endswith('.lnd'):
                tw1_lnd.markers_full(mods.wd_data(hits[0], e))
                n += 1
        self.assertGreater(n, 0)


class Build(unittest.TestCase):
    def test_missing_and_build(self):
        retail = body([(START, 1, 0, 0, 0, 0), (START, 2, 5, 5, 5, 0),
                       (OBJ, 1, 0, 0, 0, 0)])
        base = body([(START, 1, 0, 0, 0, 0)])
        self.assertEqual(placed.missing_game_markers(base, retail),
                         [(START, 2, 5, 5, 5, 0), (OBJ, 1, 0, 0, 0, 0)])
        mine = [{'name': START, 'num': 2, 'tile': 'E1', 'x': 1, 'y': 1,
                 'z': 1},
                {'name': START, 'num': 5, 'tile': 'E1', 'x': 7, 'y': 8,
                 'z': 9, 'angle': 45}]
        out, add, written, clash = placed.build_body(base, retail, mine)
        self.assertEqual(len(add), 2)
        self.assertEqual(written, [(START, 5, 7, 8, 9, 45)])
        self.assertEqual(clash, [mine[0]])
        self.assertEqual(tw1_lnd.markers(out),
                         {START: {1, 2, 5}, OBJ: {1}})
        out2, add2, _w, _c = placed.build_body(base, retail, mine[1:],
                                               fill=False)
        self.assertEqual(add2, [])
        self.assertEqual(tw1_lnd.markers(out2), {START: {1, 5}})

    def test_editor_file(self):
        d = body([(OBJ, 4, 1, 2, 3, 0)])
        guid = bytes(range(16))
        blob = placed.editor_file(d, guid)
        flags, _res, cid, g, back = mods.file_entry(blob)
        self.assertEqual((flags, cid, g, back), (0x33, 20044, guid, d))
        self.assertEqual(tw1_lnd.markers(blob), {OBJ: {4}})

    def test_numbers(self):
        d = body([(START, 3, 0, 0, 0, 0), (START, 7, 0, 0, 0, 0)])
        pl = [{'name': START, 'tile': 'E1', 'num': 9},
              {'name': START, 'tile': 'F1', 'num': 20},
              {'name': OBJ, 'tile': 'E1', 'num': 2}]
        self.assertEqual(placed.free_number(START, 'E1', d, pl), 10)
        self.assertEqual(placed.free_number(START, 'E1', d, pl,
                                            skip=pl[0]), 8)
        self.assertEqual(placed.free_number(OBJ, 'E1', d, pl), 3)
        self.assertEqual(placed.free_number(OBJ, 'F1', None, []), 1)
        self.assertTrue(placed.marker_exists(d, START, 7))
        self.assertFalse(placed.marker_exists(d, START, 8))
        self.assertFalse(placed.marker_exists(None, START, 7))


class Generate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='qf2placed_')
        self.p = Project('Gen')
        self.p.path = os.path.join(self.tmp, 'Gen.tw1proj')
        self.lv = editormaps.levels_dir(self.p)
        self.inner = mods.lnd_of_tile('E1')
        # the user's own editor tile (an import, not written by us)
        self.user = placed.editor_file(body([(OBJ, 1, 0, 0, 0, 0)]),
                                       b'U' * 16)
        self.path = os.path.join(self.lv, *self.inner.split(BS))
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'wb') as f:
            f.write(self.user)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self):
        with open(self.path, 'rb') as f:
            return f.read()

    def test_round_trip(self):
        p = self.p
        placed.placements(p).append({'name': START, 'num': 508, 'tile': 'E1',
                                     'x': 100, 'y': 120, 'z': 5, 'angle': 0,
                                     'quest': 385})
        log = []
        rep = placed.generate(p, None, None, log.append)
        self.assertEqual(rep['E1']['source'], 'editor')
        self.assertEqual(rep['E1']['placed'], [(START, 508, 100, 120, 5, 0)])
        self.assertEqual(rep['E1']['added'], [])        # no game map given
        blob = self._read()
        flags, _r, cid, guid, _back = mods.file_entry(blob)
        self.assertEqual((flags, cid), (0x33, 20044))
        self.assertEqual(guid.hex(), p.extra['tile_guids']['E1'])
        self.assertEqual(tw1_lnd.markers(blob), {OBJ: {1}, START: {508}})
        keep = os.path.join(placed.base_dir(p), *self.inner.split(BS))
        with open(keep, 'rb') as f:
            self.assertEqual(f.read(), self.user)
        self.assertEqual(p.extra['generated_tiles'], ['E1'])
        self.assertEqual([m['path'] for m in p.mods], [self.lv])
        self.assertEqual(p.mod_tiles['E1'], os.path.basename(self.lv))
        self.assertEqual(log, [('tile', 'E1', 'editor', 0, 1)])
        # a second run builds from the kept base, not from our own output
        placed.placements(p)[0]['num'] = 509
        placed.generate(p, None, None, log.append)
        self.assertEqual(tw1_lnd.markers(self._read()),
                         {OBJ: {1}, START: {509}})
        # nothing placed any more: the user's tile comes back byte for byte
        placed.placements(p).clear()
        rep = placed.generate(p, None, None, log.append)
        self.assertEqual(rep, {})
        self.assertEqual(self._read(), self.user)
        self.assertEqual(p.extra['generated_tiles'], [])
        self.assertNotIn('E1', p.mod_tiles)

    def test_fill_tile_without_base(self):
        p = self.p
        p.extra['fill_tiles'] = ['H6']          # no map anywhere for it
        rep = placed.generate(p, None, None, lambda *a: None)
        self.assertEqual(rep['H6'], {'source': None, 'added': [],
                                     'placed': [], 'clash': []})
        self.assertFalse(os.path.exists(os.path.join(
            self.lv, *mods.lnd_of_tile('H6').split(BS))))

    def test_unsaved_project(self):
        with self.assertRaises(ValueError):
            placed.generate(Project('x'), None, None)


class QuestSide(unittest.TestCase):
    """placewin without a window: which markers a taken over quest needs
    and moving a quest line to the placed marker."""

    def _quest(self):
        from questforge2 import mpmerge
        return mpmerge.apply(mp_quest(), 385, 508, 'Name', 'E1', RETAIL_TILES)

    def test_targets(self):
        from questforge2 import placewin
        q = self._quest()
        p = Project('T')
        p.quests.append(q)
        todo = q.extra['markers_todo']
        tg = placewin.quest_targets(p, q)
        self.assertEqual(len(tg), sum(1 for x in todo if not x['done']))
        self.assertEqual(tg[0]['name'], START)
        self.assertEqual((tg[0]['num'], tg[0]['tile']), (508, 'E1'))
        self.assertTrue(all(x['num'] is None for x in tg[1:]))
        self.assertTrue(all(x['placed'] is None for x in tg))
        # ticked in the editor: not offered; placed here before: offered
        todo[1]['done'] = True
        self.assertEqual(len(placewin.quest_targets(p, q)), len(tg) - 1)
        placed.placements(p).append({
            'name': todo[1]['name'], 'num': todo[1]['num'], 'tile': 'E1',
            'x': 1, 'y': 2, 'z': 3, 'angle': 0, 'quest': q.id})
        again = placewin.quest_targets(p, q)
        self.assertEqual(len(again), len(tg))
        hit = next(x for x in again if x['orig'] is not None)
        self.assertEqual(hit['placed'], {'tile': 'E1', 'x': 1, 'y': 2, 'z': 3,
                                         'num': todo[1]['num']})

    def test_retarget(self):
        from questforge2 import mpmerge, placewin
        q = self._quest()
        placewin._retarget(q, (START, 'E1', 508), (START, 'F2', 508))
        giver = next(s for s in q.speakers if s.get('new'))
        self.assertEqual((giver['tile'], giver['marker']), ('F2', 508))
        refs = mpmerge.marker_refs(q)
        ref = refs[0]
        old = (ref['name'], ref['tile'], ref['num'])
        # the two OBJECT_CREATE lines share one marker: both move with it
        same = [i for i, r in enumerate(refs)
                if (r['name'], r['tile'], r['num']) == old]
        self.assertEqual(same, [0, 1])
        others = [(r['tile'], r['num']) for i, r in enumerate(refs)
                  if i not in same]
        placewin._retarget(q, old, (ref['name'], 'G3', 77))
        after = mpmerge.marker_refs(q)
        self.assertEqual([(after[i]['tile'], after[i]['num']) for i in same],
                         [('G3', 77), ('G3', 77)])
        self.assertEqual([(r['tile'], r['num']) for i, r in enumerate(after)
                          if i not in same], others)


if __name__ == '__main__':
    unittest.main()
