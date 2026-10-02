# Plan: Phase 5 — Mod platform + NPC Life v1 (design)

*Approved 2026-10-02. Replaces the earlier draft.*

## Status: done (2026-10-02)

Every step was built and checked; all proofs pass (`python3 tests/proofs.py`, 27 proofs). What changed
from the design while building it:

| Step | Result | Proof |
|---|---|---|
| 1. Static findings | All confirmed in the emulator (boot frame 10-15, load and save cursor 0 → 2,569, EEPROM tail 0xFF and never written, cache routine arguments). Added: `game_start` 0x0204BA98 (first city entry: load or new game), used for "new game → fresh mod data". | toggle-call, toggle-data |
| 1. A1 + A2 | As designed. The core is 6.2 KB + 4 KB zeroed. Switchable call hooks chain; Thumb `jump` hooks can't be switched (build error asks for `"toggle": false`). Extra: `u32 ADDR @name`. | toggle-call, toggle-data, test_code_encodings |
| 2. A3 save block | As designed; a mod switched off when you save keeps its data (carried); blocks for mods not in the build are kept too. Worst-case game data: one variable part (24 lists, 3 bytes per item), see docs/systems.md. | save-block |
| 3. Switch record | As designed (12 switches max). | switch-persist |
| 4. Mods page | A real 4th button: the menus are data, so the core moves the menu pointer array and adds menu 5 (Mods) and 6 (info). Menus are touch-only in this game, so there is no D-pad on the page either. Info pages show up to 5 lines (label tile limits, docs/systems.md). | mods-page, npc-life-page |
| 5. Manager | `mod_manager.py` + `manager.bat`; tested here under a virtual display (tick, Build). **Not yet tried on Windows.** | test_mod_manager |
| 6. Sim | Hourly decisions (the game's timetables are hourly). Home/job/allowed areas come from the original timetables at runtime, so no extracted data is committed. Rent is capped to what the job pays; people without a job get help from family. | run_test.py (4 weeks) |
| 7. Connector | As designed. Not done: the area-load spawn wasn't tested on its own (walk-in was). | npc-life-days/walkin/off/save/page |



## Context
Phases 1–4 built a kit and an engine map; the game itself is still unchanged. Jonathan wants a living city
(townspeople with needs, jobs, money, rent, saved with the game). He also wants players to choose mods on the PC
and switch them on/off inside the game. Phase 5 delivers both:
- **5A Mod platform**: in-game switches, per-mod save data, events, an in-game Mods page, a PC mod manager.
- **5B NPC Life v1**: the first real mod built on the platform.

This replaces the earlier draft in `docs/plan-phase5.md`, with Jonathan's decisions of 2026-10-02:
- **Switches are stored once for the whole cartridge**, not per save. They go in the spare 32 bytes at the end
  of the save chip. Each mod's own data is still kept per save.
- **Platform first**: the order is A1 → A5, then B1 → B2.
- **The Mods page must be a real 4th button on the Options page.** A key combo is not acceptable.

## Static findings this design relies on (read from the code, not yet proven in the emulator)
| Thing | Address | Notes |
|---|---|---|
| Save: serializer call | BL at **0x0207EB44** in `save_finish_slot` | The slot is zeroed first (0x0207EE68 = memset 0xFE0). Bytes used are counted from the cursor *after* the call, so appended bytes are counted and checksummed. |
| Load: deserializer | `save_deserialize_all` **0x020356D8**, BL at **0x0207EE1C** in `save_load_slot` **0x0207EE00** | Exact mirror of the save path. Called from 0x0204BB04 (city enter, load mode). |
| Stream readers | `save_read_bits` 0x0207EC48, `save_read_nibbles` 0x0207ECBC, `save_read_bytes` 0x0207ED78 | Mirror the writers. `read_bytes` byte-aligns first. |
| Save-game screen | `save_game(slot)` 0x0207EBAC, called from **0x02047B20** (UI, at 0x02048018) | 0x02047B20 is the starting point for the Options page work. |
| EEPROM | read 0x02015860 / write 0x020157D4 `(offset, len, buf)` | Slots at (slot*127+1)*32 = 0x20 and 0x1000, 0xFE0 each; header 0x0–0x1F. **0x1FE0–0x1FFF is never written by any ARM caller.** Game calls 0x02098420 / 0x02098388 around card access (lock/unlock). |
| Boot save init | 0x0207EE88 (called indirectly): checks the header, reads both slots via BL at **0x0207EF00** | This is where the core reads its switches at boot. |
| City tick | BL world_tick at **0x0204C06C** in the city update 0x0204C014 | One call site, so the core owns it for `on_tick`. |
| Cache | `DC_FlushRange` 0x020B7C70, `DC_WaitWriteBufferEmpty` 0x020B7C8C, `IC_InvalidateRange` 0x020B7C98 | Identified by their CP15 instructions. Switching bytes inside code is safe at runtime. |
| Schedule literals | `schedule_table_ptr_1..5` sit right after 0x020657AC, `schedule_lookup`, 0x0206592C, `npc_present`, `npc_relocate_tick` | Relocation also follows a repointed table. |

All of these are confirmed in the emulator in step 1 or step 2 before anything is built on them. Each gets a
`code/game.sym` name, plus a `game.h` declaration where C uses it.

## 5A. Mod platform

### A1. Mod info (`mod.json`)
- New fields:
  - `version` (string)
  - `author`
  - `toggle` (default true for code mods, false for asset-only mods)
  - `default` (on/off, default on)
  - `conflicts` (list of mod names)
  - `save_bytes` (most save space the mod will use)
- `urbz_mod.py list` shows the new fields. `urbz_build.load_mod_list` / `build()` refuse conflicting mods and
  report the total `save_bytes` against the budget (A3).
- Existing `mod.json` files keep working: all new fields are optional.

### A2. Core + switches (the main builder work, in `urbz_code.py`)
- **`code/core/`**: the C source of the core (`modcore.c`, `mod.h` API) with a committed prebuilt
  `build/patch.bin` (same pattern as `mods/npc-visit`), so building ROMs still needs no compiler. Placed first in
  the code region, at a fixed address (0x0214DE20), so tests can find it without searching.
- **The core is added only when a build has at least one `toggle` mod or a mod using events.** A vanilla build
  stays byte-identical, and asset-only builds are unchanged.
- **Mod table** (generated by `apply_code`, right after the core):
  - Header `{'MODC', version, count}`.
  - One row per mod: `{char name[16], u32 name_hash, u8 on, u8 flags(toggle, default, events), u16 save_bytes,
    event pointers[8], data-patch list pointer}`.
  - Event pointers come from fixed function names in the mod's `patch.json` symbols (`mod_on_tick`,
    `mod_on_minute`, ...), so a mod adds no hooks.txt lines for events.
