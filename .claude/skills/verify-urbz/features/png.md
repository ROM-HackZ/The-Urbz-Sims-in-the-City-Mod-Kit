# PNG editing (screens and sprite frames)

`python urbz_png.py edit <mod> <asset>` writes `mods/<mod>/png/NNNNN/HHHHHH.png`, one per chunk. The builder converts edited PNGs back: screens get re-cut tiles, a rebuilt map and new colours in spare palette rows; sprite frames get their tiles rewritten with the sprite's 16 colours.

## Sub-features

- `png-screen`: full screens (palette + 32×24 map + tiles).
- `png-sprite`: simple sprite frames (chunk = one w×h frame), in captured colours when known.
- `png-composite`: composite sprites (several OBJ cells per frame) export as the assembled frame and are cut back into cells (urbz_composite.py).
- `png-strip`: chunks no layout describes, as a 16-tile-wide strip (lossless).
- `png-palette`: palette files as swatch PNGs (urbz_palette.py); `png-font`: font sheets (urbz_font.py).
- `png-identity`: an unchanged PNG gives a byte-identical build.
- `png-warnings`: off-palette sprite pixels, missing spare rows, and extra tiles are reported as `warning:` lines.

## How to get to it (user POV)

- Export, paint in any editor, save, build.

## Driving it with the kit CLI and urbz_verify

- **Identity.** Run `python urbz_png.py edit png-test 10747` and build with no further edits. Expect `[IDENTICAL to original]`.
- **Screen edit.**
  - Draw a navy box with a yellow outline and the yellow text "LIVING CITY MOD" at (40,8)-(216,36) on `mods/png-test/png/10747/000000.png`, saving as RGB.
  - Build, then smoke. `step1`–`step3` show the box, legible, with a yellow outline (spare row 15 used). Compare a 4× crop against the PNG.
- **Sprite edit.**
  - Run `python urbz_png.py edit green-hair 5776` (the player's head) and recolour the blonde pixels to a colour *from the PNG's own palette*.
  - Build, then `play --script verify/scripts/newgame.json`. The `city` shot shows the new hair colour.
  - Recolouring to an off-palette colour (green) prints ~20 warnings and stays blonde.
- **Composite.** `python urbz_png.py edit comp 1448` (player part, layout 01449), paint a band over the
  middle third of every frame, build, `play <rom> --city` with a shot: the player's arms/torso show the band,
  pieces in the right places (2026-10-02: band visible, nothing scrambled).
- **Palette.** `python urbz_palette.py edit kris 9160`, swap red/blue in all swatches but the first, build:
  Kris walks in with swapped colours (docs/player-look.md proof); unchanged sheet = identical build.
- **Font.** `python urbz_font.py edit f`, fill the 'o' glyph cell, build: the Catalog shows "Catal▮g".
- **Accents.** text line 27 = `café, niño, über, ¿qué? ¡Sí!`: the title prompt shows the accents.
- All of the above (build-level) plus emulator checks: `python tests/proofs.py png-sheets text-accents`.
- **Palettes.** `python verify/urbz_verify.py trace <rom> --script verify/scripts/newgame.json --name newgame` reports `sprite palettes captured for 23 asset(s)`.

## Gotchas

- Row 0 of the BG palette is overwritten at runtime (text layer), so it's never used for new colours. Colour 0 is transparent, so painted pixels never map to it.
- The game's text layer draws on top of screens. Edits under it are hidden.
- Sprite colours can't be added: OBJ palettes are shared at runtime.
