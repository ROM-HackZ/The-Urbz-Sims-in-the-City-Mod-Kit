# pets

Pets you buy, put down at home and look after, plus beds for them and a stray puppy and kitten to win over in
Urbania Park. Everything is described in `pets.json` (the pets) and `objects.json` (treats and beds); the kit
does the rest (urbz_pets.py, code/pets-kit).

| object | pet | its bed |
|---|---|---|
| 386 | Puppy (also a stray in Urbania Park) | 397 Dog Basket |
| 389 | Kitten (also a stray in Urbania Park) | 398 Cat Bed |
| 390 | Bunny | 399 Rabbit Hutch |
| 391 | Hamster | 400 Small Pet House |
| 392 | Guinea Pig | 400 Small Pet House |
| 393 | Cockatoo | 401 Bird Cage |
| 394 | Macaw | 401 Bird Cage |
| 395 | Snake | (sleeps on the floor) |

The pets, Pet Treats (396) and the beds are sold at the Bayou Bazaar (Farmer's Market, list 9); treats, the
Dog Basket and the Cat Bed also at Drifter Woods' stall in Urbania Park (list 18).

**Looking after them.** Put a pet down from Pockets at home. Walk up to it and press A: Pet, Play, Feed (uses
one Pet Treats) or Put in Pocket. Food and fun go down slowly: one treat and a pet or a game a day keep a pet
happy; a hungry or bored one sulks. At night each pet sleeps in its own bed if you have one and it can get
there, otherwise on the floor. Pets stay in the room you're in. They are saved, move house with you, and
Options > Mods > Pets shows how each is doing (R / L to scroll). Only your own pets can be picked up.

**The strays.** Once you're out of jail, a stray Puppy and Kitten hang around Urbania Park. Feed one on two
different days and it trusts you: then Take Home. A townsperson adopts the other one.

**Pictures.** With `sources.json` (your own copy of The Sims 2: Apartment Pets) the pets and beds are rendered
from its models; without it they keep the look of the game animal or object they copy. Pets with the same
`"palette"` group (and beds with the same group in objects.json) share one set of 16 colours: the DS has only
about 7 colour sets free at home, and when each thing has its own they run out (the rest come out in the wrong
colours).

Numbers: this mod uses **386 and 389-429**; `more-furniture` uses 430-511. No in-game switch: pick it in the
mod manager before building.
