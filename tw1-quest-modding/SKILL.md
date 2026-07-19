---
name: tw1-quest-modding
description: >
  Author new quests for Two Worlds 1 (2007, Reality Pump) and drive the
  QuestForge tool plus the legacy TW1 modding tools. Trigger whenever the task
  is about adding/editing Two Worlds 1 quests, dialog or quest text, the
  .qtx/.lan/.idx/.shf/.wd/.par formats, WhizzEdit, the Two Worlds Editor, or
  packaging/deploying a TW1 mod. Also on: "neue quest", "quest hinzufügen",
  "TwoWorldsQuests", "QuestForge", "qtx", "lan file", "mod ins spiel".
---

# Two Worlds 1 — Quest modding

Adding a quest to Two Worlds 1 is a **data-authoring** task, not reverse
engineering: the quest loader is generic and dispatches purely on text tokens
(`QUEST/GIVER/FC/AOQ/ACTION/REWARD/NPC/END`). A new `QUEST` block is a new quest.

The **QuestForge** tool (built for Marco) turns a small JSON spec into a ready
mod `.wd`. Prefer it over editing files by hand.

- Tool location: `C:\Users\marco\Desktop\TwStuff\QuestForge\`
- Full write-up: `QuestForge_Guide.html` in that folder
- Python: `C:/Users/marco/AppData/Local/Programs/Python/Python313/python.exe`
  (the bare `python` alias does NOT work on this machine)

## The pipeline (minimal path — no editor, no WhizzEdit)

1. Write a JSON quest spec (see `example_quest.json`).
2. `python questforge.py my_quest.json --deploy --register`
   → builds `out\<name>.wd`, copies it to the game `Mods\` folder, sets the
   registry DWORD that enables it.
3. Start Two Worlds, **new or loaded single-player game**, open the journal.

QuestForge internally: appends a validated `QUEST` block to the Update16
`TwoWorldsQuests.qtx` base, merges the quest text into the full master
`Language\TwoWorldsQuests.lan`, packs both at their **original inner paths**
into a `.wd`, and re-reads it with the game's own WD reader to verify.

## Hard rules (QuestForge enforces these; keep them if editing by hand)

| Rule | Why |
|------|-----|
| Quest id **381–399** only | SP loader caps at 400; 700+ is multiplayer and invisible in SP. Id must be > 0. |
| **LF line endings, never CRLF** | Parser splits on spaces; a stray `\r` corrupts the last token of every line and breaks the whole file. |
| Base = **Update16.wd**'s `TwoWorldsQuests.qtx` | Patches 1.1–1.6 overwrote it; the loose 1.0 copy in `Lan_QTX Tools\` is stale — do not use it. |
| Reuse an **existing** giver NPC (< 698) | It already has its `MARKER_QUEST_START`; avoids all editor/marker/.lnd work. |
| **Pack only with the reference tools** | Tw1WDRepacker.exe or `wdio.py`. Anything else is not worth the risk — a hand-written packer cost hours of false leads because its archives read back perfectly yet the game ignored them. Marco said this up front; he was right. |
| **Deliver new quests via `AOQ`, not a giver offer** | The working, proven pattern (first live custom quest `Q_385`): add `AOQ TAKE TAKE Q_<new>` to an existing quest — 53 retail quests chain this way. A new quest's own `0.FT.AS` giver offer never fired in testing (possibly because the giver's retail quest occupies the dialog slot). `enableLevel 1` like the retail starter quests. |
| Ship **QTD, QSD and QCD** journal texts | A missing key renders raw (`translateQ_385_QSD` appeared verbatim in the journal on solve). |
| Pick a killable FC target | Quest NPCs are extremely resistant; a `FC KILL` on one is a slog. Prefer normal NPCs/enemies, or warn the player. |

## Deploy / precedence

Two different mechanisms, both verified in-game with marker text:

**`.lan` is KEY-level merged.** The game enumerates every `Language\*.lan` it
can see (all archives), merges translations key-by-key, **later wins**. Proven
order: base `Language.wd` → mod's `TwoWorldsQuests.lan` → `ZZ_*.lan` overlays
(the GOG `ZZ_special.lan` uses exactly this trick). **Dialog trees load from a
mod .lan too** (the `DQ_385` tree came from one). So quest text does NOT need
the 3 MB master: a tiny overlay `Language\ZZ_<Name>.lan` with only your keys +
your dialog trees is enough and beats everything else.

**Other files (.par, .qtx, levels, models) are FILE-level.** One copy wins at
the original inner path — ship a full replacement there.

```
Mods\<Name>.wd  →  Scripts\Quests\TwoWorldsQuests.qtx   (full, base+your quests)
                →  Language\ZZ_<Name>.lan                (your keys + trees only)