- **Hook stubs**: generated into the code region; all ARM, with `ldr pc` doing ARM/Thumb interworking.
  - `call`: the BL goes to a stub that checks `on`; if on, `ldr pc =func`, else `ldr pc =original target`.
    - Uses r12 only. Flags may be clobbered at a call site (AAPCS).
    - Several mods on one call site form one chain: the first enabled mod in load order wins. This replaces
      today's "two mods on one address" error for calls only.
  - `wrap`: the trampoline grows from 48 to about 64 bytes. It checks `on` before `blx`; r0–r3 and flags are
    already saved.
  - `jump`, ARM: the site goes to a stub that checks `on`. If on, it goes to `func`. If off, it runs the 2
    overwritten instructions (moved, with the same no-PC check as wrap), then `ldr pc =addr+8`.
  - `jump`, Thumb: not switchable. The builder errors if the mod is `toggle: true` and says to set it false.
  - `data`/`u8..u32`:
    - The ROM image keeps the **original** bytes. The builder emits a patch list
      `{addr, len, original[], modded[]}` per mod.
    - The core writes the modded or original bytes at boot and whenever a switch changes, then calls
      `DC_FlushRange` + `IC_InvalidateRange`.
  - `toggle: false` mods: hooks are applied directly, as today (no stubs).
- **Boot**: the core call-hooks 0x0207EF00. It runs the original (read both slots), then reads its 32 bytes at
  0x1FE0 and applies the switches and data patches.
- **Switch record** (EEPROM 0x1FE0, 32 bytes):
  - Header (8 bytes): `'MODS'`, version, count, u16 checksum.
  - 12 × u16 entries: 15-bit name hash, top bit = on.
  - Mods with no entry use their `default`. The builder warns above 12 switchable mods.
  - Written straight away when a switch changes, using the game's EEPROM write inside its lock/unlock pair.
- **Events** (`code/include/mod.h`). The core owns each game hook and calls only enabled mods:
  - `on_boot`
  - `on_tick` (BL 0x0204C06C)
  - `on_minute(elapsed)`: the core compares `game_time` each tick and passes the number of minutes that passed,
    so sleep fast-forward and clock jumps don't lose time
  - `on_area_enter(area)` (a BL at the end of `area_enter`; picked in step 1)
  - `on_save(buf, max) -> used`, `on_load(buf, len)`
  - `on_enable`, `on_disable`
  - plus `mod_is_on()`
- Result: `clock-speed` and `npc-visit` become switchable with no change to their files.

### A3. Per-mod save data
- The core call-hooks **0x0207EB44**. It runs `save_serialize_all`, then appends to the stream with
  `save_write_bytes`:
  - `'MODS'`, version, then per mod `{u32 name_hash, u16 len, bytes}`, then an end marker.
  - Space = 0xFDE − (cursor − slot buffer).
  - If the blocks don't fit: drop the lowest-priority blocks, set a "save full" flag (shown on the Mods page) and
    keep the game's own data intact.
