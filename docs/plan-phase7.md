# Phase 7: NPC Life v3 (routines) and new animations

Decided with Jonathan (2026-10-02):
- People keep **their own look**: no player body (the `npc-body-proto` prototype stays a prototype).
- **No needs, money, jobs-pay or rent.** People follow daily routines: sleep, wash, eat, work, relax, chat,
  visit places in their free time. Not at the same time every day: each person has habits (early bird or
  night owl, morning or evening shower, early or late eater), every day shifts them by up to ~45 minutes,
  meals are sometimes skipped, and on arriving somewhere they first settle in for a while.
- New animations (sit, eat, toilet, shower, sleep ...) for the people who lack them come from **drawn art**
  (Jonathan or an artist); the kit provides the pipeline. Generating poses from existing frames was tried
  and looks broken (rendered 3D frames don't bend).

## Steps
1. **Routines** (`mods/npc-life/sim/`): replace the needs sim. Placement rule unchanged (everyone is where
   the original timetable puts them; out-of-town daytime hours become visits). Nothing saved: each week's
   plan comes from the game's week number. PC test + proofs.
2. **Animations per object activity:** which animation ids each object activity plays for a person
   (eat, shower, sleep, toilet, sit), from the 8 people who have object animations.
3. **Art pipeline** `urbz_anims.py`: `template <person>` (their frames on a fixed canvas + a guide sequence
   to draw over), `build` (PNGs -> new sheets, layouts, frame scripts, the person's animation rows through
   data hooks). Proven end to end on Gramma Hattie with placeholder art (DeSmuME + melonDS).
4. **Routines drive object use** for everyone with the animations; proofs; docs; full run.

## Status
- **Step 1 done.** `npc_sim.c` is now routines (no saved state, `save_bytes` gone). PC test: 4 weeks,
  nobody away from their timetable, weeks differ, the same week plans the same, all 32 people who eat vary
  their meal times day to day. Proofs: `npc-life-days` (3 days, 0 misplaced), `npc-life-stays`,
  `npc-life-visit` (Dusty Hogg visits Urbania Park in an out-of-town hour), `npc-life-reload` (replaces
  `npc-life-save`: no data saved, plans identical after reload), `npc-life-off`, `npc-life-page`, `npc-act`,
  `npc-act-release`.
- **Step 2 done.** Animations per activity (docs/systems.md): sit 0x6B/0x6C/0x6D (+0x72 stand up), eat 0x41,
  toilet 0x7B, shower 0x69 (+0xCC/0xCD towel), sleep 0x21 lie down / 0x20 get up. Art priority by how often
  you'd see it: sit (seats and benches in 10+ public areas), eat (vending, grills), toilet (5 areas), shower
  (5), sleep (6, mostly invisible beds). A full set is ~6 animations x 2 views x 10-20 frames per person.
- **Step 3 done.** `urbz_anims.py` (template / placeholder / build / list). Found and fixed: the game never
  loaded added assets (fixed-size asset tables); the builder now moves them when mods add assets (hidden
  generated mod `new-assets`; mods can be `"hidden": true`). Proof `npc-anims`: Gramma Hattie gets a
  placeholder sit animation built at test time and sits with it; the build runs in melonDS.
