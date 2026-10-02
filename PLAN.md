# The Urbz DS: the plan

*Living document. Last updated 2026-10-02 (end of Phase 4 plus the gap-closing pass).*

## Goal

A "dream version" of *The Urbz: Sims in the City* (Nintendo DS, USA, game code ASIE): add content and,
above all, make the city **live**:
- People have needs (hunger, bladder, hygiene, energy...), jobs that pay, money, and bills.
- They are simulated city-wide, and the simulation is **saved with the game**.
- When you're in their area you **see** them do things: walk to a table and eat, sit, go to work.

The DS game already moves people between areas on weekly schedules. A needs-driven "brain" replaces the
fixed timetable, so the game's own relocation code does the walking in and out (Phase 4 found and proved
that hook).

## Ground rules

1. **No game data in git.** Bring your own ROM dump (SHA1 `3c01cc5cf3491b5d0ab626ccfb5bcad370662f2f`).
   `project/` (the unpacked game), `build/`, savestates and evidence stay local.
2. **`project/` stays pristine.** Every change is a mod in `mods/<name>/` holding only what it changes
   (asset/chunk files, PNG, text, fonts, palettes, code). `mods.json` lists the enabled ones in order.
3. **A vanilla build must be byte-identical** to the original. It's the first check in every session.
4. **Prove it in the emulator.** A feature is done when the headless DeSmuME harness shows it
   (screenshots/RAM in `verify/evidence/`) and a proof in `tests/proofs.py` re-checks it.
5. **Savestates contain the game code.** Code mods are tested from a fresh boot of that build
   (`urbz_verify.py city`), never from an old savestate.
6. Facts about the engine go in `docs/systems.md` with their evidence, named addresses in
   `code/game.sym`, C declarations in `code/include/game.h`.

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Workshop: mods overlay, asset catalog, emulator harness, Windows scripts | Done |
| 2 | Remove edit limits: tighter-than-EA compressor, LZ77, chunk growth with sprite re-pointing, tile streams | Done |
| 3 | Normal formats: text (TSV), screens and sprites (PNG) | Done |
| 4 | Code patching (C + hooks) and the game-systems map | Done |
| - | Gap-closing pass (all known gaps from phases 1-4) | Done, see below |
| 5 | NPC Life v1: the living city | **Next** |
| 6 | NPC Life v2: visible actions | Planned |
| 7 | Content wiring: new items, clothes, characters | Planned |

## What exists (phases 1-4)

