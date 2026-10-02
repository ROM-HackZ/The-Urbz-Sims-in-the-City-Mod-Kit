# Extract

Extract unpacks The Urbz DS ROM into `project/` (format 4): 13,385 raw assets; 64,378 decoded chunks in three codecs (EA, LZ77, raw), with 0xE0 chunks stored after the delta filter; 623 embedded tile streams as `.tiles.bin`; `sprite_refs.json`; the sound bank; `base.nds`; and `manifest.json`.

## Sub-features

- `extract-full` creates the whole project from a ROM.
- `extract-manifest` records a SHA1 for every asset, chunk and tile stream.
- `extract-upgrade` brings an older project to format 4 in place: `python urbz_extract.py --upgrade project`.

## How to get to it (user POV)

- Run `python urbz_extract.py "<rom>.nds" project` (or `extract.bat` on Windows).

## Driving it with the kit CLI

Preconditions: an original ROM with SHA1 `3c01cc5c…2f2f`, and an empty target folder.

- **Extract.** Run `python urbz_extract.py "<rom>.nds" /tmp/proj-check`. It ends with `extracted 13385 assets (64378 compressed chunks unpacked)`.
- **Upgrade.** On a format-2 or format-3 copy, `python urbz_extract.py --upgrade <copy>` reports `added 1869 chunk files` (from format 3) and `4002 of 4006 multi-chunk assets can grow`. The vanilla build is still identical.
- **Proof.** Run `python urbz_build.py /tmp/proj-check /tmp/check.nds` (the legacy two-argument form). It must print `[IDENTICAL to original]`. Compare `sha1sum /tmp/proj-check/manifest.json` with `project/manifest.json`: the same ROM gives the same manifest.

## Gotchas

- Takes ~40 s natively. Through a remote/VM file mount it can take 10+ minutes because of the 76k small files.
- Extracting over an existing project leaves stale files. Use a fresh folder.
- Delete `/tmp/proj-check` afterwards; keep any evidence written elsewhere.
