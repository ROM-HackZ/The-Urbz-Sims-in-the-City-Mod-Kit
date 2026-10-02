# Plan: Phase 6 — greatly improved NPC AI (design)

*Approved 2026-10-02.*


## Context
Jonathan wants NPC behaviour greatly improved: a living city that still feels like the original game, where
nobody goes missing from the places the game puts them. He asked for my best recommendation:

1. **Keep everyone's real sprites** (their look is the original game). The player-body swap (every person
   drawn with the player's ~196 animations in their colours) would erase unique shapes/outfits and fit only a
   few people on screen (2 of 16 colour rows each), so it is a **prototype on one person**, not the plan.
2. **Life through behaviour**: in the area you're in, people act out what the simulation says they're doing,
   with the game's own animations: walk to the food spot when hungry, to their work spot when working, to a
   fun object, or to another person to chat (gestures 0x87/0x78/0xDB, which about half have), then stay there.
3. **Placement follows the original timetables** (nobody goes missing): the sim only fills hours when the game
   has someone out of town with visits to cafés/clubs/parks; sleep is invisible.

Already known (ROM, 2026-10-02): per-person animation lists 0x0211CDF4 (all: 0x04 stand, 0x0A walk (corrected in step 2); ~half
gestures; story people more); behaviour 0x020643C8, states at entity+0x104 via 0x0200BE50, townspeople in
state 0x23 (handler 0x0200A1F0; corrected in step 2); player body drawn by FUN_0208327c(entity, look), palettes by 0x02083538.

## Steps
1. **Placement rule** (`mods/npc-life/sim/npc_sim.c`): each hour's area = original timetable; out-of-town hours
   (82) may become visits to allowed places with matching offers. Needs, money, jobs, rent unchanged. PC test:
   never away from an original non-82 slot; 4-week report still passes. Proofs npc-life-* updated (walk-in now
   happens only in an out-of-town hour).
2. **Reverse-engineer movement** (emulator + code): how state 0x23 idles/wanders; how walk-in/out sends a person
   to a point (reuse it for any x, y); facing; when the game plays gestures; objects in the current area (active
   entity list → object number, position, use spot) using docs/objects.md. Check: a probe walks Kris to a chosen
   spot and gestures (screenshot in melonDS + RAM in DeSmuME). Documented in docs/systems.md, names in game.sym.
3. **Behaviour layer** (`mods/npc-life/code/act.c` + `acts.json`, compiled by make_data.py): for people in your
   area, at most 4 acting at once:
   - eating → nearest food object (fridge, stove, counter, vending, snack stand) or the place's counter;
   - working → their spot at work (their placement record in that area), stay busy (face, gesture);
   - fun/park → TV, arcade, decor, bench;
   - socialising → walk up to another present person, face each other, take turns gesturing;
   - at home/resting → stand quietly.
   Hands off: the person you talk to, the date partner, quest people, anyone in a state other than 0x23/ours.
   Switching npc-life off releases everyone. The info page shows "eating at ...".
4. **Player-body prototype (one person)**: draw Kris with the player body in her colours while she eats, behind a
   setting that's off by default; screenshot it in melonDS for Jonathan to judge. Roll-out only if he wants it.
5. **Proofs**, melonDS as the gate (Jonathan's emulator), DeSmuME for RAM: npc-act-eat, npc-act-social,
   npc-act-release, npc-placement, npc-body-prototype; fix the melonDS screenshot alignment; full
   tests/proofs.py passes.
6. Docs (systems.md, npc-life README, PLAN Phase 6, HANDOFF), commit, push; Jonathan tests on the Thor.

## Risks
- Walking to arbitrary points may hit walls: use object use spots and the game's way points.
- Areas without matching objects: people keep the original wandering (no fake actions).
- Story scripts moving people: we release anyone not in state 0x23/ours.

## Status
- **Step 1 done (2026-10-02).** Proven: PC test (4 weeks, nobody away from an original non-82 slot; 1303 of
  2220 out-of-town hours became visits); emulator proofs `npc-life-stays` (exhausted Kris still goes to the roof
  at 18:00, her usual place), `npc-life-visit` (Phoebe, starving at midnight in an out-of-town hour, is sent to
  eat at 51 and the game walks her in there), `npc-life-days` (3 game days: 0 people away from where the game
  puts them). Bug found and fixed on the way: the connector jumped the sim clock to the game clock, and a
  one-minute gap at midnight skipped that hour's decisions; it now always advances minute by minute.
- **Step 2 done (2026-10-02).** The game already has "walk to an object and use it" for townspeople
  (`npc_goto_object`), with their own animations (sit 0x6B, stand up 0x72, toilet 0x7B), but only offers it
  to 6 people and needs a needs block they don't have. Proof `npc-use-object` (Phoebe sits on a café chair
  and stands up when we end it). Details: docs/systems.md "People: movement and object use".
  Changes to the plan for step 3: use objects through `npc_goto_object` (not our own walking); give each
  acting person a 64-byte needs block first; end uses with the stop byte (3). Eating: where a place has
  no food object (the Coffee Shop has none), "eat" = sit at a table.
