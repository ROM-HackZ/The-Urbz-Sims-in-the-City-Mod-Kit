# Other Sims DS games: what we could borrow

Jonathan (2026-10-05): "We can probably pull pet assets from a Sims pet game for the DS. Can you check also
if there's any furniture we don't have in Urbz that may be in the other Sims games." Plan: survey each ROM,
dump what's useful, compare with Urbz, then import his picks through `urbz_art.py` (pets) and the furniture
art step (docs/plan-phase8.md). ROMs and anything taken from them never go into git.

| Game | Developer | Containers | World art | Status |
|---|---|---|---|---|
| The Sims 2 (DS, 2005) | Griptonite / Maxis | **same as Urbz**: `rom.bin` (8,866 entries) + EA chunks + `SoundData.rom` | **3D** (intro shows a 3D Strangetown) | surveyed 2026-10-05 |
| The Sims 2: Apartment Pets (DS, 2008) | Full Fat | `NTRO` archives (`*.nitro_archive`): pets, sims, lots, object meshes/animations, screens, text; SDAT sound | **3D meshes** (`.mesh` + 2 LODs) | surveyed 2026-10-05 |
| The Sims 2: Castaway (DS, 2007) | Full Fat | same `NTRO` archives (names hashed, no strings); 31 MB of object animations | 3D | surveyed 2026-10-05 |
| The Sims 3 (DS, 2009, DSi-enhanced) | EA | 983 files: `.package` (Furniture 15 MB, Animations 20 MB, CAS clothes/hair/skin), `DSM1` meshes, `DST1` textures, `.bmp` | 3D | surveyed 2026-10-05 |
| The Sims 2: Pets (DS, 2006) | | | | not in Jonathan's folder |

**Bottom line:** every other Sims DS game draws its world in 3D; only The Urbz uses 2D sprites. So furniture and
pets can't be copied straight across: they'd be rendered from the 3D models into Urbz-style sprites (5
directions, 16 colours) by a converter we'd write. The Sims 2 DS is the exception for 2D art: it uses exactly the
Urbz formats, and our own tools read it as-is.

## Findings (2026-10-05)
- **The Sims 2 DS**: `urbz_extract.py` unpacks it unchanged (8,866 assets, 5,581 with chunks). The classifier finds
  1,190 sprite sheets + 1,209 layouts, 123 screens, 1,291 palettes, 4,263 packed-data entries (probably the 3D
  models and textures). Rendered: 846 sprite first-frames and 123 screens decode with our code; the sprites are
  UI and **item icons** (food, drinks, phones, tools, doors, alien/space items) and menus. Usable now: icons for new
  Catalog/Pockets items, UI pieces. Not yet: its 3D model format. Text bank differs (`urbz_text` fails on it).
- **Apartment Pets**: `pets.nitro_archive` has 3D **dog, cat, rabbit, hamster, guinea pig, cockatoo, macaw, snake,
  goldfish, angelfish, clownfish** and ~70 pet accessories (bows, hats, collars, glasses). `object_resources` has 692
  object meshes: about ten styles each of armchairs, beds, baths, sinks, bookcases, fridges, ovens, desks, dining
  and coffee tables, mirrors, curtains, art, plus pet items (dog basket, cat bed, bowls, hamster/guinea pig homes,
  toys). Animations in `object_animations` (10 MB). Archive layout: `NTRO`, size, then a table of
  `{u32 hash, u32 type?, u32 offset, u32 size, u32 0}` records (not fully decoded).
- **Castaway**: same engine as Apartment Pets, island objects, many more animations; file names are hashed.
- **The Sims 3**: the biggest furniture set (`Furniture.package`, `DSM1` meshes, `DST1` textures), clothes and hair
  for Create-a-Sim; all 3D.

## What it would take
1. Archive + mesh + texture (+ animation) readers for one game (Apartment Pets first: it has the pets).
2. An offline renderer: the model at The Urbz's camera angle, 5 directions, Urbz scale, cut to 16 colours, feet as the
   anchor; walk frames from the game's animations; output straight into `urbz_art.py`'s template.
3. Furniture the same way, through the furniture art step (docs/plan-phase8.md).
Nothing from these games goes into git; the converter reads Jonathan's ROMs at build time, like the Urbz extractor.

## Survey (`python3 research/survey_rom.py <game.nds>`)
Reports file kinds (Urbz-style container, Nintendo NARC/NCGR/NCLR/NCER/NANR sprites, 3D models), the largest
files, and for an Urbz-style container how many entries hold EA-compressed chunks.

Reference, The Urbz DS: 2 files: `rom.bin` (Urbz-style container, 13,385 entries, about 45% hold
compressed chunks) and `SoundData.rom`; no NARC, no Nintendo sprite formats.

## What an Urbz pet needs (docs/systems.md "Pets")
5 drawn directions (the game mirrors the other 3), slot 0 standing and slot 1 walking at least, 16 colours,
about the chicken's (16x24) to the rooster's (54x75) size, feet as the anchor point.
