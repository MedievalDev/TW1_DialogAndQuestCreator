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


def validate_quest(quest, index=None, project=None, archive=None, t=None):
    t = t or _t_default
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
            elif index and not index.quest(tgt) and not (
                    project and project.quest_by_id(tgt)):
                W.append((t('val.link.unknown', id=tgt), None))
        # templates mark the places to fill in with TODO
        todo = [v for v in (quest.title, *quest.journal.values()) if 'TODO' in (v or '')]
        todo += [ln.get('text') for n in nodes.values()
                 for ln in (n.get('lines') or []) if 'TODO' in (ln.get('text') or '')]
        if todo:
            W.append((t('warn.todo', n=len(todo)), None))
        if project and sum(1 for q in project.quests if q.id == qid) > 1:
            E.append((t('val.id.twice', id=qid), None))
        if not (quest.title or '').strip():
            E.append((t('val.title'), None))
        for key in ('take', 'solve', 'close'):
            if not (quest.journal.get(key) or '').strip():
                E.append((t('val.journal.' + key), None))
        if quest.giver is None:
            E.append((t('val.giver'), None))
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
            if not isinstance(pq, int) or not known:
                E.append((t('val.after.quest', id=pq), nid))
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
    # the same message for the same target once is enough
    return _dedupe(E), _dedupe(W)


def _dedupe(items):
    seen, out = set(), []
    for msg, target in items:
        if (msg, target) not in seen:
            seen.add((msg, target))
            out.append((msg, target))
    return out


def validate_project(project, index=None, archive=None, t=None):
    """[(quest, message, target)] errors and warnings over all quests."""
    errors, warnings = [], []
    for q in project.quests:
        E, W = validate_quest(q, index, project, archive, t)
        errors += [(q, m, x) for m, x in E]
        warnings += [(q, m, x) for m, x in W]
    return errors, warnings