```

**Warning — a structurally perfect mod archive can still be ignored wholesale.**
`TagoQuest.wd` (wdio-packed, flags/metadata byte-identical to base patterns,
registry `= 1`) was never loaded, while the *same two files* dropped into
`Yamalin.wd` loaded instantly. Root cause unknown (name? registration history?).
Therefore: after any deploy, verify with a visible text marker (prefix a known
dialog line with `[MOD]`) before debugging content — and if the archive is dead,
ship via an archive that provably loads.

Enable via registry (QuestForge `--register` does this):
```
HKCU\SOFTWARE\Reality Pump\TwoWorlds\Mods    "<Name>.wd" = 1   (DWORD, 1=on)
```

### Mod-loading pitfalls (all three cost real debugging time)

1. **A `.wd` in the game ROOT loads unconditionally**, ignoring the registry.
   A community map mod sitting next to the exe kept overwriting two level
   tiles no matter what the Mod Selector said. Proof: the running game held
   the file open. To disable such a mod, **move the file out** — setting the
   registry to 0 does nothing for it.
2. **Registry `= 0` is a deliberate switch-off, never a dead entry.** Do not
   "tidy" the Mods key. An archive parked in `WDFiles\` with `= 0` was holding
   back an older `TwoWorlds.par`; deleting that entry silently reverted the
   user's gameplay tweaks. Always back up the key (`reg export`) first, and
   check `WDFiles\` and the game root before calling a file missing.
3. **Two enabled mods that ship the same inner path silently fight**, and the
   later one wins. Leftover test archives kept overriding the real quest mod.
   Remove old mod files, do not just disable them.

### Level-header cache poisoning

`Levels\Map_LevelHeaders.lhc` is a *cache*. Regenerating it while a foreign
mod is installed bakes that mod's levels into it, and the entries survive
after the mod is gone — the game then reports levels that no longer exist and
the affected tiles render wrong. Header: `"LC\0\0"` + u32 level count. Compare
the count against the base copy in `Levels.wd` (160) to spot extra entries;
the clean base copy is a safe replacement, since a mod that only edits vanilla
tiles needs no cache changes at all.
To disable a mod, set it to 0 or delete the `.wd`. Saves are unaffected — only
quests/text change. Quest *state* is baked into a save, so test with a new game
or a save from before the quest.

## Format cheat-sheet

### .qtx (quest definitions) — ASCII, LF, `(null)` = unset
```
QUEST Q_381 <EnableLevel> <Group> <Guild> <MinRep> <True|False add-to-log>
  GIVER  <ACTIVE|PASSIVE> NPC_<n> <BACK_TO_GIVER_MAP_SIGN|AUTO_CLOSE_ON_SOLVE|BACK_TO_GIVER> <NONE|CLOSE|SOLVE|TAKE>
  AOQ    <PROMOTE|TAKE|CLOSE|SOLVE|DISABLE|FAIL_CLOSE> <TAKE|SOLVE|CLOSE|ENABLE|HEAR|FAIL|FIGHT> Q_<n>
  FC     KILL|TALK NPC_<n> | BRING_OBJECT <obj> <n> | BRING_GOLD <n> | GO <marker> <sector> <range> | CLEAR_AREA <marker> <sector> <range> <party>
  ACTION <NPC_CREATE|NPC_KILL|OPEN|CLOSE|...> <time> <args...>
  REWARD <GLD|EXP|SKL> <time> <SMALL|MEDIUM|HIGH|num> | ITM <count> <obj> | REP <count> <guild>
