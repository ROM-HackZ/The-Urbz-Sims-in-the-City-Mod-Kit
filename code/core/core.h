/* Mod core internals shared by its files (modcore.c, page.c). */
#pragma once
#include "mod.h"

typedef struct {
    u32 magic;                 /* 'CORE' (tests find the state with it) */
    u32 request;               /* 0x80000000 | on << 8 | mod index: switch at the next tick
                                  (tests poke this; the Mods page calls core_set directly) */
    u32 booted, ticks, saves, loads, new_games, record_writes;
    u32 record_found;          /* 1 = the switch record in save memory was read */
    u32 time_ok, last_minute;  /* game-minute tracking for on_minute */
    u32 loaded;                /* set by core_load inside core_game_start */
    u32 carry_len;             /* bytes in the carry buffer */
    u32 saved_bytes, loaded_bytes;   /* size of the mod block in the last save / load */
} core_state_t;

extern core_state_t core;
void core_set(int index, int on);
