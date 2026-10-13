/* Bug Fixes: bugs of the original game, fixed. Each fix says what goes wrong, how it was found and which proof
   in tests/proofs.py shows it (the bug in the original ROM, and gone with this mod). List: ../README.md.
   Switched off on the Mods page, the game behaves as the original again. */
#include "game.h"
#include "mod.h"

#define E8(e, o)  (*(u8 *)((e) + (o)))
#define E16(e, o) (*(u16 *)((e) + (o)))
#define E32(e, o) (*(u32 *)((e) + (o)))
#define path_cancel GAME_FN(ADDR_path_cancel, void (*)(void *e))
#define walked_out  GAME_FN(ADDR_npc_walked_out, void (*)(void *e))

struct { u32 magic, ticks, let_out; } bug_fixes = { 0x58494642, 0, 0 };   /* 'BFIX' (tests read this) */

static u8 *world_first(void) { return *(u8 **)ADDR_entity_lists; }

/* ---- Fix 1: people who can't get out (proof fix-stuck-leaving) ----------------------------------------------
   The game sends someone out of the area by walking them to a way point (a door or lift; npc_walk_out sets entity
   +0x107 bit 1 and the target at +0x38). When that walk fails while they're on screen (you, or someone, standing
   on the spot), the game puts them back to wandering and tries again at its next relocation, every 5 s, for ever
   (off screen it just lets them go). In Waters' Gym, Sue Pirnova paced by the lift from 6:00 to past 8:30.
   Here: after 20 s of trying, someone within 64 px of their way point goes through it as if they had arrived;
   after 60 s, wherever they are. Only people wandering on their own (+0x104 = 0x23 with action 2, 7 or 0x19):
   not someone talking to you, in a story scene, or doing something for another mod. */
#define PEOPLE     49                           /* ids 31..79 */
#define LEAVE_NEAR (64 * 64)
static u32 leave_since[PEOPLE], leave_seen[PEOPLE];

static void let_stuck_people_out(u32 now)
{
    for (u8 *e = world_first(); e; e = *(u8 **)e) {
        int i = E16(e, 10) - 31;
        if (E16(e, 8) != 7 || i < 0 || i >= PEOPLE)
            continue;
        if (E8(e, 0x107) & 2) {                       /* the bit goes off after each failed walk: count from the first */
            if (!leave_since[i] || now - leave_seen[i] > 600)
                leave_since[i] = now;
            leave_seen[i] = now;
        } else if (!leave_since[i] || now - leave_seen[i] > 600) {
            leave_since[i] = 0;                       /* not asked again for 20 s: they stay after all */
            continue;
        }
        u32 t = now - leave_since[i];
        int a = E8(e, 0x105);
        if (t < 600 || E8(e, 0x104) != 0x23 || (a != 2 && a != 7 && a != 0x19) || !E32(e, 0x38))
            continue;
        int dx = ((s32)E32(e, 0x18) - (s32)E32(e, 0x38)) >> 16, dy = ((s32)E32(e, 0x1C) - (s32)E32(e, 0x3C)) >> 16;
        if (dx * dx + dy * dy > LEAVE_NEAR && t < 1800)
            continue;
        path_cancel(e);                               /* what the game does when they reach the way point */
        entity_set_state(e, 1);
        walked_out(e);
        leave_since[i] = 0;
        bug_fixes.let_out++;
    }
}

void mod_on_area_enter(int area)
{
    (void)area;
    for (int i = 0; i < PEOPLE; i++)                  /* new area, new people */
        leave_since[i] = 0;
}

void mod_on_tick(void)
{
    u32 now = ++bug_fixes.ticks;
    if (now & 15)
        return;
    let_stuck_people_out(now);
}
