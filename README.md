# The Urbz: Sims in the City (DS) - mod kit and reverse engineering

Tools to unpack *The Urbz: Sims in the City* (DS, USA) into editable files, change its
text, art, fonts, colours and code, and rebuild a playable ROM. An unedited project
rebuilds a **byte-identical** copy of the original (SHA1 `3c01cc5cf3491b5d0ab626ccfb5bcad370662f2f`).
The goal is a "dream version" of the game, starting with a living city where people have
needs, jobs and money: see **PLAN.md** for the roadmap and status, **docs/systems.md** for
how the engine works.

**No game data is in this repository.** You need your own dump of the USA ROM; `project\`
(the unpacked game), `build\` and emulator states are created locally and ignored by git.

## Quick start (Linux / cloud)

```
pip install -r requirements.txt          # ndspy, Pillow, py-desmume, capstone
python3 urbz_extract.py "Urbz.nds" project
python3 urbz_build.py --vanilla          # -> [IDENTICAL to original]
python3 tests/proofs.py vanilla clock-speed   # emulator checks (headless)
```
For C code mods install LLVM (clang, ld.lld, llvm-objcopy/nm/readelf), e.g. `apt install clang lld llvm`.

## Quick start (Windows)

1. `setup.bat`: installs ndspy, Pillow and py-desmume (needs Python 3.9+).
2. `extract.bat "path\to\Urbz.nds"`: creates `project\`. Skip this if it already exists.
3. `build.bat --vanilla`: should print `[IDENTICAL to original]`.
4. Make a mod:
   ```
   python urbz_mod.py new my-mod "what it does"
   python urbz_mod.py edit my-mod 10747        (copies asset 10747's files into the mod)
   ...edit the files under mods\my-mod\ ...
   ```
5. `build.bat`: builds `build\Urbz Mod.nds` with your enabled mods. If you put your
   emulator's .exe path in `emulator.txt`, it opens the ROM for you.
6. `verify.bat`: plays the first screens of your build and the original side by side
   (headless) and saves a comparison image under `verify\evidence\`.
   `python verify\urbz_verify.py city` gets your build into the city (from `verify\saves\city.sav`)
   for gameplay checks; see `.claude\skills\verify-urbz` for the recipes. `--from lobby` starts
   from `verify\saves\lobby.sav` instead (first goal done, Tower Lobby), and `--goto 4` loads an
   area by id first (4 = Glasstown street; ids in `docs\areas.md`).
7. `catalog.bat`: builds `catalog\index.html`, a searchable gallery of every asset with
   its type (screen, sprite sheet, palette...), a preview, and the scenes where the game
   loaded it. Rerun it after new traces to get more labels.

Extract takes about 40 s. A build takes a few seconds, plus recompression time for whatever you edited.

## Kit layout

| Path | What it is |
|---|---|
| `project\` | The unpacked original game. **Keep it pristine**; it's the reference. |
| `mods\<name>\` | Your mods. Each holds **only** the files it changes or adds, at the same paths as in `project\`. |
| `mods.json` | Which mods are enabled, in order. Later mods win if two change the same file. |
| `build\` | Built ROMs. |
| `verify\` | Headless emulator tests (`urbz_verify.py`), saved evidence, scene traces and savestates. |
| `catalog\` | Generated asset gallery (`catalog.bat`). Safe to delete and regenerate. |
| `.claude\skills\verify-urbz\` | Verification recipes Claude follows (also readable by you). |

### Mod commands (`python urbz_mod.py ...`)

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

### Build options (`python urbz_build.py ...`)

- `[out.nds]`: output path (default `build\Urbz Mod.nds`)
- `--vanilla`: ignore mods (proves the baseline is identical)
- `--mod NAME`: build with only this mod (repeatable; a name in `mods\` or a folder path), ignoring `mods.json`

## Editing text

Every line in the game (8,311 strings: dialogue, menus, item and place names) is
in one compressed text bank. You edit it as plain text:

```
python urbz_text.py find "sitting around"        search (prints string IDs)
python urbz_text.py edit my-mod 5870 5873        copy lines into mods\my-mod\text\strings.tsv
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
python urbz_png.py edit my-mod 10747             screens / sprite frames -> mods\my-mod\png\10747\*.png
```
Paint on the PNGs, save, and build.
- **Screens:** you can use any colours. Edited tiles that need new colours get them
  in a spare palette row (when the screen has one; otherwise the build warns and uses
  the nearest colours). Tiles are re-cut automatically.
- **Sprites** use a 16-colour palette: paint with the colours already in the exported PNG
  (the build warns if you used others). To change the colours themselves, edit the palette
  (next section). Sprites show real colours once `urbz_verify.py trace` has seen them in a
  scene (`verify\palettes\`), else greyscale.
- **Composite sprites** (characters made of several pieces, like the player's body parts)
  export as the finished picture; your edit is cut back into the pieces on build.
- An unchanged PNG changes nothing (the build stays identical).

## Recolouring (palettes)

Most sprites get their colours from separate palette files. Edit the file and everything
drawn with it changes colour:
```
python urbz_palette.py list                      known palette files and what uses them
python urbz_palette.py who kris                  a person's palette (Kris Thistle: 09160)
python urbz_palette.py edit my-mod 9160          -> mods\my-mod\palette\09160.png (16x16 swatches)
```
Repaint swatches and build. The player's skin, hair and shoe colours are in 11543, the 32
clothing colours in 11542 (`docs\player-look.md`).

## Fonts

The game has 8 fonts (different sizes). Edit them as PNG sheets:
```
python urbz_font.py edit my-mod          -> mods\my-mod\font\fontN_NNNNN.png + .json (all 8)
python urbz_font.py edit my-mod 0 2      just fonts 0 and 2
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
The included **`clock-speed`** mod is this kind: it makes in-game days last twice as long.
Turn it on with `python urbz_mod.py enable clock-speed`, then edit the two numbers in its
`hooks.txt` to pick another speed (the table in that file shows the options).

**C code.** `python urbz_patch.py new my-mod` adds `code\main.c` and `code\hooks.txt`. Write C
using `code\include\game.h` (the clock, needs, money, people...), say where it runs in `hooks.txt`:
```
wrap world_tick on_tick            # run on_tick 30 times a second, then carry on
call time_update_call my_time_add  # make one existing call go to my function
jump motive_get my_motive_get      # replace a whole game function
```
then `python urbz_patch.py build my-mod` and build as usual. Compiling needs LLVM
(`winget install LLVM`); building the ROM doesn't, because each mod keeps its compiled
`code\build\patch.bin`. The included **`npc-visit`** mod is a small example: it answers the
game's "where should this person be?" question so that Bayou Boo walks onto the King Tower roof
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
  "save_bytes": 64 }     most save space it uses per slot
