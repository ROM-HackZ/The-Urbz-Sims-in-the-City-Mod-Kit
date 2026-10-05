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
/* The game's text for a string id (decoded into the game's own buffer). */
#define text_get    GAME_FN(ADDR_text_get, const char *(*)(int id))

/* ---- small helpers (code/include/runtime.c) --------------------------- */
void *memcpy(void *d, const void *s, unsigned n);
void *memset(void *d, int c, unsigned n);
int memcmp(const void *a, const void *b, unsigned n);
char *str_cat(char *dst, const char *s);   /* append; returns the new end */
char *str_int(char *dst, int v);           /* append a number; returns the new end */

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

/* ---- save file (docs/systems.md "Save file") ----------------------------- */
typedef struct {                 /* save_ctx: the slot stream being written or read */
    u8 pad0[0x20];
    u8 *slot;                    /* +0x20 slot buffer (0xFE0 bytes; u16 checksum at +0xFDE) */
    u8 pad1[0x84 - 0x24];
    u8 *cursor;                  /* +0x84 next byte */
    s32 bit;                     /* +0x88 bits used in the current byte (0 = aligned) */
    u32 used;                    /* +0x8C bytes used (set after a full save/load) */
} save_ctx_t;
#define save_ctx            (*(volatile save_ctx_t *)ADDR_save_ctx)
#define SAVE_SLOT_DATA      0xFDE          /* bytes of a slot before its checksum */
#define save_serialize_all   GAME_FN(ADDR_save_serialize_all, u32 (*)(u32, u32, u32, u32))
#define save_deserialize_all GAME_FN(ADDR_save_deserialize_all, u32 (*)(u32, u32, u32, u32))
#define save_boot_read_slots GAME_FN(ADDR_save_boot_read_slots, u32 (*)(u32, u32, u32, u32))
#define game_start           GAME_FN(ADDR_game_start, u32 (*)(u32, u32, u32, u32))
#define area_enter_finish    GAME_FN(ADDR_area_enter_finish, u32 (*)(u32, u32, u32, u32))
#define world_tick           GAME_FN(ADDR_world_tick, u32 (*)(u32, u32, u32, u32))
/* Cartridge save memory (8 KB EEPROM). Return 1 on success. */
#define eeprom_read   GAME_FN(ADDR_eeprom_read, int (*)(u32 offset, u32 len, void *dst))
#define eeprom_write  GAME_FN(ADDR_eeprom_write, int (*)(u32 offset, u32 len, const void *src))

/* ---- CPU caches (NitroSDK) ----------------------------------------------- */
#define DC_FlushRange           GAME_FN(ADDR_DC_FlushRange, void (*)(const void *, u32))
#define DC_WaitWriteBufferEmpty GAME_FN(ADDR_DC_WaitWriteBufferEmpty, void (*)(void))
#define IC_InvalidateRange      GAME_FN(ADDR_IC_InvalidateRange, void (*)(const void *, u32))

/* ---- objects and critters (docs/systems.md "Buyable objects", "Pets") ----- */
/* Can this object be put down here? 1 = yes (else the game shows why). */
#define entity_palette_table GAME_FN(ADDR_entity_palette_table, void (*)(void *e, const u32 *palette_ids))
#define place_object_check GAME_FN(ADDR_place_object_check, int (*)(void *e, unsigned obj, unsigned rot))
/* Add an object to an item list (Pockets: game_state+0x154). 1 = added. */
#define list_add     GAME_FN(ADDR_list_add, int (*)(void *list, unsigned obj, unsigned a, unsigned variant))
/* Create a critter (entity type 9: chicken = kind 1) facing `facing`, at map x, y (whole units). */
#define spawn_critter GAME_FN(ADDR_spawn_critter, void *(*)(unsigned kind, unsigned facing, unsigned a, int x, int y))
/* Entity state (+0x104) and action (+0x105). */
#define entity_set_state  GAME_FN(ADDR_entity_set_state, void (*)(void *e, int state))
