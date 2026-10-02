/* NPC Life: visible actions (Phase 6). People in your area act out what their routine says
   they are doing, with the game's own objects and animations: at meal times they sit down at a
   table, at home they relax on a chair or sofa, in the morning they wash, and now and then they
   use the toilet.

   It uses the game's own "walk to an object and use it" (npc_goto_object; docs/systems.md "People:
   movement and object use"), which the original game offers to only six people. Rules:
   - only people who are calmly wandering (state 0x23, standing) and not about to leave, not the
     person you're talking to, and only while a path slot is free; at most MAX_ACTORS at once;
   - each actor gets a needs block first (townspeople have none; the use code writes through it);
   - a use is ended after a while (stop byte 3: they stand up and wander again), at once if the
     game wants them to leave, and for everyone when NPC Life is switched off;
   - a person stuck walking (no path) is put back to wandering;
   - a person only uses an object if they have the animation it plays (activity_anim: the 8 with
     the game's object set, or anyone given new art with urbz_anims.py); otherwise, or when there is
     nothing to use, they chat: one walks up to another, they face each other and take turns
     gesturing (0x87, 0x78, 0xDB: the gestures 20 of them have). */

#define MAX_ACTORS 4
#define ST_WANDER  0x23
#define ST_GOTO    0x26
#define ST_USING   0x11
#define ACT_SIT    0x38                      /* chairs, sofas, benches */
enum { NEED_HUNGER, NEED_HYGIENE, NEED_ENERGY, NEED_SOCIAL, NEED_COMFORT, NEED_BLADDER, NEED_FUN };

enum { K_OBJECT, K_CHAT };
enum { CH_WALK, CH_TALK };
#define ACT_OURS   0x30                      /* an action the wander state ignores: we drive them */

typedef struct {
    u8 *e;                    /* entity (0 = free slot) */
    u8 who, need, obj_number, kind;
    u32 since, until;         /* ticks */
    u8 *partner;              /* chat: the other person */
    u8 partner_who, phase, turn, ract;      /* ract: their routine's activity when this started */
    u32 next_gesture;
} actor_t;

static actor_t actors[MAX_ACTORS];
static s32 needs_block[SIM_PEOPLE][16];      /* entity+0x114 for people we send (64 bytes each) */
static u32 rest_until[SIM_PEOPLE];           /* no new action before this tick */
static u32 act_ticks;

struct {
    u32 magic, sent, finished, aborted, rescued, left, refused, busy_paths;
    u8 last_who, last_need, last_obj, pad;
    u32 rounds, people_seen, candidates, no_object, chats;
} npc_act = { 0x5443414E };                  /* 'NACT' (tests read this) */

#define path_count   GAME_VAR(ADDR_path_count, u8)
#define goto_object  GAME_FN(ADDR_npc_goto_object, int (*)(void *person, void *obj, int activity))
#define set_state    GAME_FN(ADDR_entity_set_state, void (*)(void *e, int state))
#define set_action   GAME_FN(ADDR_entity_set_action, void (*)(void *e, int action))
#define play_anim    GAME_FN(ADDR_entity_play_anim, void (*)(void *e, int anim))
#define path_cancel  GAME_FN(ADDR_path_cancel, void (*)(void *e))
#define face         GAME_FN(ADDR_entity_face, void (*)(void *e, int dir))
#define has_anim     GAME_FN(ADDR_npc_has_anim, int (*)(int id, int anim))
#define path_request GAME_FN(ADDR_path_request, int (*)(void *e, s32 *xy, u8 *result, int flags))
#define CLASS(n, off) (*(void **)(ADDR_object_class_table + (n) * 0x24 + (off)))
#define E8(e, o)  (*(u8 *)((e) + (o)))
#define E16(e, o) (*(u16 *)((e) + (o)))
#define E32(e, o) (*(u32 *)((e) + (o)))

static u32 act_seed = 0x2545F491;
static u32 act_rnd(void)                     /* own random numbers: the saved sim must not depend on the screen */
{
    act_seed = act_seed * 1664525u + 1013904223u;
    return act_seed >> 8;
}

