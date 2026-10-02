#include "game.h"
struct { u32 magic, calls; game_time_t last; } thumbtest = { 0x424D5554, 0, {0} };   /* 'TUMB' */

/* Compiled as Thumb on purpose: the builder must use BLX from the game's ARM code. */
__attribute__((target("thumb")))
unsigned thumb_time_add(game_time_t *t, const game_time_t *d)
{
    unsigned r = time_add(t, d);
    thumbtest.calls++;
    thumbtest.last = *t;
    return r;
}
