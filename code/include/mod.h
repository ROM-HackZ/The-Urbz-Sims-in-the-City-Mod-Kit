/* The mod platform (Phase 5): what a code mod can use from the mod core.

   The builder adds the core whenever a build has a mod that can be switched in-game
   (mod.json "toggle", the default for code mods) or that uses events. The core owns the
   game hooks below and calls only the mods that are switched on, so mods never fight
   over a hook.

   Events: define any of these functions in your mod (exact names); no hooks.txt line needed.
     void mod_on_boot(void)                 once at power-on, after the switches are read
     void mod_on_tick(void)                 every game tick while the city runs (30 a second)
     void mod_on_minute(int minutes)        the game clock moved on by this many minutes
                                            (more than 1 when it jumps: sleeping, shifts, ...)
     void mod_on_area_enter(int area)       an area finished loading (people are placed)
     int  mod_on_save(u8 *buf, int max)     write your data (at most max bytes); return the
                                            length, or -1 if it doesn't fit (the save goes on
                                            without it and the Mods page says "save full")
     void mod_on_load(const u8 *buf, int len)
                                            your data from the loaded save; buf = 0, len = 0
                                            means a new game, a vanilla save, or no data:
                                            start fresh
     void mod_on_enable(void)               switched on in the game
     void mod_on_disable(void)              switched off in the game (your hooks stop running)
     void mod_on_page(mod_page_t *page)     draw your info page (opened from the Mods page)

   Your save data is kept per save slot. While a mod is off, its data is kept and written
   back unchanged, so switching off never loses it. */
#pragma once
#include "game.h"

#define MOD_TABLE_ADDR 0x0214DE20U    /* start of the code region: the mod table */
#define MOD_TABLE_MAGIC 0x43444F4DU   /* 'MODC' */
#define MOD_EVENTS 9
enum { EV_BOOT, EV_TICK, EV_MINUTE, EV_AREA_ENTER, EV_SAVE, EV_LOAD, EV_ENABLE, EV_DISABLE, EV_PAGE };

enum { MODF_TOGGLE = 1, MODF_EVENTS = 2, MODF_DEFAULT_ON = 4, MODF_HIDDEN = 8 };   /* hidden: kit parts, not on the Mods page */

typedef struct {
    u32 addr, len;                /* game bytes this mod changes (a data/u8/u16/u32 hook) */
    const u8 *orig, *mod;         /* original bytes, the mod's bytes */
} mod_patch_t;

typedef struct {                  /* 80 bytes, written by the builder (urbz_code.py) */
    char name[16];
    char version[8];
    u32 hash;                     /* FNV-1a of the name: identifies the mod in saves */
    u8 on;                        /* hook stubs test this byte */
    u8 flags;                     /* MODF_* */
    u8 index, pad;
    u16 save_bytes, n_patches;
    const mod_patch_t *patches;
    void *ev[MOD_EVENTS];
    u32 runtime;                  /* core use: bit 0 = its last save didn't fit */
} mod_row_t;

typedef struct {
    u32 magic;                    /* 'MODC' */
    u16 version, count;
    u32 row_size;                 /* 80 */
    u32 status;                   /* core use: bit 0 = the last save dropped some mod data */
    u32 reserved[4];
    mod_row_t rows[];
} mod_table_t;

#define mod_table ((mod_table_t *)MOD_TABLE_ADDR)

/* An info page (mod_on_page): print up to 5 lines of text (each is cut to about 150 pixels,
   roughly 28 characters; '@' is a name code in the game's fonts, so don't use it). */
typedef struct mod_page mod_page_t;
struct mod_page {
    void (*print)(mod_page_t *page, const char *text);   /* one line, advances down */
    int line;
    u32 keys_down;               /* keys pressed this frame (KEY_* below), for paging */
    int scroll;                  /* lines to skip (the core changes it with UP/DOWN) */
    void *core;
};
enum { KEY_A = 1, KEY_B = 2, KEY_SELECT = 4, KEY_START = 8, KEY_RIGHT = 16, KEY_LEFT = 32,
       KEY_UP = 64, KEY_DOWN = 128, KEY_R = 256, KEY_L = 512 };
