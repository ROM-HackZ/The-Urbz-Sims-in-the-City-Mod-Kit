# Growing edits (offset fix-ups)

When an edited chunk no longer fits its slot, the builder lays the asset out again and re-points the sprite layouts that reference the moved chunks (u16 at entry+4), using `project/sprite_refs.json`. Embedded tile streams (`.tiles.bin`) are spliced back into their chunk.

## Sub-features

- `grow-fit`: an edit that still fits is padded in place, and no layout changes.
- `grow-repoint`: a mid-sheet chunk grows, later chunks move, and the paired layouts are re-pointed.
- `grow-tiles`: an edited `.tiles.bin` is recompressed and spliced into its screen chunk.
- `grow-refuse`: growth that would move chunks nobody is known to reference fails with `BUILD FAILED`.
- `grow-lz77`: LZ77 (codec 1) and raw (codec 0) chunks repack too.

## How to get to it (user POV)

- Edit any chunk or tiles file in a mod (`python urbz_mod.py edit <mod> <asset> [file]`) and build.
- The build summary says `N chunk(s) grew, M sprite layout(s) re-pointed`.

## Driving it with the kit CLI and urbz_verify

Preconditions: the project is format 4 (`manifest.json` "format": 4; run `python urbz_extract.py --upgrade project` if not), `project/sprite_refs.json` exists, and the vanilla build is identical.

- **Repoint.** Create mod `grow-test`.
  - Run `python urbz_mod.py edit grow-test 01261 000604.bin` and `... 01261 001A58.bin`, then overwrite both files with random bytes of the same length.
  - Build with `--mod grow-test`. Expect `2 chunk(s) grew, 1 sprite layout(s) re-pointed`.
- **Proof the offsets are right.**
  - Capture the decompressor output while running the intro script (exec hook at `0x01FF8F68`: output = RAM[r0:r1]).
  - Each 01261 chunk's raw (pre-delta) content must appear exactly in the captured outputs: the 2 noise frames byte-for-byte, and the moved original frames intact. 2026-10-01 run: 2 modified + 39 original matched, 1 not loaded.
  - `python verify/urbz_verify.py smoke <rom>` must PASS.
- **Tiles.**
  - Run `python urbz_mod.py edit tiles-test 10747 000000.tiles.bin` and invert each nonzero 4-bit pixel (v → 15−v).
  - The build says `1 chunk(s) grew`. Smoke: step1–step3 ~8.6% changed (EA logo in negative), step0/step4 0.0%.
- **Refuse.**
  - In a disabled mod, put random bytes in `unpacked/10368/000114.bin`.
  - `python urbz_build.py --mod <mod> /tmp/x.nds` exits 1 with `no known sprite layout points at them`, and no ROM is written.

## Gotchas

- Savestates hold already-decoded graphics in RAM. Prove growth from a fresh boot (intro script), not from `world-start.dst`.
- A sprite gfx asset can't exceed 64 KB (u16 offsets). The build refuses past that.
- The intro scenes use no LZ77 chunks, so `grow-lz77` is only proven offline so far (round trip through ndspy's independent decoder for all 1,628 chunks; all fit their slots).
- Cleanup: disable and delete the scratch mods. Keep `verify/evidence/`.