- The core call-hooks **0x0207EE1C**. It runs `save_deserialize_all`, then reads after the cursor with
  `save_read_bytes`:
  - If there is no `'MODS'`, it's a vanilla save: each mod gets `on_load(NULL, 0)` → defaults.
  - Blocks for mods that are off or not in this build are **kept in a core buffer and written back unchanged**,
    so switching a mod off never loses its data.
- `urbz_save.py info` learns to show the block (it scans for `'MODS'` and checks its structure).
- Before relying on the budget: work out the worst-case game stream size by reading `save_serialize_all`
  (fixed vs. variable-length parts), and record it in `docs/systems.md`.

### A4. In-game Mods page (a real 4th Options button)
- Reverse-engineering steps:
  1. Start from 0x02047B20 (the save-game UI) and string ids 131/132/133 ("Settings", "Save Game",
     "Quit Game").
  2. Find the Options list builder, its button table, hit boxes, layout and dispatch.
  3. Find the bottom-screen draw (`FUN_02033bc8`) and the game's input state (keys and touch).
- Add a "Mods" entry:
  - Extend the button table in the code region if it's a table; patch its count and layout.
  - The label is a new text-bank string if `urbz_text.py` can append one, or drawn by the core.
- Our page:
  - One row per mod: name, version, ON/OFF; switches marked "always on" are greyed.
  - D-pad + A or a tap switches a mod; B leaves.
  - Shows the "save full" warning.
  - Pages of 8 rows if needed.
  - Uses the game's font draw; reached through the game's own state machine, so the clock pauses like other
    menus.
- If the list can't take a 4th row as is: re-lay out the existing buttons (move hit boxes and graphics). Don't
  fall back to a key combo.
