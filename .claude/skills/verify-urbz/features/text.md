# Text editing

All 8,311 strings live in the Huffman text bank, asset 00054. A mod's `text/strings.tsv` (`ID<TAB>text`) overrides lines; the builder re-encodes the whole bank only when a mod changes text.

## Sub-features

- `text-find`: `python urbz_text.py find "<words>"` lists matching IDs.
- `text-edit`: `python urbz_text.py edit <mod> <ID>...` copies lines into the mod.
- `text-build`: the build summary says `text bank re-encoded`.
- `text-errors`: a bad ID, a line over 1,023 bytes, an unknown escape, a non-ASCII character, or a mod that both edits text and replaces assets/00054.bin each fail with `BUILD FAILED`.

## How to get to it (user POV)

- Edit `mods/<mod>/text/strings.tsv` in a text editor and build.

## Driving it with the kit CLI and urbz_verify

- **Title prompt.**
  - In mod `text-test`, run `python urbz_text.py edit text-test 27` and change it to `Welcome to the Living City! Spin the record, then touch the check box.`
  - Build and run `python verify/urbz_verify.py smoke <rom>`. `step4` shows the new prompt, word-wrapped (~1.5% changed).
- **Real dialogue.**
  - Edit 5870 (Kris: "What are you doing just sitting around?…") to `Hey @1! The whole city runs on rent and noodles now. Even I need a lunch break!` and 5873 to `Me too. Let's grab some grub!`.
  - Run `python verify/urbz_verify.py play <rom> --script verify/scripts/newgame.json --save /tmp/x.dst`.
  - `kris-line` shows the new line with @1 replaced by the player's name ("A"); `kris-replies` shows the new reply.
- **Offline.** `decode_bank(encode_bank(strings)) == strings` for all 8,311 strings.

## Gotchas

- Savestates already hold the decoded bank in RAM. Prove text changes from power-on (`newgame.json`), not from `world-start.dst`.
- Placeholders are filled in at runtime; don't expect `@1` in screenshots.
- Unedited projects never re-encode the bank (byte-identical builds).
