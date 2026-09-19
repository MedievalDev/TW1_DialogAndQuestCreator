"""Start Two Worlds from the test window and write down what can be seen
from outside (4.0.0). The game has no error log of its own - a wrong marker
just means "nothing happens" - so the report of a test carries:

- before the start: the mods switched on (name, size, time), the level
  header cache (time, number of maps, who wins the project's tiles, whether
  the markers placed in the tool are in it), the contents of the project's
  exported archive, the program that is started;
- the session: start, end, run time, exit code when it is ours, whether a
  crash report appeared;
- afterwards: new saves and screenshots (name and time only), new lines of
  log files in the game folder (an extender writes some), new crash reports
  (name and first lines).

Text only; foxfeedback scrubs user names and cuts it to size.
"""

import os
import subprocess
import threading
import time

from . import export, lhcache, mods, placed

NL = chr(10)
SAVES = os.path.join(os.path.expanduser('~'), 'Saved Games',
                     'Two Worlds Saves')
CRASH_DIRS = ('TWSECrashLogs',)
APPEAR_SECONDS = 90


def game_exes(game_dir):
    """Programs in the game folder that start the game, the plain one
    first (no backups, no patchers)."""
    out = []
    try:
        names = os.listdir(game_dir)
    except OSError:
        return out
    for n in names:
        low = n.lower()
        if low.startswith('twoworlds') and low.endswith('.exe') \
                and 'mod selector' not in low:
            out.append(n)
    return sorted(out, key=lambda n: (n.lower() != 'twoworlds.exe', n.lower()))