static u8 *world_first(void) { return *(u8 **)ADDR_entity_lists; }

static int alive(u8 *e, int who)
{
    for (u8 *p = world_first(); p; p = *(u8 **)p)
        if (p == e)
            return E16(e, 8) == 7 && E16(e, 10) == who;
    return 0;
}

/* stop byte of e's slot in the activity it is using (2 user slots at +0xC, 12 bytes each) */
static u8 *stop_byte(u8 *e)
{
    u8 *act = *(u8 **)(e + 0x100);
    for (int k = 0; act && k < 2; k++)
        if (*(u8 **)(act + 0xC + 12 * k) == e)
            return act + 0xC + 12 * k + 9;
    return 0;
}

static void resume(u8 *e, int who)              /* back to the game's own wandering */
{
    if (alive(e, who) && E8(e, 0x104) == ST_WANDER && E8(e, 0x105) == ACT_OURS) {
        path_cancel(e);
        play_anim(e, 4);
        set_action(e, 2);
    }
}

static void finish(actor_t *a, int why)
{
    u8 *e = a->e;
    if (a->kind == K_CHAT) {
        resume(e, a->who);
        resume(a->partner, a->partner_who);
        rest_until[a->partner_who - 31] = act_ticks + 600 + (act_rnd() % 900);
    } else if (alive(e, a->who)) {
        if (E8(e, 0x104) == ST_USING) {
            u8 *s = stop_byte(e);
            if (s)
                *s = 3;                                 /* abort: stand up, wander again */
        } else if (E8(e, 0x104) == ST_GOTO) {         /* still walking there: back to wandering */
            path_cancel(e);
            play_anim(e, 4);
            set_state(e, E8(e, 0x10A));
            set_action(e, 2);
        }
    }
    if (why == 1)
        npc_act.finished++;
    else if (why == 2)
        npc_act.left++;
    else if (why == 3)
        npc_act.rescued++;
    else
        npc_act.aborted++;
    rest_until[a->who - 31] = act_ticks + 600 + (act_rnd() % 900);   /* 20-50 s before the next */
    a->e = 0;
}

static int acting(u8 *e)
{
    for (int k = 0; k < MAX_ACTORS; k++)
        if (actors[k].e && (actors[k].e == e || (actors[k].kind == K_CHAT && actors[k].partner == e)))
            return 1;
    return 0;
}

/* The animation an object activity plays on a person (docs/systems.md): a person only uses an object
   when they have it (the 8 with the game's object set, plus anyone given new art: urbz_anims.py).
   Activities not listed are not offered to townspeople. */
static int activity_anim(int activity)
{
    switch (activity) {
    case 56: return 0x6B;                             /* Sit (chairs, sofas, benches) */
    case 57: return 0x21;                             /* Sleep (beds, benches, sofas) */
    case 60: return 0x69;                             /* Take a Shower */
    case 66: return 0x7B;                             /* Use (toilet) */
    case 12: case 13: case 35: case 90: case 113: case 115:
        return 0x41;                                  /* grill, have/buy a snack, snow cone, popcorn */
    }
    return 0;
}

static const u8 gestures[3] = { 0x87, 0x78, 0xDB };

static int gesture_of(int who, u32 r)
{
    for (int k = 0; k < 3; k++) {
        int g = gestures[(r + k) % 3];
        if (has_anim(who, g))
            return g;
    }
    return 0;
}

/* direction 1-8 (clockwise, 8 = up) from a to b, on the screen (isometric: y counts double) */
static int dir_to(u8 *a, u8 *b)
{
    int dx = ((s32)E32(b, 0x18) - (s32)E32(a, 0x18)) >> 16, dy = (((s32)E32(b, 0x1C) - (s32)E32(a, 0x1C)) >> 16) * 2;
    int ax = dx < 0 ? -dx : dx, ay = dy < 0 ? -dy : dy;
    if (ay * 5 < ax * 2)
        return dx > 0 ? 2 : 6;
    if (ax * 5 < ay * 2)
        return dy > 0 ? 4 : 8;
    return dx > 0 ? (dy > 0 ? 3 : 1) : (dy > 0 ? 5 : 7);
}

