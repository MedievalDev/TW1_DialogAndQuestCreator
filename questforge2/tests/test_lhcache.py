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


class ModCache(Rules):
    """4.0.1: the export packs a cache into the mod archive - the game's
    maps plus the mod's own, nothing of other mods."""

    def _entry(self, tile, tag):
        inner = mods.lnd_of_tile(tile)
        return inner, tw1_wd.Entry(inner, _map(tag), flags=0x33,
                                   extra_int=20044, guid=b'G' * 16)

    def _who(self, blob):
        out = {}
        for path, head in lhcache.parse(blob).items():
            out[path.split(BS)[1]] = [n[11:] for n in tw1_lnd.markers(
                head + bytes(64)) if n.startswith('MARKER_WHO_')]
        return out

    def test_build_for_mod(self):
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL', 'A2': 'RETAIL'})
        self.pack('Mods/Minimap.wd', {'A2': 'OTHER'})     # on, must stay out
        self.assertIsNone(lhcache.build_for_mod(self.game, None, {}))
        blob = lhcache.build_for_mod(self.game, None,
                                     dict([self._entry('A1', 'MINE'),
                                           self._entry('B7', 'NEWTILE')]))
        self.assertEqual(self._who(blob), {'Map_A01.lnd': ['MINE'],
                                           'Map_A02.lnd': ['RETAIL'],
                                           'Map_B07.lnd': ['NEWTILE']})
        # maps the archive already carries count too, entries win over them
        self.pack('Mods/Mine.wd', {'A1': 'OLD', 'A2': 'MINE2'})
        arch = os.path.join(self.game, 'Mods', 'Mine.wd')
        self.assertEqual(self._who(lhcache.build_for_mod(self.game, arch, {})),
                         {'Map_A01.lnd': ['OLD'], 'Map_A02.lnd': ['MINE2']})
        blob = lhcache.build_for_mod(self.game, arch,
                                     dict([self._entry('A1', 'MINE')]))
        self.assertEqual(self._who(blob), {'Map_A01.lnd': ['MINE'],
                                           'Map_A02.lnd': ['MINE2']})

    def test_export_packs_it(self):
        import tw1_lan
        from questforge2.model import Project
        from questforge2.tests.test_quest_export import (QTX, _Index,
                                                         make_quest)
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL', 'A2': 'RETAIL'})
        base = os.path.join(self.game, 'base')
        os.makedirs(base)
        with open(os.path.join(base, 'TwoWorldsQuests.qtx'), 'wb') as f:
            f.write(QTX.encode('latin-1'))
        with open(os.path.join(base, 'TwoWorldsQuests.lan'), 'wb') as f:
            f.write(tw1_lan.build({'translateQ_4': 'Alt'}, [],
                                  tw1_lan.build_trees([])))
        p = Project('Cachemod')
        p.quests.append(make_quest())
        logs = []
        res = export.export_mod(p, self.game, base, _Index(), logs.append,
                                register=False)
        ents = {e.path for e in tw1_wd.read(res['archive'])}
        self.assertNotIn(lhcache.LHC_INNER, ents)       # no maps, no cache
        res = export.export_mod(p, self.game, base, _Index(), logs.append,
                                register=False,
                                entries=dict([self._entry('A2', 'MINE')]))
        ents = {e.path: e for e in tw1_wd.read(res['archive'])}
        self.assertEqual(self._who(ents[lhcache.LHC_INNER].data),
                         {'Map_A01.lnd': ['RETAIL'], 'Map_A02.lnd': ['MINE']})
        self.assertIn(('lhc_packed', 2, len(ents[lhcache.LHC_INNER].data)),
                      logs)
        # and with the mod switched on the game's cache equals the packed one
        blob, _used = lhcache.build(self.game, ['Cachemod.wd'])
        self.assertEqual(blob, ents[lhcache.LHC_INNER].data)
        # the placement is gone: the map leaves the archive and the cache
        res = export.export_mod(p, self.game, base, _Index(), logs.append,
                                register=False, entries={})
        ents = {e.path: e for e in tw1_wd.read(res['archive'])}
        self.assertNotIn(mods.lnd_of_tile('A2'), ents)
        self.assertEqual(p.extra['exported']['cachemod.wd']['files'], [])
        self.assertIn(('removed', mods.lnd_of_tile('A2')), logs)
        self.assertNotIn(lhcache.LHC_INNER, ents)      # its cache too


