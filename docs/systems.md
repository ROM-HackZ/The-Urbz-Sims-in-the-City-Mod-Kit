# The Urbz DS: engine systems reference

What we know about how the game works, with the evidence for each fact.
Addresses are ARM9 RAM addresses (code loads at 0x02000000; ITCM code at 0x01FF8000).

## Assets

- **Game asset ID = file number + 1.** `assets/10747.bin` is game ID 10748.
- `0x02032CA8` = *get asset by game ID* (r0 = ID). `FUN_02032f74` is a thunk to it.
  Hooking it gives per-scene asset traces (`verify/urbz_verify.py trace`).
- `rom.bin` (FAT file 0) = u32 offset table (13,385 assets + EOF sentinel) + assets, 4-byte aligned.
- **The asset manager only fits the original assets** (proven, Phase 7): `asset_load` (0x02032B08) refuses
  game IDs >= 0x344A (13,386), and its 3 tables are sized for exactly 13,386 entries: `asset_offsets`
  0x0212352C (rom.bin's index, read at boot: 0xD128 bytes, literal 0x02032B04), `asset_ptrs` 0x02130654
  (where each loaded asset is) and `asset_refs` 0x0213D77C (a use count byte each). Code: 0x02032A60-
  0x020331F4 (5 count literals, 13 table addresses). When mods add assets, `urbz_build.py` adds a generated
  hidden code mod (`build/new-assets/`) that moves the 3 tables into the code region, sized for the build
  (9 bytes per asset of heap), and patches those literals in the ROM. Proven: proof `npc-anims` (the game
  loads a new asset; it plays in DeSmuME and the build runs in melonDS). Before this, added assets were
  silently never loaded.
- Frame scripts (an animation's frame order and timing) are assets too: pairs `{u8 frame, u8 ticks}`, then
  0xFF (hold the last frame) or 0xFD (loop). An animation row's script 0 = the default.

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
- The entity pool (people, objects) is on the heap, so it **moves up by the size of the code region** when
  code mods are built in (0x0215E344 in the original game). Tests find people by scanning
  (`tests/proofs.py` `people_in`), never at a fixed address.

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
- Known slot fields: +0x05 clock, +0x0B money (24-bit), +0x8E needs (u16[8], 8.8 fixed point: value × 256; proof `save-edit`).
- `urbz_save.py info/set/fix`. Proven: a save edited to §4,321 and 10% hunger loads with both.
- Load from power-on: `verify/scripts/loadgame.json` with `--sav file.sav`. Save from the city:
  `verify/scripts/savegame.json` (Options > Save Game > slot A > overwrite).
- **Save path (proven, Phase 5):** `save_game(slot)` 0x0207EBAC → `save_finish_slot` 0x0207EB28: clears the
  slot buffer (memset 0xFE0 at 0x0207EE68), resets the cursor, calls `save_serialize_all` (BL at
  **0x0207EB44**), then stores bytes used (cursor - buffer) at save_ctx+0x8C and the checksum. Bytes appended
  after `save_serialize_all` are therefore counted and checksummed (the mod core does this). Seen in the
  emulator: the cursor goes 0 → 2,569 on `city.sav`; then EEPROM write (0x20, 0xFE0).
- **Load path (proven):** `game_start` 0x0204BA98 (the first city entry after the title, from area_enter's
  BL at 0x0204C268) → `save_load_slot` 0x0207EE00 → `save_deserialize_all` 0x020356D8 (BL at **0x0207EE1C**).
  A new game runs `new_game_init` 0x02035C48 there instead. Readers mirror the writers (`save_read_bits/
  nibbles/bytes` 0x0207EC48/0x0207ECBC/0x0207ED78).
- **Boot:** `save_boot_init` 0x0207EE88 checks the header and reads both slots (BL at **0x0207EF00**) at
  frame 10-15, before the title screen.
- **Save memory:** 8 KB EEPROM (DeSmuME: 64 Kbit). Read/write `eeprom_read`/`eeprom_write`
  0x02015860/0x020157D4 `(offset, len, buf)`; the write locks the card itself and returns 1 on success.
  The game only touches 0x0000-0x001F and the two slots; **0x1FE0-0x1FFF is never written** (no ARM or
  Thumb caller; 0xFF in a real save). The mod core keeps its switch record there (proven: written, kept
  after power-off).
- **How big the game's data gets (static):** `save_serialize_all` writes fixed-size fields except one
  part: `0x0203D3FC` writes 24 lists with a count byte each and 3 bytes per item (placed/owned objects).
  Everything else has constant sizes. Measured: 2,569 bytes in both `city.sav` and `lobby.sav`, so 1,495 bytes
  are free early; each item in those lists costs 3 bytes. A save that runs out keeps the game's data and
  drops mod data (the Mods page says "save full").

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
  3. no, if the id is in the 10-entry visit list at 0x02142270 (they're placed in a spawn zone instead);
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

## People: movement and object use (Phase 6)

From the decompile (Ghidra 11, research/README.md) and emulator runs; proof `npc-use-object`.
- `npc_state_dispatch` (0x0200BE50) runs the state at entity+0x104; +0x105 is the action inside it,
  +0x108 a countdown, +0x10A the state to go back to, +0x10B a path result. Townspeople wander in
  **state 0x23** (`npc_wander_state` 0x0200A1F0): action 7 = stand (anim 0x04) for 150-300 ticks; then
  action 0x19 = walk (anim 0x0A) in a random direction for 30-90 ticks, stopping when blocked; Kris
  alone has a hard-coded random gesture (anim 0xD5, action 0x29). State 0x22 walks someone to an exit;
  state 0x1A (set by story scripts) walks between way points and uses objects. (Proven: Kris on the roof
  cycles actions 7/0x19/0x29 with anims 4/0x0A/0xD5.)
- **Paths:** `path_request(e, xy, &result, 0)` (0x0207DC08) walks e to a point (16.16) around obstacles;
  there are only 3 path slots (0x02146F1C, 0xA0 bytes each; count at 0x02146F18). Result byte: 2 walking,
  1 arrived, 3 failed. `path_cancel` (0x0207DB10) frees the slot.
- **Objects in the area:** a list from `object_list_head` (*0x0214490C): node `{next, ?, u16 object
  number @+8, ..., entity @+0x24}`. `object_class_table` (0x020EAF84), 0x24 bytes per object number:
  +4 list activities (node, u8 out[7]), +8 can start (node, person, activity), +0xC start, +0x10 tick,
  +0x1C usable by (node, person). `activity_need_table` (0x020EA9B0, 4 bytes per activity) = the need an
  activity serves. Example, Slice O' Life Pizza (51): 3 chairs (object 137, activity 56, comfort), 2 tables (158,
  none), sink (203, 68, hygiene), toilet (208, 66, bladder), 170 (18, fun; refuses townspeople), no food.
- **Using an object:** `npc_goto_object(person, object entity, activity)` (0x0200D720) finds the use spot,
  requests a path and sets state 0x26 (`npc_goto_object_state`); on arrival the object starts the activity
  (state 0x11, the activity at entity+0x100; it ends when its tick says so, then the person goes back to
  state +0x10A). Animations are the person's own: sit 0x6B, stand up 0x72, toilet 0x7B. Proven: Phoebe
  (54) and Gramma Hattie (43) walk to a café chair and sit; Phoebe uses the toilet.
- **Needs:** activities update entity+0x114, a block of 8 needs (s32, 0-100 in the top byte, +0x20 also
  written). Townspeople have **none** (null); `motive_apply_effect` skips null, but other code writes +0x20,
  and address 0 mirrors ITCM code, so give a person a block (64 bytes) before sending them. Without one a
  chair reads junk and stands them up at once.
- The game's own picker `npc_pick_object` (0x02008A18, action 0x3E) chooses by the person's low needs
  (only hygiene, energy, comfort, bladder, fun; never hunger) and only for people whose record has +0x36 set
  (`npc_record` table 0x020E5E5C, 0x38 bytes each: ids 33 39 41 52 54 58). Calling `npc_goto_object`
  directly works for anyone.
- **Who can use objects visibly:** `npc_has_anim(id, anim)` (0x020644A8) reads the person's animation list
  (`npc_anim_lists` 0x0211CDF4, 12-byte rows ending 0xC4). Everyone has 0x04 stand and 0x0A walk; the object
  set (0x20 0x21 0x69 0x6B-0x6D 0x7B: sit, stand up, toilet ...) only 33 39 41 45 52 53 54 58; gestures 0x87
  (20 people), 0x78 (19), 0xDB (16). Gramma Hattie (43, no 0x6B) sent to a chair stands on the chair in the standing pose.
  Seats refuse townspeople in their can-start check (activity 0x38 and type != player: chair 137's +8
  function 0x0202E934), though the sit animations exist; NPC Life skips that check for seats only.
- **Facing and chatting:** `entity_face(e, dir)` (0x02000F08), dir 1-8 clockwise with 8 = up on screen
  (7 = up-left, 3 = down-right: proven from Kris's walks). The wander state ignores actions it doesn't
  know (e.g. 0x30), so code can hold a person still, face them and play gestures, then hand them back
  with action 2 (proof `npc-act`).
- **The world's entities:** a linked list per context at `entity_lists` (0x02121AF0, 8 bytes each: head,
  first); context 0 = the world (people, objects); entity +0 = next. (Proven: the pizza place's list holds
  Phoebe, Gramma Hattie and 33.)
- **Animations the object activities play** (from each object class's start/tick code, constants only, plus
  Kris's sheets; tables can add more): seats 0x6B sit down / 0x6C / 0x6D seated loop, 0x72 stand up; beds
  0x21 lie down, 0x20 get up; shower (200) 0x69, towel 0xCC/0xCD; toilet 0x7B; fridge, microwave, stove,
  grill, vending 0x41 (eat a snack standing). Of the townspeople only Kris has 0x41; the 8 with the object
  set have 0x20/0x21/0x69/0x6B-0x6D/0x7B. Where they could be used (docs/objects.md "Objects placed by
  area records"): seats and invisible park benches in 10+ public areas, toilets in 5, vending machines in 3,
  grills in 3, showers in 5, beds (mostly invisible ones) in 6.
- **Start checks know animations:** the vending machine's (0x020ADB90) refuses a townsperson without 0x7F (press
  the button) and 0x41 (eat); nobody but the player has 0x7F. A person sent anyway stands still for that
  part, then eats (proof `npc-act-eat`).
- **Ending a use early:** the object's activity record has 2 user slots at +0x0C (12 bytes: person, ...,
  stop byte at +9). Stop byte 3 = abort: the person stands up and resumes wandering next tick (proven);
  2 had no visible effect.

## Player body on a person (Phase 6 prototype, mod `npc-body-proto`)

- An entity draws either one sprite (people: slot 0, records set by their animation list) or, with
  **+0xC5 bit 0x40** (`entity_layered` 0x020031F4), up to 4 layered slots like the player: slot k at
  +0xCC + 12k = {+1 palette row, +2 sprite number (player: 4-7), +4 sprite memory (filled by the
  renderer; +6 = 0xFFFF until then), +8 animation table}. The "Load an Urb" screen draws saved Urbs this
  way (`FUN_02046F94`).
- `player_body_setup(e, look)` (0x0208327C) fills the slots from a look and e+0xC7; then
  `entity_set_frames(e, anim, player_facing_table[e+0x12])` (0x02003130) and
  `entity_set_script(e, scripts[anim], 0)` (0x02002B68), as the player's own update (0x020374B8) does.
  `load_look_palette(look, a, b)` (0x020833E0) builds the look's two rows into OBJ rows a and b.
- Look colours: clothing colour c = palette 11542 row c % 16, shades 1-3 (c < 16) or 4-6 (c >= 16);
  skin tone and hair colour = rows of 11543 (skin in shades 1-5, hair in 6-10).
- People get OBJ palette rows from a pool starting at 9 (the pizza place with 3 people: 9, 10, 11;
  12-15 empty). The player body needs 2 rows per person, so at most ~3 people could have it at once.
- Proven (proof `npc-body-prototype`, RAM; pictures in melonDS and DeSmuME): switched on, Kris is drawn
  with the female player body in a look of ours (brown skin, dark hair, white and denim), idles and walks
  with the player's animations; switched off, her own sprite comes back. Without the layered flag and
  sprite numbers, the parts are drawn scattered. Limits: the female body always has a skirt and no cap;
  person animations the player lacks (ids >= 196 or empty) show as standing.

## Pets (Phase 8 exploration, from the code + game text; not yet played through)

- The game's pets are **Splicer Island's spliced animals**: you extract DNA from amber and splice genes at the
  Splicer Lab (minigames, strings 155/156/162), then show pets in the **Pet Show** card game (154/160).
  8 species (`pet kind` 0-7), each in 3 colours: Jackalope, Dodo, New World Dragon, Konga Gorilla, Simosaurus,
  Triceratops, Unicorn, Veloci-Rooster (the "chicken"); their "golden gift" catalog items 50-51 and 8203-8210.
  Kinds 8-12 are another animal (one shared sheet; probably the Dancing Nutria, object 236).
- **You own up to 3 pets:** 3 slots of 0x18 bytes at `pet_slots` 0x02141BA2 (game_state+0xA82): +0 kind
  (0x11 = empty), +1/+2 copied to the pet (+0x13F, +0x140 = colour variant), +3 s8 (picked as "best pet" by
  the highest value: likely affection).
- **In the world:** area record type 6 (`spawn_pet_record` 0x020729A4): param 0x0D-0x0F = your pet in slot 0-2,
  0x10 = your best pet, other values = a fixed kind. Records in Carnival (2), Planet of Apes (10), Splicer
  Island (14: 5), Splicer Island Zoo (16: 7), Tar Pit (17: 2), Splicer Lab Basement (61: 2).
- `spawn_pet` 0x0207272C (kind, x, y, slot): entity type 6, id = kind, state 0x1D (wander/play
  `FUN_0200E9C4`), 0x39 petting (`FUN_0200DAD0`: the person plays anim 0x4E/0x4F/0x50, row 26), 0x1E, 0x30,
  0x31; behaviour 0x02071EBC; walking speed per kind `pet_speed` 0x020C1AFC (16.16).
- **Art:** `pet_anim_lists` 0x0211D680: per kind a u32[anim] list of 5-facing records (same format as people);
  colours: `pet_palettes` 0x020F5F04 (kinds 0-7: 3 palette ids each), 0x020F5920 (others, one each).
- Objects 225 (Chicken), 236 (Dancing Nutria), 237 (Pet, "This is your pet, @2") have no class functions but
  the "removed" one (0x02065224). Catalog pet things: Dawg House (58), Robot Pet (127, its own code).
- **Critters: the chicken you carry home** (a different system from the Splicer pets). Entity type 9,
  7 kinds (`critter_table` 0x020C3400, 0x14 bytes: setup function, ?, ?, speed, flags): 1 white chicken,
  2 dark rooster, 4 carnivorous plant (Living Artemisia), 5 Dancing Nutria (+ dirt mound), 6 white bird;
  0 and 3 have no sprites (inferred: the fly swarm). Sprites: `critter_anims` 0x020C348C (0x28 per kind =
  5 x {records, frame script}); palettes `critter_palettes` 0x020C2FD4 (palette game id per kind);
  behaviour 0x0202A61C; `spawn_critter` 0x0202AB18 (kind, facing, ?, x, y).
  The Chicken **item** (object 225) is what you carry: placing it (allowed for object 225 alone among
  numbers >= 224, at most 6 per lot: 0x0203F698) creates the object, whose "removed" function
  (0x02065224) turns it into critter kind 1; picking the critter up (0x0202A0DC, state 0x0E) puts object
  225 back in the inventory (critter kind 5 -> object 236 likewise). Placed chickens are saved as placed
  objects. A catalog pet (a dog) = a new critter kind with its own sprites + a new object, and those 4
  places taught about it.
- **A new pet kind (proof `pet-new-kind`, mod `mods/pets`):** the Puppy (object 386, copies the
  Chicken, sold by shop list 9) placed at home becomes a critter of the new kind 7. The three critter
  tables move into the mod (20 references), kind 7 copies the dark rooster (placeholder art), the Puppy's
  class row gets the mod's "removed" function (spawns kind 7), and a stub in the pick-up code
  (critter_update, state 0x12 / action 0x0E; the "kind" test at 0x0202A2D8) gives back object 386.
  Proven: placed, kind 7 exists; put in the pick-up state, it goes back to Pockets as object 386 and the
  critter is gone. Not yet: picking it up with real inputs, the Puppy's own art and sounds.
- **Saving (seen once, 2026-10-04, not a proof):** a Chicken (or Puppy) placed at home and left running,
  then saved (Options > Save Game) and loaded, was gone; the game did the same with the original Chicken,
  so free-running critters don't seem to be saved. Caveat: home was reached with the experimental
  `--goto 68`, not by walking there. To check on the Thor: does a chicken you let loose survive a save?
- Adding a Splicer species would mean new rows in the per-kind tables (sprites, palettes, speed, names),
  new art (2 views per animation), and teaching the splicer and pet show about it; not looked at.

## Buyable objects (catalog)

- Two parallel tables indexed by object number, 0x14 bytes per row:
  `object_text_table` 0x020E6D48 `{u32 model, u32 description string, u32 name string,
  u32 catalog page, u32 ?}` and `object_info_table` 0x020E8B70 `{u32 price, u32 common, u32 uncommon, u32 rare, u32 ?}` (the 3 shop masks: bit = shop list).
- Catalog pages: 0 Appliances ... 5 Utilities, 7 = not sold (model 632).
- Proven: object 200 "The Savvy Shower" repriced from $230 to $99 shows in the Catalog.
- **The Catalog only shows; it can't buy.** Seen in the emulator (2026-10-04): tapping an item shows its name,
  price and text; tapping again or A does nothing. Its pages list every object whose page field (+0xC) is that
  page, in object order, 4 per row with up/down arrows. Seen: setting the Chicken's page (object 225, page 7)
  to 4 puts "Chicken - $20" with its icon at the end of the Recreation page. Page 6 (objects 181-198) has no
  button. Counts per page (model != 632): 13, 88, 14, 33, 9, 11, 18.
- **Shops sell; stock is picked daily.** The game state has 24 item lists, headers at **0x02141280** + 8*i
  `{u8 count, u8 capacity, u16 pad, ptr}`, slots of 6 bytes `{u16 object, u8, u8 variant}`, 0x184 = empty.
  Lists 0-20 are shop stocks, 21 holds up to 50 (unknown use, empty in city.sav), 22 = game_state+0x15C
  (8; gifts/rewards: `0x40`, `0x41`... added on day change), **23 = Pockets** (game_state+0x154, 8 slots).
  - `shop_defs` 0x020C76E8: 24 x `{u8 capacity, u8 n, u8 keep, pad, u16 *items}`; an item 0x183 means
    "pick one at random". `restock_all` 0x0203D370 runs `restock_shop` 0x0203CA30 for lists 0-20 on a
    new game and on each new day (`FUN_02083DB0`, flag 8).
  - Random picks (`shop_pick` 0x0203C53C): 60% common, 30% uncommon, 10% rare; candidates are objects whose
    `object_info_table` word +4 (common), +8 (uncommon) or +0xC (rare) has **bit = list number**, not
    already in stock. So a new object is sold in a shop by setting one bit.
  - From the masks: the Chicken (225) is common stock of **list 9** (with easels 173 and items 370-375;
    probably the Farmer's Market, not checked). List 3 = appliances (0, 2, 5, 9, 13...), 4 = seats,
    10 and 20 = general furniture.
  - The shop screen (`shop_ui` state at 0x02148F30, +4 = list number) shows 4 items of that list; buying
    (`shop_buy` 0x0209CDA8) checks money, adds the item to **Pockets** (`list_add` 0x0203D0CC) and takes
    the price. Not yet seen in the emulator (the shop that sets +4 is not found yet).
- **Placing from Pockets.** Seen: writing a Chicken into Pockets (count 0x02141338 = 2, slot at
  0x02141892 = `E1 00 00 00`) shows it in Pockets ("Chicken / A plump little chicken from Uncle Hayseed's
  Farm."); double-tapping it on the city roof says "You cannot place this item here!".
  `place_object_check` 0x0203F698: only at home (`is_home_area` 0x02046AF4: the 3 bytes per row of
  0x020C812C, or an unlocked one of 11 extra lots at 0x020C8110: areas 17, 24, 32, 52, 78, 25, 53, 55, 57,
  56, 46), fewer than 63 objects on the lot, objects 104-113 and 185-196 have extra rules, numbers >= 224
  are refused except 225, and at most 6 chickens (count of placed 225s > 5 refuses).
  **Proven (proof `pet-place`):** the starting home is area 68 (Skyline Penthouse; lot byte 0x02141230 = 0 picks
  row 0 of 0x020C812C). Double-tapping an item in Pockets puts the player in carry mode (state 0x16): the
  item is held, the D-pad walks, a tile in front shows red (blocked) or yellow (free); A places (input bit 1),
  L/R rotate (0x200/0x100; from the code), B cancels. Placed there, the Chicken leaves Pockets and a few
  seconds later walks around as critter kind 1.
- **Seven tables are indexed by object number** (found 2026-10-04): text and info (386 rows, objects
  0-385), and five that only cover the 253 placeable objects (0-252; 253+ are Pockets items: food, gifts,
  quest things): class 0x020EAF84 (0x24), `object_shapes` 0x020E6954 (u32, footprint data),
  `object_models` 0x020F1D28 (u32, art), `object_variants` 0x020F211C (5 x u32 per colour variant),
  `object_anims` 0x020F34E0 (0x1C; read by `FUN_02067D04` for the look to draw). They sit packed in the game's data, so they can't grow in place.
  The Catalog scans objects 0-279 only (`cmp #0x118` at 0x0201C6E8 and 0x0201C920); objects 280-385
  are all on page 7. `shop_pick` looks at 386 (literal 0x0203C6AC). 387 and 388 are markers (random
  pick, empty slot); the save keeps object numbers in 9 bits.
- **New objects (Phase 8 kit, `urbz_objects.py`):** a mod's `objects.json` adds rows (`like`: the object to
  copy; name/description text gets new string numbers 8311+; price, page, model, the shops that sell it).
  The builder then makes a hidden mod (`build/new-objects/`) with copies of all seven tables (room for the
  new rows), points the 132 references in the game's code at them, raises the Catalog loops and the shop
  count, and adds `code/objects` (precompiled), which makes the game's number checks (so far: the place
  check, which refuses 224+ except the Chicken) ask about the copied object. Text banks may now hold new
  strings after the game's 8,311 (the game reads strings by number, with no count).
  **Proven (proof `objects-new`):** objects 386 and 389 appear on the Recreation page with their new names,
  prices and texts; the moved text table is in the code region; object 390, a copy of the Country Class
  Chair (136), put in Pockets is placed at home and drawn like the original (an entity with id 390 and a
  sprite). Found on the way: `object_anims` starts at 0x020F34E0 (not +4); copied one field off, new
  objects drew nothing (386) or garbled sprites (389+). Open: saving and loading a placed new object, and
  what a save holding new objects does without the mod; using a copied chair (sitting).
- A mod that writes into the old tables (e.g. a price with a `u32` hook) can't be combined with a mod that
  adds objects: the builder stops and asks for an `objects.json` change instead.
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
  +4 money, +0xC clock, +0x14 social table (relationships at +0x34), +0xE4 needs, +0x820 goal table
  (`goal_table` 0x02141940; layout and quest overrides in docs/areas.md), +0xB05 game phase, +0xB10 per-sim flags.

## Game states (screens)

- Each screen (0 = top, 1 = bottom) runs a state; `set_state(state, mode, param)` 0x0204DF7C (through
  0x0204E028). State table **0x020CD8B4**: 43 rows of `{enter, update, exit}` (states 0-42), e.g. 1 city
  (0x0204C158 / 0x0204C014 / 0x0204BE4C), 5 title, 6 settings, 7 save game, 34 (0x22) the city's bottom
  menus. The update loop calls `table[state].update` (0x0204DCE0).

## Bottom-screen menus (Urb Info, Options, ...) (proven, Phase 5)

- Menus are data. `menu_table_ptrs` 0x020F5654 = 5 menu pointers (2 = Options 0x020F56EC, 4 = Urb Info
  0x020F5744, 1 = a 6-button sub-menu); the open menu's index is `menu_ui+8` (`menu_ui` = *0x02144CEC:
  +4 open, +8 menu, +0xC action, +0x10 selected). Only 4 literal words point at the array
  (`menu_ptr_lit_1..4`), so it can be moved and lengthened.
- A menu: `{u32 gfx, u32 layout, 0, 0, u32 pal16, u32 pal256, u16 count, u16}` then `count` buttons of
  20 bytes `{u32 x | y << 8 | icon frame << 16, u32 action, u32 sub-menu, u32 param, u32 label string}`.
  Options: Settings (61,57) action 6, Save Game (198,57) action 7 (param 1), Quit (128,120) action 0x28;
  Urb Info uses the 2 x 2 grid (61,57) (198,57) (61,120) (198,120). Action 0 = open the sub-menu.
- `menu_hit_test` 0x0206FBF4 (one caller, BL at 0x0206FDAC): 32 x 32 box around each icon; returns the
  action (and plays sound 1), or opens a sub-menu and returns -1. `menu_dispatch` 0x02070494 runs actions
  (unknown ids just close the menu). Menus are touch-only (the D-pad doesn't move between buttons).
- `menu_redraw` 0x0207026C builds one icon sprite per button (8 slots at 0x02144D10), then
  `menu_draw_text` 0x02070038: it clears the text layer rectangle tiles (2,1)-(30,18) (= x 16-248,
  y 8-152), draws the title (font 3, `text_draw(1, 128, 8, ...)`) and each label centred under its icon
  (font 1, `text_draw(0x29 + 0x28 * i, x, y + 18, ...)`). Each label has 40 text tiles (about 160 px);
  longer text corrupts the screen, and 8 labels run out of tiles (6 work, as in the game's own 6-button
  menu). Text drawn outside the cleared rectangle stays on screen.
- Icon colours: palette row = icon frame, except Options, which uses row (button + 1) for buttons after
  the first (the core sets row = frame for its menus).
- Proven: the core's Options has a 4th button "Mods" that opens a Mods page (menu 5) and info pages
  (menu 6); real touches switch mods (proof `mods-page`, `npc-life-page`).

## CPU caches

- NitroSDK routines (r0 = address, r1 = size): `DC_FlushRange` 0x020B7C70 (clean + invalidate data cache
  lines), `DC_WaitWriteBufferEmpty` 0x020B7C8C, `IC_InvalidateRange` 0x020B7C98. The mod core calls them
  after changing game bytes at runtime. (DeSmuME doesn't model the caches, so this is from the code.)

## The mod platform (Phase 5)

The mod core (`code/core/`, built in whenever a mod can be switched in-game or uses events) owns these
game hooks and calls only the mods that are switched on: boot (0x0207EF00), world tick (0x0204C06C),
area entered (0x0204C58C), game start (0x0204C268), save (0x0207EB44), load (0x0207EE1C), menu labels
(0x0207016C), menu taps (0x0206FDAC) and menu text (0x0207039C). The mod table is at 0x0214DE20
(`code/include/mod.h`). Everything below is proven by `tests/proofs.py`:
- switches: call, wrap, jump stubs test a switch byte; data hooks are written/restored by the core
  (`toggle-call`, `toggle-data`); the switch record survives power-off (`switch-persist`);
- per-mod save data after the game's data, back after power-off; defaults on a vanilla save; a build
  without mods loads the save; a switched-off mod's data is carried through saves (`save-block`);
- the Mods page (`mods-page`) and NPC Life (`npc-life-*`).

## Open questions

Closed in the last gap pass (details in docs/player-look.md and docs/areas.md): clothing slot pixels, the
hair-style limit, street object palette rows, record types 29/30, quest overrides, and a legitimate save past the
first goal (`verify/saves/lobby.sav`). Still open:
- Which quest switches which record group (`swap_record_groups`) in each area: Phase 7 work.
- The streets need the whole tower chapter (about 12 more goals) in a real game; tests use `--goto` from
  `lobby.sav`.
- Type-30 spawn zones and the visit list are read from the code, not yet seen at runtime.
- Hardware (see "Secure area" below): not tested on a flashcart or real DS.

## Secure area and hardware

- The ROM's first 16 KB of ARM9 code (ROM 0x4000-0x7FFF, RAM 0x02000000-0x02003FFF) is the secure area. Retail
  cards store it encrypted, and header 0x6C holds a CRC of the encrypted bytes. Our ROM (like most dumps) holds
  it decrypted.
- Code mods must change the SDK module params at 0x02000ADC (the autoload table that copies our code to
  0x0214DE20), which sit inside the secure area. There's no way around this with an autoload block: any added
  code that loads at boot needs those params. We don't (and can't, without the console's key tables) recompute
  0x6C; the builder recomputes the header CRC at 0x15E.
- Risk: low. Flashcart loaders and emulators boot decrypted ROMs and don't check 0x6C; DeSmuME runs every proof.
  ROMs without code mods keep the secure area byte-identical. To do before a release: boot a code-mod build on a
  flashcart (or melonDS) once.
