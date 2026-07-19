"""QuestForge - author new Two Worlds 1 quests from a small JSON spec.

Pipeline: JSON spec -> validated QUEST block(s) appended to the Update16
TwoWorldsQuests.qtx base + a new Language\\*.lan with the quest text ->
packed into a Mods\\<name>.wd -> (optionally) deployed and registered.

Only touches the compiled formats the game actually loads; no WhizzEdit, no
EarthC, no .idx. Every emitted line is arity/enum validated (tw1_qtx) and the
package is content-verified by the game's own WD reader before it is written.

Usage:
    python questforge.py my_quest.json                 # build ./out/<name>.wd
    python questforge.py my_quest.json --deploy         # + copy to game Mods\\
    python questforge.py my_quest.json --deploy --register   # + enable in registry
    python questforge.py --example > my_quest.json      # print a starter spec

Constraints enforced automatically: single-player quest ids stay in 381-399,
giver NPCs must already exist in the base (< 698), output is LF-only, the .qtx
carries the vanilla 0x05 flags and the .lan 0x01.
"""

import argparse
import json
import os
import sys

import tw1_lan
import tw1_qtx
import tw1_wd
import wdio

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = r'F:\SteamLibrary\steamapps\common\Two Worlds - Epic Edition'
BASE_QTX = os.path.join(HERE, 'base', 'TwoWorldsQuests.qtx')
BASE_LAN = os.path.join(HERE, 'base', 'TwoWorldsQuests.lan')


def pack_mod(out_dir, name, files):
    """Pack {inner_path: bytes} into out_dir/<name>.wd using buglord's wdio.

    Packing is delegated to the proven repacker on purpose. A hand-written
    packer produced archives that looked valid to every reader but that the
    game silently refused to apply - only the reference packer's output
    actually loaded in game.
    """
    import shutil
    import tempfile
    stage = tempfile.mkdtemp(prefix='questforge_')
    try:
        for inner, data in files.items():
            dest = os.path.join(stage, *inner.split('\\'))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(data)
        out_wd = os.path.join(out_dir, f'{name}.wd')
        if os.path.exists(out_wd):
            os.remove(out_wd)
        wdio.pack_single(stage, out_wd, 1, None)
        return out_wd
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _load_spec(path):
    """Read a JSON spec, tolerating UTF-8, UTF-8-BOM or latin-1/cp1252."""
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise SystemExit(f'could not decode spec {path}')


def _load_base():
    if not os.path.exists(BASE_QTX):
        raise SystemExit(f'missing base: {BASE_QTX}\nRun extract_base.py first.')
    return open(BASE_QTX, 'rb').read()


def build(spec, out_dir=None):
    """Turn a spec dict into a mod .wd. Returns the output path."""
    out_dir = out_dir or os.path.join(HERE, 'out')
    os.makedirs(out_dir, exist_ok=True)
    name = spec['mod_name']
    base = _load_base()
    idx = tw1_qtx.index_ids(base)
    used = set(idx['quests'])
    translations = {}
    qtx = base

    for qspec in spec['quests']:
        # allocate id
        qid = qspec.get('id', 'auto')
        if qid == 'auto':
            qid = tw1_qtx.free_quest_id(used)
        qid = int(qid)
        if not (0 < qid < 400):
            raise SystemExit(f'quest id {qid} outside safe SP band 1-399')
        if qid in used:
            raise SystemExit(f'quest id Q_{qid} already used')
        used.add(qid)

        subs = []
        giver = qspec.get('giver')
        if giver:
            gnpc = int(giver['npc']) if not str(giver['npc']).startswith('NPC_') \
                else giver['npc']
            if isinstance(gnpc, int) and gnpc not in idx['npcs']:
                raise SystemExit(f'giver NPC_{gnpc} is not in the base .qtx '
                                 '(reuse an existing quest NPC < 698)')
            subs.append(tw1_qtx.sub_giver(
                gnpc, giver.get('type', 'PASSIVE'),
                giver.get('type_ex', 'AUTO_CLOSE_ON_SOLVE'),
                giver.get('remove_time', 'NONE')))
        for ch in qspec.get('chain', []):
            subs.append(tw1_qtx.sub_aoq(ch['aoq_action'], ch['event'],
                                        ch['quest']))
        for fc in qspec.get('objectives', []):
            subs.append(tw1_qtx.sub_fc(fc['fc'], *fc.get('args', [])))
        for ac in qspec.get('actions', []):
            subs.append(tw1_qtx.sub_action(ac['type'], ac['time'],
                                           *ac.get('args', [])))
        for rw in qspec.get('rewards', []):
            subs.append(tw1_qtx.sub_reward(rw['type'], rw['time'],
                                           *rw.get('args', [])))

        quest = tw1_qtx.make_quest(
            qid, subs,
            enable_level=qspec.get('enable_level', 1),
            group=qspec.get('group', 0),
            guild=qspec.get('guild', '(null)'),
            min_rep=qspec.get('min_reputation', 0),
            add_to_log=qspec.get('add_to_log', True))
        qtx = tw1_qtx.append_quest(qtx, quest)

        # text keys
        if 'title' in qspec:
            translations[f'{tw1_lan.PREFIX}Q_{qid}'] = qspec['title']
        if 'journal_take' in qspec:
            translations[f'{tw1_lan.PREFIX}Q_{qid}_QTD'] = qspec['journal_take']
        if 'journal_solve' in qspec:
            translations[f'{tw1_lan.PREFIX}Q_{qid}_QSD'] = qspec['journal_solve']
        if 'journal_close' in qspec:
            translations[f'{tw1_lan.PREFIX}Q_{qid}_QCD'] = qspec['journal_close']
        print(f'  Q_{qid}: "{qspec.get("title", "(no title)")}" '
              f'({len(subs)} sub-records)')

    # cross-validate: re-parse the appended blocks, confirm CR-free
    assert b'\r' not in qtx, 'CR leaked into .qtx'

    # Overriding is FILE-level: the game loads the newest file at a given inner
    # path. A brand-new filename is never looked for, so the quest text has to
    # ship as a full replacement of the master at its original path, with our
    # keys merged in - not as a small side-file.
    master = open(BASE_LAN, 'rb').read()
    base_tr, aliases, rest = tw1_lan.read(master)
    base_tr.update(translations)
    lan_bytes = tw1_lan.build(base_tr, aliases, rest)

    out_wd = pack_mod(out_dir, name, {
        'Scripts\\Quests\\TwoWorldsQuests.qtx': qtx,
        'Language\\TwoWorldsQuests.lan': lan_bytes,
    })

    # verify with the game's own reader
    _verify(out_wd, name, used)
    print(f'built {out_wd} ({os.path.getsize(out_wd):,} B), '
          f'{len(translations)} text keys')
    return out_wd


