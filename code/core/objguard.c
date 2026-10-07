/* Saves that hold objects this build doesn't have (2026-10-07).

   A mod adds objects (the pets, their beds, new furniture); the save keeps their numbers. Load that save in
   a build without the mod and the game looks them up in tables that don't have them: the screen went black.
   Right after the game reads a save (core_load), anything this build doesn't know is taken out of the
   placed objects and the item lists and kept aside in the mod block ("OBJS", carried like the data of a
   mod that is off). A later load in a build that knows them again puts them back where they were.

   What a build knows: numbers below the object count (the shop_pick literal, raised by urbz_objects) that
   are the game's own or rows a mod defined (a defined new object copies another: like[obj] != obj; gaps
   copy themselves). The markers 387 (random pick) and 388 (empty slot) are left alone. Shop stock that
   isn't known is just dropped: the shop restocks. */
#include "game.h"
#include "core.h"

#define N_GAME_OBJECTS 386
#define LAST_OBJECT 511
#define NEWO 0x4F57454E
#define N_AREAS 82
#define N_PLACED 160
#define STASH_MAX 640
#define T_PLACED 1                            /* stash entries: {u8 type, u8 area or list, record} */
#define T_ITEM 2

static u8 stash[STASH_MAX];
static int stash_len;

static unsigned get16(const u8 *p) { return p[0] | p[1] << 8; }

static void move_down(u8 *dst, const u8 *src, int n)   /* dst < src, overlapping */
{
    for (int i = 0; i < n; i++)
        dst[i] = src[i];
}

static int known(unsigned obj)
{
    if (obj == 387 || obj == 388)
        return 1;
    if (obj >= *(const u32 *)ADDR_shop_pick_count_lit)
        return 0;
    if (obj < N_GAME_OBJECTS)
        return 1;
    const u8 *text = *(const u8 **)ADDR_obj_text_lit;
    const u16 *like = (const u16 *)(text - 2 * (LAST_OBJECT + 1));
    if (*(const u32 *)((const u8 *)like - 4) != NEWO)
        return 0;
    return like[obj] != obj;
}

static void stash_put(int type, int where, const u8 *rec, int len)
{
    if (stash_len + 2 + len > STASH_MAX) {
        core.obj_lost++;
        return;
    }
    stash[stash_len] = type;
    stash[stash_len + 1] = where;
    memcpy(stash + stash_len + 2, rec, len);
    stash_len += 2 + len;
    core.obj_stashed++;
}

/* ---- placed objects: u16 total, records of 10 bytes, per area {u8 first, u8 count} ---------------- */
#define TOTAL(s)    ((s)[0] | (s)[1] << 8)
#define REC(s, i)   ((s) + 2 + 10 * (i))
#define FIRST(s, a) ((s)[0x642 + 4 * (a)])
#define COUNT(s, a) ((s)[0x643 + 4 * (a)])

static void set_total(u8 *s, int n)
{
    s[0] = n;
    s[1] = n >> 8;
}

static void placed_remove(u8 *s, int a, int i)
{
    int total = TOTAL(s);
    move_down(REC(s, i), REC(s, i + 1), 10 * (total - i - 1));
    memset(REC(s, total - 1), 0, 10);
    set_total(s, total - 1);
    COUNT(s, a)--;
    for (int b = a + 1; b < N_AREAS; b++)
        FIRST(s, b)--;
}

static int placed_insert(u8 *s, int a, const u8 *rec)
{
    if (!s || a >= N_AREAS || TOTAL(s) >= N_PLACED)
        return 0;
    int total = TOTAL(s);
    int pos = FIRST(s, a) + COUNT(s, a);
    for (int i = total; i > pos; i--)                 /* (overlapping: one record at a time, from the end) */
        memcpy(REC(s, i), REC(s, i - 1), 10);
    memcpy(REC(s, pos), rec, 10);
    set_total(s, total + 1);
    COUNT(s, a)++;
    for (int b = a + 1; b < N_AREAS; b++)
        FIRST(s, b)++;
    return 1;
}

/* ---- item lists: {u8 count, u8 capacity, u16, slots of 6 bytes} --------------------------------- */
static u8 *list_header(int L) { return (u8 *)ADDR_item_lists + 8 * L; }

static void list_remove(int L, int k)
{
    u8 *h = list_header(L), *slots = *(u8 **)(h + 4);
    int n = h[0];
    move_down(slots + 6 * k, slots + 6 * (k + 1), 6 * (n - k - 1));
    memset(slots + 6 * (n - 1), 0, 6);
    slots[6 * (n - 1)] = 388 & 0xFF;                  /* an empty slot */
    slots[6 * (n - 1) + 1] = 388 >> 8;
    h[0] = n - 1;
}

static int list_insert(int L, const u8 *slot)
{
    if (L >= 24)
        return 0;
    u8 *h = list_header(L), *slots = *(u8 **)(h + 4);
    if (!slots || h[0] >= h[1])
        return 0;
    memcpy(slots + 6 * h[0], slot, 6);
    h[0]++;
    return 1;
}

/* After the game read a save: put back what this build knows from the save's stash (old, n bytes, or none),
   then take out what it doesn't. Returns the new stash (and its length) for the carry buffer. */
const u8 *objects_guard(const u8 *old, int n, int *len)
{
    u8 *s = *(u8 **)ADDR_placed_store_ptr;
    stash_len = 0;
    for (const u8 *p = old; p && p + 2 <= old + n;) {
        int type = p[0], where = p[1], size = type == T_PLACED ? 10 : 6;
        if ((type != T_PLACED && type != T_ITEM) || p + 2 + size > old + n)
            break;
        int back = known(get16(p + 2)) &&
            (type == T_PLACED ? placed_insert(s, where, p + 2) : list_insert(where, p + 2));
        if (back)
            core.obj_restored++;
        else
            stash_put(type, where, p + 2, size);
        p += 2 + size;
    }
    for (int a = 0; s && a < N_AREAS; a++)
        for (int k = 0; k < COUNT(s, a);) {
            int i = FIRST(s, a) + k;
            if (known(get16(REC(s, i)))) {
                k++;
                continue;
            }
            stash_put(T_PLACED, a, REC(s, i), 10);
            placed_remove(s, a, i);
        }
    for (int L = 0; L < 24; L++) {
        u8 *h = list_header(L), *slots = *(u8 **)(h + 4);
        for (int k = 0; slots && k < h[0];) {
            if (known(get16(slots + 6 * k))) {
                k++;
                continue;
            }
            if (L >= 21)                               /* (21 = ?, 22 = gifts, 23 = Pockets; 0-20: shop stock) */
                stash_put(T_ITEM, L, slots + 6 * k, 6);
            else
                core.obj_dropped++;
            list_remove(L, k);
        }
    }
    *len = stash_len;
    return stash;
}
