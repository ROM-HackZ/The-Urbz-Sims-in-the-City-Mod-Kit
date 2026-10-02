/* obj-probe: lists this area's objects and their activities, and sends a person to use one.
   Tests poke a request into the struct (magic 'OBJP') and read the answer on the next tick.
     request 1: scan the object list into obj[]
     request 2: npc_goto_object(person, obj[node].entity, activity) -> result
                (people get a needs block first: the game's activity code writes through e+0x114)
     request 3: stop person's activity: its user slot's stop byte (+9) = activity (2 finish, 3 abort)
     request 4: the whole sequence on its own (for proofs, which can only poke at the start): wait
                until character `person` (an id) is here, send them to the first object offering
                `activity`, let them use it for `node` ticks, then abort it; the timeline goes to log[] */
#include "game.h"
#include "mod.h"

typedef struct {
    u16 number, n_acts;
    u32 entity;
    s32 x, y;
    u8 act[8], need[8];
} probe_obj_t;

typedef struct {
    u32 magic, request, done, count;
    u32 person, node, activity;
    s32 result;
    probe_obj_t obj[32];
    u32 auto_step, log_n;
    struct { u32 tick; u8 step, state, action, anim; } log[16];
} probe_t;

probe_t probe = { 0x504A424F };
static s32 needs[4][16];
static int n_needs;

typedef int (*list_fn)(void *node, u8 *out);
#define CLASS(n, off) (*(void **)(ADDR_object_class_table + (n) * 0x24 + (off)))
#define goto_object GAME_FN(ADDR_npc_goto_object, int (*)(void *person, void *obj, int activity))

static void scan(void)
{
    u32 *node = *(u32 **)ADDR_object_list_head;
    int n = 0;
    while (node && n < 32) {
        probe_obj_t *o = &probe.obj[n++];
        u8 acts[8] = { 0 };
        o->number = *(u16 *)((u8 *)node + 8);
        o->entity = node[9];
        o->x = o->entity ? *(s32 *)(o->entity + 0x18) >> 16 : 0;
        o->y = o->entity ? *(s32 *)(o->entity + 0x1C) >> 16 : 0;
        if (o->number < 225 && CLASS(o->number, 4))
            ((list_fn)CLASS(o->number, 4))(node, acts);
        o->n_acts = 0;
        for (int k = 0; k < 7 && acts[k]; k++) {
            o->act[k] = acts[k];
            o->need[k] = *(u16 *)(ADDR_activity_need_table + acts[k] * 4);
            o->n_acts++;
        }
        node = (u32 *)node[0];
    }
    probe.count = n;
}

static int send(u8 *e, int node, int activity)
{
    if (!*(s32 **)(e + 0x114) && n_needs < 4) {
        s32 *m = needs[n_needs++];
        for (int k = 0; k < 8; k++)
            m[k] = 50 << 24;
        *(s32 **)(e + 0x114) = m;
    }
    return goto_object(e, (void *)probe.obj[node].entity, activity);
}

static int stop(u8 *e, int how)
{
    u8 *act = *(u8 **)(e + 0x100);
    for (int k = 0; act && k < 2; k++)
        if (*(u8 **)(act + 0xC + 12 * k) == e) {
            act[0xC + 12 * k + 9] = (u8)how;
            return k;
        }
    return -1;
}

/* a person by character id: scan the heap for a type-7 entity (the pool moves with code size) */
static u8 *person_by_id(int id)
{
    for (u8 *p = (u8 *)0x0214DE20; p < (u8 *)0x021AE000; p += 4)
        if (*(u16 *)(p + 8) == 7 && *(u16 *)(p + 10) == id && *(u16 *)(p + 0x146) == id)
            return p;
    return 0;
}

static u32 ticks, mark;
static u8 *who, last_state, last_action, last_anim;

static void note(int step)
{
    if (probe.log_n < 16) {
        probe.log[probe.log_n].tick = ticks;
        probe.log[probe.log_n].step = step;
        probe.log[probe.log_n].state = who ? who[0x104] : 0;
        probe.log[probe.log_n].action = who ? who[0x105] : 0;
        probe.log[probe.log_n].anim = who ? who[0xC7] : 0;
        probe.log_n++;
    }
}

static void auto_run(void)
{
    switch (probe.auto_step) {
    case 1:                                          /* wait for the person, then send them */
        if (!(ticks & 15) && (who = person_by_id(probe.person)) && who[0x104] == 0x23) {
            scan();
            for (u32 i = 0; i < probe.count; i++)
                for (int k = 0; k < probe.obj[i].n_acts; k++)
                    if (probe.obj[i].act[k] == probe.activity && probe.auto_step == 1) {
                        probe.result = send(who, i, probe.activity);
                        note(1);
                        probe.auto_step = probe.result == 1 ? 2 : 9;
                    }
        }
        break;
    case 2:                                          /* walking: wait for the use to start */
        if (who[0x104] == 0x11) {
            note(2);
            mark = ticks;
            probe.auto_step = 3;
        } else if (who[0x104] == 0x23) {
            note(8);                                 /* gave up */
            probe.auto_step = 9;
        }
        break;
    case 3:                                          /* using it: stop after `node` ticks */
        if (ticks - mark == 60)
            note(3);                                 /* settled in */
        if (ticks - mark >= probe.node) {
            stop(who, 3);
            note(4);
            mark = ticks;
            probe.auto_step = 4;
        }
        break;
    case 4:
        if (ticks - mark == 10) {
            note(5);
            probe.auto_step = 9;
        }
        break;
    }
    if (who && probe.auto_step < 9 && (who[0x104] != last_state || who[0x105] != last_action ||
                                       who[0xC7] != last_anim)) {
        last_state = who[0x104];
        last_action = who[0x105];
        last_anim = who[0xC7];
        note(0);
    }
}

void mod_on_tick(void)
{
    ticks++;
    if (probe.auto_step)
        auto_run();
    u32 r = probe.request;
    if (!r)
        return;
    probe.request = 0;
    if (r == 1)
        scan();
    else if (r == 2 && probe.person && probe.node < probe.count) {
        probe.result = send((u8 *)probe.person, probe.node, probe.activity);
    } else if (r == 3 && probe.person)
        probe.result = stop((u8 *)probe.person, probe.activity);
    else if (r == 4)
        probe.auto_step = 1;
    probe.done++;
}
