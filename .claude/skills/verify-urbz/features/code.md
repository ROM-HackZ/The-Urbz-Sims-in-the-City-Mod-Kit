# Code mods (C code and hooks in the game)

`urbz_code.py` (called by the builder) places each enabled mod's compiled blob in a new autoload
block at 0x0214DE20, moves the heap start up, and applies the mod's `code/hooks.txt`.
`urbz_patch.py build <mod>` compiles `code/*.c|*.s` (clang + ld.lld) into
`code/build/patch.bin` + `patch.json`; ROM builds never need a compiler.

## Sub-features

- `code-data`: `data`/`u8`/`u16`/`u32` hooks patch game bytes; no blob, arm9 size unchanged.
- `code-blob`: a C blob is placed, relocated, the heap moves past it, and the code runs.
- `code-hooks`: `call` (rewrite a BL), `wrap` (run before one ARM instruction), `jump` (replace a function).
- `code-relayout`: a big blob pushes arm7/FNT/FAT/banner to the end of the cartridge.
- `code-refuse`: bad hooks fail the build (not a BL, PC-relative wrap, inside BSS, two mods on one address
  (except `call` hooks of switchable mods, which chain), uncompiled C, a Thumb `jump` in a switchable mod).
- Since Phase 5 every code mod is switchable by default, so its hooks go through stubs and the mod core
  is built in (see platform.md); `"toggle": false` in mod.json gives the old direct hooks.
- `u32 ADDR @name` writes the address of something in the mod (NPC Life points the schedule words at
  its own table this way).

## How to get to it (user POV)

- `python urbz_mod.py new my-mod`, `python urbz_patch.py new my-mod`, edit `mods/my-mod/code/`,
  `python urbz_patch.py build my-mod`, then `build.bat`. The build prints
  `code mod my-mod: N hook(s), B bytes at 0214xxxx` and `heap now starts at ...`.

## Driving it

Preconditions: vanilla build identical; `code/functions.json` and `code/game.sym` present.

- **Savestates contain the code.** Never test a code mod from an old savestate. Use
  `python verify/urbz_verify.py city <rom>` (boots the build, loads `verify/saves/city.sav`,
  caches a state per ROM hash) and `--city` on `ram/play/watch/find`.
- **code-data:** build `--mod tests/mods/clock-speed`; `ram <rom> --city --frames 1` and `--frames 61` reading
  `0x0214112C:6` (game_time): the seconds advance 45 per 60 frames (original 90).
- **code-blob + code-hooks:** a test mod with `wrap world_tick f` (counter++) and
  `call time_update_call g` (calls `time_add`, counts): read the counters (find them by a magic
  word in a struct): +30 per 60 frames each, and the struct's copy of the clock equals game_time.
- **code-relayout:** add a ~25 KB blob (a 16 KB `volatile` table + 8 KB zeroed array). The header
  shows arm7 moved (0x30 > 0x1E00000); `smoke <rom>` PASSES 0.0% on every step; both mods' counters run;
  the heap handle at 0x02142004 points past the region.
- **code-refuse:** `call` on a non-BL address, `wrap` on a `ldr rX,[pc,...]`, a hook at 0x02130000,
  the same address in two mods, a `.c` file without `build/`: each prints `BUILD FAILED: ...`.

## Evidence (2026-10-01)

- hello (wrap + call): ticks and clock-update counts +30 per 60 frames; stored clock == game_time.
- 25 KB two-mod build: smoke 0.0% on all 6 steps; heap start 0x02153FA0.
- clock-speed: 10:18:55 -> 10:19:40 in 60 frames (original +1:30). After 30 s from the
  loaded save: 11:10 vs original 11:40.
- jump: `jump motive_get f` with f returning 100: every HUD need bar shows full.
- Refusals all printed BUILD FAILED: BL check, PC-using wrap, BSS address, two mods on 0x02084104,
  jump not at a function start, unknown function name, C source without build/, unknown hook kind.