END
```
`tw1_qtx.py` holds the full arity/enum table and validates every line.

### .lan (text) — binary; keys carry the `translate` prefix
```
translateQ_<n>       quest title
translateQ_<n>_QTD   journal on take
translateQ_<n>_QSD   journal on solve (optional)
translateQ_<n>_QCD   journal on close
```
Ship the **full master with your keys merged in**, at the original path (see
Deploy above) — a separate side-file is never loaded. The journal also shows
quest **groups** (`translateGROUP_<n>`), which are separate keys from quest
titles. Text-only dialog (no voice) is legal — leave the audio cue empty.

## The Python modules (reusable)

- `wdio.py` — buglord's reference WD packer/unpacker (CC0). **This is what packs
  mods.** `wdio.pack_single(dir, out_wd, 1, None)`, `unpack` via CLI.
- `tw1_wd.py` — WD **reading** only. Its `write()` is deprecated and warns:
  a hand-rolled packer produced archives that every reader accepted but the
  game silently refused to apply. Never pack a real mod with it.
- `tw1_lan.py` — `.lan` read/write. `read(bytes)->(translations, aliases, rest)`,
  `build(translations)->bytes`. Byte-exact round-trip verified.
- `tw1_qtx.py` — `.qtx` parse/emit + validated builders (`make_quest`, `sub_giver`,
  `sub_fc`, `sub_aoq`, `sub_action`, `sub_reward`, `free_quest_id`, `index_ids`).
- `questforge.py` — orchestrates all of the above from a JSON spec.

The game's WD/lan reader for cross-checking lives at
`C:\Users\marco\Desktop\twMP\tw1mp\gamelang.py` (`wd_list`, `wd_read`, `parse_lan`).

## Legacy tools (in `C:\Users\marco\Desktop\TwStuff\`)

- **Quest editor** `Lan_QTX Tools\TwDialogEditor_QTX_IDX\tw1_quest_editor_IDX_QTX.py`
  — views/edits existing `.qtx`/`.idx`, reads `.shf`. Good for inspecting retail
  quests. Cannot create new quests, and its `.qtx` save emits CRLF (use QuestForge
  for new/authored quests).
- **LAN viewer** `Lan_QTX Tools\LanViewer\tw1_lan_viewer.py` — read-only text browser.
- **PAR editor** `Par editor\...\tw1_par_editor.py` — edits values in
  `TwoWorlds.par` (start gear, run speed, …) in place.
- **WD repacker** `WdRepacker\Tw1WDRepacker.exe` — GUI folder↔.wd (QuestForge does
  this headless).
- **Two Worlds Editor** (`TwoWorldsEditorFix.exe`, D:\Games\TwoWorldsSDK) — only
  needed to place a NEW NPC at a NEW location (marker work). Not needed when reusing
  an existing giver.

## When asked to build a quest

1. Chain it via `AOQ TAKE TAKE Q_<new>` from an existing quest (the proven
   route — see Hard rules). A dialog tree is still worth shipping for the
   active/solved/closed NPC reactions.
2. Pick an FC objective (`KILL`, `BRING_OBJECT`, `BRING_GOLD`, `GO`, `CLEAR_AREA`).
3. Write the JSON spec; run `questforge.py <spec> --deploy --register`.
4. **Verify loading first**: mark one known dialog line `[MOD]`; only debug
   quest content once the marker shows in-game (see Deploy warning).
5. Tell Marco to start a NEW game and check the journal (he runs the game —
   driving the client via input automation is unreliable and may be denied).
6. Iterate. To revert, set the mod's registry value to 0.

Reference implementation of the first working quest (`Q_385`, "Der
Schutzgelderpresser", chained from `Q_4`, deployed inside `Yamalin.wd`):
`build_quest_veran.py` + the cleanup steps in the session that produced it.

Never invent opcodes: if a verb/enum isn't in `tw1_qtx.py`'s tables, confirm it
against a real quest in `base\TwoWorldsQuests.qtx` first.
