"""Test run in the game (4.5.0, Marco 2026-09-22: "Testlauf-Knopf").

A TEST BUILD of the mod: in a NEW game the hero lands next to the giver of
the quest under test and the quest is unlocked - no ride through half the
world for every test.

The starter is a hidden quest (no giver, not in the journal) hung on the
game's first quest Q_3 (the goblin fight in the temple, FC CLEAR_AREA 3
E1) with two lines:

    AOQ TAKE ENABLE Q_<starter>    Q_3 is enabled when a new game starts
    AOQ SOLVE SOLVE Q_<starter>    ... and solved after the two goblins

and it jumps twice, the second time only if the first one got lost:

    ACTION HERO_TELEPORT_DELAYED ENABLE <ticks> <marker> <tile> <angle>
    ACTION HERO_TELEPORT_DELAYED SOLVE 30 <marker> <tile> <angle>
    AOQ PROMOTE TAKE Q_<quest>     (as often as its enable level)

The first test build (2026-09-22) jumped at once and the opening scene put
the hero back on his start place; the delay counts game ticks (30 a
second, PQuestActions.ech GetGameTick - the Kira campaign's "2" was a
fifteenth of a second). The ticks stand still during the opening scene:
with 450 the hero landed 15 s after it was skipped (in the game
2026-09-22, Kunibert's talk started by itself and the quest was taken). Who landed elsewhere never solves Q_3 there, so
there is no second jump; who is still in the temple gets it after the
goblins. From the SDK (PQuests.ec): TakeQuest of a disabled quest enables
it, a quest without giver is taken at once (actions and AOQ on TAKE),
then the actions on ENABLE run; SolveQuest runs the actions on SOLVE
(retail Q_15 jumps the hero that way). Enable level 2: StartQuests
promotes every loaded quest once in a new game, the starter must not
start by itself. A loaded save keeps its own quest states: the starter
only acts in a new game.

No NPC_CREATE: once the quest is enabled the engine creates its giver at
MARKER_QUEST_START (ActivateQuestGiver/CreateQuestGiver), a second one
could stand next to it (Q_385 creates Kunibert that way, it has no
NPC_CREATE of its own). ActionTeleportHero moves only heroes that took the
starter and places them at height 0, the engine finds the ground.

HERO_TELEPORT_DELAYED reads MARKER_QUEST_TELEPORT only, and the game has 36
of them on 15 tiles: 119 of 222 giver markers have none on their tile, the
others one at a median 5685 units (256 units per cell; measured
2026-09-22). A teleport marker within NEAR of the giver is used when there
is one, else one is placed next to the giver (placed.py, ``quest`` =
TEST_TAG) and goes into the test build only.

Everything of the test lives in the starter block and the two Q_3 lines
(strip_quests takes them out); the project records the starter
(``test_build``) and every export that is not a test takes it and the
marker out again, "export this quest" and "files only" included.
"""

import math
import time

import tw1_lnd
import tw1_qtx

from . import data, mods, placed
from .lndmap import TILE_UNITS

TEST_TAG = 'test'           # placements of the test build
NEAR = 1500                 # units: an existing teleport marker this close
RINGS = (180, 300, 450)     # units around the giver for a new marker
DELAY_START = 30 * 15       # game ticks (30 a second) after the start
DELAY = 30                  # after the goblins
FIRST_QUEST = 3             # the goblin fight at the start of the game
STARTER_LEVEL = 2           # not enabled by StartQuests, only by Q_3
TELEPORT = 'MARKER_QUEST_TELEPORT'


# ---------------------------------------------------------------------------
# where to

def giver_of(quest):
    """The NPC the hero should land next to: the giver, else the first NPC
    speaking in the dialog."""
    if isinstance(quest.giver, int):
        return quest.giver
    for n in quest.graph.get('nodes', {}).values():
        if n.get('type') == 'npc' and isinstance(n.get('speaker'), int):
            return n['speaker']
    return None


