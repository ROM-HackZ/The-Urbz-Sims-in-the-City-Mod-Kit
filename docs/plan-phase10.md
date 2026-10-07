# Phase 10 — Pets, the rest (plan, approved 2026-10-06)

## Context
Phase 9 made pets real: you buy them, keep them, look after them, and they're saved. Four things were left:
- pets don't use beds;
- pets aren't moved when you move house (untested);
- there's no Pets info page on the Mods page;
- sounds (Jonathan: not needed).

Jonathan also spotted a gap. Pets are only sold at the Bayou Bazaar in the Sim Quarter, but early on the game
keeps you in Urbania. String 5428 says "You'll be free to wander around Urbania only", and the Sim Quarter
opens later (430: "You've cleared the way to the Sim Quarter!"). So a new player can't get a pet for a long
time.

Decided with him (2026-10-06):
- **Beds:** pets roam as now. At night, or when resting, they walk to their own bed or cage and sleep or lie in
  it. Without one they sleep on the floor, as now.
- **A starter-pet quest in Urbania Park**, available once you're out of jail:
  - a stray puppy and a stray kitten hang around the park;
  - they're shy at first. You win a stray's trust by feeding it Pet Treats on two different days;
  - then "Take Home" appears for that stray;
  - you adopt one. A townsperson walks up and adopts the other, shown as part of the quest.

Outcome: a new player gets a pet early through a small story. All pets have beds, follow you when you move,
and have a page that shows how they're doing.

## What we know (checked this session)
- **Urbania shops** (`docs/data/areas.json`): Urbania Park 19 has clerks for lists 18, 20, 14 and 12. The
  **Second Looks Thrift Emporium (73, off Urbania Park) sells list 10, general furniture.** Treats and beds go
  there, as well as the Bayou Bazaar (list 9). Pets stay at the Bazaar; the strays are the early route.
- **Goals:** `goal_table` 0x02141940 is a fixed 7 missions × 6 goals. There's no room for a new game goal, so
  the quest is ours: pets-kit state saved in the mod save data, steps told in the game's message box
  (`dialog_open`, text[0] only, as the game does), and progress shown on the Pets page. Out of jail = m0g4
  complete (0x02141940 + 4*0xC + 1).
- **Clock:** `game_time.day` (days since start) tells "a different day".
- **Townspeople:**
  - they walk with `path_request(e, xy, &result, 0)` 0x0207DC08 (only 3 slots; check `path_count` < 3);
  - they stand still or face someone the way NPC Life's `act.inc` does;
  - names are string 512 + id − 31;
  - they live in the world entity list (`entity_lists` 0x02121AF0).
- **Objects in the room:** `object_list_head` *0x0214490C, nodes {next, ?, u16 object @+8, entity @+0x24}.
  Pets can find their beds here.
- **Homes:** `home_lot` 0x02141230 changes on `move_home` 0x02046C7C. `home_lots` 0x020C812C gives each lot's
  area. Lot 0 = Skyline Penthouse (the start), lot 1 = Small Brownstone 22, lot 2 = Large Brownstone 23.
- **Mods page info page:** `mod_on_page(mod_page_t *)` gives 5 lines of about 28 characters, scrolled with
  UP/DOWN (core). pets-kit is a hidden mod now, so it needs a visible, non-switchable entry "Pets".
- **New text:** mods can add strings (ids 8311+; `urbz_text.py`). Objects number theirs automatically.
- **Apartment Pets models** (gallery):
  - `dog_basket`, `cat_bed`, `rabbit_hutch`, `guineapig_home`, `parrotcage`;
  - `hamster_cage` renders broken (the hamster uses the guinea pig house);
  - there's nothing for the snake (it keeps sleeping on the floor).

## Steps (each ends in a proof; melonDS for anything with taps)

### 1. Beds and cages
- **New objects in `mods/pets/objects.json`**, imported from Apartment Pets: Dog Basket, Cat Bed, Rabbit Hutch,
  Small Pet House (guinea pig and hamster), Bird Cage (cockatoo and macaw). Numbers 397+.
  - `like` = a small decorative object that sims don't use. Pick one with a 1-tile footprint after reading
    `docs/objects.md`.
  - Prices $40-120. Sold at the Thrift Emporium (list 10) and the Bayou Bazaar (list 9). Catalog page 4.
- **Bed field in `pets.json`:** a `"bed"` field per pet (object number). `urbz_pets.py` writes it into the PETA
  list (`{u16 object, u16 kind, u32 actions}` → add `u16 bed`), and pets-kit reads it.
