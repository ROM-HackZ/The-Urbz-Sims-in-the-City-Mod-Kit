# pets

New pets you buy and put down at home, like the Chicken: they run around, and you pick them up to put
them back in Pockets. Listed in `pets.json`:

| object | pet | starts from |
|---|---|---|
| 386 | Puppy | the dark rooster |
| 389 | Kitten | the chicken |

Each pet is sold where chickens are sold (shop list 9) and shown on the Catalog's Recreation page.
`from` decides how it moves and which art it wears until its own drawings exist (`art/<pet>/`, made with
`python urbz_art.py template pets <pet>`). Everything else is done by the kit (urbz_pets.py, code/pets-kit).

Numbers: this mod uses **386 and 389-429**; `more-furniture` uses 430-511. No in-game switch: pick it in
the mod manager before building. Like the game's own chickens, a pet left running is not kept by a save.
