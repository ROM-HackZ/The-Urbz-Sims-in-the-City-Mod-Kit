# Player look (Create-a-Bod / The Threads) and sprite palettes

Addresses are ARM9 RAM. Asset numbers are **file numbers** (game id = file + 1) unless "id" is written.

## 1. Look struct (RAM), what the UI changes, and the save fields  [PROVEN]

`look` = **game_state+0x24 = 0x02141144**, one byte per field (found by RAM diff while changing each option):

| +  | field | options in UI | saved bits |
|----|-------|---------------|-----------|
| 0 | gender (0 male, 1 female) | 2 | 1 |
| 1 | skin tone | 6 (0-5) | 3 |
| 2 | hair style | 4 | 2 |
| 3 | hair colour | 10 (0-9) | 4 |
| 4 | shirt style ("Shirt Style 1-6") | 6 | 3 |
| 5 | shirt colour | 32 (cannot equal sleeve colour) | 5 |
| 6 | overshirt colour (row disabled for some styles) | 32 | 5 |
| 7 | sleeve colour | 32 (cannot equal shirt colour) | 5 |
| 8 | pants colour (female label "Skirt") | 32 | 5 |
| 9 | shoes colour (female label "Boots") | 16 | 4 |

Create-a-Bod page = rows Name/Gender/Skin Tone/Hair Style/Hair Color (strings 3813-3817);
"The Threads" (3819) is NOT a shop: it is the second Create-a-Bod page (strings 3820-3833), also
reached in game through the object action "Change Clothes" (3618). No item list or prices exist;
clothes cost nothing and are pure palette choices (section 3).

Save: `FUN_0207152c` (called from `FUN_020715f8(0x02141134)` in `save_serialize_all`) packs the look
into 5 bytes at **slot+0x1E**:
```
b0 = shirt&31 | (gender&1)<<7 | (hair&3)<<5      b1 = over&31  | (skin&7)<<5
b2 = shoes&15 | (haircol&15)<<4                  b3 = sleeve&31| (style&7)<<5
b4 = pants&31
```
city.sav: `03 20 00 0a 0e` = default look `00 01 00 00 00 03 00 0a 0e 00`. Proof: look_edit.sav (edited +
checksum fixed) loads as `01 03 02 05 04 11 15 07 1b 09` (proofs/proof_save_look.png, red-haired female).

## 2. Look -> sprite parts (art)  [PROVEN by hook + mod]

Only gender and hair style select art. Clothes never change gfx (get_asset log while cycling every
Threads option: same 3 assets).

Sprite record (16 bytes): `{u32 gfx id, u32 layout id, u32 palette id or 0, u32 param}`.
A "part set" = 5 consecutive records = 5 facings (identical for Create-a-Bod front view).

**Create-a-Bod preview** (`FUN_02045f30(look)`, entity slots via `FUN_020031bc(e, slot, ptr, palrow)`):

| slot (OAM pal row) | table | male | female |
|---|---|---|---|
| 0 body/skin (row 0) | 0x0211CD9C[gender] | 0x020C7F80: 11644/11645 | 0x020C7E90: 10940/10941 |
| 1 clothes (row 1) | 0x0211CDA4[gender] | 0x020C8070: 01261/01262 | 0x020C7FD0: 00670/00671 |
| 2 hair (row 0) | 0x0211CDAC[gender] -> u32[4] | 0x0211CDB4: 05471, 05914, 06356, 06798 | 0x0211CDC4: 03698, 04141, 04583, 05025 |

(gfx listed; layout = gfx+1.) Idle animation ids: 0x0211CDD4[gender*4 + state].

**City player** (`FUN_0208327c(e, look)`): each slot -> anim table u32[196] indexed by entity+0xC7
(animation) -> 5 records, or 0 = part hidden in that animation.

| slot (row) | table ptr | male | female |
|---|---|---|---|
| 0 body/skin (0) | 0x020F75E0[g] | 0x0211FBBC | 0x0211E32C |
| 1 clothes (1) | 0x020F75D8[g] | 0x0211F59C | 0x0211DD0C |
| 2 hair (0) | 0x020F75D0[g] -> [4 styles] | 0x0211EF6C -> 0x0211FECC, 0x0211EF7C, 0x0211F28C, 0x0211F8AC | 0x0211D6DC -> 0x0211E63C, 0x0211D6EC, 0x0211D9FC, 0x0211E01C |
| 3 props (row = u8 0x020F75E8[anim], 0xFE -> game_state+0x7DD) | 0x020F75C8[g] | 0x021201DC (52 anims) | 0x0211E94C |

