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
        if e.tid not in translations:
            ln['notext'] = True              # retail line without a text key
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
        if ln.get('text') or not ln.get('notext'):
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
    lines = []
    try:
        if quest.retail:
            from . import retail
            lines += retail.block_text(quest).rstrip('\n').split('\n')
        else:
            lines += build_quest_block(quest).emit().rstrip('\n').split('\n')
    except Exception as e:           # incomplete quest: show why
        lines.append(f'(qtx: {e})')
    lines += ['', f'{tree.id}: {len(tree.entries)} lines', '']
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



# ===========================================================================
# quest export: .qtx block, texts, .lan, packing (milestone 5)
# ===========================================================================

import contextlib  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

import tw1_lan  # noqa: E402,F811
import tw1_qtx  # noqa: E402
import tw1_wd  # noqa: E402
import wdio  # noqa: E402

INNER_QTX = 'Scripts\\Quests\\TwoWorldsQuests.qtx'
INNER_LAN = 'Language\\TwoWorldsQuests.lan'
REG_MODS = r'SOFTWARE\Reality Pump\TwoWorlds\Mods'
# Every process that keeps the archives open: TwoWorlds.exe,
# TwoWorlds_RADEON.exe, TwoWorldsExtended.exe, TwoWorldsEditor*.exe ...
GAME_EXE_PREFIX = 'twoworlds'


def header_values(quest):
    """(enable_level, guild, min_rep) from the condition nodes."""
    level, guild, rep = quest.enable_level, '(null)', 0
    for c in quest.conditions_list():
        if c.get('cond') == 'level':
            level = c.get('level', level)
        elif c.get('cond') == 'guild':
            guild = str(c.get('guild') or '(null)')
            rep = c.get('min_rep', 0)
    return level, guild, rep


def all_actions(quest):
    """[(action dict, when, node id or None)]: docked first, then free."""
    g = quest.graph
    out = [(n, model.action_when(g, n), nid)
           for nid, n in quest.graph_actions()]
    out += [(a, a.get('when'), None) for a in quest.actions]
    return out


def build_quest_block(quest):
    """tw1_qtx.Quest for a project quest (retail quests: None)."""
    if quest.retail:
        return None
    level, guild, rep = header_values(quest)
    subs = [tw1_qtx.sub_giver(quest.giver, quest.giver_type, quest.map_sign,
                              'NONE')]
    task = quest.task()
    subs.append(tw1_qtx.sub_fc(task['fc'], *model.op_tokens(
        model.FC_SPECS[task['fc']], task['args'])))
    acts, rewards = [], []
    for a, when, _ in all_actions(quest):
        toks = model.op_tokens(model.ACTION_SPECS[(a['kind'], a['verb'])],
                               a['args'])
        if a['kind'] == 'REWARD':
            rewards.append(tw1_qtx.sub_reward(a['verb'], when, *toks))
        else:
            acts.append(tw1_qtx.sub_action(a['verb'], when, *toks))
    return tw1_qtx.make_quest(quest.id, subs + acts + rewards,
                              enable_level=level, group=quest.group,
                              guild=guild, min_rep=rep, add_to_log=True)


def validate_quest(quest, index=None, project=None, archive=None, t=None):
    """Kept for callers of milestone 5; the rules live in validate.py."""
    from .validate import validate_quest as _validate
    return _validate(quest, index, project, archive, t)


# -- qtx ----------------------------------------------------------------------

_BLOCK = r'^QUEST Q_%d [^\n]*\n.*?^END\n'


def _find_block(text, qid):
    return re.search(_BLOCK % qid, text, re.M | re.S)


def insert_aoq(text, pred, line):
    """Insert ``  <line>`` into the block of quest ``pred`` after its last
    AOQ (else after FC, else GIVER, else the header)."""
    m = _find_block(text, pred)
    if not m:
        raise model.ModelError(f'Q_{pred} not found in the qtx')
    block = m.group(0)
    if f'  {line}\n' in block:
        return text
    lines = block.split('\n')
    pos = 1
    for key in ('AOQ', 'FC', 'GIVER'):
        idx = [i for i, ln in enumerate(lines)
               if ln.startswith('  ' + key + ' ')]
        if idx:
            pos = idx[-1] + 1
            break
    lines.insert(pos, '  ' + line)
    return text[:m.start()] + '\n'.join(lines) + text[m.end():]


def remove_aoq_to(text, qid):
    """Drop every ``AOQ PROMOTE|TAKE <event> Q_<qid>`` line (re-export)."""
    return re.sub(r'^  AOQ (?:PROMOTE|TAKE) [A-Z_]+ Q_%d\n' % qid, '', text,
                  flags=re.M)


