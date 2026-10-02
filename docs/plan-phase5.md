# Plan: Phase 5 — Mod platform + NPC Life v1

## Context
Phases 1–4 and two gap passes are done. The game itself is still unchanged: we built a kit (build, text, graphics, fonts, palettes, save tool, C code hooks) and mapped the engine. Jonathan chose to **keep modding the real DS game** and replace systems one at a time with our own C code (not a full rewrite), and wants **players to manage mods: pick them before building, and turn them on/off in the game**. Phase 5 therefore has two parts:
- **5A Mod platform**: on/off switches that work in-game, per-mod save data, events, mod info, a PC mod manager.
- **5B NPC Life v1**: townspeople with needs, jobs, money and rent, simulated city-wide, saved, steering where people go. The first real mod on the platform.

The NPC simulation is written as plain portable C (no game addresses), with a thin connector to the game, so it can move to a PC version later.

## What we reuse (already built and proven)
- Builder + code placer: `urbz_build.py`, `urbz_code.py` (`apply_code`, autoload region at 0x0214DE20, call/jump/wrap/data hooks, `parse_hooks`), `urbz_patch.py` (compile, link-twice relocs).
- `mods/<mod>/mod.json` (name, description), `mods.json` enabled list, `urbz_mod.py` list/enable/disable.
- Engine map (`code/game.sym`, docs): `world_tick`, clock 0x0214112C, `save_serialize_all` 0x020354BC, `save_finish_slot`, `save_write_bytes`, `save_ctx` 0x021470FC, font draw `FUN_02033bc8`, people/schedules (`npc_schedule_table` 0x020E4FD8 and its 5 literal pointers, `npc_present`, `npc_relocate_tick`, quest overrides, visit list, way points), areas, needs/effect rows, money, `docs/objects.md` effects.
- Harness: `--city`, `--from lobby`, `--goto AREA`, `ram/play/watch/find`, `--export-sav`, `tests/proofs.py` (17 proofs).

## 5A. Mod platform

### A1. Mod info (`mod.json`)
Add `version`, `author`, `toggle` (can be switched in-game, default true for code mods), `default` (on/off), `conflicts` (other mod names), `save_bytes` (save space the mod asks for). `urbz_mod.py list` shows them; the builder checks conflicts and the total save budget.

### A2. In-game on/off switches (builder + a small built-in "core" blob)
Whenever any code mod is built in, the builder adds `modcore` (C, in the code region) and a generated **mod table**: per mod `{name, version, enabled byte, flags}`.
- **call** hooks: the BL goes to a generated 12–16-byte stub: if the mod is on, jump to its function, else jump to the original target (original behaviour exactly; ARM/Thumb via `bx`). Two mods on the same call site become a chain (first enabled mod in load order gets it; the rest fall through). This replaces today's "two mods on one address = error" for call hooks.
- **wrap** hooks: the existing trampoline gains the same "on?" check before calling the mod function.
- **jump** hooks: the function start goes to a stub; when off, it runs the 2 overwritten original instructions (moved, same no-PC rule as wrap) and continues at addr+8.
- **data/u8/u16/u32** hooks: the core keeps both the original and the modded bytes and writes the right ones when a switch changes (and at boot). Bytes inside code get a cache flush (find the SDK `DC_FlushRange`/`IC_InvalidateRange`; until found, data hooks on code are build-time only and the builder says so).
- `toggle: false` mods are always on (no stubs).
- Result: `clock-speed` (data mod) and `npc-visit` (call hook) become switchable with no changes to them.

### A3. Per-mod save data + events
- **Save**: wrap the end of `save_serialize_all` and append a block to the slot stream: `'MODS'`, version, enabled flags, then per mod `{u32 name hash, u16 length, bytes}`. Space check against the slot's 4,064 bytes (2,569 used early); if it doesn't fit, write a "skipped" marker and warn (mods fall back to defaults).
- **Load**: RE needed: find the deserializer and its read cursor (mirror of `save_ctx`), then read our block after the game's data. No `'MODS'` marker (vanilla save) → defaults. A vanilla game reading a modded save ignores the extra bytes (the checksum covers them; check this).
- **Events API** (`code/include/mod.h`): `on_tick`, `on_minute` (game clock minute changed), `on_area_enter(area)`, `on_save(buf)`, `on_load(buf)`, `mod_enabled()`. The core owns the single hook for each game event and calls only enabled mods, so mods don't fight over `world_tick`.

