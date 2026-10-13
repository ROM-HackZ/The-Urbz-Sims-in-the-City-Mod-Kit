# Bug Fixes

Bugs in the original *The Urbz: Sims in the City* (DS), fixed. On by default; switch it off in the game
(**Options > Mods > Bug Fixes**) to see the original behaviour. It works with or without the other mods.

| Fix | What went wrong in the original game | Proof |
|---|---|---|
| People who can't get out | Someone the game sends out of a place walks to the door or lift. If you're standing there (the walk fails while they're on screen), they go back to wandering and try again every few seconds, for ever: Sue Pirnova paced by the lift in Waters' Gym from 6:00 to past 8:30. Now, after 20 s of trying they go through when they're near it, after a minute wherever they are. | `fix-stuck-leaving` |

## Adding a fix

1. Show the bug in the original game: a script or probe in `research/` and a short note in `docs/systems.md`
   (what happens, which function, how you found it).
2. Fix it in `code/main.c`, in its own section with a comment saying what it fixes and which proof shows it.
   Change as little of the game as possible, and only while the mod is switched on.
3. Add a proof to `tests/proofs.py` that fails on the original ROM and passes with this mod, and a row above.
4. `python urbz.py patch build bug-fixes`, then commit `code/build/` too.
