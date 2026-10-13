# Pets test-play (2026-10-09)

Long DeSmuME sessions with the pets mod, read back from RAM at every screenshot (`ptlib.py`: `detail()` = each
pet's mode, action, timer, position, needs, from code/pets-kit's symbols).

- `mkday.py`: from the apartment save at 08:00, put down the 4 beds and all 8 pets (trying other walks when a spot
  is taken), save the state as build/playtest/day_allpets.dst. Run it first (and again after rebuilding).
- `s4.py`: that state from 21:30 to 14:00 the next day, every ~25 game minutes.
- `s6.py`: the Pets page (R scrolls), save + load with 8 pets. `s8.py`: out and home again (greeting).
- `s10.py`: a pet put in the next room comes back. `steal.py`: the strays quest, then the adopted stray.
- `survey2.py <anim hex> ...`: the player's animation while playing (pets_play_anim poked), 6 frames each.

Findings and fixes: docs/dev/plan-phase10.md "Test-play fixes".