### A4. In-game Mods page
- RE: the Options page (list button (128,170): Settings / Save Game / Quit Game), its button table (like the globe's at 0x020F566C), the bottom-screen text draw (`FUN_02033bc8`) and input state.
- Goal: a 4th **"Mods"** button on Options opening our page: one row per mod (name, version, on/off), tap or D-pad + A to switch, B to leave; switches saved with the game (A3).
- Fallback if adding a button is too invasive: open the same page with a key combo while Options is shown (e.g. SELECT). Decide after the RE step.
- The NPC Life debug view (5B) is a second page reached from the same screen.

### A5. PC mod manager
- `mod_manager.py` (tkinter, ships with Python on Windows) + `manager.bat`: list mods from `mods/*/mod.json` with checkboxes, info, conflicts; **Build** (runs the builder, shows errors) and **Play** (emulator from `emulator.txt`); **Add mod…** installs a mod zip into `mods/` (refuses zips containing game files).
- Same rules as `urbz_mod.py` (it calls the same functions), so command line and window agree.

## 5B. NPC Life v1

### B1. The simulation (portable C, `mods/npc-life/sim/`)
- `npc_sim.c/.h`: no game addresses. Per person (36 named people, ids 31–66; ~16 bytes each, ~600 bytes saved): 8 needs (u8), money (s16), job, current activity, place, activity end time.
- Each game minute: decay needs (rates per person); when an activity ends, score options Sims-style (need urgency × what the place gives − travel time; money check; work shifts; rent day weekly) and pick one.
- Output: a **plan table in the game's own schedule format** (u8 area per hour × 7 weekdays per person, built for the hours ahead and revised when plans change).
- Data: `npcs.json` (home, job area/shift/pay, decay multipliers, start money, likes) and `places.json` (area → offers, using real effect rows from `docs/objects.md`, area ids from `docs/areas.md`), compiled by `make_data.py` into a C header.
- **PC test harness** (`sim/test_sim.c`, host clang): run 4 weeks of city time in seconds; check needs stay in range, money cycles, nobody starves or goes broke forever, the plan never uses areas people can't reach.

### B2. The connector (`mods/npc-life/code/`)
- Point the 5 `schedule_table_ptr` literals at our live table (u32 data hooks → switchable via A2). Then the game's own relocation, area-load spawns (`npc_present`) and the phone "where I'll be" lines all follow the simulation, and the quest overrides still win (they're checked first).
- `on_minute` → advance the sim; `on_save/on_load` → its block; turning the mod off restores the original table pointer (people go back to their timetables).
- Debug page: people near you (or a chosen person) with needs, money, activity, destination.
- Skip for v1 (Phase 6/7): state-dependent dialogue lines, visible object use.

## Order of work (each ends in a check)
1. A1 + A2 (stubs, core, mod table) → proof: `npc-visit` and `clock-speed` switched on/off by poking the enabled byte change behaviour; vanilla still identical.
2. A3 RE (load path) + save block → proof: block written, survives save → power-off → load, vanilla save loads with defaults, modded save loads in a build without mods.
3. A4 RE + Mods page → screenshot of the page; switch a mod with real touch input; setting survives save/load.
4. A5 mod manager (manual test on Windows by Jonathan).
5. B1 sim + PC harness → 4-week run report.
6. B2 connector → proofs below. Then docs, README, PLAN, Claude project notes, commit.

## Verification (gate)
- `python3 tests/proofs.py`: all existing proofs pass; vanilla build still byte-identical.
- New proofs: `toggle-call`, `toggle-data`, `save-block` (round trip + vanilla save + build-without-mods), `mods-page` (screenshot with real input), `npc-life-days` (from `--from lobby`, fast-forward 3 game days: needs oscillate, money up on work days and down at meals/rent, people at food places when hungry), `npc-life-walkin` (a person walks into the current area because the sim sent them, RAM + screenshot), `npc-life-off` (switching off restores the original schedule).
- PC harness: `test_sim` passes.
- Jonathan: `manager.bat` → tick mods → Build → play; the Mods page shows and switches mods.

## Risks
- **Load path and Options UI are not mapped yet** (A3/A4 start with RE). Fallbacks: key-combo page; save block found by scanning for `'MODS'` after the game's data.
- **Save space later in the game** is unmeasured (only early saves seen). The block reports its size; budget ~1 KB; pack needs to nibbles if needed.
- **Instruction cache** when toggling bytes in code: build-time only until the flush routine is found.
- Heap: the live table (~8 KB) + sim + core stay well under the measured 700 KB+ headroom.