- **Behaviour (`pets_behaviour` `choose()`):**
  - at night, or when it picks lie/sleep, a pet looks for a placed bed of its type that no other pet has
    claimed (object list scan);
  - it walks there (new mode M_BED: `entity_go`/face, as M_GO does), then stands on the bed's spot and plays
    sleep or lie;
  - in the morning it gets up and wanders.
  - If it's stuck for more than about 5 s, it gives up and sleeps where it is.
- **Drawing:** check the pet draws on top of or inside the bed, and nudge y by a pixel or two if needed.
- **Proof `pets-beds`:** place a Puppy and a Dog Basket, set the clock to 23:00, and check the Puppy is at the
  basket and sleeping. Same for the Kitten / Cat Bed. A melonDS screenshot. A second dog with only one basket
  sleeps on the floor.

### 2. Pets move with you
- pets-kit watches `home_lot` on each tick (and after a load).
- **When it changes,** every pet in "my pets" gets the new home's area (`home_lots`[lot].area) and a "place
  near the door" flag. On the first tick in the new home they're spawned near the player, and the greet runs.
- Their beds go into the moving crate like your other things (the game does that). The pets find them again once
  they're placed.
- **Proof `pets-move`:**
  - start from `apartment-pets` with two pets placed;
  - rent the Large Brownstone at its Urbania Park sign (the `rent_first_apartment.json` approach, lot 2);
  - go home: both pets are in area 23, and none are left in 22;
  - save, load: still there.

### 3. The Pets page (Mods page)
- pets-kit shows up on the Mods page as **Pets** (no on/off switch) with an info page:
  - one line per pet, e.g. `Puppy  asleep   80  95` under a header `Pet  doing  food fun`;
  - quest lines while the strays quest runs, e.g. `Strays: Kitten trusts 1/2`;
  - scrolls when there are more than 5 lines.
- Check the core supports a visible, non-switchable mod with a page (the Phase 5 platform). If not, the
  smallest core change to allow it.
- **Proof `pets-page`** (melonDS taps Options > Mods > Pets): screenshot plus the printed lines read from RAM,
  like `npc-life-page`.

### 4. The strays quest (Urbania Park)
- **Who and where:**
  - the stray Puppy (386) and Kitten (389) are spawned by pets-kit whenever you're in Urbania Park, once m0g4
    is complete and until the quest ends;
  - they stay within a leash around a spot near a bench (`M_STRAY`: wander, walk back if more than about
    150 px away).
- **Quest state** (saved, about 16 bytes):
  - per stray: trust 0-2, the day it was last fed, adopted-by (0 = nobody / player / person id);
  - the quest stage.
- **Steps:**
  1. **First visit after jail:** a box: "A stray puppy and kitten are hanging around the park. They look hungry."
  2. **Shy:** while trust is 0, a stray backs away when you're closer than about 60 px, unless you stand still
     for 2 s. Press A at it: a box with **Feed / Leave**.
     - Feed takes one Pet Treats from Pockets (bought at the Thrift Emporium next door). Without treats: "It
       sniffs your hands. You need Pet Treats" (Thrift Emporium).
     - Feeding sets trust +1, at most once per game day: "The kitten gobbles it up. Come back tomorrow."
  3. **Trust 1:** it stops running from you. The menu is **Pet / Feed / Leave**.
  4. **Trust 2** (fed on a second day): "The kitten trusts you now!" The menu adds **Take Home**.
  5. **Take Home:** the stray goes into Pockets as the normal pet object, with the Chicken pick-up sound, and a
     box: "You adopted the Kitten! Place it at home."
- **The other stray gets adopted in front of you:**
  - pets-kit picks a townsperson present in Urbania Park (random). They walk to the other stray
    (`path_request`), both face each other, and the stray plays happy;
  - a box says "Olde Salty adopted the Puppy!";
  - the stray then follows that person (it keeps walking toward them) until they leave the area. Then it's gone
    for good.
  - If nobody is in the park, a random Urbania regular is named instead, and the stray trots off to an exit and
    vanishes.
  - Saved: who adopted it (shown on the Pets page: "Olde Salty's Puppy").
- **Text:** about 12 new strings in `mods/pets/text` (or `pets.json` "text"). `urbz_pets.py` numbers them and
  writes the numbers into pets-kit's data block, so the C code never hard-codes new string ids.
- **Saves:**
  - `verify/saves/urbania.sav`: out of jail, standing in Urbania Park with no home yet (made like
    `apartment.sav`: `lobby.sav` with goals m0g1-g4 poked complete, `--goto 19:0`, then saved through the menu);
  - `verify/saves/strays.sav`: the same with some Pet Treats.
