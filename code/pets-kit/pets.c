/* Kit code for pets (built in whenever a mod has pets.json; see urbz_pets.py). A pet is like the
   Chicken: its object (a copy of object 225) placed at home turns into a critter of the pet's own kind,
   and picking that critter up puts the object back in Pockets. The builder writes the list
   {u16 object, u16 kind} x n, then u32 n, just before the (moved) critter behaviour table. */
#include "game.h"
#include "mod.h"

#define PETM 0x4D544550                          /* 'PETM' */

typedef struct { u16 object, kind; } pet_t;

struct { u32 magic, spawned, picked, pets; } pets_count = { 0x43544550, 0, 0, 0 };   /* 'PETC' (tests) */

static const pet_t *pet_list(u32 *n)
{
    const u8 *table = *(const u8 **)ADDR_crit_table_lit;
    *n = *(const u32 *)(table - 4);
    const pet_t *p = (const pet_t *)(table - 4 - 4 * *n);
    if (*n > 64 || *((const u32 *)p - 1) != PETM)
        *n = 0;
    return p;
}

/* The object a pet critter gives back (0 = not a pet). */
unsigned pets_object_of(unsigned kind)
{
    u32 n;
    const pet_t *p = pet_list(&n);
    for (u32 i = 0; i < n; i++)
        if (p[i].kind == kind)
            return p[i].object;
    return 0;
}

/* ---- my pets: the pets placed at home, kept in the save (the game forgets critters when you leave) ---- */
#define MAX_MINE 12
#define SAVE_MAGIC 0x31544550                    /* 'PET1' */
typedef struct {
    u16 object;                                  /* the pet's object number (what goes back to Pockets) */
    u8 kind, facing;
    s16 x, y;                                    /* where it was last seen, in its home area */
    u8 area, hunger, happy, flags;               /* hunger/happy 0-100 (Phase 9 needs) */
} mypet_t;

static mypet_t mine[MAX_MINE];
static u8 *live[MAX_MINE];                      /* its critter while we're in that area (not saved) */
static u32 n_mine;
struct { u32 magic, kept, respawned, forgot, loads, loaded, ticks_home; } pets_stats = { 0x53544550, 0, 0, 0, 0, 0, 0 };   /* 'PETS' (tests) */

#define ENT_TYPE(e)  (*(u16 *)((e) + 8))
#define ENT_KIND(e)  (*(u16 *)((e) + 10))
#define ENT_FLAGS(e) (*(u32 *)((e) + 0xC))
#define ENT_X(e)     ((s16)(*(s32 *)((e) + 0x18) >> 16))
#define ENT_Y(e)     ((s16)(*(s32 *)((e) + 0x1C) >> 16))
#define is_home_area GAME_FN(ADDR_is_home_area, unsigned (*)(const void *lots, unsigned area))

static int alive(u32 i)
{
    u8 *e = live[i];
    return e && ENT_TYPE(e) == 9 && ENT_KIND(e) == mine[i].kind && !(ENT_FLAGS(e) & 2);
}

static void pets_keep(u16 object, u8 kind, u8 *e)
{
    if (!e || n_mine >= MAX_MINE)
        return;
    mypet_t *m = &mine[n_mine];
    m->object = object;
    m->kind = kind;
    m->facing = e[0x12];
    m->x = ENT_X(e);
    m->y = ENT_Y(e);
    m->area = (u8)current_area;
    m->hunger = m->happy = 80;
    m->flags = 0;
    live[n_mine++] = e;
    pets_stats.kept++;
}

/* The pick-up gave this critter back to Pockets: it is no longer one of mine. */
void pets_forget(u8 *e)
{
    for (u32 i = 0; i < n_mine; i++) {
        if (live[i] != e)
            continue;
        for (u32 j = i; j + 1 < n_mine; j++) {
            mine[j] = mine[j + 1];
            live[j] = live[j + 1];
        }
        n_mine--;
        pets_stats.forgot++;
        return;
    }
}

static void *player_entity(void)
{
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e)
        if (ENT_TYPE(e) == 0)
            return e;
    return 0;
}

static u32 need_spawn;                           /* an area was entered or a game loaded */

static void spawn_mine(int area)
{
    u8 *pl = player_entity();
    for (u32 i = 0; i < n_mine; i++) {
        mypet_t *m = &mine[i];
        if (alive(i))
            continue;
        if (m->area != (u8)area) {                /* a new home: next to the player */
            m->x = pl ? ENT_X(pl) + 16 * (int)(i % 3) - 16 : 128;
            m->y = pl ? ENT_Y(pl) + 12 + 8 * (int)(i / 3) : 128;
            m->area = (u8)area;
        }
        live[i] = spawn_critter(m->kind, m->facing, 0, m->x, m->y);
        pets_stats.respawned++;
    }
}

/* Every tick: after an area was entered (or a game loaded, which happens inside the first area entry), put
   my pets back at home; every second, note where they are. */
void mod_on_tick(void)
{
    static u32 t;
    if (need_spawn) {
        need_spawn = 0;
        pets_stats.ticks_home = current_area | n_mine << 16;
        if (n_mine && is_home_area((const void *)ADDR_home_lot, current_area))
            spawn_mine((int)current_area);
    }
    if (++t % 30)
        return;
    for (u32 i = 0; i < n_mine; i++) {
        if (!alive(i)) {
            live[i] = 0;
            continue;
        }
        mine[i].x = ENT_X(live[i]);
        mine[i].y = ENT_Y(live[i]);
        mine[i].facing = live[i][0x12];
    }
}

void mod_on_area_enter(int area)
{
    (void)area;
    for (u32 i = 0; i < n_mine; i++)
        live[i] = 0;                              /* leaving an area frees its critters */
    need_spawn = 1;
}

