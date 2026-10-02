/* The mod core (Phase 5): in-game switches, events and per-mod save data.

   The builder (urbz_code.py) adds this blob whenever a build has a mod that can be switched
   in-game or uses events, and writes the mod table at MOD_TABLE_ADDR (see mod.h). The hooks
   in hooks.txt are the only places the core touches the game; each calls the original first.

   Switches: one record for the whole cartridge, in save memory 0x1FE0-0x1FFF (the game never
   writes there). Mod data: a block after the game's own data in each save slot:
     'MODS', u8 version, u8 0, then per mod {u32 hash, u16 length, data}, then u32 0. */
#include "game.h"
#include "mod.h"
#include "core.h"

#define REC_ADDR  0x1FE0
#define REC_MAGIC 0x53444F4DU          /* 'MODS' */
#define BLOCK_MAGIC 0x53444F4DU
#define CARRY_MAX 2048

/* Visible to tests: 'CORE' marker then state (found with find_magic). */
core_state_t core = { 0x45524F43 };
static u8 carry[CARRY_MAX];            /* blocks of mods that are off or not in this build */

static u32 get32(const u8 *p) { return p[0] | p[1] << 8 | p[2] << 16 | (u32)p[3] << 24; }
static u32 get16(const u8 *p) { return p[0] | p[1] << 8; }
static void put32(u8 *p, u32 v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }
static void put16(u8 *p, u32 v) { p[0] = v; p[1] = v >> 8; }

typedef void (*ev0_t)(void);
typedef void (*ev1_t)(int);
typedef int (*ev_save_t)(u8 *, int);
typedef void (*ev_load_t)(const u8 *, int);

static void apply_patches(mod_row_t *r, int on)
{
    for (int i = 0; i < r->n_patches; i++) {
        const mod_patch_t *p = &r->patches[i];
        memcpy((void *)p->addr, on ? p->mod : p->orig, p->len);
        DC_FlushRange((void *)p->addr, p->len);         /* data cache -> memory */
        DC_WaitWriteBufferEmpty();
        IC_InvalidateRange((void *)p->addr, p->len);    /* in case the bytes are code */
    }
}

static void fire(int ev, int arg)
{
    mod_table_t *t = mod_table;
    for (int i = 0; i < t->count; i++) {
        mod_row_t *r = &t->rows[i];
        if (r->on && r->ev[ev]) {
            if (ev == EV_MINUTE || ev == EV_AREA_ENTER)
                ((ev1_t)r->ev[ev])(arg);
            else
                ((ev0_t)r->ev[ev])();
        }
    }
}

/* ---- carried save blocks ---------------------------------------------- */

static u8 *carry_find(u32 hash)
{
    u8 *p = carry;
    while (p + 6 <= carry + core.carry_len) {
        if (get32(p) == hash)
            return p;
        p += 6 + get16(p + 4);
    }
    return 0;
}

static void carry_remove(u32 hash)
{
    u8 *p = carry_find(hash);
    if (!p)
        return;
    u32 n = 6 + get16(p + 4);
    u8 *end = carry + core.carry_len;
    memcpy(p, p + n, end - (p + n));
    core.carry_len -= n;
}

static int carry_add(u32 hash, const u8 *data, u32 len)
{
    carry_remove(hash);
    if (core.carry_len + 6 + len > CARRY_MAX)
        return 0;
    u8 *p = carry + core.carry_len;
    put32(p, hash);
    put16(p + 4, len);
    memcpy(p + 6, data, len);
    core.carry_len += 6 + len;
    return 1;
}

/* ---- switches ------------------------------------------------------------ */

static void record_write(void)
{
    u8 rec[32];
    mod_table_t *t = mod_table;
    memset(rec, 0xFF, sizeof rec);
    put32(rec, REC_MAGIC);
    rec[4] = 1;
    int n = 0;
    for (int i = 0; i < t->count && n < 12; i++) {
        mod_row_t *r = &t->rows[i];
        if (r->flags & MODF_TOGGLE)
            put16(rec + 8 + 2 * n++, (r->hash & 0x7FFF) | (r->on ? 0x8000 : 0));
    }
    rec[5] = n;
    u32 sum = 0;
    for (int i = 8; i < 32; i++)
        sum += rec[i];
    put16(rec + 6, sum & 0xFFFF);
    core.record_writes += eeprom_write(REC_ADDR, sizeof rec, rec) ? 1 : 0;
}

