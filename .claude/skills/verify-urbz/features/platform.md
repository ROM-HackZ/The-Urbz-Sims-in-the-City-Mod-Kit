# Mod platform and NPC Life (Phase 5)

The mod core (`code/core/`) is built in whenever an enabled mod can be switched in-game (`mod.json`
`toggle`, default true for code mods) or uses events (`code/include/mod.h`). It adds the mod table at
0x0214DE20, switchable hook stubs, per-mod save data, the switch record in save memory 0x1FE0, and
the Mods page (Options > Mods). `mods/npc-life` is the first mod built on it.

## Sub-features

- `switch-call` / `switch-data`: a mod switched off stops (call stub goes to the original target; data
  bytes restored), switched on works again.
- `switch-persist`: a switch changed in the game is in save memory at once and holds after power-off.
- `save-block`: mod data after the game's data in a save slot; back after power-off; defaults on a
  vanilla save; a build without mods loads the save; a switched-off mod's data is carried unchanged.
- `mods-page`: Options shows Settings / Save Game / Mods / Quit Game; Mods lists each mod with ON/OFF
  (blue arrow = on, red = off); a tap switches it; "<mod>: info" opens the mod's info page; Back returns.
- `npc-life`: the sim runs on game minutes, writes live timetables, the game walks people in and out
  to match, it is saved, and switching it off restores the original timetables.
- `manager`: `mod_manager.py` window (tick, order, Build, Play, Add mod zip).

## How to get to it (user POV)

- Build with any code mod (e.g. `--mod clock-speed`). In the city tap Options (128,180), then Mods
  (61,120). Rows: slot k at x = 64 (even k) / 192 (odd k), y = 28 + 46 * (k / 2).
- `manager.bat` (Windows) or `python mod_manager.py` opens the manager.

## Driving it

- **Never run two proof runs at once**: they share `build/proofs/`.
- Find the core's state with `find_magic(rom, 1, 0x45524F43 'CORE', 8)`; poke `CORE+4 = 0x80000000 |
  on << 8 | index` to switch mod `index` at the next tick (what the Mods page does; for setup only).
- The mod table: `0x0214DE20 + 32 + 80 * index + 28` is mod `index`'s switch byte.
- NPC Life state: magic 'NPCL' in the code region; `+32` = address of the sim (`sim_t`, npc_sim.h):
  `+8 + 16 * c` = person c (ids 31 + c): needs u8[8], s16 money, act, place, until, home, work, flags.
- Fast time: `tests/mods/fast-clock` (a game minute per tick). Relocation then only runs every 150 game
  minutes, so test walk-ins at normal speed.
- People on screen: scan the heap (`people_in` in tests/proofs.py); the entity pool moves with the
  code region size.
- Save from the city: `verify/scripts/savegame.json`; `play ... --export-sav F`, then `--sav F` with
  `verify/scripts/loadgame.json` for a power-off and load.
- PC simulation test: `python mods/npc-life/sim/run_test.py` (needs a C compiler; reads timetables
  from project/base.nds at test time).
- Manager window under Linux: `xvfb-run` + `xdotool` (tkinter comes with Windows Python).

## Evidence (2026-10-02)

- Proofs: toggle-call, toggle-data, save-block, switch-persist, mods-page, npc-life-days,
  npc-life-walkin, npc-life-off, npc-life-save, npc-life-page (all PASS). Screenshots in
  `build/proofs/mods-page-*.png`, `npc-life-page-*.png`.
- `run_test.py`: 4 city weeks, TEST_SIM PASS (report in the commit "NPC Life simulation").
- Manager: `verify/evidence/manager/window-after-build.png` (tick + Build from the window).
