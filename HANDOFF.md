# Handoff (2026-10-02, end of Phase 6)

For the next Claude session (cloud or local). Read this, then `CLAUDE.md`, `PLAN.md`, `docs/plan-phase6.md`.

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

## Next
- Jonathan tests NPC Life v2 and the prototype on the Thor and decides about the player body.
- Phase 7 (content) per PLAN.md, or more NPC life: needs from object use flowing back into the sim,
  real food objects (survey which areas have hunger activities), dialogue that reflects needs/money.

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
- Only 8 people have object animations (33 39 41 45 52 53 54 58); seats refuse townspeople in their own
  check. Person 43 is Gramma Hattie (names: string 512 + id - 31).
- To see Kris in melonDS: `urbz_save.py set verify/saves/city.sav x.sav --clock 16:30` (plaza, 16-19h).

## Rules (from CLAUDE.md)
- Never commit ROMs, `project/`, `build/`, `*.dst`, or anything extracted from the game.
- Never edit `project/`; every change is a mod.
- Prove claims in the emulator and add a proof; mark docs facts proven only with evidence.
- Commits end with the Co-Authored-By / Claude-Session lines.

## Working with Jonathan
- Plain language, short sentences, say what's proven vs not. He uses "plan mode" by asking in a message.
- Don't spawn heavy subagents casually.
- Open items for him: try NPC Life v2 on the Thor (the Coffee Shop around 5 pm on a weekday: people sit and chat);
  switch on npc-body-proto and find Kris on the King Tower plaza between 4 and 7 pm; say whether to roll
  the player body out; `manager.bat` on Windows.