static void record_read(void)
{
    u8 rec[32];
    mod_table_t *t = mod_table;
    if (!eeprom_read(REC_ADDR, sizeof rec, rec) || get32(rec) != REC_MAGIC || rec[4] != 1 || rec[5] > 12)
        return;                                          /* blank (0xFF) or not ours: defaults */
    u32 sum = 0;
    for (int i = 8; i < 32; i++)
        sum += rec[i];
    if ((sum & 0xFFFF) != get16(rec + 6))
        return;
    core.record_found = 1;
    for (int k = 0; k < rec[5]; k++) {
        u32 e = get16(rec + 8 + 2 * k);
        for (int i = 0; i < t->count; i++) {
            mod_row_t *r = &t->rows[i];
            if ((r->flags & MODF_TOGGLE) && (r->hash & 0x7FFF) == (e & 0x7FFF))
                r->on = e >> 15;
        }
    }
}

/* Switch a mod on or off now (the Mods page calls this). Saves the switches at once. */
void core_set(int index, int on)
{
    mod_row_t *r = &mod_table->rows[index];
    if (!(r->flags & MODF_TOGGLE) || !r->on == !on)
        return;
    if (on) {
        r->on = 1;
        apply_patches(r, 1);
        u8 *c = carry_find(r->hash);                     /* its data from the loaded save */
        if (c && r->ev[EV_LOAD]) {
            ((ev_load_t)r->ev[EV_LOAD])(c + 6, get16(c + 4));
            carry_remove(r->hash);
        }
        if (r->ev[EV_ENABLE])
            ((ev0_t)r->ev[EV_ENABLE])();
    } else {
        if (r->ev[EV_DISABLE])
            ((ev0_t)r->ev[EV_DISABLE])();
        if (r->ev[EV_SAVE]) {                            /* keep its data while it's off */
            static u8 tmp[1024];
            int n = ((ev_save_t)r->ev[EV_SAVE])(tmp, sizeof tmp);
            if (n >= 0)
                carry_add(r->hash, tmp, n);
        }
        r->on = 0;
        apply_patches(r, 0);
    }
    record_write();
}

/* ---- hooks (hooks.txt) ---------------------------------------------------- */

/* Boot: the game has just read both save slots (frame ~10, before the title screen). */
u32 core_boot(u32 a, u32 b, u32 c, u32 d)
{
    u32 ret = save_boot_read_slots(a, b, c, d);
    mod_table_t *t = mod_table;
    if (t->magic != MOD_TABLE_MAGIC)
        return ret;
    record_read();
    for (int i = 0; i < t->count; i++)
        if (t->rows[i].on)
            apply_patches(&t->rows[i], 1);
    core.booted = 1;
    core_page_init();
    fire(EV_BOOT, 0);
    return ret;
}

static u32 now_minutes(void)
{
    return (u32)(game_time.day * 1440 + game_time.hour * 60 + game_time.minute);
}

u32 core_tick(u32 a, u32 b, u32 c, u32 d)
{
    if (core.request & 0x80000000) {
        u32 q = core.request;
        core.request = 0;
        if ((q & 0xFF) < mod_table->count)
            core_set(q & 0xFF, (q >> 8) & 1);
    }
    u32 ret = world_tick(a, b, c, d);
    u32 now = now_minutes();
    core.ticks++;
    if (!core.time_ok) {
        core.last_minute = now;
        core.time_ok = 1;
    } else if (now != core.last_minute) {
        int n = (int)(now - core.last_minute);
        core.last_minute = now;
        if (n > 0)
            fire(EV_MINUTE, n);
    }
    fire(EV_TICK, 0);
    return ret;
}

u32 core_area_entered(u32 a, u32 b, u32 c, u32 d)
{
    u32 ret = area_enter_finish(a, b, c, d);
    fire(EV_AREA_ENTER, current_area);
    return ret;
}

