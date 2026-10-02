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
  - Group 0 (base) and group 1 are spawned when the area loads (`FUN_020125C0(group)`). The other groups are
    swapped in and out by `FUN_02012690(show, hide)` (42 call sites). The group numbers mostly come from data: bytes
    in object records or entity fields (e.g. entity+0x129/+0x12A, record bytes +5..+8), so a "fixed TV" or "open
    door" group is chosen by the object that triggers it (I: read from the code; which quest flips which group in
    each area is not mapped, it is Phase 7 work).
- Types that matter:
  - 7 = person `{.., u8 char, u8 facing}` (spawn_from_record).
  - **3 = door** `{.., u8 w, u8 h, u8 entry, u8 to_area, u8 style}` (behaviour 0x0204CB50). Proven: walking into
    a Coffee Shop door loaded area 4 at entry 12; no button press is needed.
  - 20 = door variant.
  - **25 = elevator** `{.., w, h, 5 x (u8 area, u8 entry), ...}`. Proven: A opens a floor menu in record order.
  - **29 = NPC way point** `{.., u8 area (+8), u8 entry (+9), u8 set (+10)}` (create 0x020653E0; an invisible
    entity, no behaviour). Not used by the player (walking past does nothing). People walking **out**
    (`FUN_020655C0`) head for the type-29 marker whose area is where they're going (else one leading to a street,
    area < 20, else any) and leave there; people walking **in** (`FUN_020656A4`) appear on such a marker. Proven:
    loading city.sav with `npc-visit`, Bayou Boo (31) is spawned facing 4 at (164,246), the roof's type-29 marker
    toward area 4. Set 1 markers are only for person 40.
  - **30 = spawn zone** `{.., u8 set (+8), u8 half-width (+9), u8 half-height (+10), u8 key (+11)}` (create
    0x020999DC). `FUN_020644FC(id, key)` spawns a person at a random spot inside the zone with that key. Used for
    the "visit list" at 0x02142270 (`npc_busy_list`: `{s16 timer, u8 id, u8 area, u8 key, u8 state}`): when you
    enter that area, everyone listed for it with state 1 is placed in zone `key` (`FUN_02066708`), and
    `npc_present` keeps them out of their normal schedule meanwhile. `FUN_02064768` puts someone in zone 0 for
    3,600 ticks (I: a phone invite). Read from the code, not yet seen at runtime.

## Travel in normal play
- P, all without pokes, from `--city`:
  - Squeegee sign, A, A, then the minigame plays out (about 7,000 frames with no input).
  - Back on the roof (variant becomes 1), then Kris's dialogue.
  - The roof elevator: menu "4: Skyline Penthouse / 3: Executive Office / 2: Law Offices / 1: Tower Lobby / B: Gym".
  - **Script: `roof_to_lobby.json`** (10,789 frames, ends in area 66). **State: `tower_lobby.dst`.**
  - `tower_tour.json` (from tower_lobby.dst) rides 66→63→65→64→68→66 (`tower_tour_end.dst`).
  - Inputs: walk with the D-pad (about 1.4 px/frame); A on the sign or elevator; DOWN×k + A in the menu.
  - In dialogue: touch the reply (120,64), then A. Long text scrolls with DOWN. Leave with the red button (38,18).
- P: **the first goal "Slave to the Grind" is scripted with real inputs**: `verify/scripts/first-goal.json` (12,900
  frames from `--city`). After Kris's dialogue: three chats (25 → 28 → 28 → 30; one chat gave nothing), "Friendly
  Stuff" → "Give a Gift" → tap the Squeegee 'n Bucket twice, then report with "What's Up?" (goal complete, next goal
  "Get Cleaned Up" active), leave, close two pop-ups with B, ride the elevator to the lobby, then Options → Save Game
  → slot A → overwrite. The result is **`verify/saves/lobby.sav`** (Tower Lobby, day 0 17:01, Kris 30, variant 1,
  first goal complete). Use it with `--from lobby` (proof `lobby-goto`).
  - Relationships rise through chats (`add_relationship` 0x0207B074, called from the conversation code at
    0x0208FFF4); the Talk menu changes its topics after each one.
  - Save menu: the list button (128,170) → Save Game (200,58) → green check (225,118) → overwrite: RIGHT, A, then
    tap the check (168,98) twice.
- P: **the street doors still don't appear after the first goal** (no door entities in the lobby after reporting). The lobby's street doors (section 1, group 1:
  seven type-3 doors to area 4) are a script-switched group, and the chapter goes on: Get Cleaned Up (shower, nap,
  vending machine), Help Kris (move a bed, repair a TV and two fountains), Get the Key (a mechanical skill point,
  pick a lock), Find the Key, Get out of Jail (Detective Dan 30, his questions), then Find a Place to Live. Scripting
  all of that is a long job, so tests reach the streets with `--goto` (below), starting from the legitimate
  `lobby.sav`.
