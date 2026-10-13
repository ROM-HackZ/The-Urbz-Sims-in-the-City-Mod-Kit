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

What each place offers the townspeople in their free time (food, fun, social, park, gym): in the mod
manager, select npc-life and press **Tune...**, click the boxes, build. No files to edit, no compiler: your
choices are kept in `tuning\npc-life.json` and the builder writes them into NPC Life's compiled places table
(`kit/urbz_tuning.py`).

The mod's own defaults are in `places.json` (area ids and names: `docs/areas.md`). Changing those, for the
mod itself:
```
python mods/npc-life/make_data.py          # -> sim/sim_data.h
python mods/npc-life/sim/run_test.py       # 4 city weeks on the PC: a report and PASS/FAIL
python urbz.py patch build npc-life        # compile (needs LLVM)
```

## How it works

- `sim/npc_sim.c` is the routine engine: plain C with no game addresses, so it also runs on the
  PC (`sim/test_sim.c`) and could move to a PC version of the game later.
- Home = where they are at night, job = where they are on weekday working hours (both read from
  the original timetable when the game starts).
- `code/main.c` connects it to the game: the game reads everyone's timetable through 5 words
  (`schedule_table_ptr_1..5`); `code/hooks.txt` points them at the live timetables
  (`u32 ... @live_table`). Quest rules in the game are checked before the timetable, so the
  story still wins.

## Visible actions

In the area you're in, people act out their routine with the game's own objects and animations
(`code/act.inc`):
- someone eating walks to a vending machine, grill or fridge and eats; with no food object there,
  they sit down at a table; relaxing at home, they sit on a bench or sofa; now and then, the
  toilet; at night a bed, at washing time a shower (written, but not seen in a test yet);
- extra seats (`seats.json`): sofas and booth benches only drawn into a place become real seats (built into the
  place at build time with `urbz_seats.py`);
- a person only does what they have the animation for. In the original game only Kris can eat and 8
  people can sit, shower, sleep and use the toilet; `poses.json` gives everyone else borrowed ones
  (built by `urbz_poses.py` from the closest-looking person who has them, in their own colours and with
  their own head), and the 8 who had no gestures get borrowed ones to chat with. Lincoln Broadsheet is in a
  wheelchair: he eats a snack sitting in his own chair and sleeps in a bed, but never takes a seat, the toilet
  or a shower. Anyone you draw new art for with `urbz_anims.py` uses yours;
- everyone, in their free time, also goes to things they can enjoy standing up: the grill, a pay phone,
  the graffiti wall, museum exhibits, the crystal ball, a TV, a drinking fountain, the jukebox and dance
  pad, the DJ desk. They face it and gesture now and then for 10-20 s (busier by the jukebox);
- or they chat: one walks up to another (anyone standing about up to ~500 px away), they face each other and
  take turns gesturing (people who are socialising chat first, before sitting down);
- in a park or out for fun, they also stroll: a walk to another spot of the place and a look round;
- seats are picked at random among the free ones (everyone used to take the one nearest the door), one person
  per seat (where two objects seat people on the same spot, the second one gets up again), and after a sit
  people walk back the way they came (they used to stand trapped between chair and table) and carry on as
  soon as they're there;
- a toilet visit takes about 10 game minutes, a shower about 15;
- at most 4 actions at once; when their routine moves on (breakfast time), they stop and go, unless what
  they're using still fits (socialising -> eating at the same table: they stay seated); a sit lasts 10-25 s,
  then they get up and wander a while before sitting again;
- someone left sitting with nobody watching them (e.g. after you talked to them) is told to stand up after
  10 s;
  nobody is taken from a story scene, from talking to you, or from leaving for their next place;
- switched off on the Mods page, everyone stops and goes back to the game's own wandering.
- The info page shows "eating here" / "chatting here" for people acting it out.

## Not yet

The borrowed poses (`poses.json`) are made by machine from someone else's animation: up close they look a
little off-model (the donor's build, the person's colours and head). Drawing them by hand (`urbz_anims.py`)
replaces them person by person. Many chairs drawn in public places aren't seats in the game's data at all.
`seats.json` turns some into real ones (Café Z-Bach: two booth benches and the sofa by the rug, besides the game's
own two armchairs); others can't be reached by the game's walking (the café's middle booth and front sofa, the
cinema's rows), and the booths are often out of reach too, so people mostly use the sofa.