def npc_block(spk, index):
    """NPC record for a new speaker: the record of a template NPC with id,
    giver marker, tile, angle and lector replaced. [PRUEFEN] the remaining
    columns (party, guild, size, flag, look, last int) are copied from the
    template (plan 12.31)."""
    tmpl = None
    if spk.get('template') is not None and index:
        tmpl = index.npc(spk['template'])
    if tmpl is None and index and spk.get('lector') is not None:
        for nid in index.lectors.get(str(spk['lector']), []):
            if index.npc(nid):
                tmpl = index.npc(nid)
                break
    if tmpl is None and index:
        tmpl = index.npc(3)
    rec = (tmpl or {}).get('record') or \
        'NPC NPC_3 3 3 E1 0 123 25 (null) SMALL True CHAR_05(15) 0'
    p = rec.split(' ')
    nid = spk['id']
    p[1] = f'NPC_{nid}'
    p[2] = str(nid)
    p[3] = str(spk.get('marker') or nid)
    p[4] = (spk.get('tile') or '(null)').upper()
    p[5] = str(spk.get('angle', 0))
    p[6] = str(spk['lector']) if spk.get('lector') is not None else '(null)'
    return ' '.join(p) + '\n  OBJECTS True\nEND\n'


def patch_qtx(text, quests, index=None):
    """Apply all project quests to a full .qtx text. Returns (text, log)."""
    log = []
    text = text.replace('\r\n', '\n')
    if not text.endswith('\n'):
        text += '\n'
    from . import retail
    for q in quests:
        if q.retail:
            block = retail.block_text(q)
            m = _find_block(text, q.id)
            if m and m.group(0) == block:
                continue
            if m:
                text = text[:m.start()] + block + text[m.end():]
                log.append(('replace', q.id))
            else:
                text = text + block
                log.append(('append', q.id))
            continue
        block = build_quest_block(q).emit()
        npc_text = ''
        for spk in q.speakers:
            if spk.get('new') and isinstance(spk['id'], int) and not re.search(
                    r'^NPC NPC_%d ' % spk['id'], text, re.M):
                npc_text += npc_block(spk, index)
                log.append(('npc', spk['id']))
        m = _find_block(text, q.id)
        if m:
            text = text[:m.start()] + npc_text + block + text[m.end():]
            log.append(('replace', q.id))
        else:
            text = text + npc_text + block
            log.append(('append', q.id))
        text = remove_aoq_to(text, q.id)
        verb = 'PROMOTE' if q.offered else 'TAKE'
        for c in q.conditions_list():
            if c.get('cond') != 'after':
                continue
            line = f"AOQ {verb} {c.get('event', 'TAKE')} Q_{q.id}"
            text = insert_aoq(text, c['quest'], line)
            log.append(('aoq', c['quest'], line))
    if '\r' in text:
        raise model.ModelError('CR in qtx')
    return text, log


# -- lan ----------------------------------------------------------------------

def quest_texts(quest):
    """(tree, {key: text}) with title, journal, dialog and new NPC names."""
    tree, texts = graph_to_tree(quest)
    qid = quest.id
    for key, value in ((f'translateQ_{qid}', quest.title),
                       (f'translateQ_{qid}_QTD', quest.journal.get('take')),
                       (f'translateQ_{qid}_QSD', quest.journal.get('solve')),
                       (f'translateQ_{qid}_QCD', quest.journal.get('close'))):
        # a game quest keeps keys it never had
        if value or not quest.retail:
            texts[key] = value or ''
    for s in quest.speakers:
        if s.get('new') and isinstance(s['id'], int):
            texts[f"translateNPC_{s['id']}"] = s['name']
    return tree, texts


def build_lan(master, quests):
    """(full master .lan bytes, overlay .lan bytes)."""
    tr, aliases, rest = tw1_lan.read(master)
    trees = tw1_lan.parse_trees(rest)
    over_tr, over_trees = {}, []
    for q in quests:
        tree, texts = quest_texts(q)
        prefix = f'translateDQ_{q.id}_'
        for k in [k for k in tr if k.startswith(prefix) and k not in texts]:
            del tr[k]
        tr.update(texts)
        over_tr.update(texts)
        ids = [i for i, tt in enumerate(trees) if tt.id == tree.id]
        if ids:
            trees[ids[0]] = tree
        else:
            trees.append(tree)
        over_trees.append(tree)
    full = tw1_lan.build(tr, aliases, tw1_lan.build_trees(trees))
    overlay = tw1_lan.build(over_tr, [], tw1_lan.build_trees(over_trees))
    return full, overlay


# -- environment ----------------------------------------------------------------

def game_running():
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'],
                             capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess,
                                                   'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return running_game_name(out.stdout) is not None


