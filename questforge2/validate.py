"""Rule check before export (plan section 8).

``validate_quest`` returns ``(errors, warnings)``, each a list of
``(message, target)``. ``target`` is a node id of the quest graph, the
string ``'qaction:<i>'`` for an action without dialog, or None for quest
fields. Errors block the export, warnings do not.

Plan rule "edge across level borders" was dropped: the SDK check (plan 6.3)
showed such edges are normal retail practice (decision 12.18).
"""

from . import model
from .data import MIN_QUEST_ID, RETAIL_LIMIT
from .model import entry_id

INTERIOR_HINT = '_'


def _t_default(key, **fmt):
    return key + (' ' + str(fmt) if fmt else '')


def all_actions(quest):
    """[(action dict, when, target)]: docked first, then without dialog."""
    g = quest.graph
    out = [(n, model.action_when(g, n), nid)
           for nid, n in quest.graph_actions()]
    out += [(a, a.get('when'), f'qaction:{i}')
            for i, a in enumerate(quest.actions)]
    return out


def _field(t, e):
    """Readable text for a model.FieldError."""
    if isinstance(e, model.FieldError):
        return t('val.field.' + e.reason, field=t('field.' + e.key),
                 value=e.value)
    return str(e)


def _norm(s):
    return ' '.join((s or '').split()).lower()


def _npc_id(v):
    try:
        return int(str(v).replace('NPC_', ''))
    except (TypeError, ValueError):
        return None


def _talk_target(index, project, qid):
    """TALK/FIND_TALK target NPC id of another quest, or None."""
    if project:
        q = project.quest_by_id(qid)
        if q:
            task = q.task()
            if task.get('fc') in ('TALK', 'FIND_TALK'):
                return _npc_id(task['args'].get('npc'))
            return None
    info = index.quest(qid) if index else None
    fc = info.get('fc') if info else None
    if fc and fc[0] in ('TALK', 'FIND_TALK') and len(fc) > 1:
        return _npc_id(fc[1])
    return None


class Msg(str):
    """A message that remembers its text key (4.0.0): the error window
    points to the guide chapter where the solution may stand and a bug
    report names the error without the user's data."""
    key = ''


def keyed(t):
    if getattr(t, '_keyed', False):
        return t

    def wrapped(key, **fmt):
        m = Msg(t(key, **fmt))
        m.key = key
        return m
    wrapped._keyed = True
    return wrapped


# longest prefix wins; everything else goes to the trouble shooting chapter
GUIDE_REFS = (
    ('val.mod', 'mods'), ('warn.mod', 'mods'),
    ('val.tile', 'markers'), ('warn.marker', 'markers'),
    ('warn.giver', 'markers'), ('val.location', 'markers'),
    ('warn.location', 'markers'), ('warn.walk', 'markers'),
    ('warn.teleport', 'markers'), ('warn.cleararea', 'markers'),
    ('warn.kill', 'markers'), ('warn.showloc', 'markers'),
    ('warn.todo', 'quests'),
    ('val.npc', 'npcs'), ('warn.npc', 'npcs'), ('val.giver', 'npcs'),
    ('val.speaker', 'npcs'), ('warn.talk', 'npcs'),
    ('val.link', 'links'), ('val.enable', 'links'), ('warn.enable', 'links'),
    ('val.after', 'conditions'), ('warn.level', 'conditions'),
    ('val.task', 'tasks'), ('val.action', 'actions'),
    ('val.opcode', 'actions'),
    ('val.id', 'quests'), ('warn.id', 'quests'), ('warn.group', 'quests'),
    ('val.offer', 'quests'), ('val.cr', 'quests'),
    ('warn.question', 'quests'), ('val.journal', 'quests'),
)


def guide_ref(key):
    """Guide chapter for a message key ('' -> trouble shooting)."""
    best = ''
    chapter = 'trouble'
    for prefix, ch in GUIDE_REFS:
        if str(key or '').startswith(prefix) and len(prefix) > len(best):
            best, chapter = prefix, ch
    return chapter


