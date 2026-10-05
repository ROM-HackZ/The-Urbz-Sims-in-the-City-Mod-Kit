/* Kit code for new catalog objects (built in whenever a mod has objects.json; see urbz_objects.py).
   A new object copies another ("like"). The game asks some questions by object number, with
   hard-coded numbers (e.g. "nothing numbered 224 or more can be placed, except the Chicken"),
   so for new objects we ask them about the object they copy. The "like" list sits just before
   the moved object text table, after the magic 'NEWO'. Game's own objects count as themselves. */
#include "game.h"

#define LAST_OBJECT 511
#define NEWO 0x4F57454E

unsigned object_like(unsigned obj)
{
    const u8 *text = *(const u8 **)ADDR_obj_text_lit;
    const u16 *like = (const u16 *)(text - 2 * (LAST_OBJECT + 1));
    if (obj > LAST_OBJECT || *(const u32 *)((const u8 *)like - 4) != NEWO)
        return obj;
    return like[obj];
}

/* Can the player put this object down here? (the carry/place code, 0x0203DF08) */
int objects_place_check(void *e, unsigned obj, unsigned rot)
{
    return place_object_check(e, object_like(obj), rot);
}

#define OPAL 0x4C41504F

/* Objects whose catalog colours are all 0xFD are drawn in a palette of their own (the game does this
   for object 61, the Personal Painting). New objects with their own art are listed by urbz_objects.py
   just before 'NEWO': {u16 object, u16 0, u32 palette ids[4]} ..., u32 count, 'OPAL'.
   Hooked at the call the game makes for object 61; tbl is the painting's own table. */
void objects_own_palette(void *e, const u32 *tbl)
{
    unsigned id = *(const u16 *)((const u8 *)e + 0xA);
    if (id == 0x3D) {
        entity_palette_table(e, tbl);
        return;
    }
    const u8 *text = *(const u8 **)ADDR_obj_text_lit;
    const u32 *magic = (const u32 *)(text - 2 * (LAST_OBJECT + 1) - 4);
    if (magic[0] != NEWO || magic[-1] != OPAL)
        return;
    unsigned n = magic[-2];
    const u8 *list = (const u8 *)(magic - 2) - 20 * n;
    for (unsigned k = 0; k < n; k++) {
        const u8 *row = list + 20 * k;
        if (*(const u16 *)row == id) {
            entity_palette_table(e, (const u32 *)(row + 4));
            return;
        }
    }
}