/* What this person would do here, from their routine: the needs an object should serve, in order
   of preference (the game's objects say which need each of their activities serves). */
static int wants(int i, u8 *out)
{
    int n = 0, act = sim_act_at(&sim, i, week_minute());
    if (has_anim(31 + i, 0x7B) && (act == A_WASH || act_rnd() % 6 == 0))
        out[n++] = NEED_BLADDER;                         /* now and then, and every morning */
    switch (act) {
    case A_WASH:
        out[n++] = NEED_HYGIENE;
        break;
    case A_EAT:
        out[n++] = NEED_HUNGER;
        out[n++] = NEED_COMFORT;                         /* no food object here: sit at a table */
        break;
    case A_FUN:
    case A_PARK:
        out[n++] = NEED_FUN;
        out[n++] = NEED_COMFORT;
        break;
    case A_SOCIAL:
        out[n++] = NEED_SOCIAL;
        out[n++] = NEED_COMFORT;
        break;
    case A_SLEEP:
        out[n++] = NEED_ENERGY;                          /* a bed or sofa if there is one */
        out[n++] = NEED_COMFORT;
        break;
    case A_HOME:
        out[n++] = NEED_FUN;
        out[n++] = NEED_COMFORT;
        break;
    case A_WORK:
        break;                                           /* at work: keep to their spot */
    default:
        if ((act_rnd() & 3) == 0)
            out[n++] = NEED_COMFORT;
    }
    return n;
}

static int dist2(u8 *a, u8 *b)
{
    int dx = ((s32)E32(a, 0x18) - (s32)E32(b, 0x18)) >> 16, dy = ((s32)E32(a, 0x1C) - (s32)E32(b, 0x1C)) >> 16;
    return dx * dx + dy * dy;
}

/* The nearest object here offering an activity for `need` that this person may start. */
static u8 *find_object(u8 *person, int need, int *activity, int *number)
{
    u8 *best = 0;
    int best_d = 0x7FFFFFFF;
    for (u32 *node = *(u32 **)ADDR_object_list_head; node; node = (u32 *)node[0]) {
        int num = *(u16 *)((u8 *)node + 8);
        u8 *ent = (u8 *)node[9];
        if (!ent || num >= 225 || !CLASS(num, 4))
            continue;
        u8 acts[8] = { 0 };
        ((int (*)(void *, u8 *))CLASS(num, 4))(node, acts);
        for (int k = 0; k < 7 && acts[k]; k++) {
            if (*(u16 *)(ADDR_activity_need_table + acts[k] * 4) != need)
                continue;
            int anim = activity_anim(acts[k]);
            if (!anim || !has_anim(E16(person, 10), anim))
                continue;                                 /* they couldn't show it */
            /* free to use (the game's check), and may start it. The game's own start checks refuse
               townspeople seats (activity 0x38) and snacks without 0x7F (press the button), which
               nobody has; with the sit / eat animation they look right, so those two are skipped. */
            int lenient = acts[k] == ACT_SIT || anim == 0x41;
            if (((int (*)(void *, void *))CLASS(num, 0x1C))(node, person) != 1 ||
                (!lenient && ((int (*)(void *, void *, int))CLASS(num, 8))(node, person, acts[k]) != 1))
                continue;
            int d = dist2(person, ent);
            if (d < best_d) {
                best = ent;
                best_d = d;
                *activity = acts[k];
                *number = num;
            }
        }
    }
    return best;
}

static int may_act(u8 *e, int who)
{
    if (who < 31 || who >= 31 + SIM_PEOPLE || !sim.orig[who - 31])
        return 0;
    if (E8(e, 0x104) != ST_WANDER || E8(e, 0x105) != 7 || (E8(e, 0x107) & 2))
        return 0;                                    /* busy, scripted, or about to leave */
    if (*(u32 *)ADDR_talk_partner == (u32)who || acting(e))
        return 0;
    return act_ticks >= rest_until[who - 31];
}