Every row with asset ids: `parts_tables.txt` (`dump_parts.py --anims`). Hair anim 0: male 05493/05936/06378/06820,
female 03720/04163/04605/05047. Runtime check: the city player entity has slot0 0x0211FBBC row 0,
slot1 0x0211F59C row 1, slot2 0x0211FECC row 0 (t14.py).

**Option counts (UI limits)** [PROVEN for hair]: Create-a-Bod rows wrap at a count from the byte table
**0x020C8204** = `{u8 mode0, u8 mode1}` per row: gender 2/2, skin 6/8, hair style **4/4 (0x020C820A/0x020C820B)**,
hair colour 10/16 (`FUN_02048a74`, values kept at 0x02141FB8 + row*4, copied to the look on change). Proof: with
0x020C820A poked to 3 the hair style cycles 1, 2, 0, 1 (watch on 0x02141146, writer pc 0x02048C04); normally it
cycles 1, 2, 3, 0. Mode 1 (8 skin tones, 16 hair colours) matches the save's bit widths; when the game uses mode 1
is not known (I: an unlock).

**Adding a 5th hair style needs four things:** the count byte above set to 5; a 5th pointer for both hair tables
(Create-a-Bod `0x0211CDAC[g]` and city `0x020F75D0[g]`; each gender's u32[4] sits right before the other's, so
copy the tables into the code region and re-point them); art for the new style; and **a save change**: the save
keeps the hair style in 2 bits (slot+0x1E, b0 bits 5-6), so a 5th style would load back as style 0. Adding an
"outfit" means adding colours/style cases (section 3), not art.

**Proof mod `tests/mods/cab-hair`** (`code/hooks.txt`): `u32 0x0211CDB4 0x020C7E40` and
`u32 0x0211EF6C 0x0211EF7C` -> male hair style 0 shows hair style 1's art. Built
`build/cab-hair.nds`; Create-a-Bod start loads gfx 05914 instead of 05471; proofs/proof_cab.png
(columns 3-4) and proofs/proof_hair_city.png (city.sav player).

## 3. Player colours  [PROVEN: computed rows match palette RAM exactly; mods]

`FUN_020833e0(look, rowA, rowB)` -> `FUN_02083538` builds two 16-colour rows from two raw 512-byte
palette assets, pointers from `FUN_02083428`:
- **A = asset 11543** (id 11544): 16 rows x 16 colours. Row s colours 1-5 = skin tone s; row s+8
  colours 1-3 = 3-shade skin (used where female styles 4/5 bare the torso); row h colours 6-10 = hair colour h; row k colours 11-14 =
  shoes k; A[0], A[15] = transparent/outline.
- **B = asset 11542** (id 11543): clothing colour c (0-31): 3-shade at row c%16 colours 1-3 (c<16)
  or 4-6 (c>=16); 4-shade at colours 8-11 (c<16) or 12-15 (c>=16).

rowA (skin/hair) = A[0], skin(5), hair(5), shoes(4), A[15].
rowB (clothes) = B[0], X(3), Y(4), Z(4), pants4(4), with X = shirt3, defaults Y = Z = overshirt4, then
by gender/style: male 0: Z=sleeve; 1: Y=shirt4, Z=sleeve; 2: Z=skin; 3: Y=shirt4, Z=skin; 4: -; 5: Y=Z=shirt4.
female 0: Z=skin; 1: -; 2: Y=Z=shirt4; 3: Y=shirt4, Z=skin; 4: X=skin3; 5: X=skin3, Z=skin.
**Which pixels each slot covers** [PROVEN for two looks]: OBJ row 1 in hardware rewritten with 16-bit writes
(colours 1-3 red, 4-7 green, 8-11 blue, 12-15 yellow), one frame, screenshot:
- male, shirt style 0 (city.sav look): X (1-3) = shirt front, Y (4-7) = jacket body, Z (8-11) = sleeves,
  12-15 = trousers.
- female, shirt style 4 (look_edit.sav): X (1-3, skin for this style) = bare shoulder/upper arm, Y = top,
  Z = waistband **and boots**, 12-15 = skirt.
