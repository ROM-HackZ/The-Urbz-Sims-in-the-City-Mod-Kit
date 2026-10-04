# pets

A Puppy (object 386): sold at the shop that sells chickens (shop list 9) and listed on the Catalog's
Recreation page. Put it down at home and it runs around like a chicken; pick it up and it goes back
to Pockets. It is a new kind of critter (kind 7); until the real drawings exist it uses the dark
rooster's art.

How it works: `code/main.c` (the critter tables move into this mod to make room for kind 7; the
Puppy's object turns into the critter when placed; a small stub in the pick-up code gives object 386
back). Details: docs/systems.md, "Pets".

This mod uses the object numbers **386 and 389-429**; `more-furniture` uses 430-511, so the two can
be built together. No in-game switch: pick it in the mod manager before building.
