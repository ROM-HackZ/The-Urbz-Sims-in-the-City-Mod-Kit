# City areas

How areas are defined and loaded, how to travel, which people can appear where, and heap headroom.
Data for every area: `docs/data/areas.json` (made by `research/areas/build_table.py`).

Vanilla ROM (`the original ROM`). P = proven (checked in the emulator or byte-exact against the data).
I = inferred (read from the decompile, not exercised).

## Area ids and tables (P)
- There are **80 areas, ids 0..79**. `current_area` = u32 0x02141FEC. Schedules also use **82**, which has no table
  entry and matches no area, so it means "not in town".
- **AREA_TABLE 0x020C87E0**: 80 rows x 0x14 bytes `{u32 ptr (only areas 8/19/39/79), u32 name string, u32 data asset
  game id, u8[4] ?, u32 ?}`.
  - Name string = **975 + id** (70 = "5: Roof", King Tower roof, the start; 66 = "1: Tower Lobby"; 4 = Glasstown).
  - Phone "where I'll be" line = **1057 + id**.
- **AREA_GFX 0x020C8E20**: 80 rows x 0x50 bytes: 8 asset ids in 4 pairs `{a, b, 0, 0}`, 3 more asset ids at +0x40
  (+0x40 is opened with `FUN_02032f9c`), and a byte at +0x4C.
  - Runtime check: going into the lobby (66) loaded data asset 8848 and every id 8840..8851 from this row.

## Load path (P)
- Area changes go through the game-state machine. Per-screen structs are 0x8C bytes at 0x027C0070 (screen 0 = top,
  1 = bottom; the current screen index is at 0x027C0004).
  - Current state: +0 state, +4 mode, +8 param (= area id).
  - Next state: +0x2C/+0x30/+0x34.
- `set_state(state, a, b, c)` is 0x0204DF7C, reached through 0x0204E028.
- Every door or elevator calls `set_state(1, 0, area)` and stores the entry-point id in byte **0x02141C28**.
- State 1 = city, with enter/update/exit functions at 0x0204C158 / 0x0204C014 / 0x0204BE4C (table 0x020CD8B4).
- **area_enter 0x0204C158**:
  - copies the param into current_area (store at pc 0x0204C194);
  - loads `AREA_TABLE[id].data` (`FUN_02012820` parses it into a 0x2000-byte heap buffer);
  - `FUN_0204B870(id)` loads the AREA_GFX assets;
  - `FUN_0204B5B4(id)` sets up the players and spawns the date partner (I);
  - `FUN_020125C0(0)` and `(1)` spawn record groups 0 and 1.

## Area data asset format (P: parsed for all 80 areas; matches every runtime spawn checked)
- Header:
  - `u16 H, u16 nEntry`, then nEntry entry points `{s16 x, s16 y, u16 id, u16 dir}`.
  - At H: `u8 nSections, u8 variant_to_section[7]`.
  - At H+8: nSections x `{u16 offset, 6 bytes}`.
- **Variant** = byte 0x02122794 (saved; 0 in the tutorial, 1 after the Squeegee job). It picks the section.
  Section 0 is the base.
- Section: `{u16 listA, u16 listB, u16 flags (bit 0 = put the base group first), u16 listC}`, then at +8
  `{u16 nGroups, u16 off[]}`.
  - Group: `{u16 n, u8 size[n], pad to 4, records}`. Record = `{u16 type, u16 0, s16 x, s16 y, ...}`.
- Record type t is created by handler table **0x020C2308[t]** (types 1..37).
  - Group 0 (base) and group 1 are spawned when the area loads. The other groups are switched on by scripts
    (`FUN_02012690`, about 40 callers; I).
- Types that matter:
  - 7 = person `{.., u8 char, u8 facing}` (spawn_from_record).
  - **3 = door** `{.., u8 w, u8 h, u8 entry, u8 to_area, u8 style}` (behaviour 0x0204CB50). Proven: walking into
    a Coffee Shop door loaded area 4 at entry 12; no button press is needed.
  - 20 = door variant.
  - **25 = elevator** `{.., w, h, 5 x (u8 area, u8 entry), ...}`. Proven: A opens a floor menu in record order.
  - 29 `{.., u8 area, u8 entry}` sits next to doors and entries, but walking past one did not trigger it. I: an
    exit point for NPCs.
  - 30 = ?

## Travel in normal play
- P, all without pokes, from `--city`:
  - Squeegee sign, A, A, then the minigame plays out (about 7,000 frames with no input).
  - Back on the roof (variant becomes 1), then Kris's dialogue.
  - The roof elevator: menu "4: Skyline Penthouse / 3: Executive Office / 2: Law Offices / 1: Tower Lobby / B: Gym".
  - **Script: `roof_to_lobby.json`** (10,789 frames, ends in area 66). **State: `tower_lobby.dst`.**
  - `tower_tour.json` (from tower_lobby.dst) rides 66→63→65→64→68→66 (`tower_tour_end.dst`).
  - Inputs: walk with the D-pad (about 1.4 px/frame); A on the sign or elevator; DOWN×k + A in the menu.
  - In dialogue: touch the reply (120,64), then A. Long text scrolls with DOWN. Leave with the red button (38,18).
