# Other Sims DS games: what we borrow, and how

Jonathan (2026-10-05): "We can probably pull pet assets from a Sims pet game for the DS. Can you check also if
there's any furniture we don't have in Urbz that may be in the other Sims games." Then: "do all the research
necessary to learn how this all works so we can take our pick of the assets we want to move over."

**Status (2026-10-05): four games are readable and render into Urbz-style art (1,516 models in the gallery).** Pick from the gallery
(`python urbz_import.py gallery` → `catalog/imports/index.html`), name the pick in a mod's `objects.json` or
`pets.json` (`"import"`), build. Nothing from these games goes into git: the builder renders the art from your own
ROMs (`sources.json`) every build; without them a mod still builds and keeps its starting art (a warning says so).

| Game | Developer | Containers | Models | Reader | What's there |
|---|---|---|---|---|---|
| The Sims 2: Apartment Pets (2008) | Full Fat | `NTRO` archives | GX display lists + skeletons + animations | `urbz_fullfat.py` | 11 pets (dog, cat, rabbit, hamster, guinea pig, cockatoo, macaw, snake, 3 fish) with ~120 animations each for dogs/cats, ~94 accessories, ~350 objects (about ten styles each of chairs, beds, baths, sinks, bookcases, fridges, ovens, desks, tables, mirrors, curtains, art, plus pet beds, bowls, cages, toys) |
| The Sims 2: Castaway (2007) | Full Fat | same | same | `urbz_fullfat.py` | ~370 island objects: trees and fruit plants in growth stages, bushes, shelters, tools, fire, collectables, musical instruments |
| The Sims 3 (2009) | EA | `.package` runs of `DSM1` + `DST1` | GX display lists | `urbz_sims3.py` | 364 furniture groups, several colour choices each |
| The Sims 2 (2005) | Griptonite / Maxis | `rom.bin` + EA chunks (the Urbz container) | Nintendo NSBMD (`BMD0`) | `urbz_nsbmd.py` | 329 models: hotel furniture, rooms, aliens, animals (cow), props; 2D item icons readable by our Urbz tools as-is |
| The Sims 2: Pets (2006) | | | | | not in Jonathan's folder |

All four draw their worlds in 3D; only The Urbz uses 2D sprites. `urbz_import.py` renders the models the way The Urbz
draws (below) and hands the pictures to the builder.

## The Urbz camera (measured 2026-10-05)
- Orthographic, turned 45 degrees, looking **30 degrees down**: floor tiles are exactly 2:1 (the card table's top
  edges step 1 px down per 2 px across).
- **About 42 px per metre**: a 1 m floor tile is ~59 px across its diagonal; a 1.75 m person ~64 px tall; the card
  table top (~0.9 m) is 54 px across.
- Placed furniture: the art's origin is the **west corner of its tile**; the game's records 0-2 show the piece
  facing up-right, 3-4 facing down-left, mirrored for the other turns. Pets: 5 directions, dir0 facing away, dir2
  side-on (right), dir4 facing you; feet on the origin.

## Formats

### Full Fat (Apartment Pets, Castaway)
- **NTRO container** (every file): `'NTRO'`, u32 size, u32 block count, blocks `{u32 type, u32 size, u32 offset}`.
- **Archives** (`*.nitro_archive`): records `{u32 name hash, u32 group hash, u32 offset, u32 size, 0}` at 0x40
  (count at 0x3C), then the data; Apartment Pets adds a names block (128-byte slots). Castaway has no names block,
  but every file carries its own name (mesh header, texture params).
- **Texture**: blocks {1: u32 TEXIMAGE_PARAM, u32 hash, name; 3: palette; 2: texels}. DS formats 2/3/4/1/6/7 decoded
  (4x4 compressed not seen here).