def npc_place(project, index, npc):
    """(tile, marker number, name) of an NPC: a speaker the project brings
    first, then the quest file of the game and the mods."""
    for q in project.quests:
        s = q.speaker(npc)
        if s and s.get('new') and s.get('tile'):
            return (s['tile'].upper(), int(s.get('marker') or npc),
                    s.get('name') or f'NPC_{npc}')
    rec = index.npc(npc) if index else None
    if rec and rec.get('tile') not in (None, '', '(null)') and \
            rec.get('marker') is not None:
        return rec['tile'].upper(), int(rec['marker']), rec.get('name')
    return None


def tile_markers(project, modset, game_dir, tile):
    """{marker name: [(id, x, y, z, angle)]} of the tile as the game will
    see it: the base the project builds on plus the markers placed in the
    tool (the test marker left out)."""
    out = {}
    body, _phx, _src = placed.base_of(project, modset, game_dir, tile)
    if body:
        for name, lst in tw1_lnd.markers_full(body).items():
            out[name] = [(i, p[0], p[1], p[2], p[3]) for i, p in lst]
    for p in placed.placements(project):
        if p['tile'].upper() == tile and p.get('quest') != TEST_TAG:
            out.setdefault(p['name'], []).append(
                (int(p['num']), p['x'], p['y'], p['z'], p.get('angle', 0)))
    return out, body


def plan(project, index, modset, game_dir, quest, limit):
    """What a test run of ``quest`` does: {'quest', 'npc', 'name', 'tile',
    'spot': (x, y, z) or None, 'marker': number or None, 'dist', 'new':
    placement to add or None, 'promote', 'starter',
    'problem': message key or None}."""
    spec = {'quest': quest.id, 'npc': None, 'name': None, 'tile': None,
            'spot': None, 'marker': None, 'dist': None, 'new': None,
            'promote': max(0, int(quest.enable_level or 0)),
            'group': quest.group or 0, 'problem': None,
            'starter': starter_id(index, project, limit)}
    if spec['starter'] is None:
        spec['problem'] = 'testrun.noid'
        return spec
    npc = giver_of(quest)
    if npc is None:
        spec['problem'] = 'testrun.nogiver'
        return spec
    spec['npc'] = npc
    where = npc_place(project, index, npc)
    if where is None:
        spec['problem'] = 'testrun.noplace'
        return spec
    tile, num, name = where
    spec['tile'], spec['name'] = tile, name
    markers, body = tile_markers(project, modset, game_dir, tile)
    start = next((m for m in markers.get(mods.NPC_MARKER, [])
                  if m[0] == num), None)
    if start is None:
        spec['problem'] = 'testrun.nomarker'
        return spec
    spot = start[1:4]
    spec['spot'] = spot
    near = sorted((math.hypot(m[1] - spot[0], m[2] - spot[1]), m[0])
                  for m in markers.get(TELEPORT, []))
    if near and near[0][0] <= NEAR:
        spec['dist'], spec['marker'] = int(near[0][0]), near[0][1]
        return spec
    if body is None:
        spec['problem'] = 'testrun.nomap'
        return spec
    x, y, z = free_spot(project, modset, game_dir, tile, spot)
    taken = [p for p in placed.placements(project)
             if p.get('quest') != TEST_TAG]
    number = placed.free_number(TELEPORT, tile, body, taken)
    spec['new'] = {'name': TELEPORT, 'num': number, 'tile': tile,
                   'x': int(x), 'y': int(y), 'z': int(z), 'angle': 0,
                   'quest': TEST_TAG}
    spec['marker'] = number
    spec['dist'] = int(math.hypot(x - spot[0], y - spot[1]))
    return spec


def free_spot(project, modset, game_dir, tile, spot):
    """(x, y, z): a walkable place a few steps from the giver (the hero must
    not land in the NPC or in a wall). Height: the ground there, but never
    below the giver - a marker under the floor of a room is the known
    failure (skill tw1-modding, F01_1), from a bit above the hero just
    lands."""
    try:
        ter = placed.terrain(project, modset, game_dir, tile)
    except Exception:                    # the giver's place then
        ter = None
    x0, y0, z0 = spot
    if ter is None:
        return x0 + RINGS[0], y0, z0
    for r in RINGS:
        for k in range(8):
            a = k * math.pi / 4
            x, y = x0 + r * math.cos(a), y0 + r * math.sin(a)
            if 0 < x < TILE_UNITS and 0 < y < TILE_UNITS and \
                    ter.passable(x, y) is not False:
                return x, y, max(z0, ter.height(x, y))
    return x0 + RINGS[0], y0, z0