def validate_quest(quest, index=None, project=None, archive=None, t=None,
                   modset=None):
    t = keyed(t or _t_default)
    E, W = [], []
    g = quest.graph
    nodes = g['nodes']
    qid = quest.id
    own = not quest.retail
    task = quest.task()
    actions = all_actions(quest)
    qtx_changed = own
    if not own:
        from . import retail
        qtx_changed = retail.changed(quest)

    # -- quest fields -----------------------------------------------------------
    if own:
        limit = getattr(index, 'quest_limit', None) or RETAIL_LIMIT
        if not isinstance(qid, int) or qid < MIN_QUEST_ID:
            E.append((t('val.id.range', id=qid, last=limit - 1), None))
        elif qid >= limit:
            # above the limit the engine turns the quest into quest 0
            E.append((t('val.id.limit', id=qid, limit=limit), None))
        elif qid >= RETAIL_LIMIT:
            W.append((t('warn.id.limit600', id=qid), None))
        elif index and index.quest(qid):
            src = index.quest(qid)['source']
            if src == 'retail' or (archive and src != archive):
                E.append((t('val.id.taken', id=qid, src=src), None))
            else:
                W.append((t('val.id.replace', id=qid, src=src), None))
        for link in [x for x in quest.links if isinstance(x, dict)]:
            tgt = link.get('quest')
            if link.get('type') not in model.AOQ_TYPES:
                E.append((t('val.link.type', type=link.get('type')), None))
            if link.get('event') not in model.AOQ_TRIGGERS:
                E.append((t('val.link.event', event=link.get('event')), None))
            if not isinstance(tgt, int) or tgt == qid:
                E.append((t('val.link.target', id=tgt), None))
            elif tgt >= limit:
                E.append((t('val.link.limit', id=tgt, limit=limit), None))
            elif index and not index.quest(tgt) and not (
                    project and project.quest_by_id(tgt)):
                # ParseQuestNumber gives quest 0: the line does nothing
                E.append((t('val.link.unknown', id=tgt), None))
        # templates mark the places to fill in with TODO
        head = [v for v in (quest.title, *quest.journal.values())
                if 'TODO' in (v or '')]
        if head:
            W.append((t('warn.todo.head', n=len(head)), None))
        for nid, n in nodes.items():
            k = sum(1 for ln in (n.get('lines') or [])
                    if 'TODO' in (ln.get('text') or ''))
            if k:
                spk = quest.speaker(n.get('speaker'))
                who = spk['name'] if spk else t('node.player')
                W.append((t('warn.todo.node', n=k, who=who,
                            state=t('state.' + str(n.get('state')))), nid))
        if project and sum(1 for q in project.quests if q.id == qid) > 1:
            E.append((t('val.id.twice', id=qid), None))
        if not (quest.title or '').strip():
            E.append((t('val.title'), None))
        for key in ('take', 'solve', 'close'):
            if not (quest.journal.get(key) or '').strip():
                E.append((t('val.journal.' + key), None))
        if quest.giver is None:
            E.append((t('val.giver'), None))
        elif not isinstance(quest.giver, int):
            # a placeholder ("Lector 3") is no NPC: GIVER NPC_L3 fails
            E.append((t('val.giver.int', id=quest.giver), None))
        from .mpmerge import MAX_NPC_ID
        if own and isinstance(quest.giver, int) and quest.giver > MAX_NPC_ID:
            E.append((t('val.npc.limit', id=quest.giver, max=MAX_NPC_ID),
                      None))
        for s in quest.speakers:
            if own and s.get('new') and isinstance(s.get('id'), int) \
                    and s['id'] > MAX_NPC_ID:
                E.append((t('val.npc.limit', id=s['id'], max=MAX_NPC_ID),
                          None))
        from .mpmerge import current_todo
        from .mods import editor_name
        for item in current_todo(quest):
            if not item.get('done'):
                W.append((t('warn.marker.todo',
                            name=editor_name(item.get('name')),
                            num=item.get('num'), tile=item.get('tile')),
                          None))
        if index and str(quest.group) not in index.groups:
            W.append((t('warn.group', g=quest.group), None))
    for text in [quest.title] + list(quest.journal.values()):
        if '\r' in (text or ''):
            E.append((t('val.cr'), None))
            break

    # -- speakers -----------------------------------------------------------------
    for spk in quest.speakers:
        if spk.get('new') and index and isinstance(spk['id'], int) and \
                index.npc(spk['id']):
            E.append((t('val.speaker.taken', id=spk['id'],
                        name=index.npc(spk['id'])['name']), None))

    # -- task -----------------------------------------------------------------------
    fc = task.get('fc')
    if fc and fc not in model.FC_SPECS:
        E.append((t('val.opcode', op='FC ' + str(fc)), model.TASK_ID))
    elif own and not fc:
        E.append((t('val.task'), model.TASK_ID))
    elif fc and qtx_changed:
        try:
            model.op_tokens(model.FC_SPECS[fc], task['args'])
        except model.ModelError as e:
            E.append((t('val.task.field', err=_field(t, e)), model.TASK_ID))
    if fc == 'CLEAR_AREA':
        party = str(task['args'].get('party'))
        if not any(a.get('verb') == 'ENEMY_CREATE'
                   and str(a['args'].get('party')) == party
                   for a, _, _ in actions):
            W.append((t('warn.cleararea'), model.TASK_ID))
        if party not in ('18', '19', '20', '21', '22', '23'):
            W.append((t('warn.cleararea.party'), model.TASK_ID))
    if fc in ('TALK', 'FIND_TALK'):
        target = _npc_id(task['args'].get('npc'))
        if target is not None and target == quest.giver:
            W.append((t('warn.talk.giver'), model.TASK_ID))
        for c in quest.conditions_list():
            if c.get('cond') == 'after' and target is not None and \
                    _talk_target(index, project, c.get('quest')) == target:
                W.append((t('warn.talk.twice', q=c.get('quest')),
                          model.TASK_ID))
    if fc in ('KILL', 'FIND_KILL') and index:
        target = _npc_id(task['args'].get('npc'))
        if target is not None and index.npc(target):
            W.append((t('warn.kill.questnpc'), model.TASK_ID))

    # -- conditions -----------------------------------------------------------------
    afters = []
    for nid, c in nodes.items():
        if c.get('type') != 'condition':
            continue
        if c.get('cond') not in ('after', 'level', 'guild'):
            E.append((t('val.opcode', op='condition ' + str(c.get('cond'))),
                      nid))
        elif c.get('cond') == 'after':
            afters.append((nid, c))
    if own:
        if not afters:
            E.append((t('val.after'), entry_id('first')))
        for nid, c in afters:
            pq = c.get('quest')
            known = (index and index.quest(pq)) or (
                project and project.quest_by_id(pq))
            limit = getattr(index, 'quest_limit', None) or RETAIL_LIMIT
            if not isinstance(pq, int) or not known:
                E.append((t('val.after.quest', id=pq), nid))
            elif pq >= limit:
                # a multiplayer quest (700+) never runs in single player
                E.append((t('val.link.limit', id=pq, limit=limit), nid))
            elif index and index.quest(pq) and archive and not (
                    project and project.quest_by_id(pq)):
                # the AOQ line goes into the predecessor's block of the qtx
                # the export starts from: a quest of another mod is missing
                src = index.quest(pq)['source']
                if src not in ('retail', archive):
                    E.append((t('val.after.mod', id=pq, src=src,
                                target=archive), nid))
            if c.get('event') not in model.AOQ_EVENTS:
                E.append((t('val.opcode', op='AOQ ' + str(c.get('event'))),
                          nid))

    # -- dialog -----------------------------------------------------------------------
    if own:
        first = model.edge_from(g, entry_id('first'), 0)
        if not first:
            E.append((t('val.offer.empty'), entry_id('first')))
        elif nodes[first[2]]['type'] != 'npc':
            E.append((t('val.offer.npc'), first[2]))
        for st in ('running', 'closed'):
            if not model.edge_from(g, entry_id(st), 0):
                W.append((t('warn.level.empty', level=t('state.' + st)),
                          entry_id(st)))
    targets = {}
    for frm, port, to in g['edges']:
        targets[(frm, port)] = to
    for nid, n in nodes.items():
        if n.get('type') not in ('npc', 'player'):
            continue
        lines = n.get('lines') or []
        for i, ln in enumerate(lines):
            text = ln.get('text') or ''
            if '\r' in text:
                E.append((t('val.cr'), nid))
            if not text.strip() and ln.get('order') is None:
                E.append((t('val.text.empty'), nid))
            cue = ln.get('cue')
            if (cue and index and cue in index.cues
                    and (own or ln.get('order') is None)
                    and _norm(index.cues[cue][1]) != _norm(text)):
                W.append((t('warn.cue.text', cue=cue), nid))
        if n['type'] == 'npc' and quest.speaker(n.get('speaker')) is None:
            E.append((t('val.speaker'), nid))
        if n['type'] == 'player' and n.get('kind') == 'question' and \
                len(lines) > 1:
            linked = [(nid, i) in targets for i in range(len(lines))]
            if any(linked) and not all(linked):
                W.append((t('warn.question.open'), nid))

    # -- actions ---------------------------------------------------------------------
    created = {_npc_id(a['args'].get('npc')) for a, _, _ in actions
               if a.get('verb') == 'NPC_CREATE'}
    for a, when, target in actions:
        key = (a.get('kind'), a.get('verb'))
        if key not in model.ACTION_SPECS:
            E.append((t('val.opcode', op=' '.join(str(k) for k in key)),
                      target))
            continue
        check_fields = True
        if when is None:
            E.append((t('val.action.level'), target))
        else:
            allowed = (model.REWARD_WHEN if a['kind'] == 'REWARD'
                       else model.ACTION_WHEN)
            if when not in allowed:
                E.append((t('val.action.when', when=when), target))
        if check_fields:
            try:
                model.op_tokens(model.ACTION_SPECS[key], a['args'])
            except model.ModelError as e:
                E.append((t('val.action.field', err=_field(t, e)), target))
        verb = a['verb']
        if verb == 'NPC_TELEPORT' and INTERIOR_HINT in str(
                a['args'].get('tile', '')):
            W.append((t('warn.teleport.interior'), target))
        if verb == 'SHOW_LOCATION' and when != 'TAKE':
            W.append((t('warn.showloc'), target))
        if verb == 'PLAY_CUTSCENE' and str(a['args'].get('number')) in ('7',
                                                                        '8'):
            W.append((t('warn.cutscene'), target))
        if verb == 'NPC_GO' and _npc_id(a['args'].get('npc')) in created:
            W.append((t('warn.npcgo.created'), target))
        if verb == 'SHOW_LOCATION' and index:
            loc = index.locations.get(str(a['args'].get('location')))
            if loc and loc.get('type') == 10 and loc.get('radius') == 0:
                W.append((t('warn.location.type10'), target))
    if own:
        _engine_checks(quest, index, project, modset, actions, task, t, E, W)
    # the same message for the same target once is enough
    return _dedupe(E), _dedupe(W)