- P: **the tower's street doors are not spawned yet** (no door entities in the lobby). The goal "Slave to the Grind"
  still needs Kris relationship 30 and giving her the Squeegee and Bucket, so the street wasn't reached legitimately.
- P: **the globe is not locked**. Its hit box is centred on (19,163) ±13 (button table 0x020F566C), so (18,180)
  misses it.
  - Touching (19,163) opens the city map (screen 18, page 5) even in the tutorial.
  - Touching places only shows their names (King Tower, Rep Group Clubhouse). Map travel was not seen.
- EXPERIMENT (pokes): write 0x027C009C=0x81, 0x027C00A0=0, 0x027C00A4=area, 0x02141C28=entry. The game loads the
  area through its own path. This worked for all 80 areas (`heap_sweep.py`).
  - Poking screen 1 (0x027C0128...) loads an area on the bottom screen as well. Two areas at once left 961 KB free.

## Heap (EXPH, bytes)
| run | lowest free | smallest largest-block |
|---|---|---|
| P: city start → minigame → roof → lobby (no pokes) | 1,373,960 | 1,363,232 |
| P: tower tour 63/65/64/68/66 (no pokes) | 1,551,144 | 1,540,032 |
| P: city map open at the start (single sample) | 1,319,112 | 1,316,704 |
| EXP: each area entered from the lobby, 450 frames, 16:2x Monday, variant 1 | 775,592 (15 Splicer Island Awesome) | 764,288 |
| EXP: same, then the city map opened (Carnival 2) | **721,448** | **715,200** |

- Tightest areas:

  | Area | Lowest free (bytes) |
  |---|---|
  | 15 Splicer Island (Awesome) | 775K |
  | 2 Carnival | 789K |
  | 14 Splicer Island (Busted) | 845K |
  | 1 Bayou | 851K |
  | 11 The River | 928K |
  | 4 Glasstown | 1,073K |
  | 9 Paradise Island | 1,090K |

- Interiors use 1.5 to 1.7 MB free. Per-area numbers: `heap_sweep.json` and `areas.json[*].heap`.
- Caveat: the sweep is at one time of day, so the crowd size varies. The map adds about 250 KB and stays allocated
  after switching tabs.

## Schedules vs records (P statically; runtime agrees)
- `npc_schedule_table` actually has **49 entries (ids 31..79)**, ending with a 0 at id 80.
  - The lookup is `table[hour*7 + weekday]`.
  - ids 73/70 and 74/64 share a table.
- Quest overrides in `npc_present` come first.
  - Seen at runtime: Daddy Bigbucks (36) spawned in Executive Office 63, which is not in his schedule
    (override 36→63 while quest (0,0) is active).
  - Other overrides: 42→27, 53→12, 43→19/43, 50→39, 31→1/45, 69→2, 63→14, 62→19, 60→35/37, 65→27, 61→60, 32→61.
    These explain most of the "record but no schedule" areas.
- Runtime spawns matched the records exactly:
  - 63: Bigbucks at (236,191)
  - 65: Lily at (450,270)
  - 64: Misty at (358,471)
  - 13, 2, 19: sets of ids that are subsets of the records.
- **Schedule entry with no record for that person, so they can never appear there** (82 excluded):

  | Person | Area(s) with no record |
  |---|---|
  | 51 Maximillian Moore | 34 Coffee Shop |
  | 53 Olde Salty | 19 Urbania Park |
  | 56 Pritchard Locksley | 28 Cinema d'Urbania |
  | 58 Sue Pirnova | 13 Sim Quarter |
  | 74 (unnamed) | 12, 13, 15, 49 |

- Record only in a script-switched group (I: may need a quest): 38→43, 44→58, 53→13/26, 56→4, 61→61, 63→15,
  68→77, 69→36, 72→1, 74→4/19, 77→2, 78→26.
- Per-person lists: `areas.json["xref"]`. Person ids under 31 (animals and shop staff) have no schedule, so they
  always appear when their group is loaded.

## Research scripts (research/areas/)
- `area_parse.py` / `build_table.py` → `areas.json`. It holds per area: name, phone line, assets, entry points,
  sections and groups, people, doors and elevators, exits, heap; plus schedules and the cross-reference.
- `probe.py`: emulator probe (area loads, spawns, assets, player position, heap).
- `ents.py`: finds live entities by behaviour pointer.
- `fdiff.py`: lists the functions run by a script.
- `heap_sweep.py` (experiment).
- States: `squeegee_minigame.dst`, `roof_after_job.dst`, `tower_lobby.dst`, `tower_tour_end.dst`,
  `EXPERIMENT_poke_*.dst`.
- Screenshots: `shots/`, `sweep/areaNN.png`.