- **Proofs:**
  - `strays-appear`: both strays are in Urbania Park only once out of jail (not in `lobby.sav`), with the intro
    box once;
  - `strays-trust`: feed twice on day N (trust 1), again on day N+1 (trust 2), Take Home → Pockets has 386;
    the adopter walked within 30 px of the Kitten, the box was shown, the Kitten is gone after the adopter
    leaves (or after re-entering);
  - save/load mid-quest keeps trust;
  - `pets-thrift`: buy Pet Treats and a Dog Basket at the Thrift Emporium (`_shop_script` approach,
    list 10).

### 5. Gate (melonDS, real taps; DeSmuME only for trips across the map, as in pets-gate)
1. Start from `strays.sav`, buy treats at the Thrift Emporium, feed the Puppy and save.
2. Next day (sleep or a clock poke in DeSmuME), feed again, then Take Home. Watch the Kitten get adopted.
3. Rent the Small Brownstone (sign), place the Puppy, then buy and place a Dog Basket.
4. At night the Puppy sleeps in it.
5. Save, power off, load: everything is kept.
6. The Pets page shows the Puppy.

Then: full `tests/proofs.py`, docs (systems.md "Pets", README "Looking after pets" + the stray quest, areas.md
saves, `docs/plan-phase10.md`, PLAN, HANDOFF), commit, sync to the PC, Jonathan plays.

## Files
- `code/pets-kit/pets.c`: beds, moving, page, strays quest. Maybe split into `strays.inc`; `hooks.txt` and
  `mod.json` (visible, save_bytes).
- `urbz_pets.py`: the bed field, text numbering, the data block.
- `mods/pets/pets.json`, `objects.json` and text.
- `code/game.sym`: path, object-list and home symbols if missing.
- `tests/proofs.py`: pets-beds, pets-move, pets-page, strays-appear, strays-trust, pets-thrift, pets-gate2.
- `verify/saves/`: urbania.sav, strays.sav.

## Risks
- **Draw order of pet vs bed:** fallback is to place the pet just in front of the bed's spot.
- **Pets walking into furniture on the way to bed:** the stuck timer falls back to sleeping where they are.
- **The adopter walk:** the path slots may be busy (NPC Life uses them). Fallback: the other stray walks to the
  person instead, which needs no path slot.
- **Townspeople in Urbania Park depend on the hour:** handled by the fallback "a regular adopted it" line.
- **Save space:** quest about 16 bytes plus beds 0; well within the budget.
- **Text box length:** keep messages under about 3 lines (check the box in melonDS).

## Status (2026-10-06): done

All steps proven; the gate `pets-gate2` passes in melonDS (5 sessions with real taps: buy at the stall, feed day 1,
feed day 2, Take Home, at home basket + Puppy at night + the Pets page; loaded after: kept).

| Step | What | Proof |
|---|---|---|
| 1 | Beds and cages (397-401, like the Dawg House 58); pets sleep on their own bed at night | `pets-beds` |
| 2 | Pets move with you to a new home | `pets-move` |
| 3 | Options > Mods > Pets: one line per pet (doing, food/fun), then the strays | `pets-page` |
| 4 | The strays quest: intro, shy, trust over two days, Take Home, a townsperson adopts the other | `strays-appear`, `strays-trust` |
| 4 | Pet Treats, Dog Basket, Cat Bed at Drifter Woods' stall in Urbania Park (list 18) | `pets-stall` |
| 5 | melonDS gate | `pets-gate2` |

Changes from the plan:
- The early shop is **Drifter Woods' stall** (gifts, list 18, by the Brownstones), not the Second Looks Thrift
  Emporium: that one is an auction. Cheaper early beds: Dog Basket $35, Cat Bed $30.
- The strays come up to you when you stand still (instead of only "unless you stand still for 2 s"), so A works
  without lining up; while untrusted they back away when you move.
- Messages are one-answer question boxes ("OK"): the game's plain message box didn't come up from mod code.
- Pets lie on the **front half** of their bed: further in, they're drawn behind it (the draw order of objects
  and critters isn't understood yet).
- Found on the way: placed-object art drew wrong tiles when a small sprite cell came before a bigger one (fixed
  for all imported furniture); builds were slow (9 min) from re-compressing every pet frame (now cached: 25 s).
- No `strays.sav`: `urbania.sav` already starts with the strays in the park.
- A townsperson standing next to you gets your A press first (the game talks to them); step aside.