def starter_id(index, project, limit):
    """The highest quest number below the limit nobody uses. The starters
    of our own earlier test builds count as free: the index reads them
    from the mod in the game, and they leave it again anyway."""
    used = {q.id for q in project.quests}
    if index is not None:
        used |= {int(k) for k in index.quests}
    used -= starters(project) - {q.id for q in project.quests}
    top = data.max_quest_id(limit)
    for n in range(top, data.MIN_QUEST_ID - 1, -1):
        if n not in used:
            return n
    return None


# ---------------------------------------------------------------------------
# the starter in the quest file

def starter_block(spec):
    subs = []
    if spec.get('marker') is not None:
        for when, ticks in (('ENABLE', DELAY_START), ('SOLVE', DELAY)):
            subs.append(tw1_qtx.sub_action('HERO_TELEPORT_DELAYED', when,
                                           ticks, spec['marker'],
                                           spec['tile'], 0))
    for _i in range(int(spec.get('promote') or 0)):
        subs.append(tw1_qtx.sub_aoq('PROMOTE', 'TAKE', f"Q_{spec['quest']}"))
    q = tw1_qtx.make_quest(spec['starter'], subs, enable_level=STARTER_LEVEL,
                           group=spec.get('group') or 0, add_to_log=False)
    return q.emit()


def hook_lines(spec):
    return [f"AOQ TAKE ENABLE Q_{spec['starter']}",
            f"AOQ SOLVE SOLVE Q_{spec['starter']}"]


def add_starter(text, spec):
    """The quest file with the starter and its line in Q_3."""
    from . import export
    text = export.strip_quests(text, {int(spec['starter'])})
    if not text.endswith('\n'):
        text += '\n'
    text += starter_block(spec)
    for line in hook_lines(spec):
        text = export.insert_aoq(text, FIRST_QUEST, line)
    return text


def starters(project):
    """Starter numbers of test builds still in the game's copy of the mod."""
    tb = project.extra.get('test_build') or {}
    return {int(n) for n in tb.get('starters', [])}


def remember(project, spec, archive):
    tb = project.extra.setdefault('test_build', {})
    tb['starters'] = sorted(starters(project) | {int(spec['starter'])})
    tb.update(quest=spec['quest'], archive=archive,
              time=time.strftime('%Y-%m-%d %H:%M'))


def forget(project):
    project.extra.pop('test_build', None)


def active(project):
    return bool(project is not None and project.extra.get('test_build'))


# ---------------------------------------------------------------------------
# the marker

def set_marker(project, spec):
    """Put the test marker in (replacing an older one). True when the
    placements changed."""
    lst = placed.placements(project)
    before = [p for p in lst if p.get('quest') == TEST_TAG]
    lst[:] = [p for p in lst if p.get('quest') != TEST_TAG]
    if spec.get('new'):
        lst.append(dict(spec['new']))
    return before != [p for p in lst if p.get('quest') == TEST_TAG]


def clear_marker(project):
    """Take the test marker out again. True when there was one."""
    lst = placed.placements(project)
    n = len(lst)
    lst[:] = [p for p in lst if p.get('quest') != TEST_TAG]
    return len(lst) != n


def game_exe(game_dir, cfg):
    from . import gamesession
    exes = gamesession.game_exes(game_dir or '')
    want = cfg.get('game_exe')
    return want if want in exes else (exes[0] if exes else None), exes


def describe(spec, t):
    """Lines for the dialog."""
    out = [t('testrun.target', name=spec['name'] or f"NPC_{spec['npc']}",
             npc=spec['npc'], tile=spec['tile'])]
    if spec.get('new'):
        out.append(t('testrun.newmarker', num=spec['marker'],
                      tile=spec['tile'], d=spec['dist'] or 0))
    else:
        out.append(t('testrun.oldmarker', num=spec['marker'],
                      tile=spec['tile'], d=spec['dist'] or 0))
    if spec.get('promote'):
        out.append(t('testrun.unlock', id=spec['quest']))
    out.append(t('testrun.starter', id=spec['starter']))
    return out

