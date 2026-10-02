#include "game.h"

/* Counters the test harness finds by the magic word. */
struct {
    u32 magic;        /* 'HELO' */
    u32 ticks;        /* world ticks seen (wrap hook) */
    u32 time_calls;   /* clock updates routed through us (call hook) */
    game_time_t last; /* clock after our last update */
} hello = { 0x4F4C4548, 0, 0, {0} };

void on_tick(void)
{
    hello.ticks++;
}

unsigned my_time_add(game_time_t *t, const game_time_t *delta)
{
    unsigned r = time_add(t, delta);
    hello.time_calls++;
    hello.last = *t;
    return r;
}