# -- engine rules the game fails on silently (3.8.0) ---------------------------

def _known_tiles(index, modset):
    tiles = set(getattr(index, 'tiles', None) or ())
    if modset is not None:
        tiles |= set(modset.retail_tiles)
        for info in modset.enabled():
            tiles |= set(info['tiles'])
    return {x.upper() for x in tiles}


def _marker_on_tile(modset, tile, name, num):
    """True/False when the map data knows the tile, None without data."""
    from . import mods
    if modset is None:
        return None
    if num in mods.marker_ids(modset.retail_tiles.get(tile), name):
        return True
    return any(num in mods.marker_ids(i['tiles'][tile], name)
               for i in modset.tile_providers(tile))


def _all_quests(project):
    return list(project.quests) if project else []


def _npc_known(index, project, nid):
    if index is not None and hasattr(index, 'npc') and index.npc(nid):
        return True
    return any(s.get('id') == nid for q in _all_quests(project)
               for s in q.speakers)


def _incoming_promotes(quest, index, project):
    """How many quests raise this quest's enable counter."""
    n = 0
    afters = [c for c in quest.conditions_list() if c.get('cond') == 'after']
    if quest.offered:
        n += len(afters)
    for q in _all_quests(project):
        if q is quest:
            continue
        n += sum(1 for x in q.links if isinstance(x, dict)
                 and x.get('type') == 'PROMOTE' and x.get('quest') == quest.id)
    if index is not None and isinstance(getattr(index, 'quests', None),
                                        dict):
        for k, info in index.quests.items():
            if project and project.quest_by_id(int(k)):
                continue                  # the project version counts
            n += sum(1 for a in info.get('aoq') or []
                     if a[0] == 'PROMOTE' and a[2] == quest.id)
    return n, afters


