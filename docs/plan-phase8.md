# Phase 8: new clothes and new catalog objects

Decided with Jonathan (2026-10-02): Phase 8 = **clothes** (colours and colour styles for your Urb) and
**catalog objects** (new things to buy and use). Art is drawn by Jonathan or an artist; the kit provides
templates and tools, and wires things in with placeholder art first (like `urbz_anims.py`).

## What we know (docs/player-look.md, docs/systems.md, docs/objects.md)
- **Clothes are colours, not shapes.** The player's body art never changes with clothes; a look is 10 bytes
  (gender, skin, hair style, hair colour, shirt style, 4 clothing colours, shoes). `FUN_02083538` builds the
  2 palette rows from palette files 11543 (skin, hair, shoes) and 11542 (32 clothing colours, all used).
  "Shirt style" (6) only decides which body parts take which colour. The save keeps 5 bits per clothing
  colour (max 32) and 3 bits for the style (max 8). New clothing *shapes* would mean redrawing ~196
  animations x 5 facings x 2 genders: out of scope.
- **Objects** (`object_text_table` 0x020E6D48 and `object_info_table` 0x020E8B70, 0x14 bytes per row, ~386
  rows, back to back; class/behaviour table 0x020EAF84, 0x24 bytes per row). The save stores an object number
  in **9 bits** (`FUN_0203C484`): up to 512, so ~125 new objects fit without changing the save. Catalog pages
  0-6 (Appliances ... Utilities), 7 = not sold. Proven earlier: repricing an object shows in the catalog.
- Since Phase 7, mods can add new assets (the builder moves the game's asset tables), and mods can keep
  their own data in the save (Phase 5).

## Steps
1. **Research (decompile + emulator), both features.**
   - Clothes: the Create-a-Bod / The Threads colour pickers (limits table 0x020C8204, how swatches are drawn,
     how a choice is stored), every reader of the look's colour bytes, the save writer/reader of the look.
   - Objects: how a catalog page lists objects (loop bounds, per-page limits, icons), the buy flow, placing
     (footprint, rotations), how a placed object is drawn (model id -> sprite assets per rotation), its
     catalog icon, and every reader of the object tables (to move them).
   - Output: docs/systems.md sections, names in game.sym, proofs of the key facts.
2. **More clothing colours** (mod `clothes-plus`, data in `colours.json`): each new colour is one RGB value;
   the tool makes its 3 and 4 shades like the game's own. The palette builder is hooked to take colours 32+
   from our table; the pickers' limit is raised; the save's 5-bit fields keep `colour % 32` and the mod's
   save block keeps the rest, so a vanilla game never sees an out-of-range number. Proof: pick a new colour
   in The Threads with real taps, see it on the Urb, save, power off, load: still there; a save made with
   the mod loads (with old colours) without it.
3. **New clothing styles** (styles 6 and 7 fit the save): a style = which slots (front, body, sleeves, ...)
   take which colour, written in `styles.json`; hook the style switch in `FUN_02083538`; raise the limit.
   Proof: the new style in The Threads and on the street.
4. **New catalog objects** (tool `urbz_objects.py`, mod with `objects.json`):
   - the object tables move into the code region (as the asset tables did) with room for new rows;
   - a new object = a base object it behaves like (e.g. a sofa: sit and sleep) + name, description, price,
     catalog page, and its art: `template <base>` gives the base object's sprites (each rotation, the
     catalog icon) as PNGs to draw over; `build` makes the new assets and rows;
   - NPC Life: townspeople can use new objects whose activities they have animations for.
   Proof: the new object is in the catalog, buy it, place it, use it, save and load: still there; a
   townsperson uses it (if it is a seat or a snack).
5. **Gate:** melonDS (boot, real taps for the pickers and the catalog), full proofs, docs (README sections for
   Jonathan: adding colours, drawing an object), commit, push. Jonathan tests on the Thor.

## Risks / open questions
- The pickers may draw a fixed grid of 32 swatches: more colours may need a second page or a scroll.
- A save with new objects loaded **without** the objects mod would have unknown object numbers; step 1
  finds what the game does then, and the mod must keep such saves safe (e.g. keep the rows even when off).
- Placed-object art may be large (several rotations, big sprites): a template per object keeps it doable.
- Catalog pages may have a maximum item count.
