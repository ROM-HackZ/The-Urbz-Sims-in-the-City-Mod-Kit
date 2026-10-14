# Making mods

The full guide to the kit: every tool, every file format a mod can hold, and how the build puts them together.
New here? Start with the [README](../README.md) (setting up and playing), then come back for whatever you want
to change. Every command below is `python urbz.py <tool> ...` from the kit folder (`python urbz.py` lists them).

## Kit layout

| Path | What it is |
|---|---|
| `project\` | The unpacked original game. **Keep it pristine**; it's the reference. |
| `mods\<name>\` | Your mods. Each holds **only** the files it changes or adds, at the same paths as in `project\`, plus data files (`objects.json`, `pets.json`, `poses.json`, `seats.json`, `code\`, ...). |
| `mods.json` | Which mods are enabled, in order. Later mods win if two change the same file. |
| `build\` | Built ROMs, and `build\cache` (rendered art, kept between builds). |
| `kit\` | The tools; `python urbz.py <tool>` runs them. |
| `verify\` | Headless emulator checks (`verify\urbz_verify.py`), test saves, input scripts and scene traces. |
| `catalog\` | Generated asset gallery (`catalog.bat`). Safe to delete and regenerate. |
| `.claude\skills\verify-urbz\` | Verification recipes Claude follows (also readable by you). |

### Mod commands (`python urbz.py mod ...`)

| Command | Does |
|---|---|
| `list` | Show mods and which are enabled. |
| `new <mod> ["desc"]` | Create and enable a mod. |
| `edit <mod> <asset> [chunk\|--raw]` | Copy pristine file(s) into the mod so you can edit them. |
| `status [<mod>]` | List each mod file as changed / identical / new / unknown. |
| `enable` / `disable <mod>` | Toggle a mod. |
| `rescue <mod>` | Edited `project\` by accident? Moves those edits into a mod and restores `project\`. |

**Adding new assets:** put them in a mod as `assets\13385.bin`, `assets\13386.bin`, and so on, with no gaps.
They're appended after the original 13,385. Nothing in the game uses them until something
references their ID (content wiring comes in a later phase).

### Build options (`python urbz.py build ...`)

- `[out.nds]`: output path (default `game\Urbz DX.nds`)
- `--vanilla`: ignore mods (proves the baseline is identical)
- `--mod NAME`: build with only this mod (repeatable; a name in `mods\` or a folder path), ignoring `mods.json`

## Editing text

Every line in the game (8,311 strings: dialogue, menus, item and place names) is
in one compressed text bank. You edit it as plain text:

```
python urbz.py text find "sitting around"        search (prints string IDs)
python urbz.py text edit my-mod 5870 5873        copy lines into mods\my-mod\text\strings.tsv
```
Open `mods\my-mod\text\strings.tsv` in any text editor and change the text after the tab.
- **Accents:** type é, ñ, ü, ç, ¿, ¡, … and ™ directly; they're in the game's fonts. Anything
  else needs a new glyph first (see *Fonts* below).
- **Escapes:** `\n` new line, `\xNN` any byte.
- **Placeholders:** keep `@1 @2 @3` (names) and `@hh @mm @am` (clock) where the original has them.
- **Length:** up to 1,023 characters. The game wraps text to fit the box.
- **Reference:** a read-only copy of all strings is in `project\text\strings.tsv`.

## Editing pictures (PNG)

```
python urbz.py png edit my-mod 10747             screens / sprite frames -> mods\my-mod\png\10747\*.png
```
Paint on the PNGs, save, and build.
- **Screens:** you can use any colours. Edited tiles that need new colours get them
  in a spare palette row (when the screen has one; otherwise the build warns and uses
  the nearest colours). Tiles are re-cut automatically.
- **Sprites** use a 16-colour palette: paint with the colours already in the exported PNG
  (the build warns if you used others). To change the colours themselves, edit the palette
  (next section). Sprites show real colours once `verify\urbz_verify.py trace` has seen them in a
  scene (`verify\palettes\`), else greyscale.
- **Composite sprites** (characters made of several pieces, like the player's body parts)
  export as the finished picture; your edit is cut back into the pieces on build.
- An unchanged PNG changes nothing (the build stays identical).

## Recolouring (palettes)

Most sprites get their colours from separate palette files. Edit the file and everything
drawn with it changes colour:
```
python urbz.py palette list                      known palette files and what uses them
python urbz.py palette who kris                  a person's palette (Kris Thistle: 09160)
python urbz.py palette edit my-mod 9160          -> mods\my-mod\palette\09160.png (16x16 swatches)
```
Repaint swatches and build. The player's skin, hair and shoe colours are in 11543, the 32
clothing colours in 11542 (`docs\player-look.md`).

## Fonts

The game has 8 fonts (different sizes). Edit them as PNG sheets:
```
python urbz.py font edit my-mod          -> mods\my-mod\font\fontN_NNNNN.png + .json (all 8)
python urbz.py font edit my-mod 0 2      just fonts 0 and 2
```
Glyph pixels use colours 1-15 (0 = see-through); the red bar under each glyph is its width.
Empty cells after the last glyph are free codes (up to 0xEF): draw a glyph and its bar there
to add a character, then use it in text with `\xNN`.

## Code mods (changing how the game works)

A mod can also change the game's code. Two kinds:

**Number patches** (no compiler needed). `mods\<mod>\code\hooks.txt` lines like
```
u8 time_speed_table+4  1      # write a number at a named address
u32 object_info_table+4000 99 # (names come from code\game.sym)
data 0x02113B60 01 0F         # or raw bytes
```
Example: `tests\mods\clock-speed` (the kit's own test mod) makes in-game days last twice as long; copy it
into `mods\` to use it, then edit the two numbers in its `hooks.txt` (the table in that file shows the options).

**C code.** `python urbz.py patch new my-mod` adds `code\main.c` and `code\hooks.txt`. Write C
using `code\include\game.h` (the clock, needs, money, people...), say where it runs in `hooks.txt`:
```
wrap world_tick on_tick            # run on_tick 30 times a second, then carry on
call time_update_call my_time_add  # make one existing call go to my function
jump motive_get my_motive_get      # replace a whole game function
```
then `python urbz.py patch build my-mod` and build as usual. Compiling needs LLVM
(`winget install LLVM`); building the ROM doesn't, because each mod keeps its compiled
`code\build\patch.bin`. A small example is `tests\mods\npc-visit` (a test mod): it answers
the game's "where should this person be?" question so that Bayou Boo walks onto the King Tower roof
(where a new game starts) at 10:40 am.

The build prints each code mod's size and address. Code goes in a new block after the game's
own data, and the game's memory heap starts after it (there's about 1.4 MB of headroom; the build
warns above 128 KB). Mistakes fail the build with a message (a hook that isn't on a call, two mods
patching the same spot, C that wasn't compiled...).

What every address means, and how we know: `docs\systems.md`. Motive effect table:
`docs\effect_rows.md`.

## Mods in the game: switches, saved data, the Mods page

Code mods can be **switched on and off inside the game**: Options has a 4th button, **Mods**,
that lists every mod built into the ROM with ON/OFF. Tap one to switch it; the choice is kept in
the cartridge's save memory (for every save) straight away. Set it up in the mod's `mod.json`:
```
{ "name": "my-mod", "version": "1.0", "author": "me", "description": "...",
  "toggle": true,        can be switched in the game (default for code mods)
  "default": true,       starts on
  "conflicts": ["x"],    can't be built together with mod x
  "save_bytes": 64,      most save space it uses per slot
  "title": "My Mod" }    the name shown on the Mods page (default: name; the save data stays under name)
