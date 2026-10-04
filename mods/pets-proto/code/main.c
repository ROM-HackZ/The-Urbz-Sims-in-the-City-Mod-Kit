/* Pets prototype: a Puppy (object 386, copies the Chicken) you place at home; it runs around as a
   new critter kind (7) and can be picked up again. Art: the dark rooster's for now.

   How the Chicken works (docs/systems.md "Pets"): placing object 225 makes the object, whose
   "removed" function (class +0x14) swaps it for critter kind 1; picking the critter up puts
   object 225 back in Pockets. The Puppy does the same with its own numbers. */
#include "game.h"
#include "mod.h"

#define PUPPY_OBJECT 386
#define PUPPY_KIND   7
#define ART_KIND     2              /* dark rooster: placeholder art */
#define N_KINDS      8

typedef struct { u32 w[5]; } crit_row_t;          /* critter_table: 0x14 bytes per kind */
typedef struct { u32 w[10]; } crit_anim_t;        /* critter_anims: 5 x {records, frame script} */

crit_row_t crit_table[N_KINDS] = { { { 1 } } };   /* (non-zero: kept in the mod's data) */
crit_anim_t crit_anims[N_KINDS] = { { { 1 } } };
u32 crit_palettes[N_KINDS] = { 1 };

struct { u32 magic, spawned, picked; } pets = { 0x53544550, 0, 0 };   /* 'PETS' (tests read it) */

#define obj_removed_orig GAME_FN(ADDR_pet_object_removed, void (*)(u8 *obj))

/* Class +0x14 for the Puppy: what the Chicken's does, with the Puppy's kind. */
void pets_removed(u8 *obj)
{
    u8 *e = *(u8 **)(obj + 0x24);
    if (*(u16 *)(obj + 8) != PUPPY_OBJECT) {
        obj_removed_orig(obj);
        return;
    }
    if (*(u32 *)(e + 0xC) & 2)
        return;
    spawn_critter(PUPPY_KIND, e[0x12], obj[0x4A], (s16)(*(s32 *)(e + 0x18) >> 16),
                  (s16)(*(s32 *)(e + 0x1C) >> 16));
    pets.spawned++;
    entity_set_state(e, 1);
}

/* critter_update, picking up: r0 = kind, r5 = 0 (result), r6 = the critter. */
__attribute__((naked)) void pets_pick_stub(void)
{
    __asm__ volatile(
        "cmp r0, #5\n"
        "ldreq pc, =0x0202A2E0\n"          /* the Nutria: the game's own code */
        "cmp r0, #7\n"
        "ldrne pc, =0x0202A2FC\n"          /* other kinds: nothing to give back */
        "ldr r0, =0x02141274\n"            /* pockets_ptr */
        "ldr r0, [r0]\n"
        "ldr r1, =386\n"
        "mov r2, #0\n"
        "mov r3, #0\n"
        "ldr ip, =0x0203D0CC\n"            /* list_add */
        "blx ip\n"
        "mov r5, r0\n"
        "ldr r0, =pets\n"
        "ldr r1, [r0, #8]\n"
        "add r1, r1, #1\n"
        "str r1, [r0, #8]\n"
        "ldr pc, =0x0202A2FC\n"            /* "cmp r5, #1": in Pockets -> the critter goes */
        ".ltorg\n");
}

void mod_on_boot(void)
{
    memcpy(crit_table, (void *)ADDR_critter_table, 7 * sizeof(crit_row_t));
    memcpy(crit_anims, (void *)ADDR_critter_anims, 7 * sizeof(crit_anim_t));
    memcpy(crit_palettes, (void *)ADDR_critter_palettes, 7 * 4);
    crit_table[PUPPY_KIND] = crit_table[ART_KIND];
    crit_anims[PUPPY_KIND] = crit_anims[ART_KIND];
    crit_palettes[PUPPY_KIND] = crit_palettes[ART_KIND];
    u8 *cls = *(u8 **)ADDR_obj_class_lit;                  /* the (moved) class table */
    *(void (**)(u8 *))(cls + PUPPY_OBJECT * 0x24 + 0x14) = pets_removed;
}