/* The core hands us unaligned buffers (6-byte block headers): bytes only. */
static void put_bytes(u8 *dst, const void *src, u32 n)
{
    const u8 *s = src;
    while (n--)
        *dst++ = *s++;
}

int mod_on_save(u8 *buf, int max)
{
    int len = 8 + (int)n_mine * (int)sizeof(mypet_t);
    if (len > max)
        return -1;
    u32 head[2] = { SAVE_MAGIC, n_mine };
    put_bytes(buf, head, 8);
    put_bytes(buf + 8, mine, (u32)len - 8);
    return len;
}

void mod_on_load(const u8 *buf, int len)
{
    pets_stats.loads++;
    n_mine = 0;
    for (u32 i = 0; i < MAX_MINE; i++)
        live[i] = 0;
    u32 head[2];
    if (!buf || len < 8)
        return;
    put_bytes((u8 *)head, buf, 8);
    if (head[0] != SAVE_MAGIC || head[1] > MAX_MINE || 8 + head[1] * sizeof(mypet_t) > (u32)len)
        return;
    put_bytes((u8 *)mine, buf + 8, head[1] * sizeof(mypet_t));
    n_mine = head[1];
    pets_stats.loaded = n_mine;
    need_spawn = 1;
}

#define obj_removed_orig GAME_FN(ADDR_pet_object_removed, void (*)(u8 *obj))

/* Class +0x14 of every pet object: what the Chicken's does, with the pet's kind. */
void pets_removed(u8 *obj)
{
    u32 n;
    const pet_t *p = pet_list(&n);
    u8 *e = *(u8 **)(obj + 0x24);
    for (u32 i = 0; i < n; i++) {
        if (p[i].object != *(u16 *)(obj + 8))
            continue;
        if (*(u32 *)(e + 0xC) & 2)
            return;
        u8 *c = spawn_critter(p[i].kind, e[0x12], obj[0x4A], (s16)(*(s32 *)(e + 0x18) >> 16),
                              (s16)(*(s32 *)(e + 0x1C) >> 16));
        pets_keep(p[i].object, p[i].kind, c);
        pets_count.spawned++;
        entity_set_state(e, 1);
        return;
    }
    obj_removed_orig(obj);
}

/* critter_pickup (state 0x12, action 0x0E) after the Chicken case: r0 = kind, r5 = 0 (result). */
__attribute__((naked)) void pets_pick_stub(void)
{
    __asm__ volatile(
        "cmp r0, #5\n"
        "ldreq pc, =0x0202A2E0\n"          /* the Nutria: the game's own code */
        "bl pets_object_of\n"
        "cmp r0, #0\n"
        "ldreq pc, =0x0202A2FC\n"          /* not a pet: nothing to give back */
        "mov r1, r0\n"
        "ldr r0, =0x02141274\n"            /* pockets_ptr */
        "ldr r0, [r0]\n"
        "mov r2, #0\n"
        "mov r3, #0\n"
        "ldr ip, =0x0203D0CC\n"            /* list_add */
        "blx ip\n"
        "mov r5, r0\n"
        "cmp r0, #1\n"
        "moveq r0, r6\n"                  /* r6 = the critter */
        "bleq pets_forget\n"
        "ldr r0, =pets_count\n"
        "ldr r1, [r0, #8]\n"
        "add r1, r1, #1\n"
        "str r1, [r0, #8]\n"
        "ldr pc, =0x0202A2FC\n"            /* "cmp r5, #1": in Pockets -> the critter goes */
        ".ltorg\n");
}

/* critter_behaviour switches to the walk animation (slot 1) when a critter starts moving and back to
   stand (slot 0) when it stops, but only for kind 1 (the Chicken). Both "ldrh r0, [r4, #0xA]; cmp r0, #1"
   jump here: pets count as kind 1 for this test, so they walk instead of sliding in their stand pose. */
unsigned pets_anim_kind(unsigned kind)
{
    return kind == 1 || pets_object_of(kind) ? 1 : kind;
}

__attribute__((naked)) void pets_walk_stub(void)
{
    __asm__ volatile(
        "ldrh r0, [r4, #0xA]\n"
        "bl pets_anim_kind\n"
        "cmp r0, #1\n"
        "ldr pc, =0x0202A744\n"           /* bne: no walk anim */
        ".ltorg\n");
}

__attribute__((naked)) void pets_stop_stub(void)
{
    __asm__ volatile(
        "ldrh r0, [r4, #0xA]\n"
        "bl pets_anim_kind\n"
        "cmp r0, #1\n"
        "ldr pc, =0x0202A768\n"           /* bne: no stand anim */
        ".ltorg\n");
}

/* The player picking a critter up (critter_tap) only accepts kinds 1-2 (chicken, rooster): pets count
   as kind 1. r0, r3 and ip are live there. */
__attribute__((naked)) void pets_tap_stub(void)
{
    __asm__ volatile(
        "push {r0, r3, ip, lr}\n"
        "ldrh r0, [r5, #0xA]\n"
        "bl pets_anim_kind\n"
        "mov r2, r0\n"
        "pop {r0, r3, ip, lr}\n"
        "ldr r1, =0xFFFF\n"
        "ldr pc, =0x0202A578\n"
        ".ltorg\n");
}

void mod_on_boot(void)
{
    u32 n;
    const pet_t *p = pet_list(&n);
    u8 *cls = *(u8 **)ADDR_obj_class_lit;               /* the (moved) object class table */
    for (u32 i = 0; i < n; i++)
        *(void (**)(u8 *))(cls + p[i].object * 0x24 + 0x14) = pets_removed;
    pets_count.pets = n;
}
