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
