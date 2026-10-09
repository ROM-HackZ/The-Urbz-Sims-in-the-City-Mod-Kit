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

/* ---- New actions (objects.json "actions", urbz_objects.py) ---------------------------------------------
   A new object can offer actions of its own: a menu entry (a new activity number, 120+, in the moved
   activity table) that plays like one of the object's own activities ("as": walk there, its animation and
   effects) plus extra need changes per tick, and ends when its own need is full ("until") or after some game
   minutes. Rows sit before 'OPAL': {u16 object, u8 activity, u8 until, u8 quality, u8 0, u16 ticks, u8 as[4]
   (the activities of that name; the object offers one), s32 effects[8]} ..., u32 count, 'ACTS'. At power-on the objects' class rows (the moved copy) get the four
   wrappers below; the game's "go on using it?" check (object_use_continue) is replaced so that, during one of
   these actions, it adds the effects and asks about our need. */
#define ACTS 0x53544341

typedef struct {
    u16 object;
    u8 id, until, quality, pad;
    u16 ticks;
    u8 as[4];
    s32 effect[8];
} act_t;

typedef int (*use_fn)(void *, void *, int);

static const act_t *act_rows(unsigned *n)
{
    const u8 *text = *(const u8 **)ADDR_obj_text_lit;
    const u32 *m = (const u32 *)(text - 2 * (LAST_OBJECT + 1) - 4);
    *n = 0;
    if (m[0] != NEWO || m[-1] != OPAL)
        return 0;
    const u32 *a = (const u32 *)((const u8 *)(m - 2) - 20 * m[-2]);
    if (a[-1] != ACTS)
        return 0;
    *n = a[-2];
    return (const act_t *)((const u8 *)(a - 2) - sizeof(act_t) * *n);
}

static const act_t *act_of(unsigned obj, unsigned id)
{
    unsigned n;
    const act_t *a = act_rows(&n);
    for (unsigned k = 0; k < n; k++)
        if (a[k].object == obj && a[k].id == id)
            return &a[k];
    return 0;
}

static use_fn like_fn(void *node, int slot)
{
    unsigned like = object_like(*(u16 *)((u8 *)node + 8));
    return ((use_fn *)(ADDR_object_class_table + 0x24 * like))[slot];
}

/* The activity "as" stands for that this object offers (several share a name: "Sit" is 41 and 56). */
static int base_of(void *node, const act_t *a)
{
    u8 own[8] = { 0 };
    ((int (*)(void *, u8 *))like_fn(node, 1))(node, own);
    for (int k = 0; k < 7 && own[k]; k++)
        for (int j = 0; j < 4 && a->as[j]; j++)
            if (own[k] == a->as[j])
                return own[k];
    return -1;
}

#define user_record GAME_FN(ADDR_object_user_record, u8 *(*)(void *node, void *person))
#define apply_effect GAME_FN(ADDR_motive_apply_effect, void (*)(s32 *needs, int row, int quality))
#define need_of GAME_FN(ADDR_motive_get, unsigned (*)(s32 *needs, int i))

static struct { u8 *rec; const act_t *a; u16 left; } tags[4];
static int cur = -1;                                  /* the tag whose object is ticking now */

static int tag_of(u8 *rec)
{
    for (int k = 0; k < 4; k++)
        if (rec && tags[k].rec == rec)
            return k;
    return -1;
}

int objects_acts(void *node, u8 *out)
{
    int r = ((int (*)(void *, u8 *))like_fn(node, 1))(node, out);
    unsigned obj = *(u16 *)((u8 *)node + 8), n, k = 0;
    const act_t *a = act_rows(&n);
    while (k < 7 && out[k])
        k++;
    for (unsigned i = 0; i < n && k < 7; i++)
        if (a[i].object == obj && base_of(node, &a[i]) >= 0)
            out[k++] = a[i].id;
    return r;
}

int objects_can_start(void *node, void *person, int id)
{
    const act_t *a = act_of(*(u16 *)((u8 *)node + 8), id);
    int base = a ? base_of(node, a) : id;
    return base >= 0 && like_fn(node, 2)(node, person, base);
}

int objects_start(void *node, void *person, int id)
{
    const act_t *a = act_of(*(u16 *)((u8 *)node + 8), id);
    int base = a ? base_of(node, a) : id;
    if (base < 0)
        return 0;
    int r = like_fn(node, 3)(node, person, base);
    u8 *rec = user_record(node, person);
    int t = tag_of(rec);
    if (t >= 0)
        tags[t].rec = 0;
    if (r == 1 && a && rec)
        for (int k = 0; k < 4; k++)
            if (!tags[k].rec) {
                tags[k].rec = rec;
                tags[k].a = a;
                tags[k].left = a->ticks;
                break;
            }
    return r;
}

int objects_tick(void *node, void *person)
{
    int t = tag_of(user_record(node, person));
    cur = t;
    int r = ((int (*)(void *, void *))like_fn(node, 4))(node, person);
    cur = -1;
    if (t >= 0 && (r == 0 || r == 2))
        tags[t].rec = 0;
    return r;
}

static s32 scratch[16];

/* Replaces object_use_continue (the game's, then ours during a new action). */
int objects_use_continue(u8 *rec, s32 *needs, int need, s16 *timer)
{
    if (cur >= 0 && tags[cur].rec == rec) {
        const act_t *a = tags[cur].a;
        if (needs) {                                  /* the effects: as a row of the game's table */
            u32 p = (u32)scratch, base = ADDR_motive_effect_table;
            p += (32 - ((p - base) & 31)) & 31;
            for (int k = 0; k < 8; k++)
                ((s32 *)p)[k] = a->effect[k];
            apply_effect(needs, (int)((p - base) >> 5), a->quality);
        }
        if (a->ticks && --tags[cur].left == 0)
            return 0;
        if (a->until >= 8)
            return rec[8] != 1;
        need = a->until;
    }
    if (rec[8] == 1)
        return 0;
    if (need < 8) {
        if (!needs || need_of(needs, need) >= 100) {
            if (timer && (*timer)-- == 0)
                return 0;
        }
    }
    return 1;
}

void mod_on_boot(void)
{
    unsigned n;
    const act_t *a = act_rows(&n);
    u8 *cls = *(u8 **)ADDR_obj_class_lit;
    for (unsigned k = 0; k < n; k++) {
        void **row = (void **)(cls + 0x24 * a[k].object);
        row[1] = (void *)objects_acts;
        row[2] = (void *)objects_can_start;
        row[3] = (void *)objects_start;
        row[4] = (void *)objects_tick;
    }
}