def running_game_name(tasklist_csv):
    """Name of a running Two Worlds process in ``tasklist /FO CSV`` output."""
    for ln in tasklist_csv.splitlines():
        name = ln.split(',')[0].strip('"')
        if name.lower().startswith(GAME_EXE_PREFIX) and \
                name.lower().endswith('.exe'):
            return name
    return None


def wd_paths(path):
    """Inner paths of a .wd without decompressing the file data."""
    import struct
    import zlib
    with open(path, 'rb') as f:
        f.seek(-4, 2)
        dir_off = struct.unpack('<I', f.read(4))[0]
        f.seek(-dir_off, 2)
        raw = f.read()
    d = zlib.decompressobj()
    table = d.decompress(raw) + d.flush()
    off = 8
    count = struct.unpack_from('<H', table, off)[0]
    off += 2
    out = []
    for _ in range(count):
        nlen = table[off]
        off += 1
        out.append(table[off:off + nlen].decode('latin-1'))
        off += nlen
        flags = table[off]
        off += 13
        if flags & 0x08:
            off += 1 + table[off]
        if flags & 0x10:
            off += 4
        if flags & 0x20:
            off += 16
    return out


def registry_mods():
    """{archive name: DWORD} from HKCU\\...\\Mods."""
    try:
        import winreg
    except ImportError:
        return {}
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_MODS) as k:
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = val
                i += 1
    except OSError:
        pass
    return out


def enable_mod(name):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_MODS) as k:
        try:
            old = winreg.QueryValueEx(k, name)[0]
        except OSError:
            old = None
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 1)
    return old


def conflicts(game_dir, archive):
    """Other enabled Mods\\*.wd that also ship the full qtx or master lan
    (README 3.1: the later one wins silently)."""
    reg = registry_mods()
    out = []
    mods = os.path.join(game_dir, 'Mods')
    names = sorted(os.listdir(mods)) if os.path.isdir(mods) else []
    for name in names:
        if not name.lower().endswith('.wd') or name.lower() == archive.lower():
            continue
        try:
            paths = set(wd_paths(os.path.join(mods, name)))
        except Exception:
            continue
        hit = [p for p in (INNER_QTX, INNER_LAN) if p in paths]
        if hit and reg.get(name, 0):
            out.append((name, hit))
    return out


# -- packing --------------------------------------------------------------------

def _entries(path):
    return {e.path: e for e in tw1_wd.read(path)}


def pack_archive(archive, files, log=print, remove=()):
    """Merge ``files`` into ``archive`` (or create it) with buglord's wdio,
    drop the entries in ``remove``, verify content byte for byte and the
    directory metadata of every untouched entry, then replace the archive.
    A one-time backup ``<archive>.qf2backup`` keeps the state before the
    first export."""
    stage = tempfile.mkdtemp(prefix='qf2_')
    new = archive + '.new'
    remove = set(remove) - set(files)
    try:
        before = _entries(archive) if os.path.isfile(archive) else {}
        if before:
            log(('unpack', os.path.basename(archive), len(before)))
            with contextlib.redirect_stdout(io.StringIO()):
                wdio.unpack_single(archive, stage)
        for inner in remove:
            path = os.path.join(stage, *inner.split('\\'))
            if os.path.isfile(path):
                os.remove(path)
                log(('removed', inner))
        for inner, blob in files.items():
            dest = os.path.join(stage, *inner.split('\\'))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(blob)
        log(('pack', os.path.basename(archive)))
        if os.path.exists(new):
            os.remove(new)
        with contextlib.redirect_stdout(io.StringIO()):
            wdio.pack_single(stage, new, 1, None)
        after = _entries(new)
        problems = []
        for inner, blob in files.items():
            if inner not in after or after[inner].data != blob:
                problems.append(f'{inner}: content differs')
        for inner in remove:
            if inner in after:
                problems.append(f'{inner}: not removed')
        for inner, e in before.items():
            if inner in files or inner in remove:
                continue
            a = after.get(inner)
            if a is None:
                problems.append(f'{inner}: missing')
            elif (a.data != e.data or a.flags != e.flags
                  or a.extra_str != e.extra_str
                  or a.extra_int != e.extra_int
                  or bool(a.guid) != bool(e.guid)):
                problems.append(f'{inner}: data or metadata differs')
        if problems:
            raise model.ModelError('verification failed: '
                                   + '; '.join(problems[:5]))
        log(('verified', len(after)))
        if before:
            backup = archive + '.qf2backup'
            if not os.path.exists(backup):
                shutil.copy2(archive, backup)
                log(('backup', os.path.basename(backup)))
        os.replace(new, archive)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if os.path.exists(new):
            try:
                os.remove(new)
            except OSError:
                pass


