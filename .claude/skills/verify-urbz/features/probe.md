# Savestates and memory probes

Probes prove gameplay behaviour that isn't visible on the first screens, such as money, needs, clock and later NPC state. You play to a point with an input script, save a savestate, and read memory after the game runs.

## Sub-features

- `probe-play`: script input from boot or a savestate, then save a new savestate.
- `probe-ram`: read memory ranges after N frames, optionally from a savestate.
- `probe-persist`: a value survives save → reload.

## How to get to it (user POV)

- A player sees these as in-game values. The probe reads the memory behind them.

## Driving it with urbz_verify

Preconditions: a script JSON file, for example `[["wait",600],["press","A"],["press","START"],["wait",300],["shot","atsave"]]`.

- **Save a starting point.** Run `python verify/urbz_verify.py play <rom> --script s.json --save verify/states/title.dst`. It prints `saved state:` and a screenshot is written to the evidence folder.
- **Read memory.** Run `python verify/urbz_verify.py ram <rom> --state verify/states/title.dst --frames 60 --read 0x027FFE00:12`. The header mirror reads `544845205552425a20445300` ("THE URBZ DS").
- **Proof of a change.** Read the same address before and after the action (two `ram` runs, or a script containing the action). Report both values and the evidence paths.

## Gotchas

- Savestates are tied to the ROM build they came from. Re-make them after code patches.
- Game addresses are documented in `docs/systems.md` as they're found (clock, money, motives, NPC table). Don't hard-code guesses.
- Keep reusable savestates in `verify/states/`; one-off states go in a temp folder and get deleted afterwards.
