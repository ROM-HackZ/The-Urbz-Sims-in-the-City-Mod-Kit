# Contributing

Thanks for wanting to help. Mods, bug reports, docs, research findings and kit improvements are all welcome.

## The one rule: nothing from the game

Never commit anything taken from *The Urbz* or any other game: ROMs, `project/`, extracted files, sprite
sheets, palettes, text dumps, savestates (`*.dst`), or PNGs exported from the game (including art templates
the kit makes for you to draw over, until every pixel is your own). The `.gitignore` covers the usual places.
A mod whose data comes from the game is described as *instructions* the kit carries out on each person's own
copy at build time (see how `poses.json`, `objects.json` and `pets.json` work), never as copied files.

Save files (`.sav`) of your own game are fine; the kit's test saves live in `verify/saves/`.

## Setting up

1. Follow the README's "Getting started" (your own ROM, Python 3.9+, `setup.bat` or
   `pip install -r requirements.txt`, then `python urbz.py extract <rom> project`).
2. `python urbz.py build --vanilla` must print `[IDENTICAL to original]`. If it doesn't, something differs
   (the ROM, or a package version): please open an issue before changing anything.
3. For C code mods: LLVM (`clang`, `ld.lld`, `llvm-objcopy`): `winget install LLVM` on Windows,
   `apt install clang lld llvm` on Debian/Ubuntu, `brew install llvm` on macOS.

## Where things are

- `urbz.py` + `kit/`: the tools. `python urbz.py` lists them; each `kit/urbz_<tool>.py` starts with a docstring
  explaining it.
- `mods/<name>/`: one folder per mod, holding only what it changes or adds. Formats: [docs/modding.md](docs/modding.md).
- `code/`: the C side. `code/core/` is the mod core (in-game switches, mod save data, events, the Mods page;
  API in `code/include/mod.h`), `code/include/game.h` the game's functions and variables for C,
  `code/game.sym` the named addresses, `code/functions.json` a map of the game's functions.
- `docs/systems.md`: the engine reference. `docs/areas.md`, `docs/objects.md`, `docs/player-look.md`,
  `docs/effect_rows.md`, `docs/other-games.md`: more detailed tables. `docs/dev/`: the project's plan and
  history.
- `tests/proofs.py`: emulator proofs; `tests/mods/`: the small test mods they use.
- `verify/`: the headless emulator harness (DeSmuME via py-desmume; melonDS for a few checks), test saves,
  input scripts.
- `research/`: the probes and table generators behind the docs. Kept as a record; many use the absolute paths
  of the machine they were written on (`research/README.md`).

## Making a change

- **Every change to the game is a mod.** Never edit `project/` (`python urbz.py mod rescue` moves accidental
  edits into a mod).
- **Prove it in the emulator.** The kit's habit: a claim about the game ("this address is the clock", "people
  sit at this table") is checked in the emulator, screenshots or RAM, and gets a proof in `tests/proofs.py`.
  Facts in `docs/systems.md` say whether they're proven and how.
- **Name what you find.** New addresses go in `code/game.sym` (and `code/include/game.h` if C needs them),
  with a comment saying what it is.
- **Run the tests** before sending a change to the builder, the code placer, the mod core or the harness:
  ```
  python tests/proofs.py                 # everything, about 1.5 hours; one emulator at a time
  python tests/proofs.py npc-poses pets-data   # just some (python tests/proofs.py --list)
  python tests/test_code_encodings.py
  python tests/test_mod_manager.py
  python mods/npc-life/sim/run_test.py
  ```
  A few proofs need your copies of other Sims games (`sources.json`; without them they're skipped) or melonDS
  (`verify/melonds_setup.sh` builds it on Linux; without it those proofs fail). The melonDS proofs tap the touch
  screen for real and now and then miss a tap (`pets-gate2` most often): rerun one alone before suspecting a bug.
- **Compiled code is committed.** After changing a mod's C, rebuild it (`python urbz.py patch build <mod>`) and
  commit its `code/build/` too, so people without LLVM can still build the ROM. The same for `code/core/`,
  `code/objects/` and `code/pets-kit/` (`python urbz.py patch build --dir code/core`).

## Sending it in

- **Bugs and ideas:** open an issue. For a bug, say which mods you built, what you did in the game and what
  happened (a screenshot and your `.sav` help a lot).
- **Code and docs:** fork, make a branch, open a pull request. Say what it changes and how you checked it
  (which proofs, what you saw in the game).
- **A new mod:** a pull request adding `mods/<your-mod>/` with a `README.md` saying what it does, or share it
  as a zip (the mod manager's **Add mod...** installs zips).

## Using Claude Code

The repo is set up for AI-assisted work too: `CLAUDE.md` holds the rules a Claude session follows, and
`.claude/skills/verify-urbz/` the emulator recipes. They're also a readable summary for humans.

## Writing style

Docs and messages are for players as much as programmers: plain words, short sentences, say what was proven
and what wasn't.
