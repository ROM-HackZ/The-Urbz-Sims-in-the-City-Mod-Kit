# The Urbz DS: engine systems reference

What we know about how the game works, with the evidence for each fact.
Addresses are ARM9 RAM addresses (code loads at 0x02000000; ITCM code at 0x01FF8000).

## Assets

- **Game asset ID = file number + 1.** `assets/10747.bin` is game ID 10748.
- `0x02032CA8` = *get asset by game ID* (r0 = ID). `FUN_02032f74` is a thunk to it.
  Hooking it gives per-scene asset traces (`verify/urbz_verify.py trace`).
- `rom.bin` (FAT file 0) = u32 offset table (13,385 assets + EOF sentinel) + assets, 4-byte aligned.

## Chunks

Header u32 = `flags | size << 8`. Decoded by `FUN_0202d760` / `FUN_0202d83c`:

| flags bits 4–6 | codec | in this ROM |
|---|---|---|
| 0 | stored raw (memcpy) | 241 chunks (mostly 32-byte palettes) |
| 1 | Nintendo BIOS LZ77 (chunk header doubles as LZ77 header) | 1,628 chunks |
| 2 / 3 / 4 | BIOS Huffman / RLE / custom | unused |
| 6 | EA bitstream (ITCM `0x01FF8C50`) | 62,509 chunks |

- Flags bit 7 = 16-bit delta filter after decoding (`FUN_0202d928`, `x[i] += x[i-1]`).
- Assets are usually back-to-back chunks. `scan_chunks.walk_chunks` reads them in order and
  only trusts a walk that covers the whole asset.
- Some decoded chunks end with an **embedded tile stream** `[u16 length][EA stream]`
  (no chunk header). These are screens' 4bpp tiles: 623 of them, always the last block.

## Screens

Decoded chunk layout:
1. a u16 (purpose unknown)
2. 256 BGR555 colours
3. `u16 w, u16 h` (usually 32×24 tiles = 256×192)
4. tilemap: `w*h` u16 entries (tile 10 bits, hflip bit 10, vflip bit 11, palette bits 12–15)
5. `[u16 len][EA-compressed 4bpp tiles]`

Rendering verified pixel-identical to the emulator (EA logo, asset 10747).

## Sprites

- **Sprite definition records** live in the ARM9 binary, 16 bytes each:
  `{u32 gfx game ID, u32 layout game ID, u32 palette game ID or 0, u32 param}`.
  About 9,600 records in about 209 tables, plus some pairs inlined in code.
- **Layout asset** (no chunks; full format in `urbz_composite.py`, decoded from `FUN_020ae17c`,
  `FUN_02001abc`, `FUN_02005534`, `FUN_0206e774`):
  - header: +0,+1 max frame w,h; +6 u16 entry count; **+10 u8 X, +11 u8 Y** (sizes of the
    per-entry extra data); +12 u16 entry-offset table (relative to +12); padded to 4.
  - entry (one per animation frame): +0 u8 cell count (bits 0-4; bits 5-7 flags), +2/+3 w,h
    (cells' bounding box), **+4 u16 chunk offset** into the gfx asset, +6/+8 s16 x,y (bounding-box
    origin), then X*2 + Y*6 bytes of extra data, then one **u32 per cell**: bits 0-8 signed x,
    9-17 signed y, 18-19 OBJ size, 20-21 OBJ shape, 22-31 first tile (32-byte units; always the
    running sum of earlier cells).
  - The frame's chunk is each cell's 4bpp tiles back to back (row-major within a cell, 1D
    mapping). At load the game re-spaces cells to 64-byte boundaries in VRAM. Flip and palette
    come from the sprite, not the cell.
  - Checked over all 5,331 pairs (146,503 cells): 100% legal shapes and tile counts; in the city
    the decoded OAM matched the hardware 15/15 draws and the rendered player 678/680 pixels.
