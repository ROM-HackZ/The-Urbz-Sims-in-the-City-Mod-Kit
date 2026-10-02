# NPC Life (v2)

The city's 36 named people get needs (hunger, hygiene, energy, social, comfort, bladder, fun),
jobs, money and rent. Every game hour each person picks what to do next, Sims-style: a hungry
person goes to eat, a tired one goes home to sleep, people go to work on their usual shifts,
and otherwise they keep to their usual timetable. The game's own code then walks them in and
out of the area you're in. The simulation is saved with your game.

- Switch it on or off in the game: **Options > Mods > npc-life**. Off, everyone goes back to the
  game's fixed timetables; on again, they carry on from where they were.
- See what people are doing: **Options > Mods > npc-life: info** (who is in this area, then the
  hungriest people: activity, area id, money, food need).

## Tuning it

- `places.json`: what each area offers (food, fun, social, park, gym) and what a visit costs.
  Area ids and names: `docs/areas.md`.
- `npcs.json`: pay per hour, weekly rent, starting money and how fast each need drops, for
  everyone (`default`) or one person (by character id: 31 Bayou Boo ... 45 Kris ... 66 Sharona).

After editing either file:
```
python mods/npc-life/make_data.py          # -> sim/sim_data.h
python mods/npc-life/sim/run_test.py       # 4 city weeks on the PC: a report and PASS/FAIL
python urbz_patch.py build npc-life        # compile (needs LLVM)
```
then build the ROM as usual.

## How it works

- `sim/npc_sim.c` is the simulation: plain C with no game addresses, so it also runs on the PC
  (`sim/test_sim.c`) and could move to a PC version of the game later.
- Nobody goes missing (Phase 6): every hour, each person is in the area their original
  timetable gives them, and the sim only picks what they do there (work, eat a snack, rest).
  Only in hours the original game has someone out of town (area 82) are they free: then they
  may visit a place they know (a café when hungry, a club, a park, home). Sleep is invisible:
  at night they rest wherever the game has them. Home = where they are at night, job = where
  they are on weekday working hours (both read from the timetable when the game starts).
- The sim follows the game clock minute by minute, so no hour's decision is ever skipped.
- `code/main.c` connects it to the game: the game reads everyone's timetable through 5 words
  (`schedule_table_ptr_1..5`); `code/hooks.txt` points them at the simulation's live timetables
  (`u32 ... @live_table`). Quest rules in the game are checked before the timetable, so the
  story still wins.
- Save data: 584 bytes per save slot.

## Visible actions (v2, Phase 6)

In the area you're in, people act out what they're doing, with the game's own objects and
animations (`code/act.inc`):
- the 8 people who have the game's object animations (Cannonball Coleman, Dusty Hogg, Ewan
  Watahmee, Kris Thistle, Misty Waters, Olde Salty, Phoebe Twiddle, Sue Pirnova) walk to a chair and sit down when they're eating (no food object
  there), resting or just taking a break; they use the toilet when they need it;
- the others chat: one walks up to another, they face each other and take turns gesturing;
- at most 4 actions at once; a person rests 20-50 s between actions; nobody is taken from a
  story scene, from talking to you, or from leaving for their next place;
- switched off on the Mods page, everyone stops and goes back to the game's own wandering.
- The info page shows "sitting here" / "chatting here" for people acting it out.

## Not yet

People don't say different things when they're hungry or broke, and the 28 people without
object animations can't sit (they would stand on the chair). See PLAN.md.
