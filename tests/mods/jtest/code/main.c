#include "game.h"
/* Replaces motive_get: every need reads as 100 (display and game logic). */
unsigned full_motive_get(const s32 *motives, int i)
{
    (void)motives; (void)i;
    return 100;
}
