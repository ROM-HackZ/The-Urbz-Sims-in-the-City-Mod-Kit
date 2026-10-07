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
    u32 page_ready, page_taps;       /* Mods page set up; taps handled on it */
    u32 obj_stashed, obj_restored;   /* objects this build doesn't know, kept aside / put back (objguard.c) */
    u32 obj_dropped, obj_lost;       /* unknown shop stock dropped; stash full */
} core_state_t;

extern core_state_t core;
void core_set(int index, int on);
void core_page_init(void);
const u8 *objects_guard(const u8 *old, int n, int *len);
#define OBJS_HASH 0x534A424FU          /* 'OBJS': the carried stash of unknown objects */
