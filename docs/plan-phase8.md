# Phase 8: the art tool — new pets, furniture and animations, drawn by you

Decided with Jonathan (2026-10-04): Phase 8 is **pets** (everyday pets, placed at home like the Chicken)
and **functional furniture**, as separate mods (`mods/pets`, `mods/more-furniture`). Clothes wait. Both
work today with borrowed art (rooster, copied chairs). This plan is the tool that turns them into real
new things: **one tool, `urbz_art.py`, for every kind of new art**: furniture, pets and townspeople's
animations. (The earlier clothes-and-objects plan is superseded; its research is in docs/systems.md.)

## What the game's art looks like (found 2026-10-04, docs/systems.md)

All three kinds use the same building block: a **record** = {graphics file, layout file, palette, param}.
A layout cuts a frame into hardware sprite pieces; `urbz_composite.py` reads and writes that format, and
`urbz_anims.py` already turns drawn PNG frames into new graphics + layout files (Phase 7, proven).

| | what you draw | size (game's own) | colours |
|---|---|---|---|
| **Furniture, placed** | 2 views: front and back (the game mirrors them for the other 2 turns); some have states (a bed: made / slept in) | chair ~56x48, bed ~80x48 | a 16-shade ramp; each of the 5 catalog colours is a palette row (`object_variants`) that recolours the same drawing |
| **Furniture, icon** | 1 picture (Pockets and Catalog) | ~24x32 | its own 16 colours |
| **Pet (critter)** | 5 animations (stand, walk, ...) x front/back views, several frames each | chicken 16x24 | its own 16 colours |
| **Townsperson animation** | (already `urbz_anims.py`) sit, eat, toilet, shower, sleep x front/back | 96x96 canvas | the person's 16 colours |

Where they live: placed furniture art `object_models[obj]` (5 records) and `object_anims` (state frames);
icons a UI sprite table at 0x020CB134 (16-byte records indexed by the object's model number; ~632 rows);
pet art `critter_anims[kind]` (5 animations, each a records list + frame script) and `critter_palettes`.

## How you'll use it

```
python urbz_art.py template more-furniture 430          # the armchair: PNGs of the chair it copies
python urbz_art.py template pets puppy                  # the Puppy: the rooster's frames to draw over
python urbz_art.py template my-anims hattie sit         # (today's urbz_anims.py, folded in)
   ... draw over the PNGs in any paint program ...
python urbz_art.py preview more-furniture               # a picture of how it will look in the game:
                                                         #   every view, every colour, the icon, at 1x and 3x
```
Then build the ROM as usual: the builder turns the PNGs into game files by itself (no separate build step).

What a template folder looks like (example: `mods/more-furniture/art/430-farmhouse-armchair/`):
- `icon.png` (32x32), `front.png`, `back.png` (canvas sized for the piece, a guide dot on the floor point),
  `front-2.png` ... for extra states (beds), `colours.png` (the 5 catalog colours as swatches: change
  them to recolour), `README.txt` (what each file is, the size and colour limits).
- Pets (`mods/pets/art/puppy/`): `stand/front/01.png ...`, `walk/back/03.png ...`, a `timing.json` (frame
  lengths, copied from the animal it replaces), `palette.png` (its 16 colours).
- Every PNG starts as the copied thing's own art, so the first build already works and you replace
  pictures one at a time. Colours outside the allowed set snap to the nearest (preview shows where).

## Building blocks (what changes in the kit)

1. **Art from several mods at once.** Today only one mod may add art files (they are numbered after
   the game's last one). New: mods ship PNGs; the **builder** converts them and numbers all new files
   across every enabled mod, then writes the tables. `urbz_anims.py`'s mods move to this too.
2. **Furniture art**: `objects.json` gets `"art": "art/430-farmhouse-armchair"`; the builder makes the
   graphics + layout files, a new `object_models` row (the 5 records), state frames, colour rows and an
   icon entry (the icon table moves and grows, like the object tables did).
3. **Pet art and more pets**: the pets mod becomes data-driven: `pets.json` lists pets (name, object
   number, price, which animal it starts from, speed, art folder); each gets its own critter kind
   (7, 8, ...). Its art fills `critter_anims` / `critter_palettes` rows.
4. **One tool**: `urbz_art.py` (template, preview, check) for furniture, pets and people; `urbz_anims.py`
   stays as a thin alias so nothing you know breaks.

## Status (2026-10-05): done
Decided: everything within the game's own capabilities (real size, 16 colours), just new stuff; pets first.
- **Pets** (steps 1, 2, 4): pets as data (`pets.json`, `urbz_pets.py`, `code/pets-kit`), `urbz_art.py
  template/preview/placeholder`, shared art numbering (proofs `pets-data`, `pets-art`). 5 drawn directions.
- **Furniture art** (step 3): `objects.json` `"art"` (drawn, `urbz_art.py object-template`) or `"import"`;
  the builder makes the views, an own palette per object (`code/objects` `objects_own_palette`, OPAL list),
  and an icon (icon table moved, models 633+). Proof `import-furniture`.
- **Imports from the other Sims DS games** (added 2026-10-05, Jonathan: "take our pick of the assets"):
  readers for Apartment Pets / Castaway (`urbz_fullfat.py`), The Sims 3 (`urbz_sims3.py`), The Sims 2
  (`urbz_nsbmd.py`); renderer + gallery (`urbz_import.py`, 1,516 models); `mods/pets` imports the beagle
  and cat. Formats: `docs/other-games.md`. Proofs `rom-grow`, `import-render`, `import-furniture`,
  `import-pet`, `import-melonds` (the imported armchair placed with real taps in melonDS, 99.8% the same
  as DeSmuME).
- Open: buying in a shop with real taps; picking a pet up with real taps; The Sims 2 DS animals (no
  skinning/animation reader) and 16 of its models that render black; `urbz_anims.py` still separate.

## Steps (each ends with something proven in the emulator)

1. **Research** (short): which palette holds furniture colour rows and how a row is picked; icon table
   length and every reader (to move it); limits per sprite (VRAM, pieces per frame); how states map to
   frames (bed made/unmade); pet animation ids (which of the 5 is walk, stand, pick-up). Output: facts
   in docs/systems.md, names in game.sym.
2. **Shared art numbering in the builder** (block 1), with `urbz_anims` mods moved over. Proof: two mods
   each adding art build together and both show.
3. **Furniture**: template + preview + build for a placed object and its icon. Proof: a redrawn armchair
   (placeholder: the original, flipped and recoloured by the tool) shows in Pockets, the Catalog and at
   home, in all 5 colours and 4 turns.
4. **Pets**: `pets.json`, several pets, template + preview + build. Proof: two pets (e.g. Puppy, Kitten)
   with different art run around at home and go back to Pockets.
5. **Gate**: melonDS (real taps: buy, place, turn, pick up), full proofs, README "Drawing new art"
   for Jonathan, commit. Jonathan draws the first real piece and tests on the Thor.

## Risks / open questions
- Furniture is recoloured by palette rows: drawings must use the 16-shade ramp; full-colour furniture
  would need its own palette (to find out if the game allows it per object).
- Big pieces (beds, sofas) are several sprite pieces per view; a limit of 31 pieces per frame
  (`urbz_anims.cut_cells`) may need bigger pieces or splitting.
- Pets that act differently from chickens (fetch, sleep in a basket) need new behaviour code: later,
  after the art works.
- The art is drawn over the game's own pictures: template folders hold game-derived PNGs and must stay
  local (never committed); Jonathan's finished drawings are his to share.
