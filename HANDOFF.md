# Handoff (2026-10-05, Phase 8 done: pets, furniture art, imports)

For the next Claude session (cloud or local). Read this, then `CLAUDE.md`, `PLAN.md`, `docs/plan-phase7.md`.

## The project
Jonathan's "dream version" of *The Urbz: Sims in the City* (DS, USA, ROM SHA1
3c01cc5cf3491b5d0ab626ccfb5bcad370662f2f): a living city where townspeople have needs, jobs, money and rent,
saved with the game, plus new content. Approach (decided): **keep modding the real DS game** and replace systems
one at a time with our own C code via hooks (no full rewrite). New systems are portable C with a thin connector.
Players choose mods on the PC (manager) and switch them on/off in the game (Options > Mods).

## Where things stand
- Phases 1-6 done. The kit: extract/build (vanilla byte-identical), mods overlay, text, PNG, fonts, palettes,
  save tool, C code mods, mod platform (switches, mod save data, Options > Mods), headless DeSmuME harness,
  melonDS harness (**melonDS is the gate**: it's what Jonathan uses on his AYN Thor), emulator proofs
  (`tests/proofs.py`).
- **Phase 6 (this session)**, all proven (details and evidence: `docs/plan-phase6.md`, `docs/systems.md`
  "People: movement and object use" and "Player body on a person"):
  - Placement: people are always where their original timetable puts them; out-of-town hours become visits.
    Bug fixed: the connector jumped the sim clock and skipped hour decisions.
  - The people code decompiled (Ghidra 11 headless, see research/README.md; the decompile is not in git):
    wander state 0x23, path requests (3 slots), the object list and classes, `npc_goto_object`.
  - NPC Life v2 visible actions (`mods/npc-life/code/act.inc`): sit, toilet, chat with gestures.
  - Prototype `mods/npc-body-proto` (off by default): Kris with the player's body and animations.
  - Kit: `urbz_save.py set --clock`, harness `poke` script step, `snapshots(pokes_at=)`, melonDS harness
    waits for its window and measures the menu bar (the melonds proof now matches DeSmuME 100%),
    urbz_patch tracks `.inc`/`.h` files, test mod `tests/mods/obj-probe`.

- **Phase 7 (same session), decided with Jonathan:** people keep their own look (the player-body prototype stays
  a prototype); NPC Life has **no needs, money or rent** any more: daily routines from the clock and the place,
  with per-person habits and daily variation, nothing saved (week plan from the game's week number). New
  animations come from **drawn art**: `urbz_anims.py` (template / build). Found and fixed: the game never
  loaded added assets; `urbz_build.py` now moves its asset tables (hidden generated mod `new-assets`).
  Proofs: npc-life-days/stays/visit/reload, npc-act, npc-act-eat, npc-act-release, npc-anims.

- **Phase 8 exploration (2026-10-04), pets and furniture first** (Jonathan: "we plan later once we learn how to
  work on things"). Proven: the Catalog only shows (page field), shops restock daily from per-object masks, buys
  land in Pockets, double-tap + walk + A places at home (proof `pet-place`: a Chicken becomes a walking critter);
  new objects through `objects.json` (proof `objects-new`; the builder moves seven object tables, adds new text,
  `code/objects` answers the place check as the copied object); a new pet kind (proof `pet-new-kind`,
  `mods/pets`). A copied chair (390) places and draws. Pets and furniture are separate mods
  (`mods/pets`: 386, 389-429; `mods/more-furniture`: 430-511; proof `mods-split`). Open: the pet's own art; saving placed new objects; picking up with real inputs; shops not yet seen in the emulator.

- **Pets (2026-10-05)**, Jonathan: "everything within the capabilities of the game, just new stuff; start
  with pets". Done: pets as data (`mods/pets/pets.json`: Puppy 386 from the rooster, Kitten 389 from the
  chicken; `urbz_pets.py` builder stage, `code/pets-kit`), pet art (`urbz_art.py template/preview/
  placeholder`, converted at build), shared art numbering across mods, the 160 KB boot-copy limit now
  ignores zero-filled tables. Proofs `pets-data`, `pets-art`. Facts: 5 drawn directions per slot, slot 0
  stand, 1 walk (docs/systems.md "Pets").

- **Imports (2026-10-05)**, Jonathan: "take our pick of the assets we want to move over". Readers for the other
  Sims DS games (`urbz_fullfat.py`: Apartment Pets + Castaway; `urbz_sims3.py`; `urbz_nsbmd.py`: The Sims 2 DS),
  a software renderer at the Urbz camera (`urbz_import.py`: 30 degrees down, 45 round, ~42 px/m), a gallery
  (`python urbz_import.py gallery`, 1,516 models, local only), `"import"` in `objects.json` / `pets.json`.
  Furniture now has its own art, palette (`code/objects` `objects_own_palette` + OPAL list) and icon (icon
  table moved, models 633+). `mods/pets` imports the beagle and cat. Sources: a local `sources.json` with
  Jonathan's ROM paths (cloud: /root/urbz/others/*.nds). Proofs `rom-grow`, `import-render`,
  `import-furniture`, `import-pet`, `import-melonds` (they SKIP without sources). Formats:
  `docs/other-games.md`; camera, own palettes, space: `docs/systems.md`.

## Next
- **Jonathan:** set up `sources.json`, run the gallery, pick furniture (and pets); test on the Thor.
- Still open: buying in a shop with real taps; picking a pet up with real taps; saving placed new objects;
  using copied/imported furniture (sit, sleep: it behaves as its `like`); The Sims 2 DS skinning/animations
  and its 16 black models; fold `urbz_anims.py` into `urbz_art.py`.
- Later phases (PLAN.md): outfits, hair styles, characters.

## Setup in a fresh environment
1. Clone https://github.com/ROM-HackZ/The-Urbz---Sims-in-the-City-Recomp ; Jonathan supplies the ROM (never in git).
2. `pip install -r requirements.txt` (`--break-system-packages` if needed); `apt install clang lld llvm`.
3. `python3 urbz_extract.py <rom> project` then `python3 urbz_build.py --vanilla` → `[IDENTICAL to original]`.
4. `python3 tests/proofs.py` (about an hour; **never two proof runs at once**, they share `build/proofs/`),
   `python3 tests/test_code_encodings.py`, `python3 tests/test_mod_manager.py`,
   `python3 mods/npc-life/sim/run_test.py`.
5. The manager window needs tkinter (Windows Python has it; on Linux use a Python with tkinter + `xvfb-run`).

## Key facts to not relearn
- Engine names/addresses: `code/game.sym`; details + evidence: `docs/systems.md`, `docs/areas.md`.
- Savestates contain game code → test code mods from `--city` / `--from lobby` (cached per ROM hash).
- `verify/scripts/savegame.json` saves from the city; `loadgame.json` + `--sav` loads after a power-off.
- The entity pool is on the heap and moves with the code region size: scan for people (`people_in`).
- Menu labels have 40 text tiles (about 160 px) and a menu holds 6 labels safely; text outside x 16-248,
  y 8-152 isn't cleared by the game.
- `tests/mods/fast-clock` = a game minute per tick; relocation is then only every 150 game minutes.
- Switch a mod in a test: poke `CORE+4 = 0x80000000 | on << 8 | index` (find 'CORE' with `find_magic`).
- Townspeople have no needs block (entity+0x114 = 0): give them one before any object use (address 0
  mirrors game code). `npc_goto_object` ignores a failed path request: check `path_count` < 3 first.
- Objects: change or add them only through a mod's `objects.json` (`urbz_objects.py`); once any mod adds
  objects, the object tables move and the builder refuses hooks into the old tables. Tables indexed by
  object number: 7 (docs/systems.md); `object_anims` starts at 0x020F34E0 (a 4-byte mistake there made
  new objects invisible or garbled). New numbers: 386 and 389-511 (387/388 are markers).
- Critters (chickens, the Puppy) are entities type 9; their update is 0x0202A61C, pick-up = state 0x12.
- Only 8 people have object animations (33 39 41 45 52 53 54 58); seats refuse townspeople in their own
  check. Person 43 is Gramma Hattie (names: string 512 + id - 31).
- To see Kris in melonDS: `urbz_save.py set verify/saves/city.sav x.sav --clock 16:30` (King Tower roof, 16-19h).
- Anyone's day from the routines: `python mods/npc-life/sim/run_test.py day <id> [week] [weekday]`.
- The game's start checks know animations (vending needs 0x7F + 0x41); NPC Life skips them for seats and snacks.
- Added assets need the moved asset tables (urbz_build does it); keep one mod adding assets (numbers are
  baked into urbz_anims' generated data).

## Rules (from CLAUDE.md)
- Never commit ROMs, `project/`, `build/`, `*.dst`, or anything extracted from the game.
- Never edit `project/`; every change is a mod.
- Prove claims in the emulator and add a proof; mark docs facts proven only with evidence.
- Commits end with the Co-Authored-By / Claude-Session lines.

## Working with Jonathan
- Plain language, short sentences, say what's proven vs not. He uses "plan mode" by asking in a message.
- Don't spawn heavy subagents casually.
- Open items for him: try NPC Life v3 on the Thor; draw animations; `manager.bat` on Windows. He chose not to
  roll out the player body (npc-body-proto stays, off by default).
