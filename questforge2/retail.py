"""Quests from the game install: QUEST block <-> project model (plan 10).

``import_block`` fills a Quest from its ``.qtx`` block: header fields,
giver, task (FC) and actions/rewards (as actions without dialog). Lines the
model cannot express exactly (AOQ lines, unknown opcodes, tokens that do not
survive a round trip) are kept raw. The original block text and a signature
of the imported fields are stored in ``quest.extra['qtx']``; ``block_text``
returns the original text as long as nothing qtx-relevant changed, so an
unchanged quest exports byte-identical.
"""

import copy
import json
import re

import tw1_qtx

from . import model


def args_from_tokens(spec, toks):
    """Field values for an opcode spec from qtx tokens (None if the count
    does not match)."""
    if len(spec) != len(toks):
        return None
    out = {}
    for f, tok in zip(spec, toks):
        key, kind = f[0], f[1]
        if kind == 'npc':
            m = re.fullmatch(r'NPC_(\d+)', tok)
            out[key] = int(m.group(1)) if m else tok
        elif kind in ('int', 'party') or kind.startswith('marker:'):
            out[key] = int(tok) if re.fullmatch(r'-?\d+', tok) else tok
        elif kind == 'tile':
            out[key] = '' if tok == '(null)' else tok
        else:
            out[key] = tok
    return out


def _exact(spec, toks):
    """Args when they re-emit to exactly the same tokens, else None."""
    args = args_from_tokens(spec, toks)
    if args is None:
        return None
    try:
        if model.op_tokens(spec, args) != toks:
            return None
    except model.ModelError:
        return None
    return args


def _subs_of(quest):
    """Canonical sub-lines [(kw, [tokens])] for the quest's qtx part."""
    q = quest.extra.get('qtx', {})
    subs = []
    if quest.giver is not None:
        subs.append(('GIVER', [quest.giver_type, f'NPC_{quest.giver}',
                               quest.map_sign, q.get('giver_remove', 'NONE')]))
    task = quest.task()
    if task.get('fc'):
        subs.append(('FC', [task['fc']] + model.op_tokens(
            model.FC_SPECS[task['fc']], task['args'])))
    for kw, toks in q.get('raw', []):
        if kw == 'AOQ':
            subs.append((kw, list(toks)))
    from .export import all_actions
    acts, rewards = [], []
    for a, when, _ in all_actions(quest):
        toks = [a['verb'], when or 'NONE'] + model.op_tokens(
            model.ACTION_SPECS[(a['kind'], a['verb'])], a['args'])
        (rewards if a['kind'] == 'REWARD' else acts).append((a['kind'], toks))
    subs += acts + rewards
    for kw, toks in q.get('raw', []):
        if kw != 'AOQ':
            subs.append((kw, list(toks)))
    return subs


def _header_of(quest):
    from .export import header_values
    level, guild, rep = header_values(quest)
    info = quest.extra.get('qtx', {})
    log = info.get('log', True)
    group = str(quest.group)
    if 'group_raw' in info and quest.group == info.get('group_int'):
        group = info['group_raw']            # e.g. '(null)' in Q_700
    return [f'Q_{quest.id}', str(level), group, str(guild),
            str(rep), 'True' if log else 'False']


def signature(quest):
    try:
        return json.dumps([_header_of(quest), _subs_of(quest)])
    except model.ModelError as e:
        return 'invalid: ' + str(e)


def import_block(quest, block_text):
    """Fill ``quest`` from a QUEST...END block of the game. Returns the list
    of raw lines that stay untouched."""
    qb = tw1_qtx.parse_quest(block_text.rstrip('\n'))
    h = qb.header
    info = {'block': block_text if block_text.endswith('\n')
            else block_text + '\n', 'raw': [], 'log': h[5] != 'False'}
    quest.id = int(h[0][2:])
    g = quest.graph
    level = int(h[1]) if re.fullmatch(r'-?\d+', h[1]) else 0
    quest.enable_level = level
    quest.group = int(h[2]) if h[2].isdigit() else 0
    info['group_raw'], info['group_int'] = h[2], quest.group
    # header conditions (replace whatever is there)
    for nid in [nid for nid, n in g['nodes'].items()
                if n.get('type') == 'condition']:
        del g['nodes'][nid]
    model.add_node(g, model.make_condition('level', level=level))
    if h[3] != '(null)' or h[4] != '0':
        model.add_node(g, model.make_condition(
            'guild', guild=h[3], min_rep=int(h[4]) if
            re.fullmatch(r'-?\d+', h[4]) else h[4]))
    quest.giver = None
    quest.actions = []
    model.set_task(g, None)
    for kw, toks in qb.subs:
        if kw == 'GIVER' and quest.giver is None and len(toks) == 4 and \
                re.fullmatch(r'NPC_\d+', toks[1]) and \
                toks[0] in ('ACTIVE', 'PASSIVE'):
            quest.giver = int(toks[1][4:])
            quest.giver_type = toks[0]
            quest.map_sign = toks[2]
            info['giver_remove'] = toks[3]
            continue
        if kw == 'FC' and toks and toks[0] in model.FC_SPECS and \
                not g['nodes'][model.TASK_ID].get('fc'):
            args = _exact(model.FC_SPECS[toks[0]], toks[1:])
            if args is not None:
                task = model.set_task(g, toks[0])
                task['args'] = args
                continue
        if kw in ('ACTION', 'REWARD') and len(toks) >= 2:
            key = (kw, toks[0])
            allowed = model.REWARD_WHEN if kw == 'REWARD' else model.ACTION_WHEN
            if key in model.ACTION_SPECS and toks[1] in allowed:
                args = _exact(model.ACTION_SPECS[key], toks[2:])
                if args is not None:
                    quest.actions.append({'kind': kw, 'verb': toks[0],
                                          'args': args, 'when': toks[1]})
                    continue
        info['raw'].append([kw, list(toks)])
    quest.retail = True
    quest.extra['qtx'] = info
    info['sig'] = signature(quest)
    return info['raw']


def block_text(quest):
    """The QUEST block to export for a quest from the game."""
    info = quest.extra.get('qtx')
    if info and info.get('block') and signature(quest) == info.get('sig'):
        return info['block']
    header = _header_of(quest)
    subs = _subs_of(quest)
    return tw1_qtx.Quest(header, subs).emit()


def changed(quest):
    info = quest.extra.get('qtx')
    return not info or signature(quest) != info.get('sig')


def make_own(quest, new_id):
    """Turn a (copy of a) game quest into an own quest with a new id."""
    q = model.Quest.from_dict(copy.deepcopy(quest.to_dict()))
    q.id = new_id
    q.retail = False
    q.extra.pop('qtx', None)
    for n in q.graph['nodes'].values():
        for ln in n.get('lines') or []:
            for k in ('tid', 'order'):
                ln.pop(k, None)
    if not any(c.get('cond') == 'after' for c in q.conditions_list()):
        model.add_node(q.graph, model.make_condition('after', quest=4,
                                                     event='TAKE'))
    model.restack(q.graph)
    return q