Other styles follow the same slots; what Y/Z cover depends on the art for that style.
(shirt4 = shirt3 pointer + 7 colours, + 8 if shirt >= 15: game quirk, colour 15 is off by one.)
`swatch.py` reimplements this; for look `00 01 00 00 00 03 00 0a 0e 00` it equals live OBJ rows 0/1.
player_colours.png shows the tables. Player uses OBJ rows 0 and 1 (also composed for look copy
0x02147140 into rows 3/2 by FUN_02046f94).

**Proof mod `tests/mods/cab-skin`**: assets/11543.bin with skin tone 1 colours 1-5 green ->
green Sim in Create-a-Bod (proofs/proof_cab.png columns 5-6).

## 4. Where OBJ palettes come from (all sprites)  [PROVEN unless marked]

Palette RAM is written only through shadows: ctx table 0x02122FFC + engine*0x10 = {BG shadow,
0x05000000/0x05000400, OBJ shadow, 0x05000200/0x05000600}; engine = u8 0x027C0004 (0 main, 1 sub).
`FUN_0201f750(src, colour index, count, ctx)` copies to the shadow, then CPU 16-bit copy to hardware
(FUN_0204e2e4 -> FUN_020b84ac); no DMA. Main OBJ shadow observed at 0x02168C60.
Loaders: `FUN_02020100(asset id, byte offset, colour idx, n)` immediate; `FUN_0202005c(asset id, idx, n)`
queued, flushed by `FUN_0201fbe0`; `FUN_02020174(ram src, idx, n)`; BG: `FUN_020201a4`.

Sources by sprite kind:
1. Record palette field non-zero: `FUN_02001050(e, rec)` loads asset rec[2] into the entity's row
   (entity+0x90 bits 12-15). FUN_020ae0c8 itself reads only rec[0], rec[1]; its 3rd argument is the
   8bpp flag (OAM attr0 bit 13). rec[3] -> entity+0x95 = reload of the frame-delay counter +0x94
   (ticks per animation frame) [inferred from code].
2. Player: composed (section 3).
3. NPC people: `spawn_npc` -> `FUN_0206d724(e, &0x020D0054[char id])` (some quest-state overrides);
   `FUN_0206d73c` takes a free/shared row from the pool (0x02144940 + engine*0x84) and loads the
   16-colour asset. Table **0x020D0054: u32 palette id per character id**; Kris (45) = id 9161 = **file 09160**.
   Proof mod `tests/mods/npc-pal` (09160 R/B swapped): proofs/proof_npc_pal.png.
4. City objects: rows 2-8 loaded at area start by `FUN_0204b4fc` (only when area < 0x50
   [inferred: streets]) from table **0x020C82C4 = ids 1,2,3,5,6,7,8 = files 00000, 00001, 00002, 00004,
   00005, 00006, 00007** (32-byte raw palettes). Each object picks its row via entity+0x90 (e.g. puddles
   gfx 10748 -> row 3 = file 00001; gfx 10117 -> rows 2/7). Each kind of object picks its row in its own create function, through
   `set_palette_row(e, row)` (0x0206D84C): either a constant (e.g. 3 or 4 in the minigame objects at 0x020103B8) or
   a per-kind table indexed by the object's variant (entity+0xA). **Proven for area record type 16** (pick-ups,
   hidden once collected): rows come from `0x020C2828[variant]` = 7, 5, 3, 7, 2; in Glasstown the five type-16
   objects use rows 7, 7, 7, 5, 3, and with the table set to 8 all five use row 8 (proof `object-row`). Record
   type 31 uses `0x020C2B08[variant]` = 7, 7, 7, 7, 6, 5 (I). Proof mod `tests/mods/city-pal` (00001 R/B swapped): puddles turn orange
   (proofs/proof_city_pal.png).
5. Bottom-screen HUD sprites (sub engine): rows 0-7 asset 10361 (128 colours), 14/15 assets 10357/10354,
   others 256-colour blocks from loaded UI assets (FUN_020179b8).

Many 32-byte palette files are duplicates (e.g. 26 files equal 00006), so match by the table, not by content.

## Research scripts (research/cab/)
cabprobe.py (in-process emulator helper), dump_parts.py, swatch.py, t2-t16 probes, proof.py, kris.py,
states: cab.dst (Create-a-Bod), threads.dst, world.dst (new game, city).
