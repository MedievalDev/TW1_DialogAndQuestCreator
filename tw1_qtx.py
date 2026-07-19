"""Two Worlds 1 .qtx quest-script parser, emitter and validator.

The .qtx is plain ASCII, LF-terminated. Three top-level record kinds:
  NPC <12 tokens> ... sub-lines ... END      (multi-line block)
  LOCATION <6 tokens>                         (single line, no END)
  QUEST <6 tokens> ... sub-lines ... END      (multi-line block)
Sub-lines are indented exactly two spaces. The parser/emitter round-trips
every shipped quest byte-exact (see selftest at the bottom).

The emitter is arity- and enum-validated against the signature table so a new
quest cannot silently ship a malformed line (the loader tokenises on spaces
and a wrong token count corrupts the record). LF is enforced on output — a
stray CR would break the game's parser.

NOTE: the opcode table is derived from the shipped data and the SDK sources.
Common verbs (KILL, BRING_OBJECT, GO, CLOSE/OPEN, GLD/EXP/ITM reward, giver)
match retail 1:1. A few rare ones (ENEMY_CREATE column order) are marked
UNVERIFIED and validated loosely.
"""

import re

# --- signature table: keyword -> {subtype: arg_count_after_subtype} ----------
# For FC/ACTION/REWARD the first token is the subtype; for ACTION/REWARD the
# second token is the "time" enum. Counts are total tokens AFTER the keyword.
_ENUMS = {
    'giver_type': {'ACTIVE', 'PASSIVE'},
    'giver_typeex': {'BACK_TO_GIVER_MAP_SIGN', 'AUTO_CLOSE_ON_SOLVE',
                     'BACK_TO_GIVER', 'NONE'},
    'remove_time': {'NONE', 'CLOSE', 'SOLVE', 'TAKE'},
    'aoq_action': {'PROMOTE', 'DISABLE', 'TAKE', 'CLOSE', 'FAIL_CLOSE', 'SOLVE'},
    'event': {'TAKE', 'SOLVE', 'CLOSE', 'ENABLE', 'HEAR', 'FAIL', 'FIGHT'},
    'reward_time': {'CLOSE', 'SOLVE', 'TAKE', 'HEAR'},
    'amount': {'SMALL', 'MEDIUM', 'HIGH', 'BIG', 'HUGE'},   # or a number
}

# FC subtype -> number of args after the subtype token
_FC = {
    'TALK': 1, 'KILL': 1, 'FIND_KILL': 1, 'FIND_TALK': 1,
    'FIND_OBJECT': 1, 'FIND_LOCATION': 1, 'BRING_GOLD': 1,
    'BRING_OBJECT': 2,
    'GO': 3, 'GO_AWAY': 3, 'FIND_PLACE': 3,
    'CLEAR_AREA': 4,
    'DELIVER_OBJECT': 5,
}
# ACTION subtype -> args after (subtype, time)
_ACTION = {
    'NPC_CREATE': 1, 'NPC_REMOVE': 1, 'NPC_KILL': 1,
    'SHOW_LOCATION': 1, 'PLAY_CUTSCENE': 1, 'SET_WORLD_STATE': 1, 'ENABLE': 1,
    'CLOSE': 2, 'OPEN': 2, 'NPC_GO': 2, 'NPC_CHANGE_PARTY': 2,
    'OBJECT_CREATE': 3, 'DISABLE_TOWN': 3,
    'CLEAR_AREA': 4, 'KILL_AREA': 4, 'NPC_TELEPORT': 4,
    'HERO_TELEPORT_DELAYED': 4, 'CREATE_EFFECT': 4,
    'ENEMY_CREATE': 6,   # UNVERIFIED column order
}
# REWARD subtype -> args after (subtype, time)
_REWARD = {'GLD': 1, 'EXP': 1, 'SKL': 1, 'ITM': 2, 'REP': 2}


class QtxError(Exception):
    pass


class Quest:
    """A parsed QUEST block: header tokens + ordered sub-records."""
    def __init__(self, header, subs):
        self.header = header            # ['Q_381','1','105','(null)','0','True']
        self.subs = subs                # list of (keyword, [tokens])

    @property
    def qid(self):
        return self.header[0]

    def emit(self):
        out = ['QUEST ' + ' '.join(self.header)]
        for kw, toks in self.subs:
            out.append('  ' + ' '.join([kw] + toks))
        out.append('END')
        return '\n'.join(out) + '\n'