**Workshop and formats**
- `urbz_extract.py` unpacks the ROM: 13,385 assets, 64,378 decoded chunks (raw, LZ77, EA), 623 tile streams.
- `urbz_build.py` rebuilds; edited chunks are recompressed with our encoders (EA 0.982× EA's own size, LZ77
  0.998× Nintendo's), grow in place, or move with sprite layouts re-pointed (all 4,006 multi-chunk assets).
- `urbz_mod.py` (new/edit/status/enable/disable/rescue), `urbz_catalog.py` (asset gallery).
- Text: `urbz_text.py` (8,311 strings, Huffman bank re-encoded; accented letters typed directly).
- Pictures: `urbz_png.py` (screens with new colours in spare rows; simple and **composite** sprites),
  `urbz_palette.py` (recolour via palette files), `urbz_font.py` (8 fonts as PNG sheets, new glyphs).
- Save files: `urbz_save.py` (slots, checksums, clock, money, needs).

**Code mods**
- `urbz_patch.py` compiles C (clang/ld.lld, linked twice to find relocations); `urbz_code.py` places
  every mod's blob in a new autoload block at 0x0214DE20, moves the heap start, applies hooks:
  `call` / `jump` / `wrap` / `data` / `u8|u16|u32`, by address or `game.sym` name. Big blobs move arm7 &
  co. to the end of the cartridge. Shipped mods: `clock-speed` (data), `npc-visit` (C, schedule hook).

**Harness** (`verify/urbz_verify.py`): doctor, smoke, ram, play, trace, city (boot + load
`verify/saves/city.sav`, cached per ROM), find (value search), watch (exec/read/write hooks with stack),
`--poke`, `--sav`/`--export-sav`, `--heap`. Scripts: `newgame.json`, `loadgame.json`, `intro.json`.

**Engine map** (details and evidence in `docs/`): clock and tick, needs (s32 8.24) and decay, action
effect rows, money and job pay, save layout, game state struct, people (ids, schedules, relocation, spawning,
palettes), entities, catalog objects, areas (80, data format, doors/elevators, heap per area), player
look (Create-a-Bod tables and colours), fonts, sprite palette sources, composite sprite format.

## Gap-closing pass (2026-10-02)

Every gap left open by phases 1-4, and how it was closed. All are re-checked by `tests/proofs.py` where an
emulator check is possible.

| Gap | Result | Evidence |
|---|---|---|
| LZ77 repack never seen in-game | The game's own decoder decodes our re-packed, grown LZ77 chunk byte for byte (they are embedded sprite palettes) | proof `lz77` |
| 4 sprite sheets with no known layout (07279, 09195, 09197, 10368) | Paired with their neighbouring layouts (exact chunk match); 4,006/4,006 can grow; 136 bad pairings dropped | proof `grow-neighbour` |
| Font not found | 8 fonts found (assets 11546-11555), format decoded, PNG sheet tool, new glyphs possible; accented letters were already there | 'o' → box shown in the Catalog; proofs `text-accents`, `png-sheets` |
| Composite sprite format unknown | Decoded (u32 per cell), 100% of 146,503 cells valid; OAM matched hardware 15/15; PNG export/import of assembled frames | in-game band painted on the player; proof `png-sheets` |
| Sprite colours fixed / source unknown | Palette sources mapped (people table, player palettes, street rows, record field); `urbz_palette.py` | Kris, skin tone and puddle recolours shown in-game |
| Clothes / Create-a-Bod table | Look struct (10 bytes), save packing, art tables (only gender + hair style pick art), clothing = palette | hair-style swap and skin recolour shown in-game; edited save loaded |
| Which object uses which effect row | Table for every catalog/placed object and pocket item (`docs/objects.md`) | static (code), mechanism proven by proof `action-effect` |
| Where job pay goes | `add_stat(2, earned)` at 0x020516AC; money cap 999,999 | money +50 from a poked shift |
| Thumb hooks untested | ARM→Thumb calls run in-game (and a real bug fixed: the Thumb bit was lost); Thumb site stubs unit-tested | proof `hooks-thumb`, `tests/test_code_encodings.py` |
| Heap measured only on the first screen | Measured in all 80 areas: worst 721 KB free (Carnival with the map open), interiors 1.5-1.7 MB | `docs/areas.md` |
| Areas / travel unknown | 80 areas mapped (names, data, doors, elevators, people); scripted roof → tower lobby with real inputs | `docs/areas.md` |
| `npc-visit` used a raw spawn | Rewritten to answer `schedule_lookup`; the game walks Bayou Boo in by itself | proof `npc-schedule` |

**Still open (low risk or for later phases)**
- Native Windows build of the code-mod path not run on the PC (the cloud build is identical code).
- Real hardware / flashcart: code mods change module params inside the secure area; DeSmuME doesn't check
  the secure-area CRC. Test on a flashcart or melonDS before release.
- Which pixels each clothing palette slot covers; how street objects pick their palette row; record
  types 29/30; script-switched record groups (quests); the 5th-hair-style UI limit.
- The tower's street doors appear only after the first goal (befriend Kris); scripted runs reach the streets
  only with the area-load poke (experiments) until that goal is scripted.

## Phase 5: NPC Life v1 (the living city)

**Outcome:** people's whereabouts come from a simulation of needs, jobs and money instead of fixed
timetables; the state survives save/load; a debug view shows it.

**Hook points (all found and proven in Phase 4)**
- `schedule_lookup_call` 0x0206665C: the relocation loop asks where each person (31..80) should be, every
  150 ticks; our function answers from the brain. (`npc-visit` already does this for one person.)
- `world_tick` 0x02084104 (wrap): advance the simulation (cheap: once per game minute is enough).
- `npc_present` 0x02065AD0 (call sites 0x02064EF4, 0x0204B7F4): area-load spawns; keep it consistent with
  the brain (a person the brain puts here must pass).
- Save: append a versioned NPC block to the save stream after `save_serialize_all` (0x020354BC) and read it
  back on load; about 1.4 KB free per slot (2,569 of 4,064 bytes used). Unknown/old saves → defaults.

**Data (editable in a mod)**
- `mods/npc-life/npcs.json`: per person: home area, job (area, shift hours by weekday, pay), need decay
  multipliers, starting money, favourite places.
- `mods/npc-life/places.json`: area → what it offers (food: hunger +X for $Y; rest; fun; hygiene; work),
  using real effect rows from `docs/objects.md` and area ids from `docs/areas.md`.
- A small converter compiles both into a binary table the C code includes (new asset or `.rodata` in the
  blob).

**Brain (C)**
- Per person (36 named + extras, about 32-48 bytes each, so 1.5-2 KB): 8 needs (u8), money (s16/s32),
  current activity, destination area, activity end time.
- Each game minute: decay needs; when the activity ends, score candidates Sims-style (need urgency × place
  effect − travel time, money check, job shift rules), pick one, set destination + end time. Work adds money,
  food costs money, rent is due weekly.
- Off-screen people are abstract; the relocation hook only reports the destination area.
- State flavour: very low needs or money pick different dialogue lines (text mods + a hook on the line
  choice; to find).

**Debug overlay:** button combo draws nearby people's needs and money (font draw `FUN_02033bc8` /
`FUN_020340f8`, or a text box).

