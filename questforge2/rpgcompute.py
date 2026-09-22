"""The RPGCompute template: the hero's experience curve and the values of
the enemies in one script (4.5.0).

``RPGCompute.eco`` is the script the engine asks for everything computed
per unit. tools/build_rpgcompute.py compiled the SDK source once with the
curve wrapped and a table per enemy unit hooked in (see there), after
checking that the untouched source gives exactly the script of Update16.wd.
The tool only writes numbers into that template:

- ``curve_site``: the percent of the experience curve (mov edx, imm32);
- ``active_site`` / ``floor_site``: ESG(active, floor) - active 0 makes
  the table cost nothing, floor 1 keeps a kill worth at least 0;
- ``table``: per unit the offsets of its 15 numbers (FIELDS), percent and
  amount for health base, strike pause, the four protections and the kill
  experience, the damage percent.

The script goes into ``Mods\\EnemyLevels.wd`` (class id 25, resource name
RPGCompute, a fresh GUID). It is only used when the game's RPGCompute.eco
is the one the template was built against.
"""

import hashlib
import json
import os
import struct

from . import data
from .questlimit import SEP, eco_body, wd_entries, wd_read_file

INNER = SEP.join(('Scripts', 'RPGCompute', 'RPGCompute.eco'))
RES = b'RPGCompute'
CLASS_ID = 25
SOURCE_WDS = ('Update16.wd', 'Update11-15.wd')
NEUTRAL_PERCENT = 100

_cache = {}


class TemplateError(Exception):
    pass


def load():
    """(meta, body) of the shipped template."""
    if 'meta' not in _cache:
        folder = data.resource_path('questforge2', 'assets', 'rpgcompute')
        try:
            with open(os.path.join(folder, 'rpgcompute.json'),
                      encoding='ascii') as f:
                meta = json.load(f)
            with open(os.path.join(folder, 'RPGCompute.eco.body'), 'rb') as f:
                body = f.read()
        except OSError as e:
            raise TemplateError(f'template missing: {e}')
        if hashlib.sha256(body).hexdigest() != meta['template_sha256']:
            raise TemplateError('template damaged')
        _cache['meta'], _cache['body'] = meta, body
    return _cache['meta'], _cache['body']


def fields():
    return tuple(load()[0]['fields'])


def units():
    return list(load()[0]['units'])


def neutral(field):
    return NEUTRAL_PERCENT if field.endswith('_p') else 0


def _sites():
    """Every offset the tool writes, for comparing bodies."""
    meta, _body = load()
    out = {meta['curve_site'], meta['active_site'], meta['floor_site']}
    for row in meta['table']:
        out.update(row)
    return out


def patch(curve=100, stats=None, floor=True):
    """The template with the curve percent and {unit: {field: value}}
    written in; units and fields left out stay neutral."""
    meta, body = load()
    out = bytearray(body)
    struct.pack_into('<i', out, meta['curve_site'], int(curve))
    names = meta['units']
    flds = meta['fields']
    active = False
    for i, name in enumerate(names):
        vals = (stats or {}).get(name) or {}
        for k, off in zip(flds, meta['table'][i]):
            v = int(vals.get(k, neutral(k)))
            if v != neutral(k):
                active = True
            struct.pack_into('<i', out, off, v)
    struct.pack_into('<i', out, meta['active_site'], 1 if active else 0)
    struct.pack_into('<i', out, meta['floor_site'], 1 if floor else 0)
    return bytes(out)


def read(body):
    """(curve, stats, floor) of a script built from the template, None when
    the body is something else (the game's script, another mod)."""
    try:
        meta, tpl = load()
    except TemplateError:
        return None
    if len(body) != len(tpl):
        return None
    # everything but the written numbers must be the template
    norm = bytearray(body)
    for off in _sites():
        norm[off:off + 4] = tpl[off:off + 4]
    if bytes(norm) != tpl:
        return None
    curve = struct.unpack_from('<i', body, meta['curve_site'])[0]
    floor = bool(struct.unpack_from('<i', body, meta['floor_site'])[0])
    stats = {}
    for i, name in enumerate(meta['units']):
        vals = {}
        for k, off in zip(meta['fields'], meta['table'][i]):
            v = struct.unpack_from('<i', body, off)[0]
            if v != neutral(k):
                vals[k] = v
        if vals:
            stats[name] = vals
    return curve, stats, floor


def game_script(game):
    """(archive, entry, body) of the game's own RPGCompute.eco."""
    for name in SOURCE_WDS:
        p = os.path.join(game, 'WDFiles', name)
        if not os.path.isfile(p):
            continue
        try:
            e = next((x for x in wd_entries(p) if x['path'] == INNER), None)
        except Exception:
            continue
        if e:
            return p, e, eco_body(wd_read_file(p, e))
    return None


def usable(game):
    """'ok', or why the script cannot be written for this game."""
    try:
        meta, _body = load()
    except TemplateError as e:
        return str(e)
    got = game_script(game) if game else None
    if got is None:
        return 'nosource'
    if hashlib.sha256(got[2]).hexdigest() != meta['game_sha256']:
        return 'version'
    return 'ok'


def blob(curve=100, stats=None, floor=True):
    """(inner, body, resource name, class id) for the mod archive."""
    return INNER, patch(curve, stats, floor), RES, CLASS_ID
