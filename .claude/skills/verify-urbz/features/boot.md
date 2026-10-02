# Boot to Create-a-Bod

The built game boots through the legal, EA and Maxis screens and the title, and reaches Create-a-Bod. That's what a player sees in their first 30 seconds, and it exercises the asset loader and both decompressors.

## Sub-features

- `boot-doctor`: header check and first draw.
- `boot-smoke`: a side-by-side run against the original with a per-screen diff.
- `boot-time`: the same with a different DS clock (`--rtc`).

## How to get to it (user POV)

- Load the ROM in an emulator and press A/START through the intro screens.

## Driving it with urbz_verify

- **Doctor.** Run `python verify/urbz_verify.py doctor <rom>`. Expect `DOCTOR OK`.
- **Smoke.** Run `python verify/urbz_verify.py smoke <rom>`. Each step is 300 frames, a screenshot, A, then START. Expect `SMOKE PASS`. A vanilla ROM shows 0.0% on all six steps.
- **Clock.** Run `python verify/urbz_verify.py smoke <rom> --rtc 2026-01-05T23:30`. It's still PASS, and it stays repeatable between runs.
- **Proof.** `verify/evidence/<run>-smoke/compare.png` has the original on top and the build on the bottom, plus `report.txt`.

## Gotchas

- Frame counts are only stable with the pinned clock. Never compare runs with different `--rtc`.
- Mods that change code timing (recompressed chunks decode at a different speed) can shift late animations by a frame. Small % on `step5` alone isn't a failure; check the screenshot.
- `step5` (Create-a-Bod) has a 3D-rendered character. DeSmuME's threaded software 3D renderer can very occasionally lag a frame when the machine is heavily loaded, giving ~2% on `step5` even for vanilla against vanilla (seen once out of 5 runs under 4-process load, 0.0% the other times). Rerun before suspecting the ROM.
- FAIL conditions: all screenshots identical (frozen), or the build is blank where the original draws something.
