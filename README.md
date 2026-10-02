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
   for gameplay checks; see `.claude\skills\verify-urbz` for the recipes.
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
- `--mod NAME`: build with only this mod (repeatable), ignoring `mods.json`

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

## Save files

```
python urbz_save.py info "my game.sav"                         clock, money and needs per slot
python urbz_save.py set "my game.sav" edited.sav --money 5000 --motive hunger=100
```
`set` fixes the checksums, so the game accepts the edited save.

## Checking it all still works

`python tests\proofs.py` builds a set of test mods (tests\mods\) and checks each one in the
emulator: vanilla is identical, every hook kind runs, the clock/needs/money/save/people/catalog
facts in `docs\systems.md` hold. About 15 minutes; needs LLVM for the C tests.

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

- `setup.bat`, `extract.bat`, `build.bat`, `verify.bat`: Windows shortcuts
- `urbz_extract.py`: unpack a ROM into a project folder
- `urbz_build.py`: build a ROM from `project\` plus mods
- `urbz_mod.py`: create, edit, inspect and rescue mods
- `urbzcomp.py`: EA codec (decompress/compress) and the delta filter
- `scan_chunks.py`: finds chunks inside an asset
- `verify\urbz_verify.py`: headless emulator checks (`doctor`, `smoke`, `ram`, `play`, `trace`,
  `city`, `find`, `watch`); `verify\saves\city.sav` is a game saved in the city that `city` loads
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