- The NPC Life debug page (B2) is reached from the Mods page (a row's "info").

### A5. PC mod manager
- **First**: Jonathan confirms the native Windows build (`build.bat` with `clock-speed`), since the manager
  relies on it.
- `mod_manager.py` (tkinter) + `manager.bat`:
  - List from `mods/*/mod.json`: checkbox, version, author, description, conflicts, save bytes.
  - **Build** runs the builder and shows its output. **Play** runs the emulator from `emulator.txt`.
  - **Add mod…** installs a zip into `mods/`. It refuses `.nds`/`.sav`/`.dst` files and anything matching
    `project/` paths.
- It calls the same functions as `urbz_mod.py` and `urbz_build.py`, so the window and the command line always
  agree.

## 5B. NPC Life v1 (`mods/npc-life/`)

### B1. Simulation (portable C, `sim/`)
- `npc_sim.c/.h`, no game addresses. The 36 named people (ids 31–66), about 16 bytes each:
  - needs u8[8]
  - money s16
  - job id
  - activity
  - place
  - activity end (minute of week)
- `sim_advance(minutes)`:
  - Decays needs per **game minute**, so it doesn't depend on clock speed.
  - When an activity ends, scores options Sims-style: need urgency × what the place offers − travel; money
    check; work shifts pay; rent is due weekly.
- Output: each person's `u8[24][7]` plan, in the game's own schedule format.
  - It starts as a copy of their original timetable, copied from RAM at runtime, so it never contains
    extracted data.
  - The sim rewrites the current hour and the hours ahead.
  - It only uses areas from that person's original timetable plus `places.json` (so it never uses areas a
    person can't reach). Area 82 means out of town.
- Data, written by us, not extracted:
  - `npcs.json`: home, job area/shift/pay, decay multipliers, start money, likes.
  - `places.json`: area → offers, with effect rows from `docs/objects.md`.
  - `make_data.py` turns both into `sim_data.h`.
- PC harness `sim/test_sim.c` (host clang):
  - Original timetables are generated at test time from `project/` into a gitignored header.
  - It runs 4 city weeks and checks:
    - needs stay in 0..100
    - money cycles and nobody stays broke
    - every plan area is allowed
    - prints a report

### B2. Connector (`code/`)
- A live 49-pointer table in the mod's BSS: pointers to the sim's plans for ids 31–66, and the original
  pointers for 67–79.
- `u32` data hooks on `schedule_table_ptr_1..5` → the live table (switchable through A2). The game's relocation,
  area-load spawns and phone "where I'll be" lines then follow the sim, and quest overrides still win first.
- Events:
  - `on_minute(n)` → `sim_advance(n)`
  - `on_save/on_load` → about 600 bytes
  - `on_enable` → start or resume from saved state
  - `on_disable` → nothing extra: the core restores the literals, and people go back to their timetables
- Debug page (from the Mods page): people in this area, or a chosen person, with needs, money, activity and
  destination.
- Left for Phase 6/7: dialogue that depends on state, and people visibly using objects.

## Order of work (each step ends in a check; commit after each)
1. **Confirm the static findings in the emulator**:
   - save/load hook sites
   - the boot point and when it runs relative to the title screen
   - the EEPROM tail survives `--export-sav`
   - the cache routines

   Then add them to `game.sym`. Then build A1 + A2.

   Check: proofs `toggle-call` (npc-visit) and `toggle-data` (clock-speed), switched by poking the `on` byte in
   the fixed-address table; vanilla stays identical; `tests/test_code_encodings.py` covers the new stubs.
2. **A3 save block**.

   Check: proof `save-block`:
   - block written and read back after save → power off → load
   - a vanilla save loads with defaults
   - a modded save loads in a vanilla build
   - a switched-off mod's block survives a save
3. **Switch record**.

   Check: proof `switch-persist`: switch a mod off → power off → boot → still off at the title screen.
4. **A4 Mods page** (reverse engineering first).

   Check: proof `mods-page`: screenshot; real touch input switches a mod; the setting survives a reboot.
5. **A5 manager**: Jonathan tests it on Windows (after the native build check).
6. **B1 sim + PC harness**.

   Check: `test_sim` passes; a 4-week report.
7. **B2 connector**.

   Check: proofs:
   - `npc-life-days`: from `--from lobby` with `time_speed_index = 1` (sleep speed, about 50 s per game day),
     3 days; needs go up and down, money rises on work days and falls at meals/rent, hungry people go to food
     places
   - `npc-life-walkin`: RAM + screenshot
   - `npc-life-off`: switching off restores the original literals and people follow their timetables
8. Docs: `docs/systems.md` (marked proven), `docs/plan-phase5.md` (replaced by this design), PLAN.md status
   table (Phase 5 = platform + NPC Life), HANDOFF.md, the verify-urbz skill features, README.

## Execution (approved: "do it and complete the entire phase")
- First commit: this design replaces `docs/plan-phase5.md`.
- Then steps 1–8 in order on branch `claude/compassionate-albattani-e4xegv`.
  - Commit after each step's check passes, and push.
  - Never commit the ROM, `project/`, `build/` or savestates.
- If a static finding turns out wrong in step 1, fix the design in `docs/plan-phase5.md` and carry on.
- If the Options page reverse engineering hits a real wall, stop and report to Jonathan. Don't silently swap in a
  key combo.
- Things only Jonathan can do are listed in HANDOFF.md, not faked:
  - Windows `build.bat` / `manager.bat` test
  - flashcart / melonDS boot

## Files
- Changed:
  - `urbz_code.py` (core placement, mod table, stubs, data patch lists)
  - `urbz_build.py` (mod.json fields, conflicts, budget)
  - `urbz_mod.py` (list fields)
  - `urbz_save.py` (MODS block)
  - `code/game.sym`
  - `code/include/game.h`
  - `tests/proofs.py`
  - `tests/test_code_encodings.py`
  - `.claude/skills/verify-urbz/`
  - docs
- New:
  - `code/core/` (`modcore.c`, prebuilt `build/`)
  - `code/include/mod.h`
  - `mod_manager.py`
  - `manager.bat`
  - `mods/npc-life/` (`sim/`, `code/`, `npcs.json`, `places.json`, `make_data.py`, `mod.json`)
  - `.gitignore` rule for the generated timetable header
- Reused:
  - `parse_hooks`, `_arm_branch`, `_thumb_bl`, `_uses_pc`, `_wrap_trampoline`, `Arm9.write` overlap check
    (`urbz_code.py`)
  - link-twice relocation (`urbz_patch.py`)
  - `build`/`ram`/`find_magic` helpers (`tests/proofs.py`)
  - harness `--from lobby`, `--goto`, `--poke`, `--sav`/`--export-sav`

## Verification
- Every session: `python3 urbz_build.py --vanilla` → `[IDENTICAL to original]`.
- After builder changes: `python3 tests/proofs.py` (all 17 old + the new ones) and
  `python3 tests/test_code_encodings.py`.
- `test_sim` on the PC; the new proofs listed in the order above.
- Jonathan: `manager.bat` → tick mods → Build → Play; the Mods button shows on Options and switches mods.

## Risks
- **Options page layout**: unknown until reverse engineered. A 4th button may mean moving graphics as well as
  hit boxes. This is the largest unknown and the riskiest step.
- **Late-game save size**: handled by the worst-case reading in A3 and the "drop lowest priority" rule.
- **Boot hook timing**: if 0x0207EE88 runs after something a data mod affects, switch to an earlier boot hook
  (found in step 1).
- **Thumb callers**: the EEPROM search covered ARM code only. There are 4 Thumb functions; check them in step 1.
- **Flashcart / real hardware**: unchanged from Phase 4 (test once before release).
