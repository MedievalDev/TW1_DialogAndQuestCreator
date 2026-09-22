"""Community tests and bug reports (foxfeedback.py, feedbackwin.Feedback,
validate message keys) against a small server on localhost that speaks the
public part of FEEDBACK_ENDPUNKT_SPEZIFIKATION.md."""

import getpass
import http.server
import json
import os
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import foxfeedback  # noqa: E402
from questforge2 import VERSION, feedbackwin, gamesession, i18n, validate  # noqa: E402

BS = chr(92)
SUMMARY = {'schema': 1, 'updated': '2026-09-19T08:00:00Z', 'accept': True,
           'tools': {'questcreator': {
               'tests': {'placed-giver-ingame': {'since': '3.9.0', 'pass': 2,
                                                 'fail': 0,
                                                 'status': 'confirmed'},
                         'lhc-without-sdk': {'since': '3.9.2', 'pass': 0,
                                             'fail': 1, 'status': 'failed'}},
               'issues': [{'id': 'x', 'title': 'val.mod.redtile: ...',
                           'status': 'reported', 'version': '3.9.2',
                           'count': 3, 'fixed_in': ''}]}}}


class _Handler(http.server.BaseHTTPRequestHandler):
    got = []
    answer = (201, {'ok': True, 'id': '20260919-081245-3f9a'})

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.endswith('summary.json'):
            self._send(200, SUMMARY)
        else:
            self._send(404, {})

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = json.loads(self.rfile.read(n).decode('utf-8'))
        _Handler.got.append((self.path, dict(self.headers), body))
        self._send(*_Handler.answer)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}/'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        _Handler.got = []
        _Handler.answer = (201, {'ok': True, 'id': '20260919-081245-3f9a'})

    def test_submit_test(self):
        p = foxfeedback.test_payload('questcreator', '4.0.0', 'a' * 32, 'de',
                                     'placed-giver-ingame', True,
                                     message='ok', log='l', game_log='g')
        self.assertEqual(foxfeedback.submit(p, base=self.base),
                         '20260919-081245-3f9a')
        path, headers, body = _Handler.got[0]
        self.assertTrue(path.endswith('/submit'))
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        self.assertEqual(headers['User-Agent'],
                         'FoxFeedback/1 (questcreator 4.0.0)')
        self.assertEqual(body['result'], 'pass')
        # a test carries none of the bug fields (the server rejects them)
        self.assertEqual(set(body), {
            'schema', 'kind', 'tool', 'version', 'client_id', 'lang', 'os',
            'created', 'message', 'log', 'game_log', 'test_id', 'result'})
        self.assertRegex(body['created'],
                         r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')

    def test_submit_bug(self):
        p = foxfeedback.bug_payload('questcreator', '4.0.0', 'b' * 32, 'en',
                                    'val.mod.redtile: Tile {tile} ...',
                                    error_key='val.mod.redtile',
                                    error_text='Tile E1 of mod X',
                                    guide_ref='mods', message='m', log='l')
        foxfeedback.submit(p, base=self.base)
        body = _Handler.got[0][2]
        self.assertNotIn('test_id', body)
        self.assertNotIn('result', body)
        self.assertEqual(len(body['fingerprint']), 40)
        self.assertEqual(body['guide_ref'], 'mods')

    def test_errors(self):
        p = foxfeedback.test_payload('questcreator', '4.0.0', 'a' * 32, 'de',
                                     'x', False)
        for code, obj, want in ((429, {'ok': False, 'error': 'rate'}, 'rate'),
                                (503, {'ok': False, 'error': 'closed'},
                                 'closed'),
                                (400, {'ok': False, 'error': 'invalid',
                                       'field': 'version'}, 'invalid'),
                                (413, {}, 'too_large')):
            _Handler.answer = (code, obj)
            with self.assertRaises(foxfeedback.FeedbackError) as c:
                foxfeedback.submit(p, base=self.base)
            self.assertEqual(c.exception.code, want)
        with self.assertRaises(foxfeedback.FeedbackError) as c:
            foxfeedback.submit(p, base='http://127.0.0.1:9/', timeout=2)
        self.assertEqual(c.exception.code, 'offline')

    def test_summary(self):
        s = foxfeedback.fetch_summary('questcreator', '4.0.0', base=self.base)
        self.assertEqual(s['tests']['placed-giver-ingame']['status'],
                         'confirmed')
        self.assertEqual(len(s['issues']), 1)
        self.assertEqual(foxfeedback.fetch_summary(
            'minimaptool', '1.0.0', base=self.base)['tests'], {})
        self.assertIsNone(foxfeedback.fetch_summary(
            'questcreator', '4.0.0', base='http://127.0.0.1:9/', timeout=2))


class Text(unittest.TestCase):
    def test_scrub(self):
        home = os.path.expanduser('~')
        out = foxfeedback.scrub(f'{home}{BS}Desktop{BS}a.tw1proj and '
                                'F:/Users/Anna Lena/b')
        self.assertNotIn(os.path.basename(home), out)
        self.assertIn('<user>', out)
        self.assertNotIn('Anna', out)
        user = getpass.getuser()
        if len(user) > 2:
            self.assertNotIn(user, foxfeedback.scrub(f'owner {user}'))

    def test_clip_keeps_the_end(self):
        out = foxfeedback.clip('a' * 200000 + 'END', 1000)
        self.assertEqual(len(out), 1000)
        self.assertTrue(out.endswith('END'))
        self.assertEqual(foxfeedback.clip('short'), 'short')

    def test_fingerprint(self):
        a = foxfeedback.fingerprint('q', 'val.x', 'Tile "E1" has 12 errors '
                                    'in C:' + BS + 'a' + BS + 'b.wd')
        b = foxfeedback.fingerprint('q', 'val.x', 'Tile "F7" has 3 errors '
                                    'in D:' + BS + 'zz' + BS + 'c.wd')
        self.assertEqual(a, b)
        self.assertNotEqual(a, foxfeedback.fingerprint('q', 'val.y', 'x'))
        self.assertRegex(a, '^[0-9a-f]{40}$')

    def test_limits(self):
        p = foxfeedback.bug_payload('t', '1.0.0', 'c' * 32, 'fr', 'T' * 500,
                                    error_key='bad key!/x', message='m' * 9000,
                                    log='l' * 300000)
        self.assertEqual(p['lang'], 'en')
        self.assertEqual(len(p['title']), 120)
        self.assertEqual(p['error_key'], 'badkeyx')
        self.assertEqual(len(p['message']), 4000)
        self.assertEqual(len(p['log']), 120000)
        self.assertLess(len(json.dumps(p).encode()), 300 * 1024)
        self.assertIn('--- log (120000 characters) ---',
                      foxfeedback.preview(p))

    def test_session_log(self):
        log = foxfeedback.SessionLog(limit=3)
        for i in range(5):
            log.add(f'line {i}')
        self.assertEqual([ln[10:] for ln in log.text().split(chr(10))],
                         ['line 2', 'line 3', 'line 4'])


class _Cfg(dict):
    saved = 0

    def set(self, k, v):
        self[k] = v

    def save(self):
        self.saved += 1


class _App:
    def __init__(self):
        self.cfg = _Cfg()


class State(unittest.TestCase):
    def setUp(self):
        self.fb = feedbackwin.Feedback(_App())

    def test_shipped_tests(self):
        ids = [x['id'] for x in self.fb.tests]
        self.assertIn('placed-giver-ingame', ids)
        self.assertIn('lhc-without-sdk', ids)
        self.assertEqual(len(ids), len(set(ids)))
        for x in self.fb.tests:
            self.assertRegex(x['id'], '^[a-z0-9-]{1,60}$')
            for field in ('title', 'why', 'expect'):
                self.assertTrue(x[field]['de'] and x[field]['en'], x['id'])
            self.assertEqual(len(x['steps']['de']), len(x['steps']['en']))
            self.assertLessEqual(feedbackwin._vkey(x['since']),
                                 feedbackwin._vkey(VERSION))

    def test_server_state_is_taken_over(self):
        self.assertTrue(self.fb.experimental('lhc'))     # no server: stays
        self.assertEqual(self.fb.state('placed-giver-ingame'), 'unknown')
        n = len(self.fb.untested())
        self.fb.summary = SUMMARY['tools']['questcreator']
        self.assertEqual(self.fb.state('placed-giver-ingame'), 'confirmed')
        # with the server known only the tests it takes are offered: the
        # confirmed one is gone, the ones it does not list are not offered
        self.assertEqual(n, len(self.fb.tests))
        self.assertEqual([x['id'] for x in self.fb.untested()],
                         ['lhc-without-sdk'])
        self.assertFalse(self.fb.can_report('placed-object-enemy-ingame'))
        self.assertEqual(self.fb.counts('lhc-without-sdk'), (0, 1))
        self.assertTrue(self.fb.experimental('lhc'))     # failed: stays
        self.fb.summary['tests']['lhc-without-sdk']['status'] = 'confirmed'
        self.assertFalse(self.fb.experimental('lhc'))
        self.fb.summary['tests']['lhc-without-sdk']['status'] = 'failed'

    def test_client_id_is_kept(self):
        a = self.fb.client_id()
        self.assertRegex(a, '^[0-9a-f]{32}$')
        self.assertEqual(self.fb.client_id(), a)
        self.assertEqual(self.fb.app.cfg.saved, 1)

    def test_version_key(self):
        self.assertLess(feedbackwin._vkey('3.9.2'), feedbackwin._vkey('3.10.0'))
        self.assertEqual(feedbackwin._vkey('4.0.0-m1'), (4, 0, 0))


class Keys(unittest.TestCase):
    def test_messages_keep_their_key(self):
        t = validate.keyed(i18n.t)
        m = t('val.mod.redtile', tile='E1', mod='X', n=3, markers='1')
        self.assertEqual(m.key, 'val.mod.redtile')
        self.assertIn('E1', m)
        self.assertIs(validate.keyed(t), t)

    def test_guide_chapters_exist(self):
        from questforge2 import guidebook
        chapters = {c[0] for c in guidebook.CHAPTERS}
        for _prefix, ch in validate.GUIDE_REFS:
            self.assertIn(ch, chapters)
        self.assertIn('trouble', chapters)
        self.assertEqual(validate.guide_ref('val.mod.redtile'), 'mods')
        self.assertEqual(validate.guide_ref('warn.marker.missing'), 'markers')
        self.assertEqual(validate.guide_ref('val.link.limit'), 'links')
        self.assertEqual(validate.guide_ref('something.else'), 'trouble')
        self.assertEqual(validate.guide_ref(''), 'trouble')


class News(unittest.TestCase):
    """What's new with tours and guide chapters (4.5.0, Marco 2026-09-22:
    "im Fenster, wo steht, was neu ist, verlinkst du die Guides als Tour")."""

    def test_versions(self):
        now = feedbackwin.news_since(None)
        self.assertEqual(now, list(feedbackwin.NEWS.get(VERSION, ())))
        self.assertEqual(feedbackwin.news_since(VERSION), [])
        self.assertEqual(feedbackwin.news_since('4.4.0'),
                         list(feedbackwin.NEWS['4.5.0']))

    def test_links_and_texts(self):
        from questforge2 import guide, guidebook
        chapters = {c[0] for c in guidebook.CHAPTERS}
        try:
            for lang in ('de', 'en'):
                i18n.set_lang(lang)
                for items in feedbackwin.NEWS.values():
                    for nid, tour, chapter in items:
                        for part in ('title', 'text'):
                            key = f'news.{nid}.{part}'
                            self.assertNotEqual(i18n.t(key), key)
                        self.assertTrue(tour is None or tour in guide.TOURS)
                        self.assertIn(chapter, chapters)
                import types
                app = types.SimpleNamespace(show_enemy_levels=None,
                                            show_guide=None, timeline=None)
                for name, (title, steps) in guide.TOURS.items():
                    self.assertNotEqual(i18n.t(title), title)
                    for st in steps(app):
                        for part in ('title', 'text'):
                            key = st['key'] + '.' + part
                            self.assertNotEqual(i18n.t(key), key)
                    self.assertTrue(steps(app)[-1].get('final'))
        finally:
            i18n.set_lang('de')

    def test_guide_animations_and_tours(self):
        """Every ``![...](gNN)`` of the guide has its GIF in both languages,
        every ``[[tour:x]]`` is a tour."""
        import os
        from questforge2 import data, guide, guidebook
        seen = 0
        try:
            for lang in ('de', 'en'):
                i18n.set_lang(lang)
                for _cid, _titles, fn in guidebook.CHAPTERS:
                    for line in fn().split(chr(10)):
                        m = guidebook._IMAGE.match(line.strip())
                        if m:
                            seen += 1
                            p = data.resource_path(*guidebook.GIF_DIR, lang,
                                                   m.group(2) + '.gif')
                            self.assertTrue(os.path.exists(p), p)
                        m = guidebook._TOUR.match(line.strip())
                        if m:
                            self.assertIn(m.group(1), guide.TOURS)
        finally:
            i18n.set_lang('de')
        self.assertGreaterEqual(seen, 14)


class Session(unittest.TestCase):
    def test_exes(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp(prefix='qf2game_')
        try:
            for n in ('TwoWorldsExtended.exe', 'TwoWorlds.exe',
                      'TwoWorlds.exe.bak', 'TwoWorlds1 Mod Selector.exe',
                      '4gb_patch.exe'):
                open(os.path.join(d, n), 'wb').close()
            self.assertEqual(gamesession.game_exes(d),
                             ['TwoWorlds.exe', 'TwoWorldsExtended.exe'])
            s = gamesession.GameSession(d, None, 'Mine.wd')
            s.before('TwoWorlds.exe')
            s.after()
            text = s.text()
            self.assertIn('level header cache: MISSING', text)
            self.assertIn('project archive Mine.wd: not exported yet', text)
            self.assertIn('crash report: none', text)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(gamesession.game_exes(os.path.join(d, 'gone')), [])


if __name__ == '__main__':
    unittest.main()
