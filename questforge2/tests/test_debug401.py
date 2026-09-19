"""4.0.1 deep debug rounds: every case here was a real defect found by
review and reproduced before it was fixed."""

import json
import os
import shutil
import sys
import tempfile
import types
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import foxfeedback  # noqa: E402
import tw1_lnd  # noqa: E402
from questforge2 import editormaps, export, lhcache, mods, placed  # noqa: E402
from questforge2.model import Project  # noqa: E402
from questforge2.tests.test_placed import OBJ, START, body  # noqa: E402

BS = chr(92)


class _Levels(unittest.TestCase):
    """A saved project, a folder mod as the base of E1 (it stands in for
    the game map), the levels folder of the project."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='qf2dbg_')
        self.p = self.project()
        self.inner = mods.lnd_of_tile('E1')
        self.mod = os.path.join(self.tmp, 'SomeMod')
        self._put(self.mod, self.inner,
                  placed.editor_file(body([(OBJ, 1, 0, 0, 0, 0)]), b'M' * 16))
        self._put(self.mod, mods._phx_inner(self.inner), b'PHX')
        info = {'name': 'SomeMod', 'path': self.mod,
                'tiles': {'E1': {'inner': self.inner}}}
        self.ms = types.SimpleNamespace(
            retail_tiles={}, tile_providers=lambda t: [info] if t == 'E1'
            else [])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self):
        p = Project('Dbg')
        p.path = os.path.join(self.tmp, 'Dbg.tw1proj')
        return p

    @staticmethod
    def _put(root, inner, blob):
        path = os.path.join(root, *inner.split(BS))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(blob)
        return path

    def target(self):
        return os.path.join(editormaps.levels_dir(self.p),
                            *self.inner.split(BS))

    def markers(self):
        with open(self.target(), 'rb') as f:
            return tw1_lnd.markers(f.read())

    def place(self, p, num, name=START):
        placed.placements(p).append({'name': name, 'num': num, 'tile': 'E1',
                                     'x': 1, 'y': 1, 'z': 1, 'angle': 0,
                                     'quest': 385})


class Levels(_Levels):
    def test_unsaved_project_does_not_bake_markers_in(self):
        self.place(self.p, 5)
        placed.generate(self.p, self.ms, None, lambda *a: None)
        self.assertEqual(self.markers(), {OBJ: {1}, START: {5}})
        # closed without saving: generated_tiles and tile_guids are gone
        p2 = self.project()
        self.place(p2, 6)
        placed.generate(p2, self.ms, None, lambda *a: None)
        self.assertEqual(self.markers(), {OBJ: {1}, START: {6}})
        self.assertFalse(os.path.exists(placed.base_dir(p2)))  # no backup
        placed.placements(p2).clear()
        placed.generate(p2, self.ms, None, lambda *a: None)
        self.assertFalse(os.path.exists(self.target()))
        self.assertFalse(os.path.exists(os.path.join(
            editormaps.levels_dir(p2), *mods._phx_inner(self.inner)
            .split(BS))))                                    # phx gone too

    def test_new_editor_import_over_our_tile_is_kept(self):
        self.place(self.p, 5)
        placed.generate(self.p, self.ms, None, lambda *a: None)
        # the user saves E1 in the editor again and imports it
        new = placed.editor_file(body([(OBJ, 1, 0, 0, 0, 0),
                                       (OBJ, 2, 9, 9, 9, 0)]), b'V' * 16)
        with open(self.target(), 'wb') as f:
            f.write(new)
        base, _phx, src = placed.base_of(self.p, self.ms, None, 'E1')
        self.assertEqual((src, tw1_lnd.markers(base)), ('editor', {OBJ: {1, 2}}))
        placed.generate(self.p, self.ms, None, lambda *a: None)
        self.assertEqual(self.markers(), {OBJ: {1, 2}, START: {5}})
        placed.placements(self.p).clear()
        placed.generate(self.p, self.ms, None, lambda *a: None)
        with open(self.target(), 'rb') as f:
            self.assertEqual(f.read(), new)                 # theirs again
        self.assertFalse(os.path.exists(os.path.join(
            placed.base_dir(self.p), *self.inner.split(BS))))

    def test_old_levels_folder_is_never_a_base(self):
        self.place(self.p, 5)
        placed.generate(self.p, self.ms, None, lambda *a: None)
        old_lv = editormaps.levels_dir(self.p)
        old_path = self.p.path
        self.p.path = os.path.join(self.tmp, 'Dbg2.tw1proj')   # save as
        self.assertTrue(placed.move_levels(self.p, old_path))
        new_lv = editormaps.levels_dir(self.p)
        self.assertEqual([m['path'] for m in self.p.mods], [new_lv])
        self.assertEqual(self.p.mod_tiles['E1'], mods.mod_name(new_lv))
        info_old = {'name': mods.mod_name(old_lv), 'path': old_lv,
                    'tiles': {'E1': {'inner': self.inner}}}
        info = {'name': 'SomeMod', 'path': self.mod,
                'tiles': {'E1': {'inner': self.inner}}}
        ms = types.SimpleNamespace(retail_tiles={},
                                   tile_providers=lambda t: [info_old, info])
        placed.placements(self.p)[0]['num'] = 7            # marker changed
        rep = placed.generate(self.p, ms, None, lambda *a: None)
        self.assertEqual(rep['E1']['source'], 'SomeMod')
        self.assertEqual(rep['E1']['clash'], [])
        self.assertEqual(self.markers(), {OBJ: {1}, START: {7}})
        self.assertFalse(placed.move_levels(self.p, self.p.path))

    def test_forget_quest(self):
        self.place(self.p, 5)
        self.assertTrue(placed.forget_quest(self.p, 385, 390))
        self.assertEqual(placed.placements(self.p)[0]['quest'], 390)
        self.assertTrue(placed.forget_quest(self.p, 390))
        self.assertEqual(placed.placements(self.p), [])
        self.assertFalse(placed.forget_quest(self.p, 390))

    def test_plain_stream_maps(self):
        # the SDK writes a .lnd as ONE zlib stream (no editor metadata)
        plain = zlib.compress(body([(OBJ, 4, 0, 0, 0, 0)]))
        path = self._put(os.path.join(self.tmp, 'game'), self.inner, plain)
        self.assertEqual(tw1_lnd.markers(lhcache._loose_head(path)), {OBJ: {4}})
        self._put(self.mod, self.inner, plain)
        base, _phx, _src = placed.base_of(self.p, self.ms, None, 'E1')
        self.assertEqual(tw1_lnd.markers(base), {OBJ: {4}})


class Levels2(_Levels):
    """Round 2 of the review."""

    def test_other_projects_tile_is_not_ours(self):
        # a tile generated by ANOTHER project (QF2L GUID, not in our list)
        # imported into our levels folder is the user's, never deleted
        other = self.project()
        other.path = os.path.join(self.tmp, 'Other.tw1proj')
        self.place(other, 9)
        placed.generate(other, self.ms, None, lambda *a: None)
        with open(os.path.join(editormaps.levels_dir(other),
                               *self.inner.split(BS)), 'rb') as f:
            blob = f.read()
        self._put(editormaps.levels_dir(self.p), self.inner, blob)
        placed.generate(self.p, self.ms, None, lambda *a: None)
        self.assertEqual(self.markers(), {OBJ: {1}, START: {9}})

    def test_save_as_over_an_existing_levels_folder(self):
        self.place(self.p, 5)
        placed.generate(self.p, self.ms, None, lambda *a: None)
        old_path = self.p.path
        stale = os.path.join(self.tmp, 'Dbg2_levels')
        self._put(stale, self.inner, b'stale')
        self.p.path = os.path.join(self.tmp, 'Dbg2.tw1proj')
        self.assertTrue(placed.move_levels(self.p, old_path))
        self.assertEqual(self.markers(), {OBJ: {1}, START: {5}})
        aside = [n for n in os.listdir(self.tmp)
                 if n.startswith('Dbg2_levels.old-')]
        self.assertEqual(len(aside), 1)                 # kept, not deleted

    def test_no_game_maps_loaded(self):
        self.place(self.p, 5)
        placed.generate(self.p, self.ms, None, lambda *a: None)
        with self.assertRaises(ValueError):
            placed.generate(self.p, None, 'C:' + BS + 'game', lambda *a: None)
        self.assertEqual(self.markers(), {OBJ: {1}, START: {5}})
        # a base that cannot be read keeps our tile as it is
        empty = types.SimpleNamespace(retail_tiles={},
                                      tile_providers=lambda t: [])
        rep = placed.generate(self.p, empty, None, lambda *a: None)
        self.assertIsNone(rep['E1']['source'])
        self.assertEqual(self.markers(), {OBJ: {1}, START: {5}})

    def test_base_choice_survives(self):
        m2 = os.path.join(self.tmp, 'M2')
        self._put(m2, self.inner, placed.editor_file(
            body([(OBJ, 2, 0, 0, 0, 0)]), b'2' * 16))
        info1 = {'name': 'SomeMod', 'path': self.mod,
                 'tiles': {'E1': {'inner': self.inner}}}
        info2 = {'name': 'M2', 'path': m2, 'tiles': {'E1': {'inner': self.inner}}}
        ms = types.SimpleNamespace(retail_tiles={},
                                   tile_providers=lambda t: [info1, info2])
        self.p.mod_tiles['E1'] = 'M2'                  # the user's pick
        self.place(self.p, 5)
        placed.generate(self.p, ms, None, lambda *a: None)
        placed.generate(self.p, ms, None, lambda *a: None)
        self.assertEqual(self.markers(), {OBJ: {2}, START: {5}})
        placed.placements(self.p).clear()
        placed.generate(self.p, ms, None, lambda *a: None)
        self.assertEqual(self.p.mod_tiles.get('E1'), 'M2')

    def test_physics_of_an_earlier_base_goes(self):
        self.place(self.p, 5)
        placed.generate(self.p, self.ms, None, lambda *a: None)
        pt = os.path.join(editormaps.levels_dir(self.p),
                          *mods._phx_inner(self.inner).split(BS))
        self.assertTrue(os.path.isfile(pt))
        os.remove(os.path.join(self.mod, *mods._phx_inner(self.inner)
                               .split(BS)))           # new base: no physics
        placed.generate(self.p, self.ms, None, lambda *a: None)
        self.assertFalse(os.path.isfile(pt))


class Commit(_Levels):
    """placewin.commit with a small stand in for the app."""

    def test_moving_onto_the_old_place_of_another(self):
        from questforge2 import placewin
        from questforge2.model import Quest
        q = Quest(385, 'T')
        q.actions = [
            {'kind': 'ACTION', 'verb': 'OBJECT_CREATE', 'when': 'ENABLE',
             'args': {'item': 'QITEM_040', 'count': 1, 'marker': 1,
                      'tile': 'F1'}},
            {'kind': 'ACTION', 'verb': 'OBJECT_CREATE', 'when': 'ENABLE',
             'args': {'item': 'QITEM_041', 'count': 1, 'marker': 1,
                      'tile': 'E1'}}]
        q.extra['markers_todo'] = [
            {'name': OBJ, 'num': 1, 'tile': 'F1', 'done': False},
            {'name': OBJ, 'num': 1, 'tile': 'E1', 'done': False}]
        self.p.quests.append(q)
        app = types.SimpleNamespace(
            project=self.p, modset=self.ms, cfg={'game_dir': None}, quest=None,
            mark_dirty=lambda: None, load_modset=lambda force=False: None)
        spot = {'x': 5, 'y': 5, 'z': 5}
        targets = [
            {'key': (OBJ, 'F1', 1), 'name': OBJ, 'orig': None,
             'placed': dict(spot, tile='E1', num=2)},
            {'key': (OBJ, 'E1', 1), 'name': OBJ, 'orig': None,
             'placed': dict(spot, tile='E1', num=3)}]
        placewin.commit(app, q, targets)
        self.assertEqual([(a['args']['tile'], a['args']['marker'])
                          for a in q.actions], [('E1', 2), ('E1', 3)])
        self.assertEqual([(x['tile'], x['num'], x['done'])
                          for x in q.extra['markers_todo']],
                         [('E1', 2, True), ('E1', 3, True)])
        self.assertEqual(self.markers(), {OBJ: {1, 2, 3}})


class Feedback(unittest.TestCase):
    def setUp(self):
        self._names = foxfeedback._own_names
        foxfeedback._own_names = lambda: ['mark', 'MARK-PC']

    def tearDown(self):
        foxfeedback._own_names = self._names

    def test_scrub_whole_words(self):
        out = foxfeedback.scrub('warn.marker: Marker placed by mark on '
                                'MARK-PC, mail a.b@web.de, C:' + BS
                                + 'Documents and Settings' + BS + 'Max' + BS
                                + 'x')
        self.assertIn('warn.marker: Marker', out)
        self.assertNotIn('mark ', out.lower().replace('marker', ''))
        self.assertIn('<user>-PC', out.replace('<user>-PC', '<user>-PC'))
        self.assertIn('<mail>', out)
        self.assertNotIn('Max', out)

    def test_fingerprint_ignores_the_user(self):
        a = foxfeedback.fingerprint('q', 'k', 'bad marker in C:' + BS
                                    + 'Program Files (x86)' + BS + 'a b.wd')
        b = foxfeedback.fingerprint('q', 'k', 'bad marker in D:' + BS
                                    + 'x.wd')
        self.assertEqual(a, b)

    def test_body_fits_in_bytes(self):
        for fill in ('a', 'ä"' + chr(10), '€', '�\x00'):
            p = foxfeedback.test_payload('questcreator', '4.0.1', 'a' * 32,
                                         'de', 'x', True, message=fill * 4000,
                                         log=fill * 200000,
                                         game_log=fill * 200000)
            size = len(json.dumps(p, ensure_ascii=False).encode('utf-8'))
            self.assertLessEqual(size, 300 * 1024, repr(fill))
            self.assertNotIn('\x00', p['log'])

    def test_no_network_module_at_import(self):
        # urllib pulls http, email and ssl: 65 ms before the first window
        import subprocess
        code = ('import sys; sys.path.insert(0, %r); import foxfeedback; '
                'print("urllib.request" in sys.modules)'
                % os.path.dirname(os.path.dirname(HERE)))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True,
                             text=True, timeout=60).stdout.strip()
        self.assertEqual(out, 'False')


class Round2(unittest.TestCase):
    def test_scrub_placeholders_and_paths(self):
        names = foxfeedback._own_names
        foxfeedback._own_names = lambda: ['User', 'mail', 'JM']
        try:
            for raw in ('C:' + BS + 'Users' + BS + 'User' + BS + 'a',
                        "'C:" + BS * 2 + 'Users' + BS * 2 + 'JM' + BS * 2
                        + "x.wd'",
                        BS * 2 + 'FIRMA-NAS01' + BS + 'home' + BS + 'm',
                        'OneDrive - Mustermann GmbH' + BS + 'q',
                        'see https://example.com/page'):
                once = foxfeedback.scrub(raw)
                self.assertEqual(foxfeedback.scrub(once), once)
                for leak in ('JM' + BS, 'FIRMA', 'Mustermann', '<<'):
                    self.assertNotIn(leak, once)
            self.assertIn('https://example.com/page',
                          foxfeedback.scrub('see https://example.com/page'))
        finally:
            foxfeedback._own_names = names

    def test_default_account_names_are_kept_as_words(self):
        import os as _os
        env = dict(_os.environ)
        try:
            _os.environ['COMPUTERNAME'] = 'TEST'
            self.assertNotIn('TEST', [n.upper()
                                      for n in foxfeedback._own_names()])
        finally:
            _os.environ.clear()
            _os.environ.update(env)

    def test_fingerprint_same_bug_other_language(self):
        from questforge2 import i18n
        key = 'val.mod.redtile'
        a = foxfeedback.bug_payload('q', '4.0.1', 'a' * 32, 'de', 't', key,
                                    'Kachel E1 der Mod X ...',
                                    fp_text=i18n._EN[key])
        b = foxfeedback.bug_payload('q', '4.0.1', 'b' * 32, 'en', 't', key,
                                    'Tile F7 of mod Y ...',
                                    fp_text=i18n._EN[key])
        self.assertEqual(a['fingerprint'], b['fingerprint'])
        u1 = foxfeedback.fingerprint('q', 'k', 'x ' + BS * 2 + 'srv1' + BS
                                     + 'a' + BS + 'x.wd')
        u2 = foxfeedback.fingerprint('q', 'k', 'x ' + BS * 2 + 'nas-2' + BS
                                     + 'b' + BS + 'y.wd')
        self.assertEqual(u1, u2)
        e13 = foxfeedback.fingerprint('q', 'k', 'C:' + BS + 'a.wd: [Errno 13] '
                                      'Permission denied')
        e28 = foxfeedback.fingerprint('q', 'k', 'C:' + BS + 'a.wd: [Errno 28] '
                                      'No space left')
        self.assertNotEqual(e13, e28)

    def test_summary_of_odd_types(self):
        import http.server
        import threading
        answers = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                raw = json.dumps(answers[0]).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}/'
        try:
            for doc in ({'tools': [1, 2]}, {'tools': {'q': 'x'}},
                        {'tools': {'q': {'tests': [1], 'issues': 'x'}}},
                        {'tools': {'q': {'tests': {'a': 'x', 'b': {
                            'pass': 'z', 'status': 'open'}}, 'issues': [1, {
                                'title': 't'}]}}}):
                answers[:] = [doc]
                s = foxfeedback.fetch_summary('q', '1.0.0', base=base)
                self.assertIsInstance(s['tests'], dict)
                self.assertIsInstance(s['issues'], list)
                for rec in s['tests'].values():
                    self.assertIsInstance(rec['pass'], int)
                self.assertTrue(all(isinstance(i, dict) for i in s['issues']))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_decode_cut_logs(self):
        from questforge2.gamesession import _decode
        t = 'Größe Level header ok'
        self.assertEqual(_decode(t.encode('utf-8')[3:]), 'ße Level header ok')
        self.assertEqual(_decode(t.encode('utf-8')[:4]), 'Grö')
        self.assertTrue(_decode(t.encode('utf-16-le')[3:]).endswith(
            'Level header ok'))
        self.assertEqual(_decode(t.encode('cp1252')), t)


class Process(unittest.TestCase):
    def test_mod_selector_is_not_the_game(self):
        self.assertFalse(export._is_game('TwoWorlds1 Mod Selector.exe'))
        self.assertTrue(export._is_game('TwoWorldsExtended.exe'))
        self.assertTrue(export._is_game('TWOWORLDS.EXE'))
        self.assertIsNone(export.running_game_name(
            '"TwoWorlds1 Mod Selector.exe","1","Console","1","9 K"'))

    def test_process_list(self):
        names = export.process_names()
        if names is None:
            self.skipTest('no process list here')
        self.assertTrue(any(n.lower().startswith('py') for n in names))


if __name__ == '__main__':
    unittest.main()
