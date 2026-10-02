# Mods overlay

Mods keep `project/` pristine. Each `mods/<name>/` holds only changed or added files at project-relative paths. `mods.json` lists the enabled mods in order, and later mods win.

## Sub-features

- `mods-new` creates and enables a mod.
- `mods-edit` copies a pristine asset or chunk into a mod for editing.
- `mods-status` classifies mod files: changed / identical / new / unknown.
- `mods-toggle` enables or disables a mod.
- `mods-rescue` moves accidental edits made in `project/` into a mod and restores pristine files.
- `mods-new-asset` adds assets past the last ID with no gaps.
- `mods-errors` covers unknown chunk files, raw+chunk conflicts, gaps in new IDs, and missing mod folders.

## How to get to it (user POV)

- Run `python urbz_mod.py new|edit|status|list|enable|disable|rescue ...`.
- Edit files under `mods/<name>/` in any hex or image tool, then build.

## Driving it with the kit CLI

Preconditions: a vanilla build is identical; no mod named `verify-tmp` exists.

- **Create.** Run `python urbz_mod.py new verify-tmp "verification scratch"`. `python urbz_mod.py list` shows `#N verify-tmp`.
- **Edit.** Run `python urbz_mod.py edit verify-tmp 10747`, then swap red/blue in the palette (halfwords 2..512) of `mods/verify-tmp/unpacked/10747/000000.bin`.
- **Status.** Run `python urbz_mod.py status verify-tmp`. It shows `changed unpacked/10747/000000.bin`.
- **Build.** Run `python urbz_build.py --mod verify-tmp /tmp/m.nds`. The SHA1 must be `0e82919bf6be4c440eff433bf289576fe391983d`.
- **Proof.** Run `python verify/urbz_verify.py smoke /tmp/m.nds`. Expect `SMOKE PASS`, with `step1`–`step3` showing ~23% changed (EA logo red; step3 still has it on the bottom screen) `step0` and `step4` 0.0%, and `step5` up to ~2% (decode-timing shift of the Create-a-Bod animation; see boot.md). Keep `compare.png`.
- **Errors.** Each of these must stop with a `BUILD FAILED` message naming the problem:
  - a file `unpacked/10747/000123.bin`
  - `assets/13387.bin` with no `13385`
  - a mod that both replaces `assets/10747.bin` and edits its chunks
  - `--mod nope`

## Gotchas

- `mod.json` and README files inside a mod are ignored by the builder.
- `identical` files are harmless but clutter a mod. Delete them.
- Cleanup: `python urbz_mod.py disable verify-tmp`, then delete `mods/verify-tmp`. Never touch `verify/evidence/`.