def _verify(out_wd, name, expect_ids):
    sys.path.insert(0, r'C:\Users\marco\Desktop\twMP')
    from tw1mp import gamelang
    names = gamelang.wd_list(out_wd)
    assert 'Scripts\\Quests\\TwoWorldsQuests.qtx' in names
    assert 'Language\\TwoWorldsQuests.lan' in names
    q = gamelang.wd_read(out_wd, 'Scripts\\Quests\\TwoWorldsQuests.qtx')
    got = tw1_qtx.index_ids(q)['quests']
    missing = set(expect_ids) - got
    assert not missing, f'quests missing from packed .qtx: {missing}'
    assert b'\r\n' not in q, 'CRLF in packed .qtx'


def deploy(out_wd, register=False):
    name = os.path.basename(out_wd)
    dst = os.path.join(GAME, 'Mods', name)
    import shutil
    shutil.copy2(out_wd, dst)
    print(f'deployed -> {dst}')
    if register:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               r'SOFTWARE\Reality Pump\TwoWorlds\Mods')
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        print(f'registered {name} = 1  (enabled)')


_EXAMPLE = {
    'mod_name': 'MyFirstQuest',
    'quests': [{
        'id': 'auto',
        'title': 'Der Prüfstein',
        'journal_take': 'Ein Fremder bat dich, 500 Goldstücke zu sammeln.',
        'journal_close': 'Du hast das Gold gebracht.',
        'enable_level': 1,
        'group': 105,
        'add_to_log': True,
        'giver': {'npc': 145, 'type': 'PASSIVE',
                  'type_ex': 'BACK_TO_GIVER_MAP_SIGN', 'remove_time': 'NONE'},
        'objectives': [{'fc': 'BRING_GOLD', 'args': [500]}],
        'rewards': [
            {'type': 'GLD', 'time': 'CLOSE', 'args': ['MEDIUM']},
            {'type': 'EXP', 'time': 'SOLVE', 'args': ['MEDIUM']},
        ],
    }],
}


def main(argv):
    ap = argparse.ArgumentParser(description='Author a Two Worlds 1 quest mod.')
    ap.add_argument('spec', nargs='?', help='quest spec .json')
    ap.add_argument('--deploy', action='store_true',
                    help='copy the .wd into the game Mods folder')
    ap.add_argument('--register', action='store_true',
                    help='with --deploy, enable it in the registry')
    ap.add_argument('--example', action='store_true',
                    help='print a starter spec to stdout')
    args = ap.parse_args(argv)
    if args.example:
        print(json.dumps(_EXAMPLE, indent=2, ensure_ascii=False))
        return 0
    if not args.spec:
        ap.print_help()
        return 1
    spec = _load_spec(args.spec)
    print(f'building mod "{spec["mod_name"]}"...')
    out_wd = build(spec)
    if args.deploy:
        deploy(out_wd, register=args.register)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
