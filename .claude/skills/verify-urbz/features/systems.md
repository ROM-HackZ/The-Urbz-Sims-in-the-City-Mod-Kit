# Game systems (reverse-engineering facts the mods rely on)

Every address in `code/game.sym` has evidence in `docs/systems.md`. This recipe re-proves the
ones code mods depend on, so a wrong symbol is caught before a mod is built on it.

## Sub-features

- `sys-clock`: game_time 0x0214112C advances 3 s per tick; time_speed_table entry 0 drives it.
- `sys-needs`: player needs s32[8] at 0x02141204 (8.24); decay table 0x020CEDA8; frozen by sim flag bit 2.
- `sys-money`: money s32 at 0x02141124 shows on the HUD.
- `sys-save`: `urbz_save.py` edits load in game (Load-an-Urb).
- `sys-npc`: spawn_npc / npc_present / schedules; a person appears where code puts them.
- `sys-effects`: motive effect rows (0x020CEED4) drive action gains.
- `sys-catalog`: object_info_table price shows in the Catalog.

## Driving it (all from `--city` or a saved state; vanilla ROM unless noted)

- **sys-clock:** `find <rom> --city --script <shots every 300 frames> --size 1 --test t0=eq:<minute>`
  finds 0x0214112F; `watch --hook write:0x02141130:1` shows writes from 0x0201DA4C.
- **sys-needs:** `ram --poke 0x02141c30=00 --frames 1201 --read 0x02141204:0x20`: hunger drops
  2.778 per 600 ticks. With mod `u32 motive_decay_table+0 -38836` it drops half that.
- **sys-money:** `play --poke 0x02141124=39300000` with a shot: the HUD shows §12,345.
- **sys-save:** `play ... --export-sav x.sav` after Options > Save Game (check at 220,117);
  `urbz_save.py set x.sav y.sav --money 4321 --motive hunger=10`; `play <rom> --sav y.sav --script
  verify/scripts/loadgame.json`: the slot screen shows §4,321 and the HUD hunger bar is short.
- **sys-npc:** build `--mod tests/mods/npc-visit`; from `--city` run 1200 frames: the mod's struct says
  spawned=1 and the entity at the stored pointer has type 7, character 31; a new person walks on
  the start street (screenshot) where the original has none.
- **sys-effects:** `--poke 0x02141c30=00 --poke 0x02141218=00000000` (bladder 0) starts the
  accident action (row 64 via 0x0200B024); bladder refills to ~99.6 in 240 frames. With
  `u32 motive_effect_table+0x814 0x01000000` it stops at ~49.6.
- **sys-catalog:** with `u32 object_info_table+4000 99`, Urb Info (80,180) > Catalog (60,118) >
  Utilities (205,118) shows "The Savvy Shower - $99" (original $230).

## Evidence (2026-10-01)

All of the above passed; see docs/systems.md for the addresses and decompiled logic.