- **Gfx asset** = back-to-back chunks, one per frame. Simple frames (one cell) are w x h tiles
  row-major; composite frames (up to 5 cells, e.g. the player's body parts) need the layout.
  `urbz_png.py` exports both as the assembled picture and cuts edits back into cells.
- `FUN_020ae0c8({gfx, layout}, slot, ...)` decodes frames into sub-screen OBJ VRAM
  (`0x06400000`).
- Because offsets are u16, a sprite gfx asset must stay under 64 KB. The largest is 51,572 B.
- `project/sprite_refs.json` lists, per gfx asset, the layouts that point into it.
  - Built by `urbz_sprites.py`: pairs scanned from the ARM9 and kept only if every layout
    offset is a real chunk start.
  - It covers **all 4,006** multi-chunk assets; the builder uses it to re-point layouts when chunks
    grow. Four sheets whose ids the game computes (07279, 09195, 09197, 10368) are paired with the
    layout right after them, whose offsets match their chunks exactly. Pairs whose frames need more
    tiles than the chunk holds are dropped (136 coincidental offset-0 pairings).
  - Verified at runtime: every non-zero-offset chunk the game decoded in the intro and city
    start (424) has a known referencer.

## Text

- **Text bank = asset 00054** (game ID 55, 340 KB, loaded at boot and kept at RAM `0x0236CFC0`).
  - u32 at +0 = offset of the string table.
  - u16 Huffman tree at +4. Node 0x100 is the root; node n's children are at entries
    2(n−0x100) and 2(n−0x100)+1 (bit 0 → first). Values < 0x100 are bytes; 0 ends a string.
  - String table: one u32 byte offset per string (8,311). Each string starts on a byte
    boundary, and bits are read least-significant first.
  - Bytes 0xF0–0xFF act as lead bytes of 2-byte codes (unused in the US text).
- Decoder: ITCM `0x01FF85C4(id, buf, maxlen)`, called from `0x020A6D40` with a 1,024-byte
  buffer. Decoded strings sit in plain ASCII just before the bank in RAM.
- Codes: `@1`–`@3` = names (`@1` = the player's name); `@hh @mm @ss @am @DD` = clock/date;
  `\xB8` = ™; `\n` = line break. The game word-wraps to the text box.
- String IDs seen so far:
  - 27 = title "Spin the record…"
  - 22 / 25 / 26 = legal lines
  - 526 = "Kris Thistle"
  - 5870 / 5871 / 5873 = Kris's first lines
- Accented letters: the fonts have Western-European letters at 0x7B-0xB8 (© œ ¡ ¿ À Á ... ñ ... ü
  º ª … ™); `urbz_text.py` maps them to/from real characters (é = 0xA3, ñ = 0xAA, ü = 0xB4).

## Fonts

- 8 fonts, each a raw asset (no chunks), loaded at boot by `FUN_02034924` → `FUN_02033a48(slot)`
  from the table at 0x020C5CEC (8 x {u32 game id, u32 colour base}). Resident descriptors at
  0x02140D60 + slot*0x28.

  | slot | asset | height | codes | colour base |
  |---|---|---|---|---|
  | 0 | 11547 | 9 | 0x20-0xB9 | 8 |
  | 1 | 11546 (with shadow) | 9 | 0x20-0xB9 | 8 |
  | 2 | 11549 | 10 | 0x20-0xB9 | 16 |
  | 3 | 11548 | 10 | 0x20-0xB9 | 16 |
  | 4 | 11550 | 16 | 0x20-0xB9 | 16 |
  | 5 | 11552 | 20 | 0x20-0xB9 | 16 |
  | 6 | 11551 | 22 | 0x20-0xB9 | 16 |
  | 7 | 11555 | 16 | 0x20-0xBA | 16 |

- File: u16 first, u16 last, u8 height; big-endian u16 table offsets at bytes 6-7, 10-11, 14-15
  (glyph offset table, width table, bitmap). Glyphs are 4bpp, **column-major**, low nibble first,
  byte-aligned. Pixel 0 = transparent, v = colour base + v. Advance = glyph width (spacing is in
  the glyph). Codes outside first..last draw glyph 1. Draw `FUN_02033bc8`, width `FUN_020336fc`,
  measure `FUN_0203458c`.
- 0xBA-0xEF are free for new glyphs (0x40 '@' and 0xF0+ are reserved); the loader derives every
  pointer from the header, so fonts can grow. `urbz_font.py` exports/imports PNG sheets
  (width = red bar under each glyph). Proven: an 'o' changed to a box showed in the Catalog menu.

## Palettes at runtime

- **BG:** a screen's 256 colours load as-is, except **row 0**, which the game fills with the
  text layer's colours (backdrop, yellow, black, white). Spare rows (unused by the map,
  filled with `0x83FF`) can take new colours. Colour 0 of every row is transparent.
- **OBJ (sprites):** palette RAM is only written through RAM shadows: table 0x02122FFC +
  engine*0x10 = {BG shadow, BG RAM, OBJ shadow, OBJ RAM}; `FUN_0201f750` copies into the shadow
  then to 0x05000200/0x05000600 (CPU copy, no DMA). Loaders: `FUN_02020100(asset, offset, index, n)`
  now, `FUN_0202005c` queued (flushed by `FUN_0201fbe0`).
- Where sprite colours come from (all proven with recolour mods):
  1. a sprite record's palette field (non-zero) → that asset, into the entity's row (+0x90 bits 12-15);
  2. **people**: table **0x020D0054** = palette game id per character id (Kris 45 → file 09160),
     put in a free row by `FUN_0206d73c`;
  3. **the player**: built from **11543** (skin tones, hair colours, shoes) and **11542** (32
     clothing colours) by `FUN_02083538` (docs/player-look.md);
  4. **street objects**: rows 2-8 at area start from table 0x020C82C4 = files 00000, 00001, 00002,
     00004, 00005, 00006, 00007 (e.g. puddles use row 3 = 00001);
  5. bottom-screen HUD: 10361 (rows 0-7), 10357/10354 (rows 14/15).
- `urbz_palette.py` edits any palette file as a swatch PNG (`list`, `who <person>`, `edit`).
  `urbz_verify.py trace` still captures the colours actually on screen (verify/palettes/).
- LZ77 chunks (1,628, all 32-192 bytes) are embedded palettes in sprite sheets. Proven: the game's
  own decoder (`decode_chunk` 0x0202D83C) decodes our re-packed, grown LZ77 chunk byte for byte.

## New game flow (scripted in the emulator)

- Create-a-Bod → clothes → rep quiz: the check mark is at touch (233,165).
- "Are you sure you want this Urb?" defaults to NO: press LEFT, then A.
- Intro cutscene: START skips it.
- In the city, **Kris Thistle** walks up straight away (tutorial). Close her dialogue with A
  (shows replies), tap the first reply (120,64), then A twice; then A three times for the
  goal pop-ups. `verify/scripts/newgame.json` does all of this and ends in a running city.
- HUD: clock, with money under it; 8 motive bars along the bottom of the top screen.
- `verify/states/world-start.dst`: in the city at 10:03 am, §0
  (vanilla ROM, clock pinned to 2026-01-05 12:00).
- Title menu: Create-an-Urb / Load-an-Urb / Settings / Minigames; DOWN moves (the first press
  after a pause is ignored, so press twice for Load-an-Urb).
- City bottom bar: globe/map (19,163 - the hit box is centred there, (18,180) misses), Urb Info
  (80,180), Options (128,180: Settings / Save Game (203,52) / Quit), Goals (193,180), pocket
  (238,180). Save Game: confirm with the check at (220,117).
- A new game starts on **area 70, "5: Roof" of King Tower** (not a street). The Squeegee job sign
  is up-left of the start; the roof elevator leads to the tower floors (docs/areas.md).

## Game code and adding our own (Phase 4)

- **arm9** is uncompressed: load 0x02000000, entry 0x02000800, 0x123678 bytes, no overlays.
  NitroSDK module params at 0x02000ADC. Autoload blocks: ITCM 0x01FF8000 (0x1A00 bytes),
  DTCM 0x027C0000 (0x1A0 bytes). Main BSS 0x02121AC0..0x0214DE20.
- Start-up (0x0200097C) copies each autoload block, clears that block's own BSS, then clears the
  main BSS. `urbz_code.py` adds one more autoload block at **0x0214DE20** (just past BSS) holding
  every code mod, and moves the heap start (the literal at **0x020B7D88** returned by
  `OS_GetInitArenaLo`) past it. Proven: a 25 KB region with two mods boots, runs and smoke-tests
  identical to the original.
- When arm9 grows past 0x127800 in the ROM, arm7 + file-name table + FAT + banner move to the end
  of the cartridge (header fields 0x30/0x40/0x48/0x68/0x80 updated).
- Hooks (`hooks.txt`): `call` rewrites a BL, `jump` replaces a function, `wrap` runs our code
  before one moved ARM instruction (flags and r0-r3 preserved), `data`/`u8`/`u16`/`u32` write bytes.
  About 96% of the game is ARM code; `code/functions.json` (Ghidra export) gives each function's
  range and mode, and the builder checks the instruction it replaces.
- **Savestates contain the game code.** Test code mods from a cold boot (`urbz_verify.py city`).

## Heap

- One NNS "expanded heap" ('EXPH') from the arena: handle pointer at 0x02142004, start 0x0214DE20,
  end 0x023C0000. Free list head at handle+0x24, used list at handle+0x2C; blocks have a 16-byte
  header ('FR'/'UD', size at +4, next at +0xC).
- Measured with `play --heap 30`: new game to the city: lowest free **1,403 KB**, largest free
  block 1,367 KB, most used 1,096 KB. Code mods up to 128 KB build without a warning.

## Clock

- `game_time` = **0x0214112C**: `{s16 day, s8 hour, s8 minute, s8 second, s8 tick(0-29)}`.
- `time_add` (0x0201D994) adds a delta and normalises; returns bits 2 = minute, 4 = hour, 8 = day.
- `world_tick` (0x02084104) runs 30 times a second while the city runs and calls
  `time_update` (0x02083DB0) with `time_speed_table[time_speed_index]`
  (table 0x02113B5C, index u8 at 0x021473F8). Entry 0 = +3 s per tick (a game minute = 20 ticks,
  a day = 16 real minutes); entry 1 = +60 s (sleeping fast-forward). `time_update` also fires the
  hourly/daily events (bills, shops...).
- Proven: the `clock-speed` mod (data patch of entry 0 to 1 s + 15/30) halves the clock rate.
- Dialogs and pop-ups pause the world tick (the clock stops).

## Needs (motives)

- Player needs: **s32[8] at 0x02141204**, 8.24 fixed point (0..100.0). Order: hunger, hygiene,
  energy, social, comfort, bladder, fun, room (the HUD order).
- `motive_decay` (0x0205E27C) runs every tick; each need changes by `motive_rate` (0x0205DD70):
  table 0x020CEDA8 (normal; hunger -0.0046/tick = -5.6 per game hour) or 0x020CEDC8 (about 6x
  faster, when the sim's +8 field is set), with modifiers.
  - Skipped entirely while sim flag bit 2 is set (u16 at 0x02141C30: set in the tutorial, which is
    why needs don't drop at the start of a new game).
  - Only Fun decays unless `game_phase` (u8 0x02141C25) == 3.
- Decay is per *tick*, not per game minute, so a slower clock means needs drop faster per game hour.
- Gains from objects/actions: `motive_apply_effect` (0x0205DC20) adds row N of table 0x020CEED4
  (s32[8] per tick) scaled by 0x020EA998[quality] (1.0, 1.0, 1.2, 1.4, 1.6, 2.0).
- Starting needs: table 0x020CEDE8 (55, 55, 60, 75, 65, 65, 65, 85).
- HUD bars: `FUN_02039cb4` reads each need via `motive_get` and draws value*16/100 pixels.
- Proven: patching the hunger rate to half made hunger drop exactly half as fast.

## Money

- **s32 at 0x02141124** (game_state+4); saved as 24 bits. The HUD redraws it on its own refresh.
- Object upgrades: table 0x020C25BC, [category][4 levels] x 12 bytes (s16 price first);
  `buy_upgrade` (0x02018DAC) pays the price and refunds half the old level's.

## Save file

- 8 KB EEPROM. 0x0000: 0x20-byte header ("URBZ0010"), u16 at 0x1E makes the u16 sum 0.
  Slots at 0x0020 and 0x1000, 0xFE0 bytes each; the u16 at slot+0xFDE makes the slot's u16 sum 0.
- A slot is a bit/nibble/byte stream (`save_write_*`, context 0x021470FC). Early in the game it
  uses **2,569 of 4,064 bytes (63%)**, so about 1.4 KB per slot is free.
- Known slot fields: +0x05 clock, +0x0B money (24-bit), +0x8F needs (u16[8], whole numbers).
- `urbz_save.py info/set/fix`. Proven: a save edited to §4,321 and 10% hunger loads with both.
- Load from power-on: `verify/scripts/loadgame.json` with `--sav file.sav`.

## People (NPCs)

- **Character ids** in code are 31 + c, where c = 0..35 is the person in name order:
  name string 512 + c, bio string 471 + c (31 Bayou Boo, 45 Kris Thistle, 66 Sharona Faster).
  `talk_partner` (0x021474F8) holds the id of whoever you're chatting with (name = 481 + id).
- Relationships: 36 x 4 bytes at 0x02141154 (byte 0 = s8 relationship, -128 = never met; byte 1 =
  a timer that drops every 6 hours). Daily drift toward 0 happens in `FUN_0207acc8`.
- **Schedules:** `npc_schedule_table` (0x020E4FD8) holds a pointer per person (id - 31, 49 entries
  for ids 31..79) to `u8[24 hours][7 weekdays]` of area ids (weekday = day % 7; area 82 = out of
  town). `schedule_lookup(id, time)` (0x02065890) reads it. Kris: area 66 at night, 64 early
  morning, 65/63/70 by day, a different Saturday.
- **Relocation (the hook for NPC Life):** every 150 ticks (5 real seconds) `npc_relocate_tick`
  (0x02066110, from the world tick) asks `schedule_lookup` for every person 31..80: people whose
  schedule says the current area walk in from an entry point (`FUN_020657ac` picks it,
  `FUN_020656a4` spawns), people present whose schedule says elsewhere walk out (`FUN_020655c0`).
  The call at **0x0206665C** is where our code answers instead. Proven: `npc-visit` hooks it and
  Bayou Boo walks onto the roof at 10:40 (from a loaded save, schedules active).
- Byte 0x02142234 = 0 at the very start of a new game makes everyone always present (schedules
  off); a loaded save has it at 1.
- `npc_present(id, area, time)` (0x02065AD0) decides if a person appears:
  1. if the byte at 0x02142234 is 0, always yes;
  2. hard-coded quest overrides (by quest flags);
  3. no, if the id is in the 10-entry busy list at 0x02142270;
  4. the date partner (game_state+0xAEE) follows separate rules;
  5. otherwise the schedule table (no table = always yes).
- **Spawning:** an area's placement records (`{u16 7, u16, s16 x, s16 y, u8 id, u8 facing}`) are
  read on area load; `spawn_from_record` (0x02064ED8) asks `npc_present` and calls
  `spawn_npc(id, facing, x<<16, y<<16)` (0x0206499C). Area 70 (King Tower roof) has one record:
  Kris at (146, 255). Placement records only matter at area load; relocation (above) brings people
  in through entry points without one. Calling `spawn_npc` directly also works, but the game then
  walks the person out again at the next relocation if their schedule says elsewhere.
- Areas: 80 areas (ids 0-79), names = string 975 + id, data/graphics tables, door/elevator records,
  per-area people and heap: **docs/areas.md**.

## Entities and actions

- Entities (people, objects, the player) come from a pool of 0x148-byte structs at 0x0215E344
  (about 127), linked in an active list. Fields: +0x08 type (0 player, 7 person), +0x0A/+0x146
  character id, +0x0C flags, +0x18/+0x1C x/y (16.16), +0x4C behaviour function, +0x104 state,
  +0x105 action, +0xC7 animation.
- `entity_set_state` 0x02000E20, `entity_set_action` 0x02000E54, `entity_play_anim` 0x02000F34
  (people route to 0x020647E0, the player to 0x02037908). People can play animations through the
  same call, which Phase 6 (visible actions) will use.
- **Action effects:** while an action runs, its code calls `motive_apply_effect(needs, row, quality)`
  every tick. 70 rows at 0x020CEED4 (s32[8] per row, per tick). Examples: 12-20 eating (hunger),
  8-11 sleeping (energy), 44/62 showers (hygiene), 45-49 sitting (comfort), 59 toilet (bladder),
  64 bladder accident, 65 passing out, 39/41 Room drifting toward the area's score.
  `docs/effect_rows.md` lists every row and the code that uses it; **docs/objects.md** lists every
  object (catalog and placed), its actions, rows and how long each runs (from the code; the
  mechanism is proven in-game with the accident row).
- When a need hits 0, `motive_failure` (0x0205DEB8) starts its failure action (per-need
  animation table 0x18 bytes each).
- Proven: patching row 64's bladder gain from +2.0 to +1.0 made the accident refill bladder to
  49.6 instead of 99.6.

## Buyable objects (catalog)

- Two parallel tables indexed by object number, 0x14 bytes per row:
  `object_text_table` 0x020E6D48 `{u32 model, u32 description string, u32 name string,
  u32 catalog page, u32 ?}` and `object_info_table` 0x020E8B70 `{u32 price, u32 flags, ...}`.
- Catalog pages: 0 Appliances ... 5 Utilities, 7 = not sold (model 632).
- Proven: object 200 "The Savvy Shower" repriced from $230 to $99 shows in the Catalog.
- Clothes are not separate art: Create-a-Bod's "Threads" page is palette choices. The look is
  10 bytes at **0x02141144** (gender, skin, hair style, hair colour, shirt style, 4 clothing colours,
  shoes); only gender and hair style pick sprite art. Tables and save fields: **docs/player-look.md**.

## Jobs and money

- `add_stat(kind, delta)` (0x02035350): kind 2 = money (capped at 999,999, refreshes the HUD);
  kinds 0/1 = u16 counters at 0x02141B88 / 0x02141B86.
- When a shift ends, the results code calls `add_stat(2, earned)` at **0x020516AC**, where earned
  = s16 at +4 of the job session (`*0x021420D0`). Proven by setting earned to 50: money +50.

## Game state

- One big struct of globals at **0x02141120** (324 code references): +0 0x55AA55AA marker,
  +4 money, +0xC clock, +0xE4 needs, +0xB05 game phase, +0xB10 per-sim flags.

## Open questions

- Which pixels each clothing palette slot covers (read from screenshots, not traced).
- Where a street object gets its palette row number (entity+0x90 is set somewhere per object).
- Record types 29 and 30 in area data (29 sits next to doors: probably exit points for people).
- Groups 2+ of area records are switched on by scripts (`FUN_02012690`): which quests.
- The tower's street doors appear only after the first goal; reaching the streets in a scripted
  run needs that goal (or the area-load poke in docs/areas.md, for experiments).
- Hardware: DeSmuME doesn't check the secure-area CRC (header 0x6C) or emulate caches; code mods
  change the module params inside the secure area, so a flashcart test is still to do.
