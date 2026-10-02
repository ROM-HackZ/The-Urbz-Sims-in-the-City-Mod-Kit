# Research scripts

The probes and table generators behind `docs/` (areas, player look, objects, composite sprites)
and the reverse-engineering helpers. They're kept so every documented fact can be re-derived.

They were written in the cloud workspace and use its absolute paths. To rerun one, recreate
those paths (or edit the constants at the top of the script):

| path in the scripts | what it is | how to make it |
|---|---|---|
| `/root/urbz/kit9` (also `kit8`, `kit10`) | a kit checkout with `project/` | this repo + `python urbz_extract.py <rom> project` |
| `/root/urbz/work/van.nds` | the original ROM | your own dump (SHA1 3c01cc5c...) |
| `/root/urbz/arm9.bin` | the game code, loaded at 0x02000000 | `python -c "import ndspy.rom as r; open('arm9.bin','wb').write(r.NintendoDSRom.fromFile('van.nds').arm9)"` |
| `/root/urbz/itcm.bin` | ITCM code at 0x01FF8000 | the second section of `ndspy.code.MainCodeFile(arm9, 0x02000000, 0x02000ADC)` |
| `/root/urbz/ghidra/arm9_decomp.c` | decompile of every function | Ghidra 11 headless: import arm9.bin as ARM v5t LE at 0x02000000, run `ghidra/ExportDecomp.java` |
| `/root/urbz/ghidra/functions_arm9.json` | function map (addr, end, Thumb, callers) | `ghidra/ExportMap.java <seeds.txt> <out.json>` (seeds: BL targets) |

Headless Ghidra, as used:
```
analyzeHeadless <dir> urbzproj -import arm9.bin -processor ARM:LE:32:v5t \
    -loader BinaryLoader -loader-baseAddr 0x02000000 -scriptPath research/ghidra \
    -postScript ExportDecomp.java
analyzeHeadless <dir> urbzproj -process arm9.bin -noanalysis -scriptPath research/ghidra \
    -postScript ExportMap.java seeds.txt functions_arm9.json
```
The kit's `code/functions.json` is the compact form of that map (`[addr, end, thumb]`).

Top level: `ex.py` (run steps from a savestate, save a new one, contact sheet of shots),
`snaps.py` (RAM snapshots at each shot), `npcq.py` (log NPC presence checks),
`heapwalk.py` (walk the game heap). Folders: `areas/` (area data parser, heap sweep,
`roof_to_lobby.json` = the input script from the city start to the tower lobby), `cab/`
(Create-a-Bod and palette probes, `swatch.py` = the player palette builder), `objects/` (object →
action → effect row analysis), `composite/` (OAM/VRAM capture and checks for the sprite format),
`ghidra/` (export scripts).
