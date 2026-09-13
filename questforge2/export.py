"""Dialog graph <-> ``.lan`` dialog tree (plan sections 5.2, 6.3, 12.19).

``tree_to_graph`` turns a retail ``DialogTree`` into the quest graph:
every NPC entry becomes an NPC node, hero entries that form a reply menu
(the ``next`` list of one entry) become one player question node with one
line per entry, single hero entries become answer nodes. Flags map to a
level plus the three event checks; whatever cannot be expressed is kept
raw on the line (``raw_flags``, ``cams``) so an unchanged tree exports
byte-identical. ``graph_to_tree`` is the inverse.
"""

from . import model
from .model import PLAYER, STATES, entry_id, is_entry, line_flags

DQ = 'translateDQ_%d'
STATE_SUFFIX = {'first': '0.FT', 'known': '0.QNT', 'running': '0.QNS.AE',
                'taken': '0.QT', 'solved': '0.QS.AE', 'closed': '0.QC',
                'failed': '0.QF', 'lowrep': '0.LR', 'neutral': '0.X'}
CAM_DEFAULT = {'npc': model.CAM_NPC, 'player': model.CAM_HERO}


class ImportReport:
    def __init__(self):
        self.entries = 0
        self.menus = 0
        self.lossy = []        # human readable notes
        self.speakers = []     # speakers created


# ---------------------------------------------------------------------------
# tree -> graph

def tree_to_graph(quest, tree, translations, index=None, qid=None):
    """Fill ``quest.graph`` and ``quest.speakers`` from a DialogTree.
    Returns an ImportReport."""
    rep = ImportReport()
    ents = tree.entries
    rep.entries = len(ents)
    n = len(ents)
    hero = [e.lector == 1 for e in ents]
    referenced = set()
    for e in ents:
        for nx in e.next:
            referenced.add(abs(nx))

    # reply menus: the next list of an entry, all targets hero lines
    owner = {}          # hero entry index -> group key
    groups = {}         # key -> {'members': [...], 'first': index}
    for i, e in enumerate(ents):
        if len(e.next) < 2:
            continue
        key = tuple(abs(x) for x in e.next)
        if not all(0 <= k < n and hero[k] for k in key):
            rep.lossy.append(f'entry {i}: menu with non-hero targets')
            continue
        if key in groups:
            continue
        if any(k in owner for k in key):
            rep.lossy.append(f'entry {i}: menu shares lines with another menu')
            continue
        groups[key] = {'members': list(key), 'first': min(key)}
        for k in key:
            owner[k] = key

    graph = model.new_graph()
    quest.graph = graph
    node_of = {}        # entry index -> (node id, line index)
    speakers_by_lector = {}
    for s in quest.speakers:
        if s.get('lector') is not None:
            speakers_by_lector.setdefault(s['lector'], s)

    def speaker_for(lector):
        s = speakers_by_lector.get(lector)
        if s:
            return s['id']
        cands = list(index.lectors.get(str(lector), [])) if index else []
        giver = None
        if index and qid is not None and index.quest(qid):
            giver = index.quest(qid)['giver']
        nid = giver if giver in cands else (cands[0] if cands else None)
        if nid is not None and quest.speaker(nid) is not None:
            nid = None                # id already used with another lector
        if nid is not None:
            npc = index.npc(nid)
            s = {'id': nid, 'name': npc['name'], 'lector': lector,
                 'tile': npc['tile'], 'new': False}
        else:
            s = {'id': f'L{lector}', 'name': f'Lector {lector}',
                 'lector': lector, 'tile': '', 'new': False}
        quest.add_speaker(s)
        speakers_by_lector[lector] = s
        rep.speakers.append(s)
        return s['id']

    def line_from(i):
        e = ents[i]
        state, take, close, fight = model.flags_to_state(e.flags)
        ln = model.new_line(state)
        ln.update({'text': translations.get(e.tid, ''), 'cue': e.cue,
                   'cam': e.cams[0] if len(e.cams) == 1 else None,
                   'anim': e.anim1, 'take': take, 'close': close,
                   'fight': fight, 'tid': e.tid, 'order': i})
        if (e.flags & model.STATE_MASK) and state == 'neutral':
            ln['raw_flags'] = e.flags            # unknown combination
        if len(e.cams) != 1:
            ln['cams'] = list(e.cams)
        if e.anim2 != e.anim1:
            ln['anim2'] = e.anim2
        return state, ln

    # nodes
    for i, e in enumerate(ents):
        if hero[i] and i in owner:
            key = owner[i]
            g = groups[key]
            if 'node' not in g:
                node = model.make_node('player', 0, 0, 'first')
                node['kind'] = 'question'
                node['lines'] = []
                states = []
                for k in g['members']:
                    st, ln = line_from(k)
                    node['lines'].append(ln)
                    states.append(st)
                node['state'] = states[0]
                for st, ln in zip(states, node['lines']):
                    if st != node['state']:
                        ln['state'] = st
                g['node'] = model.add_node(graph, node)
                rep.menus += 1
            node_of[i] = (g['node'], g['members'].index(i))
            continue
        st, ln = line_from(i)
        if hero[i]:
            node = model.make_node('player', 0, 0, st)
        else:
            node = model.make_node('npc', 0, 0, st, speaker_for(e.lector))
        node['lines'] = [ln]
        node_of[i] = (model.add_node(graph, node), 0)

    # edges: one per source line. When the referenced lines differ from
    # what the target node exports by default (all lines of a question,
    # the first line otherwise) or carry negative indices, the exact
    # reference is kept on the source line as ``next_ref``; it only applies
    # while the edge still points at the same node.
    for i, e in enumerate(ents):
        if not e.next:
            continue
        frm, port = node_of[i]
        refs = [node_of[abs(x)] for x in e.next if abs(x) < n]
        to = refs[0][0]
        if any(r[0] != to for r in refs):
            rep.lossy.append(f'entry {i}: next {e.next} spans several nodes')
            refs = [r for r in refs if r[0] == to]
        graph['edges'].append([frm, port, to])
        sel = [r[1] for r in refs]
        neg = [r[1] for r, x in zip(refs, e.next) if x < 0]
        if sel != _default_sel(graph['nodes'][to]) or neg:
            graph['nodes'][frm]['lines'][port]['next_ref'] = {
                'to': to, 'sel': sel, 'neg': neg}

    # entries: first unreferenced line of each level starts that level
    for st in STATES:
        if st == 'neutral':
            continue
        roots = [i for i in range(n) if i not in referenced
                 and _line_state(graph, node_of[i]) == st]
        if not roots:
            continue
        model.ensure_entry(graph, st)
        graph['edges'].append([entry_id(st), 0, node_of[roots[0]][0]])
        for r in roots[1:]:
            rep.lossy.append(f'entry {r}: second root of level {st}')
    model.auto_layout(graph)
    return rep


