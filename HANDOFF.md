# Handoff (2026-10-02, end of Phase 5)

For the next Claude session (cloud or local). Read this, then `CLAUDE.md`, `PLAN.md`, `docs/plan-phase5.md`.

## The project
Jonathan's "dream version" of *The Urbz: Sims in the City* (DS, USA, ROM SHA1
3c01cc5cf3491b5d0ab626ccfb5bcad370662f2f): a living city where townspeople have needs, jobs, money and rent,
saved with the game, plus new content. Approach (decided): **keep modding the real DS game** and replace systems
one at a time with our own C code via hooks (no full rewrite). New systems are portable C with a thin connector.
Players choose mods on the PC (manager) and switch them on/off in the game (Options > Mods).

## Where things stand
- Phases 1-5 done. The kit: extract/build (vanilla byte-identical), mods overlay, text, PNG, fonts, palettes,
  save tool, C code mods, headless emulator harness, 27 emulator proofs (`tests/proofs.py`).
- **Phase 5 (this session)**, all proven in the emulator:
  - Mod platform: `code/core/` (built in whenever a mod is switchable or uses events) + `code/include/mod.h`.
    Mod table at 0x0214DE20; switchable call/wrap/jump stubs; data hooks applied/restored by the core;
    per-mod save data after the game's data; switch record in save memory 0x1FE0; events.
  - Mods page: a real 4th Options button. The bottom menus are data (`menu_table_ptrs`); the core moves the
    pointer array and adds menu 5 (Mods) and 6 (a mod's info page). See docs/systems.md "Bottom-screen menus".
  - `mod_manager.py` + `manager.bat` (tkinter window; zip install with safety checks).
  - NPC Life v1 (`mods/npc-life/`): portable sim (`sim/npc_sim.c`, PC test `sim/run_test.py`), connector
    (`code/main.c`, points the 5 schedule literals at live timetables via `u32 ADDR @live_table`).
- Order of commits on the branch: design → core/switches/save/record → Mods page → manager → sim → connector →
  docs.

## Next (Phase 6, see PLAN.md)
NPC Life v2, visible actions: people in your area walk to an object and use it (eat at a table, sit), with the
effect rows applied to their sim needs. Start from `entity_set_state/action/play_anim` (docs/systems.md
"Entities and actions") and docs/objects.md. Open bits from Phase 5 worth doing first:
- test the area-load spawn with NPC Life on its own (walk-in is proven, load spawn is inferred);
- fun/social balance in the sim is simple (tune `mods/npc-life/*.json`, rerun `run_test.py`).

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

## Rules (from CLAUDE.md)
- Never commit ROMs, `project/`, `build/`, `*.dst`, or anything extracted from the game.
- Never edit `project/`; every change is a mod.
- Prove claims in the emulator and add a proof; mark docs facts proven only with evidence.
- Commits end with the Co-Authored-By / Claude-Session lines.

## Working with Jonathan
- Plain language, short sentences, say what's proven vs not. He uses "plan mode" by asking in a message.
- Don't spawn heavy subagents casually.
- Open items for him: try `manager.bat` on Windows (tick clock-speed, Build & Play; the clock should run at
  half speed and Options > Mods should list it); a flashcart/melonDS boot of a code-mod build.
