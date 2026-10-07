/* Max Needs (testing aid): while switched on (Options > Mods > Max Needs), the player's 8 needs are kept full.
   The needs are player_motives: s32[8], the top byte 0-100 (docs/systems.md "Needs"). */
#include "game.h"
#include "mod.h"

#define FULL 0x64000000                         /* 100 */

struct { u32 magic, ticks; } max_needs = { 0x4D58414D, 0 };   /* 'MAXM' (tests) */

void mod_on_tick(void)
{
    s32 *m = (s32 *)ADDR_player_motives;
    for (int i = 0; i < 8; i++)
        m[i] = FULL;
    max_needs.ticks++;
}
