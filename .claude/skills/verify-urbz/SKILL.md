---
name: verify-urbz
description: Verify the Urbz DS Mod Kit end to end by building the ROM from project/ plus mods and driving it headlessly in DeSmuME (py-desmume) via verify/urbz_verify.py. Use after any change to the kit, a mod, or game-code patches, before handing a ROM to the player.
---

# Verify the Urbz DS Mod Kit

The "app" is the Nintendo DS ROM this kit builds (`build/Urbz Mod.nds`). A player touches it in an emulator. This skill drives it the same way: a real headless DeSmuME with button presses, touch input, screenshots and memory reads. All paths are relative to the kit root (the folder holding `urbz_build.py`).

## Launch

There is no long-lived server. Each drive is one emulator in its own subprocess.

1. Dependencies (once): `pip install -r requirements.txt` (ndspy, Pillow, py-desmume). On Linux, set `SDL_VIDEODRIVER=dummy`; the harness sets it itself.
2. Build the ROM under test: `python urbz_build.py`. It prints `built ... sha1=...`, the ready signal. `--vanilla` ignores mods; `--mod <name>` builds only that mod.
3. A vanilla build must print `[IDENTICAL to original]`. If it doesn't, someone edited `project/` directly. Run `python urbz_mod.py rescue <mod>` before anything else.

Teardown: nothing to stop. Each `urbz_verify.py` command spawns its emulator child and it exits when the command returns.

## Doctor

`python verify/urbz_verify.py doctor [rom]` (read-only):
- checks the header is THE URBZ DS / `ASIE`
- boots 360 frames
- fails if the screen never draws (crash on boot)

Run it first, and again after any surprising result. Also confirm `project/base.nds` exists and the vanilla build is identical (Launch step 3).

## Drive

All driving goes through `verify/urbz_verify.py` (run `help` for the full text):
- `smoke [rom] [--ref project/base.nds] [--rtc ISO]` runs the build and the original side by side with the same input. It reports % of pixels changed per screen and flags frozen or blank screens.
- `play <rom> --script s.json [--state in.dst] --save out.dst [--rtc ISO]` runs an input script and saves a savestate as a test starting point.
- `ram <rom> [--state f.dst] [--script s.json] --frames N --read ADDR:LEN ... [--rtc ISO]` dumps memory after running.
- `city [rom]` boots the build and loads `verify/saves/city.sav` (Load-an-Urb), caching a savestate
  per ROM hash. **Savestates contain the game code**, so code mods must start from `--city`
  (or `--sav`), never from an old state. `--city` works on ram/play/trace/find/watch.
  `--from lobby` does the same with `verify/saves/lobby.sav` (first goal done, Tower Lobby, Kris 30).
- `--goto AREA[:ENTRY]` loads an area through the game's own loader before the script (the streets
  are still locked in a real game at that point; say so when a check relies on it).
- `find <rom> --city --script s.json --test SHOT=COND ...` searches RAM values across shots;
  `watch <rom> --city --frames N --hook exec:ADDR|read:ADDR|write:ADDR [--stack] [--r0 V]` logs who
  touches an address. `--poke ADDR=HEX` sets memory before a run (experiments only, not proof).
- `play ... --export-sav F` saves the cartridge save memory; `--sav F` boots with one.
- `play ... --heap 30` reports the game heap's tightest point.

Ready-made scripts: `verify/scripts/intro.json` (power-on to Create-a-Bod), `verify/scripts/newgame.json` (power-on through Kris Thistle's tutorial chat to a running city, about 7,000 frames) and `verify/scripts/loadgame.json` (with `--sav`: Load-an-Urb slot 1, about 2,000 frames). `trace` also captures sprite palettes into `verify/palettes/`.

Input scripts are JSON step lists: `["wait",n]`, `["press","A",hold?]`, `["touch",x,y,hold?]`, `["shot","name"]`.

The DS clock is pinned (default `2026-01-05T12:00`), so runs are repeatable. Identical ROMs give 0.0% difference. Use `--rtc` to test time-of-day behaviour (NPC schedules).

Stable handles: the smoke script's screens are fixed points (`step0` legal, `step1–2` EA logo, `step3` Maxis on top with EA still on the bottom screen, `step4` title, `step5` Create-a-Bod). Use frame counts from a pinned clock, not wall time.

## Evidence

- Every command writes to `verify/evidence/<timestamp>-<command>/`: screenshots, `compare.png` (top row = original, bottom = build), `report.txt`, and the recorded input movie (`*.dsm`).
- Proof standards:
  - Drive the real ROM through button/touch input. Don't poke memory to fake an outcome
    (`--poke` may set up a precondition, e.g. unfreezing tutorial needs, never the result).
  - Capture the before and after state: the reference ROM in `smoke`, or a `ram` read before and after the action.
  - For changes with side effects (save data, NPC state), read the memory that holds them and confirm it survives a `play --save` → `ram --state` reload.
  - Byte-identical vanilla build plus a passing vanilla smoke are the baseline for every proof.

## Cleanup

- Delete only scratch you created: temporary ROMs (e.g. `/tmp/*.nds`) and savestates you don't want to keep.
- Never delete `verify/evidence/`. Proof outlives the run.
- Never delete or edit `project/`. To undo a mod, `python urbz_mod.py disable <mod>`.
- No processes outlive a command. If one does hang, kill only the PID it printed, never every python process.

## Helpers

- `python urbz_build.py [out.nds] [--vanilla | --mod NAME ...]`: build
- `python urbz_mod.py list|new|edit|status|enable|disable|rescue`: manage mods
- `python urbz_patch.py new|build <mod>`: compile a code mod; `python urbz_save.py info|set|fix`: save files
- `python verify/urbz_verify.py doctor|smoke|ram|play`: drive and observe
- `python urbz_extract.py <rom.nds> project`: regenerate `project/` from a ROM

## Regression proofs

`python tests/proofs.py` (`--list` for names) re-runs the proofs behind every "Proven" claim in
docs/systems.md: it builds the test mods in tests/mods/ and checks results in the emulator, printing
PASS/FAIL per proof. Run it after changing the builder, the code placer or the harness.

## Feature map

Read `features/README.md` before a verification pass. A proof that covers one entry point is incomplete if the map lists others. Keep the map honest with the `maintain-verification-skill` skill.
