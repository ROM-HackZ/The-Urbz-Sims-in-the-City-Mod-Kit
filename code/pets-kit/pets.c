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
        spawn_critter(p[i].kind, e[0x12], obj[0x4A], (s16)(*(s32 *)(e + 0x18) >> 16),
                      (s16)(*(s32 *)(e + 0x1C) >> 16));
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