class ForeignArchive(ModCache):
    """Round 2: exporting INTO someone else's mod (target archive set to
    e.g. the campaign's archive) never takes their files away."""

    def _setup_base(self):
        import tw1_lan
        from questforge2.tests.test_quest_export import QTX
        base = os.path.join(self.game, 'base')
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, 'TwoWorldsQuests.qtx'), 'wb') as f:
            f.write(QTX.encode('latin-1'))
        with open(os.path.join(base, 'TwoWorldsQuests.lan'), 'wb') as f:
            f.write(tw1_lan.build({'translateQ_4': 'Alt'}, [],
                                  tw1_lan.build_trees([])))
        return base

    def test_their_map_and_cache_stay(self):
        from questforge2.model import Project
        from questforge2.tests.test_quest_export import _Index, make_quest
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL', 'A2': 'RETAIL'})
        # their mod: its own A2 and its own (empty) cache
        arch = os.path.join(self.game, 'Mods', 'Theirs.wd')
        export.pack_archive(arch, {
            mods.lnd_of_tile('A2'): tw1_wd.Entry(
                mods.lnd_of_tile('A2'), _map('THEIRS'), flags=0x33,
                extra_int=20044, guid=b'T' * 16),
            lhcache.LHC_INNER: b'LC' + bytes(10)}, log=lambda *a: None,
            backup=False)
        base = self._setup_base()
        p = Project('X')
        p.target_archive = 'Theirs.wd'
        p.quests.append(make_quest())
        logs = []
        # 1. no maps of ours: their cache is not touched
        export.export_mod(p, self.game, base, _Index(), logs.append,
                          register=False)
        ents = {e.path: e.data for e in tw1_wd.read(arch)}
        self.assertEqual(ents[lhcache.LHC_INNER], b'LC' + bytes(10))
        # 2. we bring A1: the cache is rebuilt, their A2 counted in
        export.export_mod(p, self.game, base, _Index(), logs.append,
                          register=False,
                          entries=dict([self._entry('A1', 'MINE')]))
        ents = {e.path: e.data for e in tw1_wd.read(arch)}
        self.assertEqual(self._who(ents[lhcache.LHC_INNER]),
                         {'Map_A01.lnd': ['MINE'], 'Map_A02.lnd': ['THEIRS']})
        self.assertEqual(p.extra['exported']['theirs.wd']['files'],
                         [mods.lnd_of_tile('A1')])      # their cache: not ours
        # 3. no maps again: our A1 goes, their A2 and a cache stay
        export.export_mod(p, self.game, base, _Index(), logs.append,
                          register=False, entries={})
        ents = {e.path: e.data for e in tw1_wd.read(arch)}
        self.assertNotIn(mods.lnd_of_tile('A1'), ents)
        self.assertIn(mods.lnd_of_tile('A2'), ents)
        self.assertIn(lhcache.LHC_INNER, ents)
        # 4. another target archive starts with an empty record
        p.target_archive = 'Other.wd'
        export.export_mod(p, self.game, base, _Index(), logs.append,
                          register=False, entries={})
        self.assertEqual(p.extra['exported']['other.wd']['files'], [])

    def test_failed_pack_records_nothing(self):
        from questforge2.model import Project
        from questforge2.tests.test_quest_export import _Index, make_quest
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL'})
        base = self._setup_base()
        p = Project('Y')
        p.quests.append(make_quest())
        real = export.pack_archive

        def boom(*a, **k):
            raise OSError('locked')
        export.pack_archive = boom
        try:
            with self.assertRaises(OSError):
                export.export_mod(p, self.game, base, _Index(),
                                  lambda *a: None, register=False,
                                  entries=dict([self._entry('A1', 'MINE')]))
        finally:
            export.pack_archive = real
        self.assertEqual((p.extra.get('exported') or {}).get('y.wd', {})
                         .get('files'), None)

    def test_mod_cache_ignores_loose_maps(self):
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL', 'A2': 'RETAIL'})
        os.makedirs(os.path.join(self.game, 'Levels'), exist_ok=True)
        with open(os.path.join(self.game, 'Levels', 'Map_A01.lnd'),
                  'wb') as f:
            f.write(placed.editor_file(_map('LOOSE'), b'L' * 16))
        blob = lhcache.build_for_mod(self.game, None,
                                     dict([self._entry('A2', 'MINE')]))
        self.assertEqual(self._who(blob), {'Map_A01.lnd': ['RETAIL'],
                                           'Map_A02.lnd': ['MINE']})

    def test_unreadable_game_archive_fails(self):
        self.pack('WDFiles/Levels.wd', {'A1': 'RETAIL'})
        with open(os.path.join(self.game, 'WDFiles', 'Broken.wd'),
                  'wb') as f:
            f.write(b'not an archive')
        with self.assertRaises(ValueError):
            lhcache.build_for_mod(self.game, None,
                                  dict([self._entry('A1', 'MINE')]))


if __name__ == '__main__':
    unittest.main()
