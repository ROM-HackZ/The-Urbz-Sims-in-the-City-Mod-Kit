# New objects and pets (Phase 8)

Mods add objects with `objects.json` (urbz_objects.py: the builder moves the seven object tables into
the code region and adds `code/objects`); `mods/pets` adds a critter kind. Facts: docs/systems.md
"Buyable objects" and "Pets". Proofs: `pet-place`, `objects-new`, `pet-new-kind`, `mods-split`.

## Sub-features

- `obj-build`: a mod with objects.json builds; the report says `objects: N new (...)`; vanilla stays identical.
- `obj-catalog`: a new object is listed on its Catalog page with its new name and price.
- `obj-place`: put in Pockets, a new object is placed at home and drawn like the object it copies.
- `pet-place`: a Chicken (vanilla) or Puppy (`mods/pets`) placed at home becomes a walking critter.
- `pet-pickup`: a critter in the pick-up state goes back to Pockets as its object.

## Driving it

- Put an object in Pockets: `--poke 0x02141338=02 --poke 0x02141892=<object u16 LE>0000` (2nd slot).
- Home: `--city --goto 68` (the starting home, Skyline Penthouse; experimental area loader).
- Place: Pockets icon (236,166), Pockets (84,75), double-tap the item (164,36), close (236,166),
  DOWN x3 (12 frames each), A. Yellow tile = free, red = blocked. `tests/proofs.py place_script()`.
- Catalog: Urb Info (56,128) > Catalog; pages Appliances (56,63) ... Furniture (56,128), Recreation
  (130,128); next row (196,51); item n of a row at x = 64 + 34n, y = 51.
- Find critters / objects in `0x0214DE20:0x42000`: entity type at +8 (5 object, 9 critter), id at +10,
  object number at +0x146, sprite at +0x8C (0 = not drawn). Pick-up: poke the critter's +0x108 = 0000
  and +0x104 = 12 0E (state 0x12, action 0x0E).

## Expected

- New object rows read through the moved text table (literal 0x02014130 points into the code region).
- Placed new object: an entity with its number and a non-zero sprite; Pockets count drops by one.
- Not covered yet: buying in a shop with real taps, using copied furniture, saving placed new objects.