```
A C mod can also use **events** (no hooks.txt line needed, just define the function; see
`code\include\mod.h`): `mod_on_tick`, `mod_on_minute(n)`, `mod_on_area_enter(area)`,
`mod_on_save(buf, max)` / `mod_on_load(buf, len)` (its own data in each save slot, kept even while
the mod is switched off), `mod_on_enable` / `mod_on_disable`, and `mod_on_page` (an info page,
opened from the Mods page). `u32 ADDR @name` in hooks.txt writes the address of something in the
mod (e.g. to point a game table at your own).

## Mod manager (window)

`manager.bat` (or `python mod_manager.py`) shows every mod with a tick box, its version and
description. Tick the ones you want, change their order, then **Build**, **Play** (opens the
ROM in the emulator named in `emulator.txt`) or **Build & Play**. **Add mod...** installs a
mod from a zip file (it refuses zips with ROMs, saves or programs in them).

## NPC Life

**`mods\npc-life`** makes the city live: the 36 townspeople have needs, jobs, money and rent and
keep to the places the original game puts them, visiting cafés, clubs and parks in their free
hours, saved with your game. In your area they act it out: they sit down at tables, use the
toilet, and walk up to each other to chat. Switch it in the game (Options > Mods), see what
people are doing on its info page, and tune it with two JSON files: see `mods\npc-life\README.md`.

**`mods\npc-body-proto`** (a prototype, off by default) draws Kris Thistle with the player's body
and animations in her own colours. Switch it on in Options > Mods and find Kris on the King Tower
roof between 4 and 7 pm.

## New animations for the townspeople (drawn by you)

Only 8 townspeople have the game's sit/toilet/shower/sleep animations (and only Kris can eat).
`urbz_anims.py` lets you draw the missing ones for anyone, in their own look:
```
python urbz_anims.py list                         who has which animation
python urbz_anims.py template my-anims hattie sit # Gramma Hattie: frames to draw + a guide
```
Then draw `mods\my-anims\people\43-gramma\sit_6b\front\NN.png` and `...\back\NN.png`: each starts
as her own standing frame, and `guide\sit_6b\...` shows the same frame on Kris (pose and timing to
copy). Every PNG is 96x96 with the feet on pixel (40, 72); use her own colours. Then:
```
python urbz_anims.py build my-anims               new sprite sheets + the game data
python urbz_patch.py build my-anims               (needs LLVM)
```
and build the ROM with `my-anims` enabled. NPC Life then sends her to chairs like the others. Groups:
sit, eat, toilet, shower, sleep. The frames come from the game's art, so keep your mod to yourself.

## New objects and pets (Phase 8, early)

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
the new rows by itself. `python urbz_objects.py show 225` prints an object's row.
New numbers: 386 and 389-511. A new object can have its own art: `"art": "art/<folder>"` (your drawings,
"Drawing furniture" below) or `"import": {...}` (a model from another Sims DS game, "Importing from other Sims
games" below). Without either it wears the copied object's art.

Two mods use this, each picked on its own in the mod manager (no in-game switch):
- **`mods\pets`** adds pets from `pets.json` (a Puppy and a Kitten): buy them where chickens are sold,
  place them at home and they run around; pick them up and they go back to Pockets. Their art: see
  "Drawing a pet" below. Numbers 386 and 389-429.
- **`mods\more-furniture`** adds three pieces of furniture to the Catalog and the furniture shop
  (copies of a chair, a bed and a recliner with new names and prices, until new art exists).
  Numbers 430-511.

## Drawing a pet

Pets live in `mods\pets\pets.json` (Puppy and Kitten so far; add more the same way). Each starts from
an animal of the game (`"from"`: chicken, rooster or nutria): it moves like that animal and wears its art
until you draw your own:
```
python urbz_art.py template pets puppy      mods\pets\art\puppy\: the rooster's frames to draw over
python urbz_art.py preview pets puppy       art\puppy\preview.png: every frame, big, off-colour pixels pink
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
python urbz_art.py object-template mods\more-furniture\art\armchair 136    start from object 136's art
```
The folder holds `view-away.png` (the piece facing up-right; the game shows it for 3 of its turns),
`view-toward.png` (facing down-left), extra state frames `view-away-1.png ...` (e.g. a slept-in bed; missing
ones repeat the first), `palette.png` (its own 16 colours: unlike the game's furniture it isn't recoloured by
the catalog colours) and `icon.png` (32x32, for Pockets and the Catalog) with `icon-palette.png`. Canvas
128x128; the west corner of the piece's floor tile is pixel (24, 100). Point an object at it with
`"art": "art/armchair"` in `objects.json`.

## Importing from other Sims games

You can bring pets and furniture over from The Sims 2: Apartment Pets, The Sims 2: Castaway, The Sims 3 and
The Sims 2 (DS). Their worlds are 3D; the kit renders each model the way The Urbz draws (from above at its
angle, its size, 16 colours) every time you build. Your copies of those games stay on your computer:
1. Create `sources.json` next to `urbz_build.py` (it is never committed):
   `{"aptpets": "D:\\ROMS\\Apartment Pets.nds", "castaway": "...", "sims3": "...", "sims2": "..."}`
   (a `.zip` holding the `.nds` works too; it is unpacked once into `build\sources`)
2. `python urbz_import.py gallery` renders every model into `catalog\imports\index.html`: pick from there.
   `python urbz_import.py show aptpets dog` shows one model in 5 turns and walking.
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

`mods\pets` already imports the Apartment Pets beagle (Puppy) and black cat (Kitten). To use your own
drawing instead, remove that pet's `"import"` line. In the game: buy, Pockets, place at home, turn, pick up,
all as usual; tested in DeSmuME and melonDS.

What limits how much you can add: not the ROM file (it grows as needed; DS ROMs go up to 512 MB and
emulators load them fine), but the DS's memory while playing: keep pieces Urbz-sized, 16 colours each,
and don't crowd one room with many different imported pieces (each takes a palette row; there are 16).
Formats and findings: `docs\other-games.md`.

## Save files

```
python urbz_save.py info "my game.sav"                         clock, money and needs per slot
python urbz_save.py set "my game.sav" edited.sav --money 5000 --motive hunger=100 --clock 16:30
```
`info` also lists mod data in each slot and the in-game mod switches.
`set` fixes the checksums, so the game accepts the edited save.

## Checking it all still works

`python tests\proofs.py` builds a set of test mods (tests\mods\) and checks each one in the
emulator: vanilla is identical, every hook kind runs, the clock/needs/money/save/people/catalog
facts in `docs\systems.md` hold, mods switch on and off, mod data survives saving, the Mods page
works with real taps, NPC Life moves people and they sit, chat and use objects. About an hour (run one at a time); needs LLVM for
the C tests. Also `python tests\test_code_encodings.py`, `python tests\test_mod_manager.py` and
`python mods\npc-life\sim\run_test.py` (no emulator).

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

Got an older project? `python urbz_extract.py --upgrade project` adds the tile files, the
LZ77/raw chunks and `sprite_refs.json` in place (about a minute).
After updating the kit, also run `python urbz_sprites.py` (refreshes `sprite_refs.json`: all
4,006 sheets can grow) and `python urbz_text.py export` (the reference text now shows é, ñ, ...).

## Inside project\

| Path | What it is |
|---|---|
| `base.nds` | The untouched original. Code, header and banner are reused from it. |
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

- `setup.bat`, `extract.bat`, `build.bat`, `verify.bat`, `manager.bat`: Windows shortcuts
- `mod_manager.py`: the mod manager window
- `code\core\`: the mod core (switches, mod save data, events, the Mods page); `code\include\mod.h`: its API
- `urbz_extract.py`: unpack a ROM into a project folder
- `urbz_build.py`: build a ROM from `project\` plus mods
- `urbz_mod.py`: create, edit, inspect and rescue mods
- `urbzcomp.py`: EA codec (decompress/compress) and the delta filter
- `scan_chunks.py`: finds chunks inside an asset
- `verify\urbz_verify.py`: headless emulator checks (`doctor`, `smoke`, `ram`, `play`, `trace`,
  `city`, `find`, `watch`); `verify\saves\city.sav` is a game saved in the city that `city` loads,
  `verify\saves\lobby.sav` one saved after the first goal (made by `verify\scripts\first-goal.json`)
- `urbz_patch.py`: compile a code mod; `urbz_code.py`: puts code mods into the ROM (used by the build)
- `urbz_save.py`: read and edit save files
- `urbz_font.py`: fonts as PNG sheets; `urbz_palette.py`: palettes as swatch PNGs;
  `urbz_composite.py`: the composite sprite format
- `tests\proofs.py`, `tests\test_code_encodings.py`, `tests\mods\`: regression proofs
- `docs\`: `systems.md` (engine reference), `areas.md`, `player-look.md`, `objects.md`,
  `effect_rows.md`, `data\areas.json`; `research\`: the scripts behind them
- `PLAN.md`: the roadmap, status and decisions
- `code\game.sym`, `code\include\game.h`, `code\functions.json`: named game addresses, the C header,
  and a map of the game's functions (used to check hooks)
- `urbz_catalog.py`, `urbz_classify.py`, `urbz_gfx.py`: asset catalog, type detection, screen/tile/palette renderers
- `urbz_sprites.py`: builds `sprite_refs.json` from the game's sprite tables
- `urbz_text.py`: find, view and edit the game's text
- `urbz_png.py`: export screens and sprite frames as PNG, and import edits
- `verify\scripts\newgame.json`: plays a new game from power-on through Kris Thistle's tutorial
  chat into the city; `verify\scripts\loadgame.json`: loads save slot 1 from power-on
- `docs\systems.md`: what we know about the engine, with evidence
- `requirements.txt`: Python packages

## Asset IDs

The game refers to assets by **game ID = file number + 1** (asset `10747.bin` is game ID 10748).
The catalog shows both.
