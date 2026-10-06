/* Research (Phase 9): open the game's question dialog (the rent sign's) with our own strings. */
#include "game.h"
#include "mod.h"
#define push_state GAME_FN(0x0204E038, void (*)(int state))
#define dialog_open GAME_FN(0x02078530, void (*)(void))
struct { u32 magic, ticks, opened; u32 res7c, resd4, state84, sel78; } spike = { 0x4B495053, 0, 0, 0, 0, 0, 0 };

void mod_on_tick(void)
{
    u32 scr = *(u32 *)0x027C0004;
    spike.res7c = *(u32 *)(0x027C007C + scr * 0x8C);
    spike.resd4 = *(u32 *)(0x027C00D4 + scr * 0x8C);
    spike.state84 = *(u32 *)(0x027C0084 + scr * 0x8C);
    spike.sel78 = *(u32 *)(0x027C0078 + scr * 0x8C);
    if (spike.opened || ++spike.ticks < 150 || current_area != 22)
        return;
    u16 *q = (u16 *)(0x02146EB8 + scr * 10);
    q[0] = 292; q[1] = 725; q[2] = 3657; q[3] = 3632; q[4] = 3654;
    u8 *b = (u8 *)(0x02146ECC + scr * 12);
    b[3] = 1; b[4] = 0;
    dialog_open();
    spike.opened = 1;
}