/* A chats with someone else here who is free: A walks up to them. Social people chat more. */
static int start_chat(int slot, u8 *e, int who)
{
    if (!gesture_of(who, 0) || (sim_act_at(&sim, who - 31, week_minute()) != A_SOCIAL && (act_rnd() % 3)))
        return 0;
    u8 *best = 0;
    int best_d = 0x7FFFFFFF;
    for (u8 *p = world_first(); p; p = *(u8 **)p) {
        if (p == e || E16(p, 8) != 7 || !may_act(p, E16(p, 10)))
            continue;
        int d = dist2(e, p);
        if (d < best_d) {
            best = p;
            best_d = d;
        }
    }
    if (!best || best_d > 160 * 160)
        return 0;
    /* stand next to them, on their side facing us */
    s32 xy[2];
    int dx = ((s32)E32(e, 0x18) - (s32)E32(best, 0x18)) >> 16, dy = ((s32)E32(e, 0x1C) - (s32)E32(best, 0x1C)) >> 16;
    int len = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy) * 2;
    if (len < 1)
        len = 1;
    xy[0] = (s32)E32(best, 0x18) + ((dx * 24 / len) << 16);
    xy[1] = (s32)E32(best, 0x1C) + ((dy * 24 / len) << 16);
    E8(e, 0x10B) = 0;
    if (path_request(e, xy, (u8 *)(e + 0x10B), 0) != 1) {
        npc_act.refused++;
        return 0;
    }
    actor_t *a = &actors[slot];
    a->e = e;
    a->who = who;
    a->kind = K_CHAT;
    a->partner = best;
    a->partner_who = E16(best, 10);
    a->phase = CH_WALK;
    a->since = act_ticks;
    a->need = NEED_SOCIAL;
    a->obj_number = 0;
    a->ract = (u8)sim_act_at(&sim, who - 31, week_minute());
    set_action(e, ACT_OURS);
    play_anim(e, 0x0A);
    set_action(best, ACT_OURS);                       /* they wait for us */
    play_anim(best, 4);
    face(best, dir_to(best, e));
    rest_until[a->partner_who - 31] = act_ticks + 300;
    npc_act.sent++;
    npc_act.chats++;
    npc_act.last_who = who;
    npc_act.last_need = NEED_SOCIAL;
    npc_act.last_obj = a->partner_who;
    return 1;
}

static void chat_tick(actor_t *a)
{
    u8 *e = a->e, *b = a->partner;
    if (!alive(b, a->partner_who) || E8(e, 0x104) != ST_WANDER || E8(b, 0x104) != ST_WANDER ||
        E8(e, 0x105) != ACT_OURS || E8(b, 0x105) != ACT_OURS) {
        finish(a, 0);                                 /* something else took over */
        return;
    }
    if ((E8(e, 0x107) | E8(b, 0x107)) & 2) {
        finish(a, 2);
        return;
    }
    if (a->phase == CH_WALK) {
        int r = E8(e, 0x10B);
        if (r == 1 || dist2(e, b) < 30 * 30) {        /* there: face each other and talk */
            path_cancel(e);
            play_anim(e, 4);
            face(e, dir_to(e, b));
            face(b, dir_to(b, e));
            a->phase = CH_TALK;
            a->until = act_ticks + 300 + act_rnd() % 300;    /* 10-20 s */
            a->next_gesture = act_ticks;
            a->turn = 0;
        } else if (r == 3 || act_ticks - a->since > 600)
            finish(a, 3);
        return;
    }
    if (act_ticks >= a->until) {
        finish(a, 1);
        return;
    }
    if (act_ticks >= a->next_gesture) {               /* take turns: one gestures, the other listens */
        u8 *talker = a->turn ? b : e, *other = a->turn ? e : b;
        int g = gesture_of(a->turn ? a->partner_who : a->who, act_rnd());
        play_anim(other, 4);
        play_anim(talker, g ? g : 4);
        a->turn ^= 1;
        a->next_gesture = act_ticks + 75 + act_rnd() % 45;   /* 2.5-4 s */
    }
}