def _default_sel(node):
    lines = node.get('lines') or []
    if node['type'] == 'player' and node.get('kind') == 'question':
        return list(range(len(lines)))
    return [0] if lines else []


def _line_state(graph, ref):
    nid, li = ref
    node = graph['nodes'][nid]
    ln = node['lines'][li]
    return ln.get('state') or node.get('state')


# ---------------------------------------------------------------------------
# graph -> tree

def export_order(quest):
    """[(node id, line index)] in file order: imported lines keep their
    original index; new lines follow, grouped by level in the proven order
    (first, ..., closed) and by conversation flow."""
    g = quest.graph
    nodes = g['nodes']
    dialog = [nid for nid, n in nodes.items() if n['type'] in ('npc', 'player')]
    rank = {s: i for i, s in enumerate(STATES)}
    # DFS position from every level entry in level order, then loose nodes
    pos = {}
    for st in STATES:
        ent = entry_id(st)
        if ent not in nodes:
            continue
        stack = [ent]
        while stack:
            nid = stack.pop()
            if nid in pos or nid not in nodes:
                continue
            pos[nid] = len(pos)
            for s in reversed(model.successors(g, nid)):
                if s not in pos:
                    stack.append(s)
    for nid in dialog:
        pos.setdefault(nid, len(pos))
    keyed = []
    for nid in dialog:
        node = nodes[nid]
        for li, ln in enumerate(node.get('lines') or []):
            st = ln.get('state') or node.get('state', 'neutral')
            if ln.get('order') is not None:
                key = (0, ln['order'], 0, 0)
            else:
                key = (1, rank.get(st, 99), pos[nid], li)
            keyed.append((key, nid, li))
    keyed.sort(key=lambda k: k[0])
    return [(nid, li) for _, nid, li in keyed]