```
A mod with `"toggle": false` and an info page shows up on the Mods page as just its page (like Pets).
A C mod can also use **events** (no hooks.txt line needed, just define the function; see
`code\include\mod.h`): `mod_on_tick`, `mod_on_minute(n)`, `mod_on_area_enter(area)`,
`mod_on_save(buf, max)` / `mod_on_load(buf, len)` (its own data in each save slot, kept even while
the mod is switched off), `mod_on_enable` / `mod_on_disable`, and `mod_on_page` (an info page,
opened from the Mods page). `u32 ADDR @name` in hooks.txt writes the address of something in the
mod (e.g. to point a game table at your own).

**Leaving a mod out of a build:** a save keeps what mods added (a placed Dog Basket, Pet Treats in Pockets).
Loaded in a build without that mod, those things are set aside (not shown, kept in the save) and come back
when you build with the mod again. This needs the mod core, which is in any build with a switchable mod or
NPC Life; the original game can't load such a save.

## Mod manager (window)

`manager.bat` (or `python urbz.py manager`) shows every mod with a tick box, its version and
description. Tick the ones you want, change their order, then **Build**, **Play** (opens the
ROM in the emulator named in `emulator.txt`) or **Build & Play**. **Add mod...** installs a
mod from a zip file (it refuses zips with ROMs, saves or programs in them).

## Borrowed poses (automatic)

In the original game only 8 townspeople can sit, shower, sleep or use the toilet, and only Kris can eat.
With NPC Life on, the build gives everyone else those animations: each one is taken from the
closest-looking person who has it, recoloured to the person's own colours and given their own head. They
look a little off-model up close, but everyone can now sit at a table, eat, wash and sleep. The first
build makes them from your game (about a minute; kept in `build\cache` after that). Which groups, and who
to leave alone: `mods\npc-life\poses.json` (Lincoln Broadsheet, in a wheelchair, gets no sit, toilet or
shower and eats in his own chair; Mokey is left out because the game draws him its own way). To look at
them first: `python urbz.py poses preview <folder> hattie` (contact sheets, the original pose above each
borrowed one).

## New animations for the townspeople (drawn by you)

Only 8 townspeople have the game's sit/toilet/shower/sleep animations (and only Kris can eat); the
borrowed poses above fill in the rest. `python urbz.py anims` lets you draw your own for anyone, in their own
look (a person you draw for keeps your drawings instead of the borrowed ones):
```
python urbz.py anims list                         who has which animation
python urbz.py anims template my-anims hattie sit # Gramma Hattie: frames to draw + a guide
```
Then draw `mods\my-anims\people\43-gramma\sit_6b\front\NN.png` and `...\back\NN.png`: each starts
as her own standing frame, and `guide\sit_6b\...` shows the same frame on Kris (pose and timing to
copy). Every PNG is 96x96 with the feet on pixel (40, 72); use her own colours. Then:
```
python urbz.py anims build my-anims               new sprite sheets + the game data
python urbz.py patch build my-anims               (needs LLVM)
```
and build the ROM with `my-anims` enabled. NPC Life then sends her to chairs like the others. Groups:
sit, eat, toilet, shower, sleep. The frames come from the game's art, so keep your mod to yourself.

## New objects and pets

How buying works in this game: the **Catalog only shows** things. **Shops sell** them; each shop
restocks every day from the objects marked for it. What you buy goes into **Pockets**; double-tap
it there, walk to a spot (yellow tile = free), press A to put it down at home (L/R turn it).

A mod adds or changes objects with an `objects.json`:
```
{"objects": [
  {"id": 386, "like": 225, "name": "Puppy", "description": "A playful pup.",
   "price": 60, "page": 4, "sell": {"9": "common"}}
]}
```
`like` is the object to copy (art and behaviour); `page` is the Catalog page (0 Appliances ...
5 Utilities, 7 = not shown); `sell` = shop lists that may stock it. The builder makes room for
the new rows by itself. `python urbz.py objects show 225` prints an object's row.
New numbers: 386 and 389-511. A new object can have its own art: `"art": "art/<folder>"` (your drawings,
"Drawing furniture" below) or `"import": {...}` (a model from another Sims DS game, "Importing from other Sims
games" below). Without either it wears the copied object's art.
Each object with its own art takes one of the ~7 sprite colour sets the DS has free at home (past that, things
come out in the wrong colours); objects with the same `"palette": "<group>"` share one set (their colours are
fitted together), and so do pets with the same `"palette"` in pets.json.

New furniture can also be better or do more than the piece it copies:
- `"quality": 1-5` - how fast it fills needs (the game's own scale: 1 = x1.0 ... 5 = x2.0; a $50 sofa is 1,
  the $1,100 one 5).
- `"actions"` - extra choices in its menu. Each plays like one of the object's own (`"as": "Sit"` or
  `"Sleep"`: you walk there and sit or lie down as usual) and also changes needs every tick, then ends when
  `"until"` (a need) is full or after `"minutes"` game minutes:
  ```
  "actions": [{"name": "Read a Book", "as": "Sit", "fun": 0.25},
              {"name": "Nap", "as": "Sit", "energy": 0.12, "minutes": 60}]
  ```
  Needs: hunger, hygiene, energy, social, comfort, bladder, fun, room. For scale, the game's chairs give
  comfort 0.2-0.3 a tick (30 ticks a second). The sitting itself still gives its comfort too.

Two mods use this, each picked on its own in the mod manager (no in-game switch):
- **`mods\pets`** adds eight pets from `pets.json` (Puppy, Kitten, Bunny, Hamster, Guinea Pig, Cockatoo,
  Macaw, Snake) and Pet Treats: buy them at the Farmer's Market, let them loose at home and look after them
  ("Looking after pets" below). Their art: see "Drawing a pet" below. Numbers 386 and 389-429.
- **`mods\more-furniture`** adds 13 pieces (the kit's own models, "The kit's own models" below): armchairs, a recliner, sofas, a loveseat, beds,
  a dining chair and tables, sold at the furniture shop (some also at the Second Looks Thrift Emporium).
  Some have their own actions: the Club Armchair's Read a Book, the Mission Recliner's Nap, Daydream on the
  Club Sofa and Camelback Loveseat, Read in Bed on the Mission Double Bed. Numbers 430-511.

## Drawing a pet

Pets live in `mods\pets\pets.json` (eight so far; add more the same way). Each starts from
an animal of the game (`"from"`: chicken, rooster or nutria): it moves like that animal and wears its art
until you draw your own:
```
python urbz.py art template pets puppy      mods\pets\art\puppy\: the rooster's frames to draw over
python urbz.py art preview pets puppy       art\puppy\preview.png: every frame, big, off-colour pixels pink
```
In the folder: `0-stand\dir0\00.png ...` (slot 0 = standing, 1 = walking, 2-4 = other moves; dir0 faces
away, dir2 side-on (facing right), dir4 faces you, the game mirrors the rest), `palette.png` (the pet's 16 colours: the
first square is see-through; change a square to recolour everything drawn in it), `timing.json` (frame
lengths; `same_as` reuses another slot). Every frame is 88x88 with the feet on pixel (32, 64); the
shadow is part of the drawing. Keep the number of frames the template has (other counts aren't
tested yet). Then build
the ROM as usual: the builder turns the drawings into game art itself (and numbers new art so pets,
townspeople's animations and later furniture can all be built together).
The template pictures are the game's own: keep the `art` folder to yourself until it's all your drawing.

## Drawing furniture

```
python urbz.py art object-template mods\more-furniture\art\armchair 136    start from object 136's art
```
The folder holds `view-away.png` (the piece facing up-right; the game shows it for 3 of its turns),
`view-toward.png` (facing down-left), extra state frames `view-away-1.png ...` (e.g. a slept-in bed; missing
ones repeat the first), `palette.png` (its own 16 colours: unlike the game's furniture it isn't recoloured by
the catalog colours) and `icon.png` (32x32, for Pockets and the Catalog) with `icon-palette.png`. Canvas
128x128; the west corner of the piece's floor tile is pixel (24, 100). Point an object at it with
`"art": "art/armchair"` in `objects.json`.

## Settings players can change (the Tune window)

The mod manager's **Tune...** lets players change some of a mod's settings without editing its files:
- `pets.json`: a pet's name, price, description, and which shops sell it (common / uncommon / rare);
- `objects.json`: the same for objects, plus quality (1-5);
- `places.json` (NPC Life): what each place offers.

Their changes go in `tuning\<mod>.json` (never committed) and the builder applies them over the mod's own
files when it reads them (`kit/urbz_tuning.py`; `python urbz.py tuning show` lists them). Data compiled into a
mod's C code can be tuned too when the kit knows its layout: NPC Life's places table (`sim_places`, a fixed
80 rows) is rewritten in the compiled code at build time, so nobody needs a compiler. The named shops are
the furniture shop (list 4), the Bayou Bazaar (9), the Second Looks Thrift Emporium (10) and Drifter Woods'
stall (18).

## The kit's own models

The pets, the pet beds and the More Furniture pieces are 3D models built from simple shapes in code
(`kit/urbz_models.py`: a rig and actions for four-legged pets, birds and the snake; a function per piece of
furniture), drawn the way The Urbz draws its world (below) when you build. They're original, so they ship with
the kit, and a build needs nothing but your Urbz ROM.
- `python urbz.py models list` lists them; `python urbz.py models show puppy` draws a sheet of one (every action
  in 5 turns) into `build\models\`.
- Use one in a mod like any import: `"import": {"from": "kit", "model": "club_sofa"}`.
- To add one: a function returning its parts (shapes, each with a colour) in `urbz_models.py`, listed in
  `FURNITURE` (or a new entry in `QUAD` for a four-legged pet: proportions, ears, tail, colours).

## Importing from other Sims games

Optional: you can bring pets and furniture over from The Sims 2: Apartment Pets, The Sims 2: Castaway, The Sims 3
and The Sims 2 (DS), if you own them. Their worlds are 3D; the kit renders each model the way The Urbz draws (from above at its
angle, its size, 16 colours) every time you build. Your copies of those games stay on your computer:
1. Create `sources.json` in the kit folder, next to `urbz.py` (it is never committed):
   `{"aptpets": "D:\\ROMS\\Apartment Pets.nds", "castaway": "...", "sims3": "...", "sims2": "..."}`
   (a `.zip` holding the `.nds` works too; it is unpacked once into `build\sources`)
2. `python urbz.py import gallery` renders every model into `catalog\imports\index.html`: pick from there.
   `python urbz.py import show aptpets dog` shows one model in 5 turns and walking.
3. Name your pick in a mod:
   - furniture, `objects.json`: `{"id": 440, "like": 136, "name": "Green Lounger", "price": 140, "page": 3,
     "import": {"from": "aptpets", "model": "armchair4"}}` (`like`: the object it behaves like; choose one
     with a similar size and use);
   - pets, `pets.json`: `{"name": "Puppy", "object": 386, "from": "rooster", "import": {"from": "aptpets",
     "model": "dog", "textures": {"collie2": "beagle", "collie": "beagle"}}}`.
   Options: `"scale"` (1.0 = real size; pets default to the size of the animal they replace), `"textures"`
   (swap texture names, e.g. a dog breed), `"colour"` (The Sims 3: which colour choice), `"anims"` (pets:
   which animation for each slot, e.g. `{"0-stand": "sitidle"}`).
4. Build. Without the source game the mod still builds, with its drawn art if it has some, else the
   starting animal's or object's art (a warning says so).
5. `"import"` can be a list, best first: the first whose game you have is used. The shipped mods do this, e.g.
   `"import": [{"from": "aptpets", "model": "dog", "coat": "beagle"}, {"from": "kit", "model": "puppy"}]`: with
   Apartment Pets in `sources.json` the Puppy is drawn from its dog, otherwise from the kit's own.

`mods\pets` and `mods\more-furniture` use the kit's own models, or the Apartment Pets and Sims 3 ones when you
have those games (`"coat"` picks another dog breed or cat coat, see `docs\other-games.md`). To use your own
drawing instead, remove that pet's `"import"` line. In the game: see "Looking after pets" above.

What limits how much you can add: not the ROM file (it grows as needed; DS ROMs go up to 512 MB and
emulators load them fine), but the DS's memory while playing: keep pieces Urbz-sized, 16 colours each,
and don't crowd one room with many different imported pieces (each takes a palette row; there are 16).
Formats and findings: `docs\other-games.md`.

## Extra seats in places

Many chairs and sofas in public places are only painted into the background, so nobody can sit on them. A mod's
`seats.json` adds the game's own invisible seats there at build time:
```
{"areas": {"42": [{"object": 134, "x": 388, "y": 306, "facing": 7, "note": "Cafe Z-Bach: the blue sofa"}]}}
```
`object` 134 is the Invisible Park Bench (others: `docs\objects.md`), `x`/`y` are the place's world pixels and
`facing` 1/3/5/7 = up-right, down-right, down-left, up-left. Finding the spot: `python research\areas\area_map.py
<rom> cafe 42 map.png` stitches the whole place into one picture with a coordinate grid, and
`research\areas\seat_probe.py` sends people to your seats and marks where they sit. A bench seats its sitter about
42 px to its side (63 px facing up-right or up-left). Seats the game's walking can't reach are refused: try another
spot. NPC Life ships three, in Café Z-Bach (`mods\npc-life\seats.json`).

## Save files

```
python urbz.py save info "my game.sav"                         clock, money and needs per slot
python urbz.py save set "my game.sav" edited.sav --money 5000 --motive hunger=100 --clock 16:30
```
`info` also lists mod data in each slot and the in-game mod switches.
`set` fixes the checksums, so the game accepts the edited save.

## Checking it all still works

`python tests\proofs.py` builds a set of test mods (`tests\mods\`) and checks each one in the emulator: vanilla
is identical, every hook kind runs, the facts in `docs\systems.md` hold, mods switch on and off, mod data survives
saving, the Mods page works with real taps, NPC Life moves people about, pets live their lives. About an hour and
a half; one emulator at a time. More in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Editing art that grows

Edited chunks are recompressed with an encoder that packs slightly *tighter* than EA's
own (0.987× on average; LZ77 chunks 0.998× Nintendo's), so most edits fit their old slot and
nothing else moves. If an edit doesn't fit:
- **Sprite sheets** (5,000+ assets): the chunks after it move, and the builder re-points the
  sprite layouts that reference them (`project\sprite_refs.json`, read from the game's own
  sprite tables). The build summary says how many layouts it re-pointed. A sheet must stay under 64 KB.
- **Screens:** the tiles live in `unpacked\NNNNN\HHHHHH.tiles.bin`. Edit that file, and the
  builder recompresses it and puts it back into its screen.
- **Anything else** that would move data with no known referencer stops with a
  `BUILD FAILED` message saying how big the edit packs versus its slot.

Got an older project? `python urbz.py extract --upgrade project` adds the tile files, the
LZ77/raw chunks and `sprite_refs.json` in place (about a minute).
After updating the kit, also run `python urbz.py sprites` (refreshes `sprite_refs.json`: all
4,006 sheets can grow) and `python urbz.py text export` (the reference text now shows é, ñ, ...).

## Inside project\

| Path | What it is |
|---|---|
| `base.nds` | The untouched original. Code and header are reused from it, and the banner too, except that a build with mods gets the title "Urbz DX". |
| `assets/NNNNN.bin` | One file per game asset (13,385). Raw bytes: the container for any compressed chunks. |
| `unpacked/NNNNN/HHHHHH.bin` | Every chunk inside asset NNNNN, **decoded and ready to edit** (EA, LZ77 or raw). `HHHHHH` = the chunk's byte offset (hex) inside the asset. 64,378 chunks in total. |
| `unpacked/NNNNN/HHHHHH.tiles.bin` | The tile graphics embedded at the end of a screen chunk, decompressed (623 screens). |
| `sprite_refs.json` | Which sprite layouts point at which chunks (used when chunks grow). |
| `text\strings.tsv` | All 8,311 strings, read-only reference (edit text through a mod). |
| `sound/SoundData.rom` | Sound bank (not unpacked yet). |
| `manifest.json` | Asset order, hashes and chunk table. The builder relies on this, so don't edit it by hand. |

**Golden rule:** asset numbers are IDs the game code uses. Never renumber
or delete files. Add new assets through a mod (see above).

## How rebuilding works

- Untouched chunks reuse the original compressed bytes, which keeps the copy perfect.
- Edited chunks are recompressed with the game's own format:
  - If the result fits the original slot, it is zero-padded into place.
  - Otherwise the asset is repacked and any sprite layouts pointing into it are
    re-pointed (see *Editing art that grows*). If nothing known points at the data
    that would move, the build stops with a clear `BUILD FAILED` message instead of
    producing a broken ROM.
- The ROM grows past 32 MB automatically, and the cartridge size field is updated.

## Formats (reverse-engineered)

**rom.bin archive.** A u32 offset table (13,385 entries + EOF sentinel) followed
by 4-byte-aligned assets.

**Chunk header.** A u32: `flags | (decompressed_size << 8)`.
- `flags` bits 4–6 = codec: 0 raw, 1 BIOS LZ77, 2 Huffman, 3 RLE, 4 custom, **6 EA bitstream** (this ROM uses 0, 1 and 6).
- `flags` bit 7 = 16-bit delta filter afterwards (`x[i] += x[i-1]`).
- So `0x60` = EA compression and `0xE0` = EA compression + delta. Files in
  `unpacked/` are stored **after** the delta step, which is exactly what the game uses.

**EA bitstream codec.** The decoder is at ITCM `0x01FF8C50`; `urbzcomp.py` is a
byte-exact port (verified against 329 in-emulator decompressions).
- 4-byte header: dictionary length, escape prefix, offset bits, prefix bits; then
  up to 32 dictionary bytes.
- 32-bit little-endian words, read MSB-first.
- Literals, gamma-coded LZ matches, short matches, escaped literals, runs; gamma 255 = end.

**Nested streams.** Some decoded chunks end with more compressed data as
`[u16 length][stream]` with no header (a screen's tile graphics), extracted as `.tiles.bin`.

**Other codecs.** Chunks can also be stored raw (flags 0x00) or as Nintendo BIOS LZ77
(flags 0x10; the chunk header doubles as the LZ77 header). See `docs\systems.md`.

**Screen container** (e.g. asset 10747, the EA logo): 256-entry BGR555 palette
→ `u16 w, u16 h` (32×24 tiles) + tilemap → `[u16 len][compressed 4bpp tiles]`.

**Sprites.** Layout assets (start with width,height bytes): `u16 count` at +6,
a `u16` table at +0xC, and each entry has a `u16` byte offset at +4 into its paired
graphics asset. Pairs come from 16-byte sprite records in the game code (see `docs\systems.md`).

## Files

- `urbz.py`: runs every tool (`python urbz.py` lists them); the tools are in `kit\`, each explained in its first lines.
- `*.bat`: Windows shortcuts (`setup`, `extract`, `manager`, `build`, `catalog`, `verify`).
- `code\core\`: the mod core (switches, mod save data, events, the Mods page); `code\include\mod.h`: its API.
  `code\game.sym`, `code\include\game.h`, `code\functions.json`: named game addresses, the C header, and a map
  of the game's functions (used to check hooks).
- `verify\urbz_verify.py`: headless emulator checks (`doctor`, `smoke`, `ram`, `play`, `trace`, `city`, `find`,
  `watch`); `verify\saves\`: test saves; `verify\scripts\`: input scripts (`newgame.json` plays from power-on
  into the city, `loadgame.json` loads save slot 1).
- `tests\`: the proofs; `docs\`: guides and the engine reference ([docs/README.md](README.md));
  `research\`: the probes behind the docs.

## Asset IDs

The game refers to assets by **game ID = file number + 1** (asset `10747.bin` is game ID 10748).
The catalog shows both.