def build_files(project, base_qtx, master_lan, index=None, overlay_name=None):
    """{inner path: bytes} for all quests of the project."""
    quests = list(project.quests)
    files = {}
    base_text = base_qtx.decode('latin-1')
    text, _ = patch_qtx(base_text, quests, index)
    if text != base_text.replace('\r\n', '\n') or any(
            not q.retail for q in quests):
        files[INNER_QTX] = text.encode('latin-1')
    full, overlay = build_lan(master_lan, quests)
    files[INNER_LAN] = full
    files[f'Language\\ZZ_{overlay_name or "QuestForge"}.lan'] = overlay
    return files


def clean_other_overlays(entries, project, own_overlay):
    """Tool overlays (``ZZ_QF_*.lan``) of other projects in the same archive
    that still carry texts or dialog trees of this project's quest ids
    would compete with the new overlay (the game keeps the last loaded
    one). Returns ({inner: stripped lan}, [inner paths to remove])."""
    ids = {q.id for q in project.quests}
    if not ids:
        return {}, []
    pat = re.compile(r'^translateD?Q_(%s)(?![0-9])'
                     % '|'.join(str(i) for i in sorted(ids)))
    replace, remove = {}, []
    for inner, e in entries.items():
        low = inner.lower()
        if (not low.startswith('language\\zz_qf_') or not low.endswith('.lan')
                or low == own_overlay.lower()):
            continue
        try:
            tr, aliases, rest = tw1_lan.read(e.data)
            trees = tw1_lan.parse_trees(rest)
        except Exception:        # not a readable .lan: leave it alone
            continue
        keys = [k for k in tr if pat.match(k)]
        trees2 = [t for t in trees if not pat.match(t.id)]
        aliases2 = [(k, v) for k, v in aliases
                    if not pat.match(k) and not pat.match(v)]
        if not keys and len(trees2) == len(trees) \
                and len(aliases2) == len(aliases):
            continue
        for k in keys:
            del tr[k]
        if not tr and not trees2 and not aliases2:
            remove.append(inner)
        else:
            replace[inner] = tw1_lan.build(tr, aliases2,
                                           tw1_lan.build_trees(trees2))
    return replace, remove


def overlay_stem(project):
    """ZZ_ overlay name: QF_<project>, never the name of an archive's own
    overlay."""
    name = re.sub(r'[^A-Za-z0-9_-]+', '', project.display_name() or '')
    return 'QF_' + (name or 'Quests')


def archive_name(project):
    name = (project.target_archive or '').strip()
    if not name:
        name = re.sub(r'[^A-Za-z0-9_-]+', '', project.display_name() or '') \
            or 'QuestForgeMod'
    if not name.lower().endswith('.wd'):
        name += '.wd'
    return name


def export_mod(project, game_dir, base_dir, index=None, log=print,
               files_only=None, register=True):
    """Full export (plan 3.1 "Exportieren als Mod"). Returns a summary.
    ``files_only``: write the files into that folder instead of packing."""
    name = archive_name(project)
    archive = os.path.join(game_dir, 'Mods', name)
    base_qtx = master_lan = None
    own_overlay = f'Language\\ZZ_{overlay_stem(project)}.lan'
    stale, remove = {}, []
    if os.path.isfile(archive):
        ents = _entries(archive)
        if INNER_QTX in ents:
            base_qtx = ents[INNER_QTX].data
            log(('base', 'qtx', name))
        if INNER_LAN in ents:
            master_lan = ents[INNER_LAN].data
            log(('base', 'lan', name))
        stale, remove = clean_other_overlays(ents, project, own_overlay)
        del ents
    if base_qtx is None:
        with open(os.path.join(base_dir, 'TwoWorldsQuests.qtx'), 'rb') as f:
            base_qtx = f.read()
        log(('base', 'qtx', 'Update16.wd'))
    if master_lan is None:
        with open(os.path.join(base_dir, 'TwoWorldsQuests.lan'), 'rb') as f:
            master_lan = f.read()
        log(('base', 'lan', 'Language.wd'))
    files = build_files(project, base_qtx, master_lan, index,
                        overlay_stem(project))
    for inner, blob in files.items():
        log(('file', inner, len(blob)))
    if files_only:
        for inner, blob in files.items():
            dest = os.path.join(files_only, *inner.split('\\'))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(blob)
        return {'archive': None, 'files': list(files)}
    os.makedirs(os.path.dirname(archive), exist_ok=True)
    for inner in list(stale) + remove:
        log(('overlay_cleaned', inner))
    pack_archive(archive, {**files, **stale}, log, remove)
    old = None
    if register:
        old = enable_mod(name)
        log(('registry', name, old))
    return {'archive': archive, 'files': list(files), 'registry_old': old}
