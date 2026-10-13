# Playing the mods

How to get the mods into your game and what each one does. Setting up the kit itself: the
[README](../README.md#getting-started).

## Building and playing

1. Put a DS emulator anywhere (melonDS works best; the Windows zip from its GitHub releases. A copy kept in the
   kit's `emulator\` folder is ignored by git) and put the full path of its `.exe` in a file called
   `emulator.txt` in the kit folder.
2. Open **`manager.bat`** (or `python urbz.py manager`): tick the mods you want, change their order if you
   like, then **Build & Play**. Rebuilding replaces `build\Urbz Mod.nds` but never the save next to it, so your
   game carries on. **Add mod...** installs a mod someone sent you as a zip (zips with ROMs, saves or programs in
   them are refused).
3. melonDS keeps the save next to the ROM with the same name: `build\Urbz Mod.sav`. To start somewhere handy,
   copy one of the kit's saves there (it replaces your game in that file), then Load Game, slot A:

   | save (`verify\saves\`) | where you are |
   |---|---|
   | `city.sav` | the very start of the game |
   | `lobby.sav` | Tower Lobby, first goal done |
   | `urbania.sav` | just out of jail in Urbania Park, no home yet, $200; the stray puppy and kitten are in the park (Pets) |
   | `out-of-jail.sav` | the same with $2,000, rested, and Drifter Woods' stall stocked with Pet Treats, a Dog Basket and a Cat Bed |
   | `apartment.sav` | just moved into the Small Brownstone, $850, a crate to unpack |
   | `apartment-pets.sav` | the same, with all eight pets in Pockets (Pets) |
   | `pet-shop.sav` | at the Bayou Bazaar clerk (Farmer's Market) with $850; today's shelf has pets |
   | `cafe.sav`, `pizza.sav` | in Café Z-Bach / Slice O' Life Pizza in the afternoon (NPC Life) |

4. A fresh melonDS has **no keys set**: Config > Input and hotkeys. For example arrows = D-pad, X = A, Z = B,
   S = X, A = Y, Q = L, W = R, Enter = Start, Backspace = Select, Tab = fast forward; the mouse is the stylus.

Mods with an in-game switch can be turned on and off any time: **Options > Mods** (a 4th button the kit adds).
The choice is kept for every save.

The built ROM is bigger than the original cartridge (about 72 MB with every mod, from the pets' and furniture's
art). Emulators don't mind; on a real DS it needs a flashcart.

## The mods

### NPC Life (`mods\npc-life`)

The city lives. The 36 townspeople keep to the places the original game sends them, but in their free hours
they visit cafés, clubs and parks of their own choosing, with per-person habits and a daily routine that
follows the game's week. Where you can see them, they act it out:

- at meal times they eat (a snack at a grill or vending machine, or sit down at a table); they relax on
  chairs, sofas and benches, use the toilet, wash and sleep;
- in their free time they chat with each other (walking up, facing each other, taking turns gesturing), stroll
  round the place, or go and look at things: the jukebox, a TV, the museum exhibits, the crystal ball;
- everyone gets the animations they need: in the original game only 8 townspeople can sit and only Kris can
  eat, so the build *borrows* each missing animation from the closest-looking person who has it, recoloured
  and with the person's own head. Lincoln Broadsheet, in his wheelchair, eats sitting in his own chair;
- a few chairs that were only painted into a place are real seats now (Café Z-Bach's booths and sofa).

Switch it in the game (Options > Mods > NPC Life). Its info page shows what people here are doing. Details and
tuning: [`mods/npc-life/README.md`](../mods/npc-life/README.md).

### Pets (`mods\pets`)

Eight pets (Puppy, Kitten, Bunny, Hamster, Guinea Pig, Cockatoo, Macaw, Snake), Pet Treats, and a bed or cage
for each.

- **Your first pet: the strays.** Once you're out of jail, a stray puppy and a stray kitten hang about in the
  middle of **Urbania Park**. They're shy: stand still near one and it comes up to you; press A: Feed (one Pet
  Treats) or Leave. Feed it on two different days and it trusts you: "Take Home" puts it in Pockets. Someone in
  the park then adopts the other one.
- **Buying:** Drifter Woods' stall in Urbania Park (by the Brownstones) sells Pet Treats, the Dog Basket and
  the Cat Bed. Later the **Bayou Bazaar** stall at the Sim Quarter Farmer's Market sells every pet, treat, bed
  and cage. What's on the shelf changes every day.
- **Letting one loose:** Pockets, double-tap the pet, walk to a free (yellow) tile at home, A.
- **Looking after it:** walk up to your pet, face it, press A: *Pet*, *Play*, *Feed* or *Put in Pocket*.
  Pets wander, sniff, sit, play by themselves, greet you when you come home and sleep at night, in their own
  bed or cage if you have one. Food and fun go down slowly: one treat and a pet or a game a day keep a pet
  happy. They stay at home when you leave, move house with you and are saved with your game (up to 12).
  **Options > Mods > Pets** shows how each one is doing (R / L scroll).
- Only your own pets can be picked up.

The pets' pictures are rendered from your own copy of *The Sims 2: Apartment Pets* when you build (see
"Importing from other Sims games" in [modding.md](modding.md)); without it they wear the look of a game animal.
More: [`mods/pets/README.md`](../mods/pets/README.md).

### More Furniture (`mods\more-furniture`)

13 pieces from The Sims 3 and Apartment Pets (rendered from your own copies of those games): armchairs, a
recliner, sofas, a loveseat, beds, a dining chair and tables, sold at the furniture shop (some also at the
Second Looks Thrift Emporium). Better pieces fill needs faster, and some have their own actions: Read a Book,
Nap, Daydream, Read in Bed. List: [`mods/more-furniture/README.md`](../mods/more-furniture/README.md).

### Max Needs (`mods\max-needs`, testing aid)

Keeps your Sim's needs full (never hungry, tired or passing out) while it's ON: handy for exploring. Switch it
in the game: Options > Mods > Max Needs. It starts ON; turn it off to play normally.

## Mixing mods and saves

A save keeps what mods added (a placed Dog Basket, Pet Treats in Pockets). Loaded in a build without that mod,
those things are set aside (not shown, kept in the save) and come back when you build with the mod again. A
save made with mods can't be loaded by the original, unmodded game.