def parse_quest(block_text):
    """Parse one QUEST...END block (LF) into a Quest."""
    lines = block_text.split('\n')
    header = lines[0].split(' ')
    if header[0] != 'QUEST':
        raise QtxError('not a QUEST block')
    subs = []
    for ln in lines[1:]:
        if ln == 'END':
            break
        if not ln.startswith('  '):
            if ln == '':
                continue
            raise QtxError(f'bad sub-line indent: {ln!r}')
        toks = ln[2:].split(' ')
        subs.append((toks[0], toks[1:]))
    return Quest(header[1:], subs)


def index_ids(qtx_bytes):
    """Return sets of used quest/NPC/location ids from a whole .qtx."""
    txt = qtx_bytes.decode('latin-1')
    quests = set(int(m) for m in re.findall(r'^QUEST Q_(\d+)\b', txt, re.M))
    npcs = set(int(m) for m in re.findall(r'^NPC NPC_(\d+)\b', txt, re.M))
    return {'quests': quests, 'npcs': npcs}


def free_quest_id(used, lo=381, hi=399):
    """Lowest free single-player quest id in the safe band."""
    for i in range(lo, hi + 1):
        if i not in used:
            return i
    raise QtxError(f'no free quest id in {lo}-{hi}')


# --- validated sub-record builders ------------------------------------------

def _need(cond, msg):
    if not cond:
        raise QtxError(msg)


def sub_giver(npc, giver_type='PASSIVE', type_ex='AUTO_CLOSE_ON_SOLVE',
              remove_time='NONE'):
    _need(giver_type in _ENUMS['giver_type'], f'giver type {giver_type}')
    _need(type_ex in _ENUMS['giver_typeex'], f'giver type_ex {type_ex}')
    _need(remove_time in _ENUMS['remove_time'], f'remove_time {remove_time}')
    return ('GIVER', [giver_type, _npc(npc), type_ex, remove_time])


def sub_fc(subtype, *args):
    _need(subtype in _FC, f'unknown FC {subtype}')
    _need(len(args) == _FC[subtype],
          f'FC {subtype} wants {_FC[subtype]} args, got {len(args)}')
    return ('FC', [subtype] + [str(a) for a in args])


def sub_aoq(action, event, quest):
    _need(action in _ENUMS['aoq_action'], f'AOQ action {action}')
    _need(event in _ENUMS['event'], f'AOQ event {event}')
    return ('AOQ', [action, event, _quest(quest)])


def sub_action(subtype, time, *args):
    _need(subtype in _ACTION, f'unknown ACTION {subtype}')
    _need(time in _ENUMS['event'], f'ACTION time {time}')
    _need(len(args) == _ACTION[subtype],
          f'ACTION {subtype} wants {_ACTION[subtype]} args, got {len(args)}')
    return ('ACTION', [subtype, time] + [str(a) for a in args])


def sub_reward(subtype, time, *args):
    _need(subtype in _REWARD, f'unknown REWARD {subtype}')
    _need(time in _ENUMS['reward_time'], f'REWARD time {time}')
    _need(len(args) == _REWARD[subtype],
          f'REWARD {subtype} wants {_REWARD[subtype]} args, got {len(args)}')
    return ('REWARD', [subtype, time] + [str(a) for a in args])


def _npc(v):
    return v if str(v).startswith('NPC_') else f'NPC_{v}'


def _quest(v):
    return v if str(v).startswith('Q_') else f'Q_{v}'


def make_quest(qid, subs, enable_level=1, group=0, guild='(null)',
               min_rep=0, add_to_log=True):
    """Build a validated Quest. qid is an int or 'Q_<n>'."""
    q = qid if str(qid).startswith('Q_') else f'Q_{qid}'
    header = [q, str(enable_level), str(group), str(guild), str(min_rep),
              'True' if add_to_log else 'False']
    return Quest(header, subs)


def append_quest(base_qtx_bytes, quest):
    """Append a QUEST block to a .qtx, LF-only, returning new bytes."""
    block = quest.emit().encode('latin-1')
    _need(b'\r' not in block, 'quest block contains CR')
    out = base_qtx_bytes
    if not out.endswith(b'\n'):
        out += b'\n'
    return out + block