static void start_one(void)
{
    if (path_count >= 2) {                           /* leave a path slot for the game */
        npc_act.busy_paths++;
        return;
    }
    int slot = -1;
    for (int k = 0; k < MAX_ACTORS; k++)
        if (!actors[k].e)
            slot = k;
    if (slot < 0)
        return;
    npc_act.rounds++;
    for (u8 *e = world_first(); e; e = *(u8 **)e) {
        if (E16(e, 8) != 7)
            continue;
        int who = E16(e, 10);
        npc_act.people_seen++;
        if (!may_act(e, who))
            continue;
        npc_act.candidates++;
        int i = who - 31;
        u8 want[6];
        rest_until[i] = act_ticks + 300;             /* look again in 10 s whatever happens */
        int n = wants(i, want);
        for (int w = 0; w < n; w++) {
            int activity, number;
            u8 *obj = find_object(e, want[w], &activity, &number);
            if (!obj) {
                npc_act.no_object++;
                continue;
            }
            if (!*(s32 **)(e + 0x114)) {
                for (int k = 0; k < 8; k++)
                    needs_block[i][k] = 50 << 24;            /* the game's use code reads and writes these */
                *(s32 **)(e + 0x114) = needs_block[i];
            }
            if (goto_object(e, obj, activity) != 1) {
                npc_act.refused++;
                continue;
            }
            actor_t *a = &actors[slot];
            a->e = e;
            a->who = who;
            a->need = want[w];
            a->obj_number = number;
            a->kind = K_OBJECT;
            a->ract = (u8)sim_act_at(&sim, i, week_minute());
            a->since = act_ticks;
            a->until = act_ticks + (want[w] == NEED_BLADDER || want[w] == NEED_HYGIENE ? 1800 :
                                    450 + act_rnd() % 600);           /* sit for 15-35 s */
            npc_act.sent++;
            npc_act.last_who = who;
            npc_act.last_need = want[w];
            npc_act.last_obj = number;
            return;                                  /* one new action per round */
        }
        if (start_chat(slot, e, who))                /* nothing to use here they can show: a chat */
            return;
    }
}

/* Every tick from mod_on_tick (NPC Life on, city running). */
static void act_tick(void)
{
    act_ticks++;
    if (act_ticks & 15)
        return;
    for (int k = 0; k < MAX_ACTORS; k++) {
        actor_t *a = &actors[k];
        if (!a->e)
            continue;
        u8 *e = a->e;
        if (!alive(e, a->who)) {                     /* gone (area change, despawn) */
            if (a->kind == K_CHAT)
                resume(a->partner, a->partner_who);
            a->e = 0;
            continue;
        }
        if (a->ract != sim_act_at(&sim, a->who - 31, week_minute())) {
            int who = a->who;
            finish(a, 1);                            /* their day moved on (e.g. breakfast time) */
            rest_until[who - 31] = act_ticks + 30;   /* pick the next thing almost at once */
            continue;
        }
        if (a->kind == K_CHAT) {
            chat_tick(a);
            continue;
        }
        int st = E8(e, 0x104);
        if (E8(e, 0x107) & 2)
            finish(a, 2);                            /* the game wants them elsewhere */
        else if (st == ST_GOTO && act_ticks - a->since > 900)
            finish(a, 3);                            /* 30 s and not there: stuck */
        else if (st == ST_USING && act_ticks >= a->until)
            finish(a, 1);
        else if (st != ST_GOTO && st != ST_USING) {  /* done by itself (or the use failed) */
            a->e = 0;
            npc_act.finished++;
            rest_until[a->who - 31] = act_ticks + 600 + (act_rnd() % 900);
        }
    }
    start_one();
}

/* Switched off, or the area is being left: everyone stops. */
static void act_release_all(void)
{
    for (int k = 0; k < MAX_ACTORS; k++)
        if (actors[k].e)
            finish(&actors[k], 0);
}

/* For the info page: what this person is doing here, or 0. */
static const char *act_doing(int who)
{
    static const char *const what[] = { "eating", "washing", "resting", "chatting", "sitting", "on the loo",
                                        "having fun" };
    for (int k = 0; k < MAX_ACTORS; k++)
        if (actors[k].e && (actors[k].who == who || (actors[k].kind == K_CHAT && actors[k].partner_who == who)))
            return actors[k].need <= NEED_FUN ? what[actors[k].need] : "busy";
    return 0;
}
