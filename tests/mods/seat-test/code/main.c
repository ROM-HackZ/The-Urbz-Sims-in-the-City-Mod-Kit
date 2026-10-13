#include "game.h"
#include "mod.h"

/* Test: every 2 s, someone standing about here (state 0x23, action 7) is sent to the next seat object (Sit,
   activity 56) of the numbers below that nobody of ours is on, with a needs block (the use code reads and
   writes it). They are stood up again after 8 s (stop byte 3), so every seat gets tried in turn. */
#define goto_object GAME_FN(ADDR_npc_goto_object, int (*)(void *person, void *obj, int activity))
#define path_count  GAME_VAR(ADDR_path_count, u8)
#define E8(e, o)  (*(u8 *)((e) + (o)))
#define CLASS(n, off) (*(void **)(ADDR_object_class_table + (n) * 0x24 + (off)))

struct {
    u32 magic, sent, refused, ticks;
    u16 seat_obj[24];              /* per seat tried (object list order): object number */
    s16 seat_x[24], seat_y[24];
    u8 tries[24];
    u16 st_seen[64];               /* ticks seen in each state (0..63) by someone we sent */
    u8 last_st[8], last_ac[8];
    u32 n_log;
    u8 log[64][4];                 /* transitions of the people sent: slot, state, action, path result */
} seat_test = { 0x54414553 };      /* 'SEAT' */

static s32 needs[8][16];
static u8 *sent_e[8];
static u32 sent_at[8];
static int next_seat;

static int is_seat(int num)
{
    return num == 134;                               /* the Invisible Park Bench: what seats.json adds */
}

void mod_on_area_enter(int area)
{
    (void)area;
    next_seat = 0;
    for (int k = 0; k < 8; k++)
        sent_e[k] = 0;
}

void mod_on_tick(void)
{
    seat_test.ticks++;
    for (int k = 0; k < 8; k++)                      /* forget them after 8 s */
        if (sent_e[k]) {
            u8 st = E8(sent_e[k], 0x104);
            if (st < 64)
                seat_test.st_seen[st]++;
            u8 ac = E8(sent_e[k], 0x105);
            if (st != seat_test.last_st[k] || ac != seat_test.last_ac[k]) {
                u8 *l = seat_test.log[seat_test.n_log++ % 64];
                l[0] = k;
                l[1] = st;
                l[2] = ac;
                l[3] = E8(sent_e[k], 0x10B);
            }
            seat_test.last_st[k] = st;
            seat_test.last_ac[k] = ac;
            if (st == 0x11)                          /* watch them: you stand just below */
                for (u8 *me = *(u8 **)ADDR_entity_lists; me; me = *(u8 **)me)
                    if (*(u16 *)(me + 8) == 0) {
                        s32 x = *(s32 *)(sent_e[k] + 0x18), y = *(s32 *)(sent_e[k] + 0x1C) + (36 << 16);
                        *(s32 *)(me + 0x18) = *(s32 *)(me + 0x20) = x;
                        *(s32 *)(me + 0x1C) = *(s32 *)(me + 0x24) = y;
                    }
            if (seat_test.ticks - sent_at[k] > 240)
                sent_e[k] = 0;
        }
    if (seat_test.ticks % 60 || path_count >= 3)
        return;
    int n = 0, want = -1, want_num = 0;
    u8 *obj = 0;
    u32 *want_node = 0;
    for (u32 *node = *(u32 **)ADDR_object_list_head; node; node = (u32 *)node[0]) {
        int num = *(u16 *)((u8 *)node + 8);
        u8 *ent = (u8 *)node[9];
        if (!ent || !is_seat(num) || n >= 24)
            continue;
        seat_test.seat_obj[n] = num;
        seat_test.seat_x[n] = (s16)((s32)*(s32 *)(ent + 0x18) >> 16);
        seat_test.seat_y[n] = (s16)((s32)*(s32 *)(ent + 0x1C) >> 16);
        if (want < 0 && n >= next_seat % 24) {
            want = n;
            obj = ent;
            want_node = node;
            want_num = num;
        }
        n++;
    }
    if (!obj) {
        next_seat = 0;
        return;
    }
    int slot = -1;
    for (int k = 0; k < 8; k++)
        if (!sent_e[k]) {
            slot = k;
            break;
        }
    if (slot < 0)
        return;
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e) {
        if (*(u16 *)(e + 8) != 7 || E8(e, 0x104) != 0x23 || E8(e, 0x105) != 7 || (E8(e, 0x107) & 2))
            continue;                            /* (0x107 bit 1: about to leave) */
        int busy = 0;
        for (int k = 0; k < 8; k++)
            busy |= sent_e[k] == e;
        if (busy)
            continue;
        if (!*(s32 **)(e + 0x114)) {
            for (int k = 0; k < 16; k++)
                needs[slot][k] = 50 << 24;
            *(s32 **)(e + 0x114) = needs[slot];
        }
        if (((int (*)(void *, void *))CLASS(want_num, 0x1C))(want_node, e) != 1) {   /* the game's "free to use" */
            seat_test.refused++;
            continue;                                /* (someone else may) */
        }
        if (goto_object(e, obj, 56) == 1) {
            sent_e[slot] = e;
            sent_at[slot] = seat_test.ticks;
            seat_test.sent++;
            seat_test.tries[want]++;
            next_seat = want + 1;
        } else
            seat_test.refused++;
        return;
    }
    next_seat = want + 1;                            /* nobody could: the next seat next time */
}