- P: **the globe is not locked**. Its hit box is centred on (19,163) ±13 (button table 0x020F566C), so (18,180)
  misses it.
  - Touching (19,163) opens the city map (screen 18, page 5) even in the tutorial.
  - Touching places only shows their names (King Tower, Rep Group Clubhouse). Map travel was not seen.
- EXPERIMENT (pokes): write 0x027C009C=0x81, 0x027C00A0=0, 0x027C00A4=area, 0x02141C28=entry. The game loads the
  area through its own path. This worked for all 80 areas (`heap_sweep.py`). The harness does this with
  **`--goto AREA[:ENTRY]`** (e.g. `ram ROM --from lobby --goto 4` = Glasstown street); it waits 400 frames and fails
  if the area didn't load. The screen must be in state 1 (the city): with a pop-up open (state 2) the poke is
  ignored, which is why `--from` closes the load-time pop-up first.
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
- Quest overrides in `npc_present` come first (full list below). Seen at runtime: Daddy Bigbucks (36) spawned in
  Executive Office 63, which is not in his schedule.

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

## Quest overrides (read from the decompile of `npc_present` and `npc_relocate_tick`; goal flags proven in RAM)
Goal flags live in `goal_table` 0x02141940: 7 missions x 6 goals x 12 bytes. Goal (m,g) is at
`0x02141940 + m*0x48 + g*0xC`: +0 active, +1 complete (set when you report back to the quest giver), +2+2s sub-goal
s shown, +3+2s sub-goal s done. Proven: at the start m0g0 = `01 00 01 00 ..`; after the first goal's three steps it
is `01 00 01 01 01 01 01 01`; "complete" is set only when you report back (Kris's new "What's Up?" topic), which also
activates m0g1 (`01 00 01 00 01 00 01 00`: three sub-goals shown).

`npc_present(id, area)` answers these before the visit list, the date partner and the schedule. "Only X" means the
person appears in area X and nowhere else while the condition holds.

| Person | While | Then |
|---|---|---|
| 36 Daddy Bigbucks | m0g0 active and m0g5 not complete | only 63 Executive Office |
| 36 Daddy Bigbucks | m0g5 active and m4g5 not complete | nowhere |
| 42 | m2g0 active and not complete | only 27 |
| 53 Olde Salty | m2g5 sub-goal 3 done and m2g5 not complete | only 12 |
| 43 | m0g5 complete and m1g5 not complete | only 19 Urbania Park |
| 43 | m3g2 complete and m3g3 not complete | only 43 |
| 50 | m2g5 active and not complete | only 39 |
| 31 Bayou Boo | m3g1 sub-goal 1 done and m3g2 sub-goal 1 not done | only 1 |
| 31 Bayou Boo | m3g2 sub-goal 1 done and m4g2 not complete | only 45 |
| 69 | m3g2 complete (for good) | only 2 |
| 41 | m4g5 active and not complete | not in 40 |
| 63 | m6g1 not complete (most of the game) | only 14 |
| 62 | m6g2 sub-goal 2 not done | only 19 |
| 60 | m6g2 sub-goal 1 not done | only 35 |
| 60 | m6g4 active and `FUN_02034fa4(0x2d)` = 0 | only 37 |
| 65 | m6g2 sub-goal 0 not done | only 27 |
| 61 | m6g4 complete, m4g5 complete, m6g5 sub-goal 0 not done | only 60 |
| 32 | m6g4 complete, m4g5 complete, m6g5 not complete | only 61 |
| anyone | m6g5 active and not complete | nobody in area 2 |

`npc_relocate_tick` skips the same people under the same conditions (so quest people are never walked in or out),
and also always skips 26, 74, 77 and 79, people with no schedule, and people `FUN_0206546c` reports as busy; 31 and
35 are skipped in two story modes (`game_state+0x81C` = 3 / 1 with flag bit 0 of 0x021420E8).

**For NPC Life (Phase 5):**
- Hooking `schedule_lookup_call` (0x0206665C) changes who walks in and out; the overrides above still win, because
  the relocation skips quest people before it asks the schedule. So quests stay safe.
- `npc_present` reads the schedule table **directly** (not through `schedule_lookup`) when an area loads. The table
  address is in 5 literal words (`schedule_table_ptr_1..5` in `code/game.sym`). I: pointing all 5 at a new table in
  our code region moves people both at area load and during relocation (not yet tried).
- The visit list (0x02142270, 10 entries, see record type 30) is how the game sends someone to a place for a while
  outside their schedule; a mod can use it for visits too.

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
