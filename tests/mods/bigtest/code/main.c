#include "game.h"
#define N 16384
volatile u8 table[N] = { [0] = 1, [N - 1] = 2, [N / 2] = 3 };
u32 big_bss[2048];
struct { u32 magic, ticks, sum; } big = { 0x47494221, 0, 0 };
void big_tick(void)
{
    big.ticks++;
    big.sum = table[0] + table[N - 1] + table[N / 2] + big_bss[big.ticks & 2047];
}
