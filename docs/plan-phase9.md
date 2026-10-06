# Phase 9 — Pets, completed (plan, approved 2026-10-06)

## Context
Phase 8 gave us eight pets imported from Apartment Pets: Puppy, Kitten, Bunny, Hamster, Guinea Pig, Cockatoo,
Macaw and Snake. They are bought, put in Pockets and placed at home, where they walk around. They are still
"chickens with new art":
- they probably vanish on save/load and when you leave home;
- they use the chicken's Pockets icon;
- they can't be picked up with real buttons (we haven't even found how the Chicken is picked up);
- buying them in a shop has never been seen;
- they only stand and walk.

Jonathan: "plan and design the next phase with all of the above (for pets). let's get pets completed in this
next phase."

Decided with him (2026-10-06):
- **Walking up and pressing A opens a menu:** Pet / Play / Pick up, plus Feed.
- **Light needs:** hunger and happiness, saved with the game. Neglect only makes a pet mope; it never runs away.
- **Caged animals keep roaming with a hop**, as now.

Outcome: pets you buy in a shop, keep, look after and play with, which survive saves. This is proven in
melonDS with real taps.

## What we know (from the code; see docs/systems.md "Pets")
- **Pets are critters** (entity type 9):
  - `critter_table` row per kind: {setup fn, +4 / +8 collision callbacks, speed, flags}.
  - The setup copies +4 / +8 into entity +0x84 / +0x88. These are the callbacks for its hitboxes 0 / 1.
  - The ITCM collision pass (0x01FF8000) calls them when two entities' boxes overlap.
- **The chicken's pick-up** is the +8 callback `critter_tap` 0x0202A4F8. It fires when the player's box touches
  the critter's second box while the player is in state 0x10 and a per-sim flag is set. Our pets copy the
  hitboxes from the source layout's `extra` (`urbz_art.build_pet_art`).
- **Animations:** `critter_play_anim` 0x02029804 picks the records for the facing and starts the frame script.
  The game gives only 5 slots per kind and switches walk/stand only for kind 1 (patched).
- **Mod platform events:**
  - `mod_on_save` / `mod_on_load` give per-slot save data, about 1.4 KB free per slot.
  - `mod_on_area_enter`, `mod_on_tick` and `mod_on_minute`.
  - `mod_on_page` gives a Mods-page info page.
  - The menus are data (Phase 5).
- **Existing helpers to reuse:**
  - Rent-sign style dialogs: question + options, string ids, state 2, 0x020463A8.
  - The Splicer pets' petting: person anims 0x4E/0x4F/0x50, state 0x39 `FUN_0200DAD0`.
  - `spawn_critter` 0x0202AB18.
  - `is_home_area` / `home_lot` 0x02141230.
  - The Pockets list (list 23).
  - `shop_ui` 0x02148F30 (+4 = list) and `shop_buy`.

## Steps (each ends in a proof in the emulator; melonDS for anything with taps)

### 1. Pets stay (persistence)
- **Check first, writing a proof:**
  - do placed pets survive leaving home and coming back?
  - do they survive save → power-off → load?
  - same for the vanilla Chicken.
- **pets-kit keeps a "my pets" list** of up to 12 pets: {object, x, y, facing, hunger, happiness, flags}.
  - Pets are added when placed (`pets_removed`) and removed when picked up (the pick stub).
  - Positions are refreshed every few seconds from live critters.
  - `mod_on_area_enter(home)` respawns any that aren't there.
  - `mod_on_save` / `mod_on_load` store the list, about 12 × 10 bytes.
  - pets-kit becomes an events mod: hidden, not switchable.
- Moving home (`move_home`) moves the pets too.
- **Proof `pets-persist`:** place two pets, leave and come back, save, power off, load. Both are back at home
  (DeSmuME), and the same in melonDS.

### 2. Their own icons
- `pet_art` also renders a 24×32 icon (front view, like object icons).
- `urbz_pets` passes it to `urbz_objects` as `"icon"`. This adds to `urbz_objects.objects_mod`: a new model
  number (633+) copying the like-object's model rows, plus an icon record in the moved `ui_sprite_table`.
  Reuse the "import" icon path (`urbz_art.build_object_art` / `icon_record`).
- **Proof:** Pockets and Catalog show eight different icons (screenshot compared against the renders).

### 3. Walking up to a pet: the menu
- **Research** (watch/RAM, short):
  - What makes the player touch a critter's second box in state 0x10, i.e. how the vanilla Chicken is picked
    up. Leads: hitbox `extra` in the layout, player state 0x10, per-sim flag &1.
  - How the rent sign opens its dialog: 0x02046A38 sets +0x4C to the dialog handler, `FUN_0205d460`, string
    ids at 0x02146EB8+.
- **pets-kit sets the pet kinds' +8 callback** to its own `pets_tap`. Touching a pet while standing still (or
  pressing A at it) stops the pet, turns both to face each other and opens a dialog: "Puppy: Pet / Play / Feed /
  Pick up / Cancel", as new strings.
  - Use the game's dialog if it takes 4+ options; else a bottom-screen menu built like the Mods page
    (`menu_table` moved in Phase 5).
