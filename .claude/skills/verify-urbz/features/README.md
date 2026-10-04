# Urbz DS Mod Kit verification map

The maintained source for proving the kit works from the player's and modder's point of view. Read the index, then use the matching feature file as the recipe.

## Baseline preconditions

- Kit root contains `project/` (pristine, made by `urbz_extract.py`) and `project/base.nds` with SHA1 `3c01cc5cf3491b5d0ab626ccfb5bcad370662f2f`.
- `python urbz_build.py --vanilla build/vanilla.nds` prints `[IDENTICAL to original]`.
- `python verify/urbz_verify.py doctor build/vanilla.nds` prints `DOCTOR OK`.

## Driving conventions

- All emulator runs use the pinned clock unless a recipe sets `--rtc`.
- Build into `build/` or a temp path; never write ROMs into `project/`.
- Treat commands as literal. Keep quoted names unchanged.

## Proof and skip reporting

- Keep `verify/evidence/<run>/` paths in the report for every claim.
- Report an unreachable feature with the command attempted and the unmet precondition.

## Features

| ID | Feature | File |
|---|---|---|
| extract | Unpack a ROM into an editable project | [extract.md](extract.md) |
| build | Rebuild a byte-identical ROM; safe failure on bad edits | [build.md](build.md) |
| mods | Mods overlay: new/edit/status/enable/disable/rescue, new assets | [mods.md](mods.md) |
| boot | The built game boots and reaches Create-a-Bod; visual diff vs original | [boot.md](boot.md) |
| probe | Savestates and memory probes for gameplay/NPC behaviour | [probe.md](probe.md) |
| grow | Edits that outgrow their slot: re-pointed sprite layouts, tile streams, LZ77/raw chunks | [grow.md](grow.md) |
| text | Edit dialogue and menu text; re-encoded text bank | [text.md](text.md) |
| png | Edit screens and sprite frames as PNG; captured sprite palettes | [png.md](png.md) |
| code | C code and hooks in the game: blobs, call/wrap/jump/data hooks, cartridge relayout | [code.md](code.md) |
| systems | Clock, needs, money, save file, NPCs, action effects, catalog: the facts mods use | [systems.md](systems.md) |
| platform | Mod platform: in-game switches, mod save data, Mods page, mod manager; NPC Life | [platform.md](platform.md) |
| objects | New objects (objects.json) and pets: catalog, placing, critters | [objects.md](objects.md) |