/* First city entry after the title: a load (core_load runs inside) or a new game. */
u32 core_game_start(u32 a, u32 b, u32 c, u32 d)
{
    core.loaded = 0;
    u32 ret = game_start(a, b, c, d);
    if (!core.loaded) {                                  /* new game: everyone starts fresh */
        core.carry_len = 0;
        mod_table_t *t = mod_table;
        for (int i = 0; i < t->count; i++) {
            mod_row_t *r = &t->rows[i];
            if (r->on && r->ev[EV_LOAD])
                ((ev_load_t)r->ev[EV_LOAD])(0, 0);
        }
        core.new_games++;
    }
    core.time_ok = 0;
    return ret;
}

static void align_cursor(void)
{
    if (save_ctx.bit > 0) {
        save_ctx.cursor++;
        save_ctx.bit = 0;
    }
}

/* After the game wrote its data into the slot buffer: append the mod block. */
u32 core_save(u32 a, u32 b, u32 c, u32 d)
{
    u32 ret = save_serialize_all(a, b, c, d);
    mod_table_t *t = mod_table;
    align_cursor();
    u8 *slot = save_ctx.slot, *p = save_ctx.cursor;
    u8 *end = slot + SAVE_SLOT_DATA - 4;                 /* keep room for the end marker */
    u8 *q = p + 6;
    int dropped = 0, entries = 0;
    core.saves++;
    if (q > end)
        dropped = 1;
    for (int i = 0; i < t->count && !dropped; i++) {
        mod_row_t *r = &t->rows[i];
        r->runtime &= ~1;
        if (!r->on || !r->ev[EV_SAVE])
            continue;
        int room = end - (q + 6);
        int n = room > 0 ? ((ev_save_t)r->ev[EV_SAVE])(q + 6, room) : -1;
        if (n < 0 || n > room) {
            r->runtime |= 1;
            dropped = 1;
            continue;
        }
        put32(q, r->hash);
        put16(q + 4, n);
        q += 6 + n;
        entries++;
    }
    u8 *c2 = carry;                                      /* data of mods that are off */
    while (c2 + 6 <= carry + core.carry_len) {
        u32 n = 6 + get16(c2 + 4);
        if (q + n <= end) {
            memcpy(q, c2, n);
            q += n;
            entries++;
        } else
            dropped = 1;
        c2 += n;
    }
    t->status = (t->status & ~1) | dropped;
    if (entries) {
        put32(p, BLOCK_MAGIC);
        p[4] = 1;
        p[5] = 0;
        put32(q, 0);
        save_ctx.cursor = q + 4;
        core.saved_bytes = q + 4 - p;
    } else
        core.saved_bytes = 0;                            /* nothing to add: a plain game save */
    return ret;
}

/* After the game read its data from the slot buffer: read the mod block. */
u32 core_load(u32 a, u32 b, u32 c, u32 d)
{
    u32 ret = save_deserialize_all(a, b, c, d);
    mod_table_t *t = mod_table;
    u32 got = 0;                                         /* bit i = row i got its data */
    align_cursor();
    u8 *slot = save_ctx.slot, *p = save_ctx.cursor;
    u8 *end = slot + SAVE_SLOT_DATA;
    core.carry_len = 0;
    core.loaded = 1;
    core.loads++;
    core.loaded_bytes = 0;
    if (p + 10 <= end && get32(p) == BLOCK_MAGIC && p[4] == 1) {
        u8 *q = p + 6;
        while (q + 4 <= end) {
            u32 hash = get32(q);
            if (!hash) {
                q += 4;
                save_ctx.cursor = q;
                core.loaded_bytes = q - p;
                break;
            }
            if (q + 6 > end || q + 6 + get16(q + 4) > end)
                break;                                   /* damaged: ignore the rest */
            u32 n = get16(q + 4);
            int i;
            for (i = 0; i < t->count; i++)
                if (t->rows[i].hash == hash)
                    break;
            if (i < t->count && t->rows[i].on && t->rows[i].ev[EV_LOAD]) {
                ((ev_load_t)t->rows[i].ev[EV_LOAD])(q + 6, n);
                got |= 1u << i;
            } else
                carry_add(hash, q + 6, n);               /* off, or not in this build: keep it */
            q += 6 + n;
        }
    }
    for (int i = 0; i < t->count; i++) {
        mod_row_t *r = &t->rows[i];
        if (r->on && r->ev[EV_LOAD] && !(got & (1u << i)))
            ((ev_load_t)r->ev[EV_LOAD])(0, 0);           /* vanilla save or no data: defaults */
    }
    core.time_ok = 0;
    return ret;
}
