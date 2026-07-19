"""Reference implementation: the first custom quest that runs in-game.

Q_385 "Der Schutzgelderpresser" - Tago (NPC_3) sends you to kill the
extortionist Vesit Delurna (NPC_151) in Komorin. Fully play-tested:
offer dialog, journal texts, kill objective, return-to-giver reward.

Every design decision here was validated the hard way; do not "simplify":

  * AOQ PROMOTE TAKE Q_385 on the PREVIOUS quest (Q_4) is what makes the
    giver OFFER the quest. A new quest without an AOQ chain is never
    offered, no matter what enableLevel says. PROMOTE = unlock the offer;
    TAKE TAKE would silently auto-accept it instead (no offer dialog).
  * The offer plays in the NEXT conversation after the promoting quest was
    taken - the engine only starts offers at conversation begin. There is
    no way to splice it into the running dialog as an extra menu option.
  * The offer chain in the dialog tree MUST use flag 0.FT.AS (0x20001).
    Plain 0.FT (0x1) is a passive greeting - the NPC stays silent.
  * Ship QTD, QSD *and* QCD journal texts. A missing key shows up raw
    in the journal ("translateQ_385_QSD").
  * Deploy into an archive that provably loads (see --into) and verify
    with a text marker before debugging quest logic: structurally perfect
    standalone mod archives have been ignored wholesale by the game.

Usage:
    python build_quest_tago.py                  -> out/TagoQuest.wd (standalone)
    python build_quest_tago.py --into <mod.wd>  -> merge into an existing,
                                                   known-to-load archive
Packed with buglord's wdio.py - never with a hand-rolled packer.
"""

import os
import shutil
import sys
import tempfile

import questforge
import tw1_lan
import tw1_qtx
import wdio

QID = 385                      # free single-player id (381-399 are unused)
GROUP = 190                    # journal group "Der Ort Komorin"
PREV = 4                       # quest whose TAKE unlocks the offer
GIVER = 3                      # Tago - stands at the game start
GIVER_LECTOR = 123             # from his retail dialog lines
TARGET = 151                   # Vesit Delurna (a quest NPC: tanky - see README)
HERO = 1                       # lector id of the hero
DQ = f'translateDQ_{QID}'

# Dialog-state flags, exactly as the shipped quests use them.
F_FTAS = 0x20001      # 0.FT.AS  Greetings_ActiveStartFirstTime - the offer
F_QNSAE = 0x100       # 0.QNS.AE ActiveEnd, quest not solved yet
F_QSAE = 0x40200      # 0.QS.AE  ActiveEnd, quest solved -> reward
F_QC = 0x8            # 0.QC     quest closed

# (speaker, suffix, flags, cam, next targets)   cams: [1]/[2]=NPC, [6]/[7]=hero
LINES = [
    (GIVER_LECTOR, '0.FT.AS_0',  F_FTAS,  2, [1],
     'Du hast dich als zuverlaessig erwiesen. Vielleicht kannst du mir noch '
     'einmal helfen.'),
    (HERO,         '0.FT.AS_1',  F_FTAS,  7, [2], 'Sprich.'),
    (GIVER_LECTOR, '0.FT.AS_2',  F_FTAS,  2, [3],
     'In Komorin treibt sich ein gewisser Vesit Delurna herum. Er presst den '
     'Haendlern dort Schutzgeld ab.'),
    (HERO,         '0.FT.AS_3',  F_FTAS,  6, [4], 'Und das soll ich richten?'),
    (GIVER_LECTOR, '0.FT.AS_4',  F_FTAS,  2, [5],
     'Kuemmere dich um ihn, und du wirst entlohnt. Du findest ihn mitten in '
     'der Siedlung.'),
    (HERO,         '0.FT.AS_5',  F_FTAS,  6, [], 'Ich reite nach Komorin.'),
    (GIVER_LECTOR, '0.QNS.AE_0', F_QNSAE, 1, [],
     'Delurna treibt es in Komorin weiter. Du solltest dich beeilen.'),
    (GIVER_LECTOR, '0.QS.AE_0',  F_QSAE,  2, [],
     'Ich wusste, dass auf dich Verlass ist. Hier, dein Lohn.'),
    (GIVER_LECTOR, '0.QC_0',     F_QC,    2, [],
     'Die Haendler in Komorin koennen wieder ruhig schlafen. Das ist dein '
     'Verdienst.'),
]