def _stamp(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


def _listing(folder):
    """{name: (size, mtime)} of the files directly in ``folder``."""
    out = {}
    try:
        for n in os.listdir(folder):
            p = os.path.join(folder, n)
            if os.path.isfile(p):
                st = os.stat(p)
                out[n] = (st.st_size, st.st_mtime)
    except OSError:
        pass
    return out


class GameSession:
    def __init__(self, game_dir, project=None, archive_name=None):
        self.game = game_dir
        self.project = project
        self.archive = archive_name
        self.lines = []
        self.state = 'idle'          # idle, waiting, running, ended, failed
        self.started = self.ended = None
        self._logs = self._saves = self._crashes = None
        self._proc = None

    def add(self, text=''):
        self.lines.append(text)

    def text(self):
        return NL.join(self.lines)

    # -- before ---------------------------------------------------------------

    def before(self, exe):
        a = self.add
        a(f'== before the start  {_stamp(time.time())}')
        a(f'program: {exe}')
        active = sorted(lhcache.active_mods())
        a(f'mods switched on: {len(active)}')
        folder = os.path.join(self.game, 'Mods')
        for name, (size, mt) in sorted(_listing(folder).items()):
            if name.lower() in active:
                a(f'  {name}  {size} bytes  {_stamp(mt)}')
        missing = [n for n in active
                   if n not in {x.lower() for x in _listing(folder)}]
        if missing:
            a('  switched on but not in the Mods folder: ' + ', '.join(missing))
        self._cache_state()
        self._archive_state()
        self._logs = {n: s for n, (s, _m) in _listing(self.game).items()
                      if n.lower().endswith('.log')}
        self._saves = _listing(SAVES)
        self._crashes = {d: set(_listing(os.path.join(self.game, d)))
                         for d in CRASH_DIRS}

    def _cache_state(self):
        a = self.add
        path = os.path.join(self.game, lhcache.LHC_FILE)
        if not os.path.isfile(path):
            a('level header cache: MISSING')
            return
        try:
            with open(path, 'rb') as f:
                cache = lhcache.parse(f.read())
        except Exception as e:
            a(f'level header cache: unreadable ({e})')
            return
        a(f'level header cache: {len(cache)} maps, written '
          f'{_stamp(os.path.getmtime(path))}')
        try:
            fresh = lhcache.build(self.game)[0]
            with open(path, 'rb') as f:
                a('  matches what is installed now: '
                  + ('yes' if f.read() == fresh else 'NO - rebuild it'))
        except Exception as e:
            a(f'  could not compare with the installed maps ({e})')
        if self.project is None:
            return
        import tw1_lnd
        try:
            src = lhcache.sources(self.game)
        except OSError:
            src = {}
        by_tile = {}
        for p in placed.placements(self.project):
            by_tile.setdefault(p['tile'], []).append(p)
        tiles = set(by_tile) | placed.fill_tiles(self.project)
        for tile in sorted(tiles):
            inner = mods.lnd_of_tile(tile)
            head = next((h for k, h in cache.items()
                         if k.lower() == inner.lower()), None)
            winner = src.get(inner.lower())
            a(f'  tile {tile}: wins {os.path.basename(winner[2]) if winner else "-"}')
            if head is None:
                a('    NOT in the cache')
                continue
            have = tw1_lnd.markers(head)
            for p in by_tile.get(tile, []):
                ok = int(p['num']) in have.get(p['name'], set())
                a(f"    {p['name']} {p['num']} at {p['x']},{p['y']},{p['z']}: "
                  + ('in the cache' if ok else 'MISSING in the cache'))

    def _archive_state(self):
        a = self.add
        if not self.archive:
            return
        path = os.path.join(self.game, 'Mods', self.archive)
        if not os.path.isfile(path):
            a(f'project archive {self.archive}: not exported yet')
            return
        st = os.stat(path)
        a(f'project archive {self.archive}: {st.st_size} bytes '
          f'{_stamp(st.st_mtime)}')
        try:
            for e in mods.wd_directory(path):
                a(f'  {e.path}  {e.rlen}')
        except Exception as e:
            a(f'  unreadable ({e})')

    # -- run ------------------------------------------------------------------------

    def start(self, exe_name, on_change=None):
        """Start the game and watch it in a thread; ``on_change(state)`` is
        called from that thread."""
        exe = os.path.join(self.game, exe_name)
        self.before(exe_name)
        try:
            self._proc = subprocess.Popen([exe], cwd=self.game)
        except OSError as e:
            self.add(f'could not start: {e}')
            self.state = 'failed'
            return False
        self.started = time.time()
        self.state = 'waiting'
        self.add(f'== started  {_stamp(self.started)}')
        threading.Thread(target=self._watch, args=(on_change,),
                         daemon=True).start()
        return True

    def _watch(self, on_change):
        def tell():
            if on_change:
                try:
                    on_change(self.state)
                except Exception:          # the window may be gone
                    pass
        # a launcher may end at once and the real game appear a bit later
        seen = False
        while time.time() - self.started < APPEAR_SECONDS:
            if export.game_running():
                seen = True
                break
            if self._proc.poll() is not None and \
                    time.time() - self.started > 20:
                break
            time.sleep(1.5)
        if not seen:
            self.add('the game process never appeared')
            self.state = 'failed'
            self.after()
            tell()
            return
        self.state = 'running'
        tell()
        while export.game_running():
            time.sleep(2)
        self.ended = time.time()
        self.state = 'ended'
        self.after()
        tell()

    # -- after ---------------------------------------------------------------------

    def after(self):
        a = self.add
        end = self.ended or time.time()
        a(f'== after the game  {_stamp(end)}')
        if self.started:
            a(f'run time: {int(end - self.started)} s')
        code = self._proc.poll() if self._proc else None
        if code is not None:
            a(f'exit code of the started program: {code}')
        new = {n: v for n, v in _listing(SAVES).items()
               if n not in (self._saves or {})
               or v[1] > (self._saves or {}).get(n, (0, 0))[1]}
        a(f'new saves and screenshots: {len(new)}')
        for n, (_s, mt) in sorted(new.items(), key=lambda kv: kv[1][1])[-20:]:
            a(f'  {n}  {_stamp(mt)}')
        crashed = False
        for d, old in (self._crashes or {}).items():
            folder = os.path.join(self.game, d)
            for n in sorted(set(_listing(folder)) - old):
                crashed = True
                a(f'NEW CRASH REPORT {d}/{n}')
                a(self._read(os.path.join(folder, n), 0, 3000, indent='    '))
        a('crash report: ' + ('YES' if crashed else 'none'))
        for n, (size, _mt) in sorted(_listing(self.game).items()):
            if not n.lower().endswith('.log'):
                continue
            old = (self._logs or {}).get(n, 0)
            if size < old:
                old = 0                       # the file was started anew
            if size > old:
                a(f'-- new in {n} --')
                a(self._read(os.path.join(self.game, n), old, 40000))

    @staticmethod
    def _read(path, offset, limit, indent=''):
        try:
            with open(path, 'rb') as f:
                f.seek(offset)
                raw = f.read()
        except OSError as e:
            return f'{indent}(unreadable: {e})'
        text = raw[-limit:].decode('utf-8', 'replace')
        return NL.join(indent + ln for ln in text.splitlines())