def graph_to_tree(quest, propagate_take=True):
    """(DialogTree, {tid: text}) for the quest's graph."""
    g = quest.graph
    nodes = g['nodes']
    qid = quest.id or 0
    dq = DQ % qid
    order = export_order(quest)
    index_of = {ref: i for i, ref in enumerate(order)}
    if propagate_take:
        take_set = _propagate(g, order, index_of)
    else:
        take_set = set()
    # edge lookup: (node, port) -> target node
    target = {(e[0], e[1]): e[2] for e in g['edges']}
    used_tids = set()
    counters = {}
    texts = {}
    entries = []
    for i, (nid, li) in enumerate(order):
        node = nodes[nid]
        ln = node['lines'][li]
        st = ln.get('state') or node.get('state', 'neutral')
        is_hero = node['type'] == 'player'
        # flags
        if 'raw_flags' in ln:
            flags = ln['raw_flags']
        else:
            flags = line_flags(st, ln)
            if (nid, li) in take_set:
                flags |= model.EVENT_BITS['take']
        # next
        to = target.get((nid, li))
        nxt = []
        if to is not None and to in nodes:
            tn = nodes[to]
            nlines = len(tn.get('lines') or [])
            sel, neg = _default_sel(tn), []
            ref = ln.get('next_ref')
            if ref and ref.get('to') == to and all(
                    0 <= k < nlines for k in ref.get('sel', [])):
                sel, neg = ref['sel'], ref.get('neg', [])
            for k in sel:
                j = index_of.get((to, k))
                if j is None:
                    continue
                nxt.append(-j if (k in neg and j) else j)
        # tid (imported lines keep theirs, even when retail repeats one)
        tid = ln.get('tid')
        if not tid or (tid in used_tids and ln.get('order') is None):
            suffix = STATE_SUFFIX[st] + ('.AS' if (st == 'first' and
                                                   flags & 0x20000) else '')
            k = counters.get(suffix, 0)
            while True:
                tid = f'{dq}_{suffix}_{k}'
                k += 1
                if tid not in used_tids:
                    break
            counters[suffix] = k
        used_tids.add(tid)
        texts[tid] = ln.get('text', '')
        # camera, lector
        if 'cams' in ln:
            cams = list(ln['cams'])
        elif ln.get('cam') is not None:
            cams = [ln['cam']]
        else:
            cams = [CAM_DEFAULT['player' if is_hero else 'npc']]
        if is_hero:
            lector = 1
        else:
            spk = quest.speaker(node.get('speaker'))
            lector = spk.get('lector') if spk and spk.get('lector') is not None \
                else 0
        anim1 = ln.get('anim', 0) or 0
        anim2 = ln.get('anim2', anim1)
        entries.append(model_entry(lector, tid, ln.get('cue') or '', nxt,
                                   flags, cams, anim1, anim2))
    import tw1_lan
    return tw1_lan.DialogTree(dq, entries), texts


def model_entry(lector, tid, cue, nxt, flags, cams, anim1, anim2):
    import tw1_lan
    return tw1_lan.DialogEntry(lector=lector, tid=tid, cue=cue, next=nxt,
                               flags=flags, cams=cams, anim1=anim1,
                               anim2=anim2)


def _propagate(g, order, index_of):
    """Lines downstream of a 'take' line within the same level also get
    TakeNow (retail marks whole chains, plan 6.3 result)."""
    nodes = g['nodes']
    succ = {}
    for frm, port, to in g['edges']:
        succ.setdefault((frm, port), []).append(to)
    out = set()
    for nid, li in order:
        node = nodes[nid]
        ln = node['lines'][li]
        if not ln.get('take') or 'raw_flags' in ln:
            continue
        st = ln.get('state') or node.get('state')
        stack = [(nid, li)]
        seen = set()
        while stack:
            ref = stack.pop()
            if ref in seen:
                continue
            seen.add(ref)
            for to in succ.get(ref, []):
                tn = nodes.get(to)
                if not tn or tn['type'] not in ('npc', 'player'):
                    continue
                for k, l2 in enumerate(tn.get('lines') or []):
                    # imported lines keep their exact retail flags
                    if (l2.get('state') or tn.get('state')) == st \
                            and 'raw_flags' not in l2 \
                            and l2.get('order') is None:
                        out.add((to, k))
                        stack.append((to, k))
    return out


# ---------------------------------------------------------------------------
# text preview

def preview_text(quest, index=None, t=lambda k, **f: k):
    """Readable listing of the exported tree (plan 3.1, "Vorschau")."""
    tree, texts = graph_to_tree(quest)
    lines = [f'{tree.id}: {len(tree.entries)} lines', '']
    for i, e in enumerate(tree.entries):
        st, take, close, fight = model.flags_to_state(e.flags)
        who = 'Held' if e.lector == 1 else f'L{e.lector}'
        if e.lector != 1:
            for s in quest.speakers:
                if s.get('lector') == e.lector:
                    who = s['name']
                    break
        ev = ''.join(x for x, on in (('+TAKE', take), ('+CLOSE', close),
                                     ('+FIGHT', fight)) if on)
        nxt = ', '.join(str(x) for x in e.next) if e.next else '-'
        lines.append(f'{i:3}  [{t("state." + st)}{ev}]  {who}: '
                     f'{texts.get(e.tid, "")}')
        lines.append(f'      -> {nxt}   flags={hex(e.flags)}  cue={e.cue or "-"}'
                     f'  cam={e.cams}  anim={e.anim1}')
    return '\n'.join(lines)
