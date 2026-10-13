#include "game.h"
#include "mod.h"

/* Test: when `anim` is poked (non-zero), the player plays it (again every `every` ticks). */
#define play_anim GAME_FN(ADDR_entity_play_anim, void (*)(void *e, int anim))

struct { u32 magic; u16 anim, every; u32 ticks, played; } player_anim = { 0x4D494E41, 0, 150 };   /* 'ANIM' */
static u16 last;

void mod_on_tick(void)
{
    player_anim.ticks++;
    if (!player_anim.anim)
        return;
    if (player_anim.anim == last && player_anim.ticks % player_anim.every)
        return;
    last = player_anim.anim;
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e)
        if (*(u16 *)(e + 8) == 0) {
            play_anim(e, player_anim.anim);
            player_anim.played++;
            return;
        }
}