**Gate**
1. Fast-forward 3 game days from a loaded save (harness): the RAM probe shows needs oscillating, money rising
   on work days and falling at meals, people found at food places when hungry.
2. Save → reload: the NPC block round-trips (`urbz_save.py` learns to show it).
3. In a reachable area, a person walks in because the brain sent them (screenshot + RAM).
4. `tests/proofs.py` gets proofs for each.

**Risks:** the date partner and quest overrides in `npc_present` must keep working (don't move quest
characters during their quests); schedules use area 82 (out of town) for absent people.

## Phase 6: NPC Life v2 (visible actions)

- In the player's current area, people the brain says are "eating/sitting/using X" walk to a matching object
  and play its animation: `entity_set_state` / `entity_set_action` / `entity_play_anim` (people route to
  0x020647E0), positions from the area's object records, effect rows applied with `motive_apply_effect` on
  the NPC's own needs.
- Reuse the player's object-use flow where possible (action → walk → animation → effect); fall back to
  "walk to the object and play the animation in place".
- Cap the number of simultaneously acting people (entity pool ≈127, OAM limits, heap ≥ 700 KB free).

**Gate:** in an area with food, a person walks to it, plays the eat animation and their hunger rises
(screenshot + RAM).

## Phase 7: Content wiring

- **Outfits:** clothes are palette choices (`docs/player-look.md`): new colours = palette rows in 11542 +
  UI limits; a new shirt style = a new case in the colour-composition code (`FUN_02083538`).
- **Hair styles:** a 5th style = a 5th pointer in both hair tables (`0x0211CDAC`, `0x020F75D0`) + new
  sprite sheets (appended assets, composite PNG import) + the UI limit (to find).
- **Catalog objects:** append rows to the object tables (`0x020E6D48`, `0x020E8B70`, descriptors
  `0x020EAF84`) — the tables are in arm9, so appending means moving them into a code-mod region and
  re-pointing their users.
- **Characters:** new character ids need entries in the schedule, palette (`0x020D0054`) and name tables.

**Gate:** buy and use/wear the new thing in the harness.

## Working in the cloud

1. Clone the repo; put your ROM somewhere outside git (e.g. `~/roms/urbz.nds`).
2. `pip install -r requirements.txt`; `apt install clang lld llvm` for code mods.
3. `python3 urbz_extract.py ~/roms/urbz.nds project` (about 40 s).
4. `python3 urbz_build.py --vanilla` → `[IDENTICAL to original]`.
5. `python3 tests/proofs.py` (about 15 minutes) → all PASS.
6. Read `CLAUDE.md`, then the `verify-urbz` skill in `.claude/skills/`.

## Decisions log

- 2026-10-01: mods overlay instead of editing `project/`; later mods win.
- 2026-10-01: our own EA/LZ77 encoders (optimal parse) so most edits fit their slots.
- 2026-10-01: code goes in a new autoload block after BSS with the heap moved up (not ITCM, which the SDK
  may hand out); each mod is linked at 0 and relocated by the builder (no compiler needed to build ROMs).
- 2026-10-01: Phase 4 maps everything up front (Jonathan's choice); clock-speed kept as the demo mod.
- 2026-10-02: test from a loaded save (Jonathan's suggestion) instead of replaying character creation:
  `city` boots and loads `verify/saves/city.sav` (10 s vs 30 s).
- 2026-10-02: NPC Life hooks `schedule_lookup` at the relocation call instead of spawning people directly:
  the game then handles walking in/out, entry points and despawning.
- 2026-10-02: no game data in the repo; test mods whose data comes from the game are generated by
  `tests/proofs.py` at run time.
