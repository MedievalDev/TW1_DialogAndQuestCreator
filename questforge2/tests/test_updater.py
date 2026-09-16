"""Update check and self-update helpers (no network)."""

import hashlib
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import updater  # noqa: E402

PAYLOAD = {
    'tag_name': 'v3.4.1', 'html_url': 'https://github.com/x/releases/tag/v3.4.1',
    'body': 'Notes\n\n---\n\nDeutsch', 'draft': False, 'prerelease': False,
    'assets': [{'name': 'other.zip', 'size': 1},
               {'name': 'TW1QuestCreator.exe', 'size': 5,
                'browser_download_url': 'https://example/exe',
                'digest': 'sha256:' + hashlib.sha256(b'hello').hexdigest()}]}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Versions(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(updater.parse_version('v3.3.2'), (3, 3, 2))
        self.assertEqual(updater.parse_version('3.4'), (3, 4, 0))
        self.assertIsNone(updater.parse_version('latest'))
        self.assertTrue(updater.is_newer('v3.10.0', '3.9.9'))
        self.assertFalse(updater.is_newer('v3.3.2', '3.3.2'))
        self.assertFalse(updater.is_newer('v3.3.1', '3.3.2'))
        self.assertFalse(updater.is_newer('nightly', '3.3.2'))

    def test_release_info(self):
        info = updater.release_info(PAYLOAD)
        self.assertEqual(info['version'], '3.4.1')
        self.assertEqual(info['url'], 'https://example/exe')
        self.assertEqual(info['sha256'], hashlib.sha256(b'hello').hexdigest())
        no = updater.release_info({'tag_name': 'v1.0.0', 'assets': []})
        self.assertIsNone(no['url'])
        self.assertIsNone(no['sha256'])


class Download(unittest.TestCase):
    def test_verified_and_mismatch(self):
        info = updater.release_info(PAYLOAD)
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, 'TW1QuestCreator.exe.new')
            seen = []
            updater.download(info, dest, lambda a, b: seen.append((a, b)),
                             opener=lambda req, timeout: _Resp(b'hello'))
            self.assertEqual(open(dest, 'rb').read(), b'hello')
            self.assertEqual(seen[-1], (5, 5))
            bad = os.path.join(d, 'bad.new')
            with self.assertRaises(ValueError):
                updater.download(info, bad,
                                 opener=lambda req, timeout: _Resp(b'evil!'))
            self.assertFalse(os.path.exists(bad))
            self.assertFalse(os.path.exists(bad + '.part'))
            nodigest = dict(info, sha256=None)
            with self.assertRaises(ValueError):
                updater.download(nodigest, bad,
                                 opener=lambda req, timeout: _Resp(b'hello'))

    def test_swap_script(self):
        s = updater.swap_script(r'C:\x\TW1QuestCreator.exe',
                                r'C:\x\TW1QuestCreator.exe.new', 4711)
        self.assertIn('tasklist.exe" /FI "PID eq 4711"', s)
        self.assertIn('find.exe" " 4711 "', s)
        self.assertLess(s.index('PID eq 4711'), s.index('move /y'))
        self.assertIn(r'move /y "C:\x\TW1QuestCreator.exe" '
                      r'"C:\x\TW1QuestCreator.exe.old"', s)
        self.assertIn(r'start "" "C:\x\TW1QuestCreator.exe"', s)
        self.assertIn('\r\n', s)

    def test_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, 'a.exe')
            for suffix in ('.old', '.new.part'):
                open(exe + suffix, 'wb').close()
            updater.cleanup_old(exe)
            self.assertEqual(os.listdir(d), [])


if __name__ == '__main__':
    unittest.main()
