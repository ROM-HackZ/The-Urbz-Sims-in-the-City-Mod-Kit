# The Urbz DS: the plan

*Living document. Last updated 2026-10-02 (end of Phase 7: NPC Life v3, routines and drawn animations).*

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
| 5 | Mod platform (in-game switches, mod save data, Mods page, manager) + NPC Life v1 | Done (Windows check of the manager open) |
| 6 | NPC Life v2: visible actions, placement that keeps to the original timetables, player-body prototype | Done (Jonathan's check on the Thor open) |
| 7 | NPC Life v3: daily routines (no needs), drawn animations pipeline, new assets that load | Done (art to draw; Jonathan's check on the Thor open) |
| 8 | Content wiring: new items, clothes, characters | **Next** |

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
`--from NAME` (another save: `lobby` = first goal done), `--goto AREA` (load any area), `--poke`,
`--sav`/`--export-sav`, `--heap`. Scripts: `newgame.json`, `loadgame.json`, `intro.json`, `first-goal.json`.

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

## Second gap pass (2026-10-02)

| Gap | Result | Evidence |
|---|---|---|
| No legitimate way past the tutorial for tests | First goal scripted with real inputs (`first-goal.json`: chats with Kris to 30, give the Squeegee, report, save); `verify/saves/lobby.sav` + `--from lobby` | proof `lobby-goto` |
| Streets unreachable in tests | Still locked in a real game (the whole tower chapter, ~12 more goals); `--goto AREA` loads any area through the game's loader from `lobby.sav` | proof `lobby-goto` (Glasstown) |
| Quest overrides for NPC Life | Full list of the 19 hard-coded overrides with their goal-flag conditions; goal table layout (7 x 6 x 12 bytes at 0x02141940) | `docs/areas.md`; flags checked in RAM before/after the first goal |
| Save tool read needs wrongly | Needs are 8.8 fixed point at slot+0x8E (the tool read +0x8F as whole numbers, which only worked on round values); fixed | proof `save-edit` (now on `lobby.sav`) |
| Clothing slot → pixels | Recoloured each slot in-game: male style 0 = shirt front / jacket / sleeves / trousers; female style 4 = shoulder / top / waistband + boots / skirt | `docs/player-look.md` |
| Hair-style UI limit | Count byte 0x020C820A (=4); poking 3 makes it wrap at 3. A 5th style also needs table copies, art, and a save change (2 bits) | `docs/player-look.md` |
| Street object palette row | Set per object kind (`set_palette_row`); record type 16 uses `0x020C2828[variant]`, changed in-game | proof `object-row` |
| Record types 29/30 | 29 = NPC way points (walk in/out; Bayou Boo spawned on one); 30 = spawn zones for the visit list (code only) | `docs/areas.md` |
| Record groups 2+ | `swap_record_groups(show, hide)`; group numbers come from object data. Per-quest mapping left for Phase 7 | `docs/areas.md` |
| Secure area | Documented: unavoidable with an autoload block, low risk, flashcart test before release | `docs/systems.md` |

**Still open**
- Native Windows build of a code mod (`build.bat` with `clock-speed`) on Jonathan's PC: the cloud build uses the
  same code, so this only checks the install.
- A flashcart / melonDS boot of a code-mod build (before a public release).
- Which quest flips which record group (Phase 7), type-30 zones seen at runtime.

## Phase 5: mod platform + NPC Life v1 (done 2026-10-02)

Design and per-step results: **`docs/plan-phase5.md`**. In short:
- **Mod platform** (`code/core/`, `code/include/mod.h`): code mods can be switched on/off in the game
  (Options > Mods, a real 4th button); the choice is kept in the cartridge's save memory. Mods get
  events (tick, game minute, area entered, save/load, on/off, info page) and their own data in each
  save slot, kept even while switched off. `mod.json` has version, author, toggle, default,
  conflicts, save_bytes. A window (`manager.bat`) picks mods, builds and plays.
- **NPC Life v1** (`mods/npc-life/`): 36 people with needs, jobs, money and rent; hourly Sims-style
  choices written into the game's own timetable format, so the game walks them in and out; saved;
  switchable; info page. Portable C simulation with a PC test (4 city weeks).
- Proven in the emulator (tests/proofs.py, 27 proofs): switches, persistence, save data, Mods page with
  real taps, 3 simulated days, a person walking in because the sim sent her, off = back to timetables,
  exact save round trip.

Still open from Phase 5:
- Jonathan: the manager and a code-mod build on Windows; a flashcart/melonDS boot of a code-mod build.
- The area-load spawn with NPC Life wasn't tested on its own (walk-in was); fun/social balance is
  simple (people mostly meet those needs at home and their usual places).

## Phase 6: NPC Life v2 (visible actions) — done

Plan and status: `docs/plan-phase6.md`. In short:
- **Placement:** every hour, each person is where their original timetable puts them; only hours the
  original game has them out of town become visits (cafés, clubs, parks, home). Nobody goes missing.
- **Visible actions** (`mods/npc-life/code/act.inc`): with the game's own "walk to an object and use it"
  (only 6 people had it), the 8 people with object animations sit on chairs and use the toilet; the others
  chat (walk up, face each other, take turns gesturing). Max 4 at once; switching off releases everyone.
- **Player-body prototype** (`mods/npc-body-proto`, off by default): Kris drawn with the player's body and
  animations in her own colours. Jonathan decides whether to roll it out (limits: skirt, no cap, 2 palette
  rows per person).

Not done / later: eating at real food objects (the places we tried have none: people sit at a table),
the needs that objects restore don't flow back into the sim yet, the 28 people without object
animations can't sit (the player body could fix that), people don't say different things yet.

## Phase 7: NPC Life v3 (routines) and drawn animations — done

Plan and status: `docs/plan-phase7.md`. People keep their own look; no needs, money or rent; daily routines
that vary from day to day; `urbz_anims.py` to draw the missing animations per person; the builder now makes
added assets actually load (the game's asset tables are moved to fit them).

## Phase 8: Content wiring (plan: docs/plan-phase8.md: clothes and catalog objects first)

**Changed with Jonathan (2026-10-04):** clothes can wait; first **pets** (everyday pets: dogs, cats...,
bought and placed at home like the Chicken) and **functional furniture**. Exploring before planning.
Learned so far (docs/systems.md "Buyable objects", "Pets"): the Catalog only shows, shops sell (daily stock
from per-object masks), buys go to Pockets, placing works only at home. Built and proven: new object rows
(`objects.json`, `urbz_objects.py`: seven tables moved, new text), and a prototype new pet (`mods/pets-proto`,
critter kind 7). Also a copied chair places and draws. Open: a pet's own art (critter sprites); saving
placed new objects; picking up with real inputs. The real Phase 8 plan is written once these are known.

- **Outfits:** clothes are palette choices (`docs/player-look.md`): new colours = palette rows in 11542 +
  UI limits; a new shirt style = a new case in the colour-composition code (`FUN_02083538`).
- **Hair styles:** a 5th style = a 5th pointer in both hair tables (`0x0211CDAC`, `0x020F75D0`) + new
  sprite sheets (appended assets, composite PNG import) + the UI limit (to find).
- **Catalog objects:** append rows to the object tables (`0x020E6D48`, `0x020E8B70`, descriptors
  `0x020EAF84`) — the tables are in arm9, so appending means moving them into a code-mod region and
  re-pointing their users. New art can now be added as new assets (Phase 7 fixed asset loading).
- **Characters:** new character ids need entries in the schedule, palette (`0x020D0054`) and name tables.

**Gate:** buy and use/wear the new thing in the harness.

## Working in the cloud

1. Clone the repo; put your ROM somewhere outside git (e.g. `~/roms/urbz.nds`).
2. `pip install -r requirements.txt`; `apt install clang lld llvm` for code mods.
3. `python3 urbz_extract.py ~/roms/urbz.nds project` (about 40 s).
4. `python3 urbz_build.py --vanilla` → `[IDENTICAL to original]`.
5. `python3 tests/proofs.py` (about an hour; one emulator at a time) → all PASS.
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
- 2026-10-02 (Phase 5, Jonathan): in-game switches are stored once for the whole cartridge (save
  memory 0x1FE0), not per save; platform before NPC Life; the Mods page must be a real Options button.
- 2026-10-02: the Mods page reuses the game's own menu system (menus are data) instead of a new screen
  state; NPC Life decides hourly and writes the game's timetable format, so the game does the walking;
  homes/jobs/allowed areas are read from the original timetables at runtime (nothing extracted in git).
