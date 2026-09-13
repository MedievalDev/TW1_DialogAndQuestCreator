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
- **QuestForge 2** (graphical node editor, `TW1QuestCreator.exe`): clone
  `C:\Users\marco\Desktop\TW1QuestCreator`, branch `questforge2`. Start with
  `py -3.12 -m questforge2`, build the exe with `build_exe.bat` (PyInstaller
  under Python 3.13). See README section 13 and `NODE_EDITOR_PLAN.md`.

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
| Quest id **381–399 only** | **There IS a 400 cap in single-player** — play-tested, and it invalidates the older "no cap" note that used to stand here. From 400 up the engine resolves every AOQ reference to the quest down to **quest 0**: the quest never appears and the journal instead shows a phantom entry reading `translateQ_0` / `translateGROUP_0` / `translateQ_0_QTD`, complete with a stray map marker. The identical quest phantomed as `Q_400` and worked on the first try as `Q_389`. (MP map files do use ids like 2001/4001 — that is a different code path, not a counter-example.) That leaves **19 usable ids**; when they run out, reuse ids of retail quests the player has already finished. |
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

### What a single-player save actually stores (format decoded 2026-07)

The active folder is **`%USERPROFILE%\Saved Games\Two Worlds Saves\`** with
the `NNNNNN.TwoWorldsSave` files sitting DIRECTLY in it and **no _files_.txt**
— the load-list label comes from inside each save. (An old
`Documents\TwoWorlds files\Players\<name>\Single\` layout may also exist but
the retail game does NOT load it — writing there does nothing.)
`tw1_save.find_save_dir()` returns the right one.

Format: `"RGMH"` + u32 1 + u32 0x2028 (payload offset) + u32 4 + u32 0 +
u32 pngLen, GUID, a generic UTF-16 header label ("Two Worlds") to 0x2028;
at 0x2028: u32 pngLen again + PNG thumbnail; then ~91 B of UNCOMPRESSED
payload-head preview; then ONE zlib stream (level 6) to EOF. **No length
field or checksum anywhere** — an edited payload re-deflated at level 6 is
accepted by the game (verified: a title change loads fine). `tw1_save.py`
does byte-exact round-trip + title editing.

Payload: `"SV\x01"` + dstring "1.6" + UTF-16 save name + **GUID of the loaded
TwoWorlds.par** (content fingerprint; matches `PARAM_GUID` in
tw1mp/savegame.py for stock) + sections. ~3-6 MB decompressed.

The save does NOT store file versions — it stores **content**:
- an embedded level-state block per *visited* tile. Structure: a u32
  tile-count, then per tile a 20-byte head `[col, tileX, worldY, worldX,
  pathLen]` + dstring `Levels\Map_X.lnd` + tile data + `LN\0\0` + UTF-16
  place name + u32 128 + u32 128 + grid data. Blocks are variable size
  (3-16 KB) and packed back to back. On visited tiles the save's state
  always wins over any mod; unvisited tiles load fresh.
- every spawned quest NPC as a world object (`NPC_Q_006`, …)
- quest state, but **no qtx/lan copies** — quest definitions, texts and dialog
  trees load fresh from the archives on every load. Text mods and .par values
  therefore work in old saves.

**Why a new quest still doesn't appear in an old save:** its `AOQ PROMOTE`
trigger sits on taking the hook quest — in an old save that moment has passed
and never re-fires. Fix without save editing: chain the quest *additionally*
onto a quest the player has not taken yet (multiple AOQ lines are legal). The
Quest Creator's "Also after" field does exactly this.

**Tile reset (parked, 2026-07).** Making a visited tile load fresh from a
map mod by editing the save is HARD and currently unsolved:
- Removing a tile block (and fixing the u32 count) **crashes the game** —
  there are hidden length/offset fields further in the payload that a size
  change breaks.
- A length-preserving edit **loads fine** (no crash), but renaming the
  block's `Levels\Map_X.lnd` path to a phantom had **no effect** — the game
  does not key tile state on that path string (likely on the head
  coordinates instead).
So: size changes are unsafe; the tile identity is not the path. A real
solution needs every size/offset field mapped, or the exact "visited" key
found. Not worth it for the niche benefit (only players with old saves;
new games see mods anyway).

## Removing the end of the game (post-Gandohar free roam) — PROVEN

The game does **not** end because Gandohar dies. It ends because the final
quests fire a cutscene, and the EarthC campaign code
(`PQuestActions.ech::ActionPlayCutscene`) sets `bEndGameAfter = true` **only**
for cutscene numbers 7 or 8 in single-player. Nothing else ends the game.

Those two cutscenes are triggered from the `.qtx`:
- `Q_21` (`FC KILL NPC_5` — NPC_5 is Gandohar) → `ACTION PLAY_CUTSCENE SOLVE 8`
- `Q_18` (the final showdown)               → `ACTION PLAY_CUTSCENE SOLVE 7`

**Delete those two ACTION lines from the qtx and the game never ends.**
Verified in-game via the Komorin early-Gandohar-kill exploit: with the lines
removed, Gandohar dies, no cutscene plays, and the world stays open. This
needs **no EarthC recompile** — the SDK's EarthC.exe (1.6, v0.002) emits a
`78 9c` .eco format the 1.7 game does not load, so avoid that route; the
`.qtx` edit is the whole fix. The other cutscenes (5, 6, 3) are mid-story
and must stay.

To test fast: new game, go to Komorin, kill Gandohar early. Ending gone =
success. (Test needs a NEW game — quest state is baked into saves.)

## Editor markers — each kind has its OWN number space

Positions come from markers placed in the Two Worlds Editor. **The number alone
means nothing** — `Teleport 1` and `Create_Enemy 1` are unrelated points. Every
action reads exactly one kind, and using the right number of the wrong kind is
the single most common cause of "the action silently does nothing":

| qtx | reads marker kind |
|---|---|
| `ACTION HERO_TELEPORT_DELAYED`, `ACTION NPC_TELEPORT` | `Q_Action_Teleport` |
| `ACTION NPC_GO` | `Q_Action_Walk` |
| `ACTION ENEMY_CREATE` | `Q_Action_Create_Enemy` |
| `ACTION OBJECT_CREATE` | `Q_Action_Create_Object` |
| `FC GO`, `FC CLEAR_AREA` | `Q_Solve` |
| NPC placement (`NPC <id> … <cell>`) | `Q_Giver`, **number = the NPC id** |

Retail numbers a quest's markers after the quest (Q_235 spawns at marker 235
and clears marker 235); copying that removes all ambiguity. Verified case:
giver marker 6 in `F02_1` places `NPC_6` (Reist Tungard).

**An NPC declared for a cell with no matching `Q_Giver` marker FREEZES the game
when that cell loads** — the engine wants to instantiate it and has no position.

## Engine pitfalls (each one cost a debugging round)

**`FC CLEAR_AREA` only counts enemies the quest itself spawned.** Editor-placed
enemies are ignored. It needs a paired `ACTION ENEMY_CREATE` of the same group
(106 of retail's 113 CLEAR_AREA quests have one), and the group must be a
*hostile faction*: retail only ever uses 18–23, and group 1 leaves them
peaceful. If nothing spawned — e.g. the spawn fires while the player is in
another cell so the target map is not loaded — the area counts as **already
clear**, and the quest is taken, solved and closed in the same instant, never
reaching the journal. Prefer `FC GO`, which cannot satisfy itself.

**Never `NPC_TELEPORT` into an interior cell.** All 30 retail NPC teleports
target outdoor cells; moving an NPC into a cave crashes the game. For someone
inside, declare the NPC with the interior as its home cell and `NPC_CREATE` it
— retail does exactly that (`NPC_6` in `F2_1`, `NPC_141` in `B8_1`).

**`NPC_GO` only moves an NPC within its own cell, and never straight after
creation.** Retail's four uses all sit on `SOLVE`/`CLOSE` for NPCs long since
present. Ordering a freshly created NPC to walk crashed the game.

**A quest solved by talking to its own giver skips the offer.** The engine
solves first and picks the dialogue state afterwards, so the player hears the
*solved-state* line and the offer conversation is never shown. Put the real
conversation in `0.QS.AE` for such quests. For the same reason, two consecutive
quests must not both be solved by talking to the same NPC — the handover
collapses both conversations into one line.

**`ACTION SHOW_LOCATION` works on `TAKE` only** (20 retail uses on TAKE, zero on
SOLVE) **and only for real POIs**. Location types 19/17/16/12/20 are revealable;
type 10 with radius 0 is a plain region label and cannot be marked — Yamalin
(`LOC_F01_0_05`) ships as one, so it had to be retyped to 19/50 first. A marker
on the map needs a quest whose objective *is* the location (`FC FIND_LOCATION`).

**Reply menus: keep every `next` entry positive.** A negative index is *not*
"hide after use" — the engine treats it as hidden outright, so a menu of four
negatives plus one positive collapses to a single option.

**Regenerate the level-header cache after map edits** with the SDK's
`LevelHeadersCacheGen.bat`. It reads the game's virtual file system, so the maps
must already be packed and swapped in — a map change therefore needs two passes:
pack+swap, run the bat, pack+swap again.

## Voice — reusing the original actors

A dialog line's `cue` names an XACT cue (`XACT\win\Sounds.xsb` holds 7578 of
them; audio in `UnitTalk.xwb`, lip sync in `LipSync\data.lipsync`). **Put an
existing cue on a NEW line and the engine plays that original recording, with
lip sync, for free** — no audio work at all. The price: the subtitle must match
the recording word for word, so such lines are assembled from sentences the
actors already spoke. Available: hero 1820 lines (989 short), Gandohar 101,
Ferid 43, Kira 37. Search them with `voice_index.py`.

Lines without a cue are silent subtitles — 46 % of the hero's retail lines are
too, so mixing is unnoticeable. **When editing an existing dialog, never drop
`cue`/`anim1`/`anim2`**: doing so silences a voiced retail conversation (it
happened to Gandohar's `DQ_5`). The Quest Creator preserves them.

## Removing a quest — strip it everywhere

Deleting the `QUEST` block is not enough. Its dialog tree `translateDQ_<n>` and
its text keys (`translateQ_<n>*`, `translateDQ_<n>_*`) live in the `.lan`, in
the master **and in every `ZZ_` overlay**. Left behind, the giver keeps offering
a quest that no longer exists. Keep the giver's shared retail name
(`translateNPCName…`) and his retail dialog.

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

## Dialog flags — what the SDK script does with them

Source: `D:\Games\TwoWorldsSDK\Scripts\Campaigns\Missions\PInc\PQuestsCommon.ech`
(`GetDialogInputFlags`, `UpdateQuestStateAfterDialog`). Code reading, no game
test yet, consistent with all game findings so far.

The flag word is two bit groups, not an enum. **State bits** decide whether a
line may play: the script starts from all eight and removes the bits of the
current quest state; a line plays when all its state bits are in the current
state, `0x0` always plays. **Event bits** are reported when the conversation
ends after passing such a line.

| Bit | SDK name | meaning |
|---|---|---|
| `0x1` | eFirstTime | first talk, quest enabled and never offered |
| `0x2` | eQuestNotTaken | offer heard, not taken |
| `0x4` | eQuestTaken | taken |
| `0x8` | eQuestClosed | closed |
| `0x10` | eQuestFailed | failed |
| `0x20` | eQuestLowReputation | reputation below the header's minimum |
| `0x100` | eQuestNotSolved | task not done (enabled or taken) |
| `0x200` | eQuestSolved | task done (item/gold/location checked at talk start) |
| `0x10000` | eQuestFightNow | event: giver turns hostile, FIGHT actions |
| `0x20000` | eQuestTakeNow | event: TakeQuest, TAKE actions/rewards |
| `0x40000` | eQuestCloseNow | event: CloseQuest, items/gold removed, CLOSE rewards |

So `0.FT.AS` = FirstTime+TakeNow, `1.TAKE` = NotSolved+TakeNow, `0.QS.AE` =
Solved+CloseNow. There are **no per-line conditions or actions** beyond these
bits; actions hang on quest events. Reply menus (several `next`) only point at
hero lines; state branching goes through hero lines with different state bits,
and `next` across state boundaries is normal retail practice. `HEAR` fires at
the start of the very first talk. The loader also knows `ACTION NPC_DIALOG
<time> NPC_<n> <tree>` (unused in retail, not in `tw1_qtx`, untested).

Columns verified against the loader (`PQuestLoader.ech`):
`ACTION ENEMY_CREATE <time> <type> <count> <level> <marker> <tile> <party>`,
`ACTION OBJECT_CREATE <time> <object> <marker> <tile>`,
`ACTION HERO_TELEPORT_DELAYED <time> <delay> <marker> <tile> <angle>`.
