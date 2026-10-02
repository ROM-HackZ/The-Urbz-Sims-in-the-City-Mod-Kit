/* The Urbz DS (USA): what C code can use from the game.
   Addresses come from code/game.sym (see docs/systems.md for evidence).
   Game functions are called through absolute addresses, so mod code can be
   placed anywhere without a linker knowing the game. */
#pragma once
#include "game_syms.h"

typedef unsigned char u8;   typedef signed char s8;
typedef unsigned short u16; typedef signed short s16;
typedef unsigned int u32;   typedef signed int s32;

#define GAME_FN(addr, type) ((type)(addr))
#define GAME_VAR(addr, type) (*(volatile type *)(addr))

/* ---- clock ------------------------------------------------------------ */
typedef struct {
    s16 day;       /* days since the game started */
    s8 hour;       /* 0-23 */
    s8 minute;     /* 0-59 */
    s8 second;     /* 0-59 */
    s8 tick;       /* 0-29 (1/30 s) */
} game_time_t;

#define game_time        GAME_VAR(ADDR_game_time, game_time_t)
#define time_speed_table ((game_time_t *)ADDR_time_speed_table)
#define time_speed_index GAME_VAR(ADDR_time_speed_index, u8)

/* t += delta, normalised. Returns bits: 2 = minute, 4 = hour, 8 = day changed. */
#define time_add GAME_FN(ADDR_time_add, unsigned (*)(game_time_t *, const game_time_t *))

/* ---- assets / text ---------------------------------------------------- */
/* Load an asset from the cartridge and return where it sits in RAM
   (flags 0, unpack 0 = keep its chunks as stored). Game id = file number + 1. */
#define get_asset    GAME_FN(ADDR_get_asset, void *(*)(int game_id, int flags, int unpack))
/* Decode one chunk (header word + data) with the game's own decoders. Returns the size. */
#define decode_chunk GAME_FN(ADDR_decode_chunk, u32 (*)(const void *chunk, void *dst))
#define text_decode GAME_FN(ADDR_text_decode, void (*)(int id, char *buf, int maxlen))

/* ---- small helpers (code/include/runtime.c) --------------------------- */
void *memcpy(void *d, const void *s, unsigned n);
void *memset(void *d, int c, unsigned n);

/* ---- people ------------------------------------------------------------- */
#define current_area GAME_VAR(ADDR_current_area, u32)
/* Is this person in this area at this time? (quest rules, then their weekly schedule) */
#define npc_present  GAME_FN(ADDR_npc_present, int (*)(unsigned char_id, unsigned area, game_time_t *t))
/* u8[24][7] area ids by hour and weekday, per character (char_id - 31); 0 = no schedule */
#define npc_schedule_table ((u8 **)ADDR_npc_schedule_table)
/* Where a person's weekly schedule puts them now (area id; 82 = out of town). The game
   calls this every 150 ticks for every person and walks them in or out of the current area. */
#define schedule_lookup GAME_FN(ADDR_schedule_lookup, unsigned (*)(unsigned char_id, game_time_t *t))
/* Create a person on the current screen (x, y in the area's map units, 16.16 fixed point). */
#define spawn_npc    GAME_FN(ADDR_spawn_npc, void *(*)(unsigned char_id, int facing, int x, int y))