JOURNAL = {
    f'translateQ_{QID}': 'Der Schutzgelderpresser',
    f'translateQ_{QID}_QTD':
        'Tago hat dir berichtet, dass ein gewisser Vesit Delurna in Komorin '
        'die Haendler mit Schutzgeld drangsaliert. Du sollst dich um ihn '
        'kuemmern.',
    f'translateQ_{QID}_QSD':
        'Vesit Delurna ist tot. Kehre zu Tago zurueck und hole dir deine '
        'Belohnung ab.',
    f'translateQ_{QID}_QCD':
        'Vesit Delurna erpresst niemanden mehr. Tago hat dich dafuer '
        'entlohnt.',
}


def build_files():
    """Return {inner_path: bytes} for the quest mod."""
    base_qtx = open(questforge.BASE_QTX, 'rb').read()
    idx = tw1_qtx.index_ids(base_qtx)
    assert QID not in idx['quests'], f'Q_{QID} already exists in the base'
    assert GIVER in idx['npcs'] and TARGET in idx['npcs'], 'NPC missing'

    # --- the quest ---------------------------------------------------------
    quest = tw1_qtx.make_quest(QID, [
        tw1_qtx.sub_giver(GIVER, 'ACTIVE', 'BACK_TO_GIVER_MAP_SIGN', 'NONE'),
        tw1_qtx.sub_fc('KILL', f'NPC_{TARGET}'),
        tw1_qtx.sub_reward('GLD', 'CLOSE', '500'),
        tw1_qtx.sub_reward('EXP', 'CLOSE', '250'),
    ], enable_level=1, group=GROUP)
    qtx = tw1_qtx.append_quest(base_qtx, quest).decode('latin-1')

    # --- chain the offer off the previous quest ----------------------------
    marker = f'QUEST Q_{PREV} '
    start = qtx.index(marker)
    end = qtx.index('END', start)
    block = qtx[start:end]
    assert f'AOQ PROMOTE TAKE Q_{QID}' not in block
    assert '\n  REWARD' in block, 'unexpected Q_4 layout'
    patched = block.replace(
        '\n  REWARD', f'\n  AOQ PROMOTE TAKE Q_{QID}\n  REWARD', 1)
    qtx = qtx[:start] + patched + qtx[end:]
    qtx = qtx.encode('latin-1')
    assert b'\r' not in qtx, 'CRLF would corrupt the qtx parser'

    # --- text + dialog tree: merged master AND a tiny ZZ_ overlay ----------
    # The .lan system merges keys from every Language\*.lan it sees, later
    # wins. Ship both: the full master (canonical path) and a small overlay.
    new_text = dict(JOURNAL)
    entries = []
    for lector, suffix, flags, cam, nxt, text in LINES:
        tid = f'{DQ}_{suffix}'
        new_text[tid] = text
        entries.append(tw1_lan.DialogEntry(
            lector=lector, tid=tid, cue='', next=nxt, flags=flags,
            cams=[cam], anim1=0, anim2=0))
    tree = tw1_lan.DialogTree(DQ, entries)

    master = open(questforge.BASE_LAN, 'rb').read()
    translations, aliases, rest = tw1_lan.read(master)
    translations.update(new_text)
    trees = [t for t in tw1_lan.parse_trees(rest) if t.id != DQ] + [tree]
    full_lan = tw1_lan.build(translations, aliases, tw1_lan.build_trees(trees))
    overlay = tw1_lan.build(new_text, [], tw1_lan.build_trees([tree]))

    return {
        'Scripts\\Quests\\TwoWorldsQuests.qtx': qtx,
        'Language\\TwoWorldsQuests.lan': full_lan,
        'Language\\ZZ_TagoQuest.lan': overlay,
    }


def main():
    files = build_files()
    for p, d in files.items():
        print(f'  {p}  {len(d):,} B')

    if '--into' in sys.argv:
        target = sys.argv[sys.argv.index('--into') + 1]
        tmp = tempfile.mkdtemp(prefix='qf_merge_')
        wdio.unpack_single(target, tmp)
        for inner, data in files.items():
            dest = os.path.join(tmp, inner.replace('\\', os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, 'wb').write(data)
        out = target + '.new'
        wdio.pack_single(tmp, out, 1, None)
        shutil.rmtree(tmp)
        print(f'merged -> {out}  (rename over {target} while the game is '
              f'CLOSED, after keeping a backup)')
    else:
        out = questforge.pack_mod(os.path.join(questforge.HERE, 'out'),
                                  'TagoQuest', files)
        print(f'built: {out}')
        print('NOTE: standalone mod archives are sometimes ignored by the '
              'game - verify with a text marker, or use --into (see README).')


if __name__ == '__main__':
    main()