def _engine_checks(quest, index, project, modset, actions, task, t, E, W):
    from . import mods
    from .export import header_values
    from .mpmerge import MAX_NPC_ID
    tiles = _known_tiles(index, modset)
    from .mpmerge import current_todo
    todo = {(x.get('name'), str(x.get('tile')).upper(), x.get('num'))
            for x in current_todo(quest) if not x.get('done')}

    # enable counter: starts at -1, the game start adds one, every
    # AOQ PROMOTE one more; enabled when counter >= level (PQuests.ec 229)
    level, _g, _r = header_values(quest)
    if quest.offered and isinstance(level, int):
        n, afters = _incoming_promotes(quest, index, project)
        if level > n:
            E.append((t('val.enable.never', level=level, n=n),
                      entry_id('first')))
        elif level == 0 and afters:
            W.append((t('warn.enable.zero'), entry_id('first')))

    # NPC ids in giver, task and actions: 1..697 and known somewhere
    refs = []
    if isinstance(quest.giver, int):
        refs.append((quest.giver, None))
    if task.get('fc') and 'npc' in (task.get('args') or {}):
        refs.append((_npc_id(task['args']['npc']), model.TASK_ID))
    for a, _w, target in actions:
        if 'npc' in (a.get('args') or {}):
            refs.append((_npc_id(a['args']['npc']), target))
    for nid, target in refs:
        if nid is None:
            continue
        if not 1 <= nid <= MAX_NPC_ID:
            E.append((t('val.npc.range', id=nid, max=MAX_NPC_ID), target))
        elif hasattr(index, 'npc') and not _npc_known(index, project, nid):
            W.append((t('warn.npc.unknown', id=nid), target))

    # new NPCs: tile, start marker, created at all, defined twice
    needed = {}
    fc = task.get('fc')
    if fc in ('TALK', 'FIND_TALK', 'KILL', 'FIND_KILL'):
        needed.setdefault(_npc_id(task['args'].get('npc')), t('why.task'))
    for a, _w, _x in actions:
        if a.get('verb') in ('NPC_GO', 'NPC_TELEPORT', 'NPC_REMOVE',
                             'NPC_KILL', 'NPC_DIALOG', 'NPC_CHANGE_PARTY'):
            needed.setdefault(_npc_id(a['args'].get('npc')),
                              t('why.action', verb=a['verb']))
    givers = {q.giver for q in _all_quests(project)}
    created = {_npc_id(a['args'].get('npc'))
               for q in _all_quests(project)
               for a, _w, _x in all_actions(q)
               if a.get('verb') == 'NPC_CREATE'}
    for s in quest.speakers:
        sid = s.get('id')
        if not s.get('new') or not isinstance(sid, int):
            continue
        tile = str(s.get('tile') or '').upper()
        num = s.get('marker') or sid
        if not tile or tile == '(NULL)' or (tiles and tile not in tiles):
            E.append((t('val.speaker.tile', name=s.get('name'), id=sid,
                        tile=tile or '-'), None))
        elif (mods.NPC_MARKER, tile, num) not in todo and \
                _marker_on_tile(modset, tile, mods.NPC_MARKER, num) is False:
            W.append((t('warn.giver.marker', name=s.get('name'), id=sid,
                        tile=tile, num=num), None))
        if sid in needed and sid not in givers and sid not in created:
            W.append((t('warn.npc.notcreated', name=s.get('name'), id=sid,
                        why=needed[sid]), None))
        for q in _all_quests(project):
            if q is quest:
                continue
            other = next((x for x in q.speakers if x.get('id') == sid
                          and x.get('new')), None)
            if other and any(str(other.get(k)) != str(s.get(k))
                             for k in ('tile', 'marker', 'lector')):
                E.append((t('val.npc.twice', id=sid, q=q.id), None))

    # tiles and markers of task and actions
    try:
        refs = mods.marker_refs(mods.quest_block(quest))
    except Exception:                    # an invalid quest: said elsewhere
        refs = []
    for kind, tile, num in refs:
        name = mods.MARKER_NAMES.get(kind)
        if tiles and tile not in tiles:
            E.append((t('val.tile.bad', tile=tile, kind=kind), None))
            continue
        if name and (name, tile, num) not in todo and \
                _marker_on_tile(modset, tile, name, num) is False:
            W.append((t('warn.marker.missing', kind=kind, num=num,
                        tile=tile), None))
    # lines with a marker field but an empty tile export "(null)"
    for spec_args, target in [(task.get('args') or {}, model.TASK_ID)] + [
            (a.get('args') or {}, x) for a, _w, x in actions]:
        if 'tile' in spec_args and 'marker' in spec_args and \
                str(spec_args.get('tile') or '').strip() in ('', '(null)'):
            E.append((t('val.tile.empty'), target))
    # NPC_GO reads its marker on the tile the NPC stands on
    for a, _w, target in actions:
        if a.get('verb') != 'NPC_GO':
            continue
        nid = _npc_id(a['args'].get('npc'))
        num = model_int(a['args'].get('marker'))
        spk = quest.speaker(nid)
        tile = str((spk or {}).get('tile') or
                   ((index.npc(nid) or {}).get('tile')
                    if hasattr(index, 'npc') else '') or '').upper()
        if num is not None and tile and \
                _marker_on_tile(modset, tile, 'MARKER_QUEST_WALK', num) \
                is False:
            W.append((t('warn.walk.marker', num=num, tile=tile), target))
    # locations
    if isinstance(getattr(index, 'locations', None), dict):
        locs = []
        if fc == 'FIND_LOCATION':
            locs.append((task['args'].get('location'), model.TASK_ID))
        locs += [(a['args'].get('location'), x) for a, _w, x in actions
                 if a.get('verb') == 'SHOW_LOCATION']
        for loc, target in locs:
            if loc and str(loc) not in index.locations:
                E.append((t('val.location', loc=loc), target))