- **The actions:**
  - **Pet:** player anim 0x4E–0x50 (the Splicer petting), pet plays its "petted" animation, happiness +.
  - **Play:** pet's play/trick animation (dog `trick1`, `chasetailloop`; cat `pawscreen`…), player cheers
    (an existing person anim), happiness ++, hunger −.
  - **Feed:** uses one "Pet Treats" from Pockets (a new Pockets item, object 396). Pet plays `eat`, hunger +.
    Without treats it says "No pet treats in Pockets".
  - **Pick up:** the existing critter → Pockets path, plus it leaves "my pets".
- **Proof `pets-menu`** (melonDS taps): walk to the Puppy, A, pick each option. Check the state changes
  (happiness, hunger, Pockets) and the person/pet animation ids.

### 4. Buying them in a shop
- **Research:** which shop screen uses list 9 (the Chicken's), via `shop_ui`+4 writes while entering each shop
  in the city. Pets and treats then go on that list, or on a better-suited list (a pet section) if one fits.
- **Proof `pets-shop`** (melonDS taps): go to the shop (from a save near it), buy the Puppy and Pet Treats,
  money −price, both in Pockets. A save `verify/saves/pet-shop.sav` is added for testing.

### 5. A life of their own (behaviour engine)
- **More animations per pet:** pets get their own animation table (pets-kit), not the game's 5 slots. Up to 16
  named actions: stand, walk, run, sit, lie, sleep, sniff, scratch, play, eat, happy, sad, petted, greet,
  idle2, special.
  - `pets_play(e, action)` does what `critter_play_anim` does (records by facing + frame script) from our
    table.
  - `urbz_pets` / `urbz_import.ANIMALS` map actions → source animations per animal and render them.
    Missing ones fall back to stand.
- **Behaviour:** the pet kinds' behaviour (+0x4C) becomes `pets_behaviour`, a small state machine in C:
  - wander (using the game's movement as now);
  - idle variants;
  - sit / lie down / sleep:
    - at night (the game clock), or when happiness is low → mope;
    - to its bed if one is placed: dog basket / cat bed / hutch, the imported objects, found in the room's
      object list;
  - greet you when you come home (walk to the player, happy);
  - sometimes follow you around the room.
  - Hunger and happiness drift per game minute (`mod_on_minute`). Hungry pets beg (sit + sad) near you;
    unhappy ones mope.
- Caged animals use the same engine with their idles and hop; no sleeping in beds unless they have one.
- **Info page** (Mods page → Pets): each pet's name, what it's doing, hunger and happiness.
- **Proofs:**
  - `pets-life`: over a game day the Puppy does several different actions, sleeps at night, and greets on
    entering home.
  - `pets-needs`: hunger falls over time, Feed raises it, and a neglected pet plays sad animations.

### 6. Sounds (only if cheap)
- Look for fitting Urbz sound effects (barks, squeaks) in the game's sound table (`FUN_02097b58` ids) and play
  them on greet/play. No new audio this phase.

### 7. Gate
- **melonDS, real taps, one session from `pet-shop.sav`:**
  - buy the Puppy and treats;
  - go home and place it;
  - it lives (several actions), greets you;
  - Pet / Play / Feed via the menu;
  - save, power off, load: it's still there with its needs;
  - pick it up: back in Pockets with its own icon.
- **The other seven pets:** the `pet-walk` / `pets-life` proofs loop over every pet in pets.json.
- **Wrap-up:**
  - full `tests/proofs.py`;
  - docs: `docs/systems.md` "Pets", `docs/plan-phase9.md`, README "Pets", PLAN, HANDOFF;
  - commit and sync to the PC;
  - Jonathan plays it on the PC and the Thor.

## Files
- `code/pets-kit/pets.c` and `hooks.txt` (events, my-pets list, tap/menu, behaviour, animation table);
  `code/game.sym` (new addresses).
- `urbz_pets.py` (per-pet action table, icons, treats object, behaviour data); `urbz_import.py`
  (`ANIMALS` actions, icon render); `urbz_objects.py` (`"icon"` for any entry); `urbz_art.py` (reuse icon
  helpers).
- `mods/pets/pets.json`: Pet Treats.
- `tests/proofs.py`: pets-persist, pets-menu, pets-shop, pets-life, pets-needs; extend pet-walk.
- Docs as above. Plan copy: `docs/plan-phase9.md`; `PLAN.md` gets a Phase 9 section.

## Risks
- **The dialog / menu:** the game's dialog may be limited to 2 options. Fallback: a bottom-screen menu like the
  Mods page (proven).
- **Collision trigger unknown:** if the player's touch can't be made reliable, open the menu with A when facing a
  pet within one tile instead. That means our own check in `mod_on_tick` using the player's position and
  facing.
- **Save space:** about 120 bytes for 12 pets, well inside the ~1.4 KB.
- **Heap:** more animation files load only while playing. The code grows by a few KB.
- **Renders:** each extra action adds frames (ROM only). Every frame must keep within 32 tiles (`pet_art`
  checks).
