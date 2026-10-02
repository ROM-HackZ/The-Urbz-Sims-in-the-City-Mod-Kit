# NPC Life (v3)

The city's 36 named people follow daily routines. Every hour each person is where the original
game puts them, so nobody goes missing; in the hours the original game sends someone out of
town, they may instead visit a place they know: lunch or dinner at a food place, a park or
friends by day, a club in the evening.

What they do follows the clock and the place: they sleep at home at night, wash in the morning
or before bed, eat breakfast, lunch and dinner, work during work hours, relax at home, chat now
and then. Not like clockwork: everyone has their own habits (early bird or night owl, morning or
evening shower, early or late eater), each day shifts them by up to about 45 minutes, meals are
sometimes skipped, and on arriving somewhere people settle in before eating.

- Switch it on or off in the game: **Options > Mods > npc-life**. Off, everyone goes back to the
  game's fixed timetables and wandering.
- See what people are doing: **Options > Mods > npc-life: info** (who is in this area and what
  they're doing, then who comes next).
- Nothing is saved: each week is planned from the game's week number, so the same week always
  comes out the same, and every week is a little different.

## Tuning it

- `places.json`: what each area offers (food, fun, social, park, gym) for free-time visits.
  Area ids and names: `docs/areas.md`.

After editing it:
```
python mods/npc-life/make_data.py          # -> sim/sim_data.h
python mods/npc-life/sim/run_test.py       # 4 city weeks on the PC: a report and PASS/FAIL
python urbz_patch.py build npc-life        # compile (needs LLVM)
```
then build the ROM as usual.

## How it works

- `sim/npc_sim.c` is the routine engine: plain C with no game addresses, so it also runs on the
  PC (`sim/test_sim.c`) and could move to a PC version of the game later.
- Home = where they are at night, job = where they are on weekday working hours (both read from
  the original timetable when the game starts).
- `code/main.c` connects it to the game: the game reads everyone's timetable through 5 words
  (`schedule_table_ptr_1..5`); `code/hooks.txt` points them at the live timetables
  (`u32 ... @live_table`). Quest rules in the game are checked before the timetable, so the
  story still wins.

## Visible actions (v2, Phase 6)

In the area you're in, people act out what they're doing, with the game's own objects and
animations (`code/act.inc`):
- the 8 people who have the game's object animations (Cannonball Coleman, Dusty Hogg, Ewan
  Watahmee, Kris Thistle, Misty Waters, Olde Salty, Phoebe Twiddle, Sue Pirnova) walk to a chair
  and sit down when they're eating (where there's no food object), relaxing or taking a break;
  they use the toilet now and then;
- the others chat: one walks up to another, they face each other and take turns gesturing;
- at most 4 actions at once; a person rests 20-50 s between actions; nobody is taken from a
  story scene, from talking to you, or from leaving for their next place;
- switched off on the Mods page, everyone stops and goes back to the game's own wandering.
- The info page shows "sitting here" / "chatting here" for people acting it out.

## Not yet

The 28 people without object animations can't sit, eat, wash or sleep visibly yet: that needs
new art, drawn per person (Phase 7, `docs/plan-phase7.md`).