def model_int(v):
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return None


def _dedupe(items):
    seen, out = set(), []
    for msg, target in items:
        if (msg, target) not in seen:
            seen.add((msg, target))
            out.append((msg, target))
    return out


def validate_project(project, index=None, archive=None, t=None,
                     modset=None):
    """[(quest, message, target)] errors and warnings over all quests."""
    errors, warnings = [], []
    deps = None
    if modset is not None:
        from . import mods
        deps = mods.dependencies(project, modset)
    for q in project.quests:
        E, W = validate_quest(q, index, project, archive, t, modset)
        errors += [(q, m, x) for m, x in E]
        warnings += [(q, m, x) for m, x in W]
        if modset is not None:
            E, W = validate_mods(q, project, modset, t, deps)
            errors += [(q, m, x) for m, x in E]
            warnings += [(q, m, x) for m, x in W]
    return errors, warnings


def validate_mods(quest, project, modset, t=None, deps=None):
    """Checks against the mods of the project (update 5b): quest numbers a
    mod uses too, marker dependencies on red or contested tiles."""
    from . import mods
    t = keyed(t or (lambda k, **f: k))
    errors, warnings = [], []
    if quest.extra.get('mod'):
        return errors, warnings
    for info, qid, q in modset.quests():
        if qid != quest.id:
            continue
        if q['state'] == 'new' and not quest.retail:
            warnings.append((t('warn.mod.id', mod=info['name']), None))
        elif q['state'] == 'changed' and quest.retail:
            warnings.append((t('warn.mod.override', mod=info['name']), None))
    if deps is None:
        deps = mods.dependencies(project, modset)
    for d in deps:
        uses = [u for u in d['uses'] if u[0] == quest.id]
        if not uses:
            continue
        nums = ', '.join(str(n) for _q, _k, n in uses)
        if d['status'] == 'missing':
            errors.append((t('val.mod.redtile', tile=d['tile'], mod=d['mod'],
                             n=len(d['missing']), markers=nums),
                           'fill:' + d['tile']))   # the fix button's target
        elif d['status'] == 'conflict':
            errors.append((t('val.mod.conflict', tile=d['tile'],
                             mods=', '.join(d['providers']), markers=nums),
                           None))
    return errors, warnings
