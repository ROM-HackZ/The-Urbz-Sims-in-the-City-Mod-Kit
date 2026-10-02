# Build

Build turns `project/` plus enabled mods into `build/Urbz Mod.nds`. It patches the original cartridge image in place, reusing untouched chunks byte for byte and recompressing edited ones. Bad edits stop the build instead of producing a broken ROM.

## Sub-features

- `build-vanilla`: byte-identical rebuild with no mods.
- `build-mods`: build with `mods.json` or `--mod NAME`.
- `build-grow`: an edited chunk that is last in its asset grows the asset; the ROM can grow past 32 MB.
- `build-refuse`: growth that would move chunks with no known referencer fails with `BUILD FAILED` (see grow.md; sprite sheets now grow instead).

## How to get to it (user POV)

- Run `python urbz_build.py` (default output `build/Urbz Mod.nds`) or `build.bat`.
- Run `python urbz_build.py --vanilla <out>` for the original game.

## Driving it with the kit CLI

- **Vanilla.** Run `python urbz_build.py --vanilla /tmp/v.nds`. The output ends `[IDENTICAL to original]`.
- **Grow.** In a scratch mod, append bytes to `unpacked/10747/000000.bin` (the EA logo screen, a trailing chunk). Build: it prints `1 changed` and a different SHA, and `verify/urbz_verify.py smoke /tmp/x.nds` passes.
- **Refuse.** In a disabled scratch mod, put random bytes in `unpacked/10368/000114.bin` (one of the 4 multi-chunk assets with no known referencer). Run `python urbz_build.py --mod <scratch> /tmp/x.nds`. It exits 1 with `no known sprite layout points at them`, and `/tmp/x.nds` is not created.

## Gotchas

- `changed` counts assets, not files.
- Editing `project/` directly still builds, but it breaks the "pristine" baseline. Run `urbz_mod.py rescue`.
- Sprite-sheet chunks can grow (layouts are re-pointed), but sheets must stay under 64 KB.
