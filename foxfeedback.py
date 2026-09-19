"""Test results and bug reports of the TW1 tools (standard library only, so
every Python tool can take this one file along).

The server side is specified in FEEDBACK_ENDPUNKT_SPEZIFIKATION.md (Marco's
desktop, 2026-09-19) and lives at https://alchemy-fox.de/game/_feedback/:

- ``POST submit``       no key - a test result or a bug report, JSON
- ``GET summary.json``  no key - state of every test, known issues

There is NO key in here and there must never be one: everything a tool does
works without. Reading the reports is the maintainer's side.

Rules this module keeps for every tool:
- nothing is sent silently; the tool shows ``preview(payload)`` first
- user names in paths become ``<user>`` (``scrub``)
- logs are cut to the size the server takes, the END is kept (``clip``)
- a bug title is made by the tool from the error, never typed by the user
  (it becomes public in the known issues at once)
"""

import getpass
import hashlib
import json
import os
import platform
import re
import threading
import time
import urllib.error
import urllib.request
import uuid

BASE = 'https://alchemy-fox.de/game/_feedback/'
SCHEMA = 1
MAX_LOG = 120000
MAX_MESSAGE = 4000
MAX_TITLE = 120
TIMEOUT = 15


# -- text ---------------------------------------------------------------------

def scrub(text):
    """``text`` without the user's name: the home folder and every
    ``Users/<name>`` path part become ``<user>``."""
    text = str(text or '')
    names = set()
    try:
        names.add(getpass.getuser())
    except Exception:                  # no user name in this environment
        pass
    home = os.path.expanduser('~')
    if home and home != '~':
        names.add(os.path.basename(home.rstrip('/' + chr(92))))
    text = re.sub(r'(?i)([/\\]users[/\\])[^/\\\r\n"<>|]+', r'\1<user>', text)
    for name in sorted((n for n in names if n and len(n) > 2), key=len,
                       reverse=True):
        text = re.sub(re.escape(name), '<user>', text, flags=re.I)
    return text


def clip(text, limit=MAX_LOG):
    """At most ``limit`` characters, the end kept (the newest lines)."""
    text = str(text or '')
    if len(text) <= limit:
        return text
    head = '[... cut ...]' + chr(10)
    return head + text[-(limit - len(head)):]


def fingerprint(tool, error_key, message):
    """The same bug gives the same 40 hex characters on every PC: numbers,
    paths and quoted names are taken out of the message first."""
    msg = scrub(message).lower()
    msg = re.sub(r'[a-z]:[/\\][^\s"\']+', '<path>', msg)
    msg = re.sub(r'"[^"]*"|\'[^\']*\'', '<s>', msg)
    msg = re.sub(r'\d+', '#', msg)
    msg = re.sub(r'\s+', ' ', msg).strip()[:300]
    raw = f'{tool}|{error_key or ""}|{msg}'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def os_name():
    try:
        return f'{platform.system()} {platform.release()} ' \
               f'{platform.version()}'[:80]
    except Exception:
        return 'unknown'


def new_client_id():
    """Random per installation, says nothing about the person."""
    return uuid.uuid4().hex


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


# -- session log -----------------------------------------------------------------

class SessionLog:
    """What the tool did in this session, newest last; goes along with a
    report. Thread safe, bounded."""

    def __init__(self, limit=400):
        self.limit = limit
        self.lines = []
        self._lock = threading.Lock()

    def add(self, text):
        line = f'{time.strftime("%H:%M:%S")}  {str(text)[:500]}'
        with self._lock:
            self.lines.append(line)
            del self.lines[:-self.limit]

    def text(self):
        with self._lock:
            return chr(10).join(self.lines)


# -- payloads ----------------------------------------------------------------------

def _base(kind, tool, version, client_id, lang, message, log, game_log):
    return {'schema': SCHEMA, 'kind': kind, 'tool': tool, 'version': version,
            'client_id': client_id, 'lang': 'de' if lang == 'de' else 'en',
            'os': os_name(), 'created': now_iso(),
            'message': scrub(message)[:MAX_MESSAGE],
            'log': clip(scrub(log)), 'game_log': clip(scrub(game_log))}


def test_payload(tool, version, client_id, lang, test_id, passed,
                 message='', log='', game_log=''):
    p = _base('test', tool, version, client_id, lang, message, log, game_log)
    p.update(test_id=test_id, result='pass' if passed else 'fail')
    return p


def bug_payload(tool, version, client_id, lang, title, error_key='',
                error_text='', guide_ref='', message='', log='', game_log=''):
    """``title`` comes from the tool (error text in English or the key),
    ``message`` is what the user typed."""
    p = _base('bug', tool, version, client_id, lang, message, log, game_log)
    key = re.sub(r'[^A-Za-z0-9._-]', '', error_key or '')[:80]
    p.update(error_key=key, title=scrub(title).replace(chr(10), ' ')
             .strip()[:MAX_TITLE] or 'bug',
             fingerprint=fingerprint(tool, key, error_text or title),
             guide_ref=str(guide_ref or '')[:80])
    return p


def preview(payload):
    """Exactly what will be sent, as text for the user to read."""
    short = dict(payload)
    out = []
    for key in ('log', 'game_log'):
        body = short.pop(key, '')
        if body:
            out.append(f'--- {key} ({len(body)} characters) ---')
            out.append(body)
    return json.dumps(short, indent=2, ensure_ascii=False) + chr(10) \
        + chr(10).join(out)


# -- network -------------------------------------------------------------------------

class FeedbackError(Exception):
    """``code``: 'rate', 'closed', 'too_large', 'invalid', 'offline'."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code} {detail}'.strip())
        self.code = code
        self.detail = detail


def _agent(tool, version):
    return f'FoxFeedback/1 ({tool} {version})'


def submit(payload, base=BASE, timeout=TIMEOUT):
    """Send one report. Returns the id the server gave it."""
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        base + 'submit', data=body, method='POST',
        headers={'Content-Type': 'application/json; charset=utf-8',
                 'User-Agent': _agent(payload.get('tool'),
                                      payload.get('version'))})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            answer = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            info = json.loads(e.read().decode('utf-8'))
        except Exception:
            info = {}
        code = info.get('error') or {413: 'too_large', 429: 'rate',
                                     503: 'closed'}.get(e.code, 'invalid')
        raise FeedbackError(code, info.get('field') or str(e.code))
    except (OSError, ValueError) as e:
        raise FeedbackError('offline', str(e))
    if not answer.get('ok'):
        raise FeedbackError(answer.get('error') or 'invalid')
    return answer.get('id')


def fetch_summary(tool, version, base=BASE, timeout=TIMEOUT):
    """{'tests': {...}, 'issues': [...], 'accept': bool} of one tool, or
    None when the server cannot be reached."""
    req = urllib.request.Request(
        base + 'summary.json',
        headers={'Cache-Control': 'no-cache',
                 'User-Agent': _agent(tool, version)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode('utf-8'))
    except (OSError, ValueError):
        return None
    mine = (data.get('tools') or {}).get(tool) or {}
    return {'tests': mine.get('tests') or {},
            'issues': mine.get('issues') or [],
            'accept': bool(data.get('accept', True)),
            'updated': data.get('updated')}
