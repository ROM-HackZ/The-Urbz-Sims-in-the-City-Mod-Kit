# Other Sims DS games: what we could borrow

Jonathan (2026-10-05): "We can probably pull pet assets from a Sims pet game for the DS. Can you check also
if there's any furniture we don't have in Urbz that may be in the other Sims games." Plan: survey each ROM,
dump what's useful, compare with Urbz, then import his picks through `urbz_art.py` (pets) and the furniture
art step (docs/plan-phase8.md). ROMs and anything taken from them never go into git.

| Game | Developer | Why | Status |
|---|---|---|---|
| The Sims 2 (DS, 2005) | Griptonite (same studio as The Urbz DS) | furniture; probably the same file formats | waiting for the ROM |
| The Sims 2: Pets (DS, 2006) | Full Fat | dogs, cats | waiting for the ROM |
| The Sims 2: Apartment Pets (DS, 2008) | Full Fat | dogs, cats, other pets | waiting for the ROM |
| others Jonathan has | ? | ? | waiting for the ROMs |

## Survey (`python3 research/survey_rom.py <game.nds>`)
Reports file kinds (Urbz-style container, Nintendo NARC/NCGR/NCLR/NCER/NANR sprites, 3D models), the largest
files, and for an Urbz-style container how many entries hold EA-compressed chunks.

Reference, The Urbz DS: 2 files: `rom.bin` (Urbz-style container, 13,385 entries, about 45% hold
compressed chunks) and `SoundData.rom`; no NARC, no Nintendo sprite formats.

## What an Urbz pet needs (docs/systems.md "Pets")
5 drawn directions (the game mirrors the other 3), slot 0 standing and slot 1 walking at least, 16 colours,
about the chicken's (16x24) to the rooster's (54x75) size, feet as the anchor point.