- **Mesh**: {0xB: header + name; 0xC: a GX display list (the DS 3D engine's own command stream); 0xE: materials,
  13 words each: words 1-7 = display-list offsets of the commands it sets, +8 DIF_AMB, +10 POLYGON_ATTR,
  +11 texture hash; 0x10: bone slots `{LOAD_4x4 offset, MULT_4x3 offset, SCALE offset, bone}`}. Vertices are in
  the bind pose; the game writes each bone's skin matrix into its MULT_4x3. A material applies from its first
  command to the next material.
- **Skeleton**: {0x11: bone count, 0x12: 88-byte bones `{s32 parent, s32, 4x4 fx12 inverse bind matrix (row
  vectors, translation last), name[16]}`}.
- **Animation**: {0x13: frames, bones, fps; 0x14: per bone first rotation key / first position key; 0x15: rotation
  keys `{u32 frame, s16 x y z w}` (quaternion, fx12); 0x16: position keys `{u32 frame, s32 x y z}`}. World =
  local x parent; skin = inverse bind x world. Proven by rendering the dog's walk (legs move, root moves forward).
- **Object script** (`object_definitions`): `{key hash: value}` pairs; SIZE_Y (0x8652A74D) is the object's height in
  metres, which gives each mesh's scale (static meshes are in their own units: an armchair in quarter metres, a dog
  basket in ~1/7.7 m). Units: pets and skinned meshes are in metres.
- Facing: pets face +Z, objects -Z.

### The Sims 3
- `*.package`: a plain run of `DSM1` meshes and `DST1` textures, no index. An object = its meshes (each part in 5
  levels of detail, most detailed first), then its textures as mip chains (128, 64, 32, 16, 8); several chains of
  the first texture = its colour choices (`"colour": n` in an import).
- `DSM1`: `'DSM1' 03 01 01 01`, u32 n, a GX display list of n bytes (metres), then materials (texture file names) and
  named points (slots like `berth_1`). `DST1`: `'DST1' 02 01 01 01`, u32 format (bit 16 starts a new texture),
  u16 width, height, colours, palette, texels. Furniture faces -Z.

### The Sims 2 (DS)
- Models are standard Nintendo **NSBMD** (`BMD0`: MDL0 + TEX0) inside the EA-compressed `rom.bin` assets (329).
  `urbz_nsbmd.py` reads dictionaries (entries start at offset + the u16 at +6), nodes (translation, rotation incl.
  the pivot form, scale), the render bytecode (NODEDESC 0x06, MTX 0x03, MAT 0x04, SHP 0x05, RET 0x01), materials
  and TEX0 textures (all DS formats incl. 4x4 compressed).
- **Textures usually live in the next asset:** the model's TEX0 has the dictionaries but its texel data is zero;
  the following `rom.bin` asset holds the data, **palettes first, then texels**. The reader splices it in when the
  model's own data is empty.
- Units 1/8 m after the model's position scale; furniture faces -Z.
- Result: 310 of 329 models render textured, 16 render black (a texture we haven't matched), 3 have none.
  Skinning (NODEMIX 0x09), billboards and animations (BCA0, 2,818 files) are not read, so its people and animals
  come out in their bind pose: fine for furniture, not for pets.

## Using it
```
sources.json (next to urbz_build.py, yours only):
  {"aptpets": "D:/ROMS/Sims 2 Apartment Pets.nds", "castaway": "...", "sims3": "...", "sims2": "..."}
python urbz_import.py gallery            # every model, front and back, at the Urbz angle
python urbz_import.py show aptpets dog   # one model: 5 turns + walk frames
```
`objects.json`: `{"id": 440, "like": 136, "name": "Green Lounger", "price": 140, "page": 3,
"import": {"from": "aptpets", "model": "armchair4"}}`. `pets.json`: `{"name": "Puppy", "object": 386, "from":
"rooster", "import": {"from": "aptpets", "model": "dog", "textures": {"collie2": "beagle", "collie": "beagle"}}}`.
Options: `scale` (1.0 = real size; pets default to the size of the animal they replace), `textures` (swap texture
names, e.g. a dog breed), `colour` (The Sims 3 colour choice), `anims` (pets: which animation per slot).

## Survey tool (`python3 research/survey_rom.py <game.nds>`)
Lists a ROM's file kinds, largest files and, for an Urbz-style container, how many entries hold EA chunks. (It
misses formats inside compressed chunks: The Sims 2 DS's NSBMD models were found by decompressing.)
