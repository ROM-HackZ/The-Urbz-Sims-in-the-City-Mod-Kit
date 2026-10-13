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
     gesturing (0x87, 0x78, 0xDB: 20 people have them, the other 8 get borrowed ones with
     urbz_poses.py). */

#define MAX_ACTORS 4
#define ST_WANDER  0x23
#define ST_GOTO    0x26
#define ST_USING   0x11
#define ACT_SIT    0x38                      /* chairs, sofas, benches */
enum { NEED_HUNGER, NEED_HYGIENE, NEED_ENERGY, NEED_SOCIAL, NEED_COMFORT, NEED_BLADDER, NEED_FUN };

enum { K_OBJECT, K_CHAT, K_LOOK, K_STROLL };   /* K_LOOK: at an object anyone can enjoy without its animations;
                                                   K_STROLL: a walk to another spot of the place */
enum { CH_WALK, CH_TALK };
#define ACT_OURS   0x30                      /* an action the wander state ignores: we drive them */

typedef struct {
    u8 *e;                    /* entity (0 = free slot) */
    u8 who, need, obj_number, kind;
    u32 since, until;         /* ticks */
    u8 *partner;              /* chat: the other person; object: the object; look: the thing looked at */
    u8 partner_who, phase, turn, ract;      /* ract: their routine's activity when this started */
    u32 next_gesture;
} actor_t;

static actor_t actors[MAX_ACTORS];
static s32 needs_block[SIM_PEOPLE][16];      /* entity+0x114 for people we send (64 bytes each) */
static u32 rest_until[SIM_PEOPLE];           /* no new action before this tick */
static u32 after_act[SIM_PEOPLE];            /* just did something: not asked to chat before this tick */
static u32 walk_off[SIM_PEOPLE];             /* after a use: walk away from it at this tick (0 = no) */
static s32 came_from[SIM_PEOPLE][2];         /* where they were when sent to an object (reachable: they walked) */
static u8 off_result[SIM_PEOPLE];            /* path_request's result byte for that walk */
static u32 off_until[SIM_PEOPLE];            /* walking away until this tick (0 = not walking away) */
static s32 off_x[SIM_PEOPLE], off_y[SIM_PEOPLE];   /* where they were at the last check of that walk */
static u32 act_ticks;

struct {
    u32 magic, sent, finished, aborted, rescued, left, refused, busy_paths;
    u8 last_who, last_need, last_obj, pad;
    u32 rounds, people_seen, candidates, no_object, chats;
    u32 loose, forced;                       /* watch_loose: told to stand up / put back to wandering */
    u32 kept;                                /* routine moved on, the use still serves it: carried on */
    u32 walked_off;                          /* stepped away from an object after using it */
    u32 looks;                               /* went to look at / dance by / watch something */
    u32 taken_skips;                         /* an object someone of ours is already on (2026-10-12) */
    u32 strolls;                             /* walked to another spot of the place (2026-10-12) */
    u32 chat_end[4];                         /* chats ended: why (0 taken over, 1 done, 2 leaving, 3 no way) */
    u8 chat_end_st[4];                       /* the last one taken over: states and actions (e, partner) */
    u32 let_out;                             /* watch_leaving: someone who couldn't get out, let out (2026-10-13) */
} npc_act = { 0x5443414E };                  /* 'NACT' (tests read this) */

#define path_count   GAME_VAR(ADDR_path_count, u8)
#define goto_object  GAME_FN(ADDR_npc_goto_object, int (*)(void *person, void *obj, int activity))
#define set_state    GAME_FN(ADDR_entity_set_state, void (*)(void *e, int state))
#define set_action   GAME_FN(ADDR_entity_set_action, void (*)(void *e, int action))
#define play_anim    GAME_FN(ADDR_entity_play_anim, void (*)(void *e, int anim))
#define path_cancel  GAME_FN(ADDR_path_cancel, void (*)(void *e))
#define walked_out   GAME_FN(ADDR_npc_walked_out, void (*)(void *e))
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
        npc_act.chat_end[why & 3]++;
        if (!why) {
            npc_act.chat_end_st[0] = E8(e, 0x104);
            npc_act.chat_end_st[1] = E8(e, 0x105);
            npc_act.chat_end_st[2] = E8(a->partner, 0x104);
            npc_act.chat_end_st[3] = E8(a->partner, 0x105);
        }
        resume(e, a->who);
        resume(a->partner, a->partner_who);
        rest_until[a->partner_who - 31] = act_ticks + 450 + (act_rnd() % 600);
        after_act[a->partner_who - 31] = rest_until[a->partner_who - 31];
    } else if (a->kind == K_LOOK || a->kind == K_STROLL) {
        resume(e, a->who);
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
    rest_until[a->who - 31] = act_ticks + 450 + (act_rnd() % 600);   /* 15-35 s before the next (was 20-50: a café stayed still for minutes) */
    after_act[a->who - 31] = rest_until[a->who - 31];
    if (a->kind == K_OBJECT)
        walk_off[a->who - 31] = act_ticks + 45;
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

/* Where people end up sitting on each object (learned this visit): Café Z-Bach's two invisible love seats put
   their sitter on the same spot, so "a free seat" could still be on top of someone (2026-10-12). */
#define N_SPOTS 12
static struct { u8 *obj; s16 x, y; } spots[N_SPOTS];

static u8 *someone_using_at(u8 *self, int x, int y)
{
    for (u8 *p = world_first(); p; p = *(u8 **)p) {
        if (p == self || E16(p, 8) != 7 || E8(p, 0x104) != ST_USING)
            continue;
        int dx = ((s32)E32(p, 0x18) >> 16) - x, dy = ((s32)E32(p, 0x1C) >> 16) - y;
        if (dx * dx + dy * dy < 8 * 8)
            return p;
    }
    return 0;
}

static int spot_taken(u8 *obj)
{
    for (int k = 0; k < N_SPOTS; k++)
        if (spots[k].obj == obj)
            return someone_using_at(0, spots[k].x, spots[k].y) != 0;
    return 0;
}

static void spot_learn(u8 *obj, u8 *person)
{
    int free = -1;
    for (int k = 0; k < N_SPOTS; k++) {
        if (spots[k].obj == obj)
            return;
        if (!spots[k].obj && free < 0)
            free = k;
    }
    if (free >= 0) {
        spots[free].obj = obj;
        spots[free].x = (s16)((s32)E32(person, 0x18) >> 16);
        spots[free].y = (s16)((s32)E32(person, 0x1C) >> 16);
    }
}

/* An object here offering an activity for `need` that this person may start (picked at random). */
static u8 *find_object(u8 *person, int need, int *activity, int *number)
{
    u8 *best = 0;
    int found = 0;
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
            int ours = 0;                                 /* someone we sent is on it already (two people drawn on
                                                             one armchair, 2026-10-12) */
            for (int j = 0; j < MAX_ACTORS; j++)
                ours |= actors[j].e && actors[j].kind == K_OBJECT && actors[j].partner == ent;
            if (ours || spot_taken(ent)) {
                npc_act.taken_skips++;
                break;
            }
            if (((int (*)(void *, void *))CLASS(num, 0x1C))(node, person) != 1 ||
                (!lenient && ((int (*)(void *, void *, int))CLASS(num, 8))(node, person, acts[k]) != 1))
                continue;
            /* any of them, not always the nearest: everyone coming in the same door took the same chair
               and the rest of the table stayed empty */
            if (act_rnd() % (u32)++found == 0) {
                best = ent;
                *activity = acts[k];
                *number = num;
            }
        }
    }
    return best;
}

static int may_act_now(u8 *e, int who, int rested)
{
    if (who < 31 || who >= 31 + SIM_PEOPLE || !sim.orig[who - 31])
        return 0;
    if (E8(e, 0x104) != ST_WANDER || (E8(e, 0x105) != 7 && E8(e, 0x105) != 0x19) || (E8(e, 0x107) & 2))
        return 0;                                    /* busy, scripted, or about to leave (standing or strolling
                                                        about may: only standing used to, so few ever chatted) */
    if (*(u32 *)ADDR_talk_partner == (u32)who || acting(e))
        return 0;
    return rested ? act_ticks >= rest_until[who - 31] : act_ticks >= after_act[who - 31];
}

static int may_act(u8 *e, int who)
{
    return may_act_now(e, who, 1);
}

/* A walks to a spot next to B: side 0 = on B's side facing A, 1 and 2 = to B's left and right, 3 = behind B
   (in a café the near side is often a table or a wall: no way there). */
static int chat_path(u8 *e, u8 *b, int side)
{
    s32 xy[2];
    int dx = ((s32)E32(e, 0x18) - (s32)E32(b, 0x18)) >> 16, dy = ((s32)E32(e, 0x1C) - (s32)E32(b, 0x1C)) >> 16;
    int len = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy) * 2;
    if (len < 1)
        len = 1;
    int ox = dx * 24 / len, oy = dy * 24 / len;
    if (side == 1 || side == 2) {                    /* a quarter turn (y counts double on screen) */
        int t = ox;
        ox = side == 1 ? -oy * 2 : oy * 2;
        oy = side == 1 ? t / 2 : -t / 2;
    } else if (side == 3) {
        ox = -ox;
        oy = -oy;
    }
    xy[0] = (s32)E32(b, 0x18) + (ox << 16);
    xy[1] = (s32)E32(b, 0x1C) + (oy << 16);
    E8(e, 0x10B) = 0;
    return path_request(e, xy, (u8 *)(e + 0x10B), 0) == 1;
}

/* A chats with someone else here who is free: A walks up to them. Social people chat more. */
static int start_chat(int slot, u8 *e, int who)
{
    if (sim_act_at(&sim, who - 31, week_minute()) != A_SOCIAL && (act_rnd() & 1))
        return 0;                                    /* (anyone may chat: without gestures they just face each
                                                        other; only 20 people have gestures) */
    u8 *best = 0;
    int best_d = 0x7FFFFFFF;
    for (u8 *p = world_first(); p; p = *(u8 **)p) {
        if (p == e || E16(p, 8) != 7 || E8(p, 0x105) != 7 || !may_act_now(p, E16(p, 10), 0))
            continue;                                /* (standing: one walking about kept walking off) */
        int d = dist2(e, p);
        if (d < best_d) {
            best = p;
            best_d = d;
        }
    }
    if (!best || best_d > 500 * 500)                  /* (160 px: nobody ever chatted in Urbania Park, people are
                                                         hundreds of pixels apart there) */
        return 0;
    if (!chat_path(e, best, 0)) {
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
        int stuck = r == 3 || act_ticks - a->since > 600;
        if (r == 1 || dist2(e, b) < 30 * 30 || (stuck && dist2(e, b) < 72 * 72)) {
            /* there: face each other and talk (or as near as they got: in a crowded café the spot next to
               the other person is often a table, and the walk ends a step short) */
            path_cancel(e);
            play_anim(e, 4);
            face(e, dir_to(e, b));
            face(b, dir_to(b, e));
            a->phase = CH_TALK;
            a->until = act_ticks + 300 + act_rnd() % 300;    /* 10-20 s */
            a->next_gesture = act_ticks;
            a->turn = 0;
        } else if (r == 3 && a->obj_number < 3 && path_count < 3) {
            path_cancel(e);                           /* no way to that side of them: another side */
            if (!chat_path(e, b, ++a->obj_number))
                finish(a, 3);
        } else if (stuck)
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

/* Things anyone can do at an object without its own animations (most people only have stand, walk and a few
   gestures): walk up, face it and take it in, gesturing now and then. 1 = calm (admire an exhibit, gaze into
   the crystal ball, critique graffiti, watch TV, have a drink at the fountain, wash hands; and by number: stand
   at a grill, make a call at a phone), 2 = lively (dance by the jukebox or on the dance pad, spin at the DJ
   desk). Activity numbers: docs/objects.md. */
static int look_kind(int activity)
{
    switch (activity) {
    case 8: case 25: case 94: case 69: case 83: case 68:
        return 1;
    case 17: case 18: case 100:
        return 2;
    }
    return 0;
}

static u8 *find_look(u8 *person, int *kind)
{
    u8 *best = 0;
    int found = 0;
    for (u32 *node = *(u32 **)ADDR_object_list_head; node; node = (u32 *)node[0]) {
        int num = *(u16 *)((u8 *)node + 8);
        u8 *ent = (u8 *)node[9];
        if (!ent || num >= 386 || num == 225 || num == 236 || !CLASS(num, 4) || !E32(ent, 0x18))
            continue;                                     /* (225, 236: the chicken and the nutria) */
        int taken = 0;
        for (int k = 0; k < MAX_ACTORS; k++)
            taken |= actors[k].e && actors[k].kind == K_LOOK && actors[k].partner == ent;
        if (taken || dist2(person, ent) > 400 * 400)
            continue;
        if (num == 1 || (num >= 205 && num <= 207)) {        /* by the grill, on the phone (no activity of theirs) */
            if (act_rnd() % (u32)++found == 0) {
                best = ent;
                *kind = 1;
            }
            continue;
        }
        u8 acts[8] = { 0 };
        ((int (*)(void *, u8 *))CLASS(num, 4))(node, acts);
        for (int k = 0; k < 7 && acts[k]; k++) {
            int lk = look_kind(acts[k]);
            if (!lk)
                continue;
            if (act_rnd() % (u32)++found == 0) {
                best = ent;
                *kind = lk;
            }
            break;
        }
    }
    return best;
}

/* A spot a step from the object: first on the side we come from, then the other three diagonals (a phone on a
   wall or an exhibit against one can only be reached from the open side). */
static int look_path(u8 *e, u8 *obj, int try_no)
{
    static const s8 side[4][2] = { { 26, 13 }, { -26, 13 }, { 26, -13 }, { -26, -13 } };
    int sx = E32(e, 0x18) > E32(obj, 0x18) ? 0 : 1, sy = E32(e, 0x1C) > E32(obj, 0x1C) ? 0 : 2;
    int k = ((sx | sy) + try_no) & 3;
    s32 xy[2] = { (s32)E32(obj, 0x18) + (side[k][0] << 16), (s32)E32(obj, 0x1C) + (side[k][1] << 16) };
    E8(e, 0x10B) = 0;
    return path_request(e, xy, (u8 *)(e + 0x10B), 0) == 1;
}

static int start_look(int slot, u8 *e, int who)
{
    int kind = 0;
    u8 *obj = find_look(e, &kind);
    if (!obj)
        return 0;
    if (!look_path(e, obj, 0)) {
        npc_act.refused++;
        return 0;
    }
    actor_t *a = &actors[slot];
    a->e = e;
    a->who = who;
    a->kind = K_LOOK;
    a->partner = obj;
    a->partner_who = (u8)kind;
    a->phase = CH_WALK;
    a->since = act_ticks;
    a->need = NEED_FUN;
    a->obj_number = 0;                                    /* (K_LOOK: the side tried, 0-3) */
    a->turn = 0;
    a->ract = (u8)sim_act_at(&sim, who - 31, week_minute());
    set_action(e, ACT_OURS);
    play_anim(e, 0x0A);
    npc_act.sent++;
    npc_act.looks++;
    npc_act.last_who = who;
    return 1;
}

static void look_tick(actor_t *a)
{
    u8 *e = a->e, *obj = a->partner;
    if (E8(e, 0x104) != ST_WANDER || E8(e, 0x105) != ACT_OURS) {
        finish(a, 0);                                     /* something else took over */
        return;
    }
    if (E8(e, 0x107) & 2) {
        finish(a, 2);
        return;
    }
    if (a->phase == CH_WALK) {
        int r = E8(e, 0x10B);
        if (r == 1 || dist2(e, obj) < 36 * 36) {
            path_cancel(e);
            play_anim(e, 4);
            face(e, dir_to(e, obj));
            a->phase = CH_TALK;
            a->until = act_ticks + 300 + act_rnd() % 300;   /* 10-20 s */
            a->next_gesture = act_ticks + 45;
        } else if (r == 3 && a->obj_number < 3 && path_count < 3) {
            path_cancel(e);                               /* no way there from this side: another side */
            if (!look_path(e, obj, ++a->obj_number))
                finish(a, 3);
        } else if (r == 3 || act_ticks - a->since > 600)
            finish(a, 3);
        return;
    }
    if (act_ticks >= a->until) {
        finish(a, 1);
        return;
    }
    if (act_ticks >= a->next_gesture) {
        int g = a->turn ? 0 : gesture_of(a->who, act_rnd());
        play_anim(e, g ? g : 4);
        a->turn ^= 1;
        a->next_gesture = act_ticks + (a->partner_who == 2 ? 30 + act_rnd() % 30 : 120 + act_rnd() % 150);
    }
}

/* A stroll (2026-10-12): in a park or out for fun, a walk to another spot 80-200 px away, a look round there,
   then back to their own wandering. Urbania Park has only a grill and two phones, so everyone's free time was
   standing at those one after another. */
static int start_stroll(int slot, u8 *e, int who)
{
    int ang = act_rnd() & 7, len = 80 + act_rnd() % 120;
    static const s8 dirs[8][2] = { { 2, 0 }, { 1, 1 }, { 0, 2 }, { -1, 1 }, { -2, 0 }, { -1, -1 }, { 0, -2 }, { 1, -1 } };
    s32 xy[2] = { (s32)E32(e, 0x18) + ((dirs[ang][0] * len / 2) << 16), (s32)E32(e, 0x1C) + ((dirs[ang][1] * len / 4) << 16) };
    E8(e, 0x10B) = 0;
    if (path_request(e, xy, (u8 *)(e + 0x10B), 0) != 1)
        return 0;
    actor_t *a = &actors[slot];
    a->e = e;
    a->who = who;
    a->kind = K_STROLL;
    a->partner = 0;
    a->phase = CH_WALK;
    a->since = act_ticks;
    a->need = NEED_FUN;
    a->obj_number = 0;
    a->turn = 0;
    a->ract = (u8)sim_act_at(&sim, who - 31, week_minute());
    set_action(e, ACT_OURS);
    play_anim(e, 0x0A);
    npc_act.sent++;
    npc_act.strolls++;
    npc_act.last_who = who;
    return 1;
}

static void stroll_tick(actor_t *a)
{
    u8 *e = a->e;
    if (E8(e, 0x104) != ST_WANDER || E8(e, 0x105) != ACT_OURS) {
        finish(a, 0);
        return;
    }
    if (E8(e, 0x107) & 2) {
        finish(a, 2);
        return;
    }
    if (a->phase == CH_WALK) {
        int r = E8(e, 0x10B);
        if (r == 1 || r == 3 || act_ticks - a->since > 450) {
            path_cancel(e);
            play_anim(e, 4);
            a->phase = CH_TALK;
            a->until = act_ticks + 90 + act_rnd() % 150;    /* a look round: 3-8 s */
            a->next_gesture = act_ticks + 30;
        }
        return;
    }
    if (act_ticks >= a->until) {
        finish(a, 1);
        return;
    }
    if (act_ticks >= a->next_gesture && !a->turn) {
        int g = gesture_of(a->who, act_rnd());
        if (g)
            play_anim(e, g);
        else
            face(e, 1 + (act_rnd() & 7));                  /* no gestures: looks about */
        a->turn = 1;
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
        if (sim_act_at(&sim, i, week_minute()) == A_SOCIAL && act_rnd() % 3 && start_chat(slot, e, who))
            return;                                  /* socialising: a chat before a seat (they sat alone instead) */
        int n = wants(i, want), walking = 0;
        for (int k = 0; k < MAX_ACTORS; k++)          /* one of ours on the way to something at a time: two sent
                                                         at once to Café Z-Bach's love seats got the same place */
            walking |= actors[k].e && actors[k].kind == K_OBJECT && E8(actors[k].e, 0x104) == ST_GOTO;
        if (walking)
            n = 0;
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
            /* (a little off where they were: two people who came in the same door walked back onto one spot) */
            came_from[i][0] = (s32)E32(e, 0x18) + (s32)((act_rnd() % 25) - 12) * 0x10000;
            came_from[i][1] = (s32)E32(e, 0x1C) + (s32)((act_rnd() % 13) - 6) * 0x10000;
            actor_t *a = &actors[slot];
            a->e = e;
            a->who = who;
            a->partner = obj;
            a->need = want[w];
            a->obj_number = number;
            a->kind = K_OBJECT;
            a->ract = (u8)sim_act_at(&sim, i, week_minute());
            a->since = act_ticks;
            a->until = act_ticks + (want[w] == NEED_BLADDER ? 300 + act_rnd() % 150 :     /* 10-15 s: 8-11 game minutes */
                                    want[w] == NEED_HYGIENE ? 450 + act_rnd() % 300 :     /* a shower, 11-19 minutes */
                                    300 + act_rnd() % 450);           /* sit for 10-25 s (about 15-35 game minutes) */
            npc_act.sent++;
            npc_act.last_who = who;
            npc_act.last_need = want[w];
            npc_act.last_obj = number;
            return;                                  /* one new action per round */
        }
        int act = sim_act_at(&sim, i, week_minute());     /* free time: look at things here, or chat */
        int free = act == A_FUN || act == A_PARK || act == A_HOME || act == A_SOCIAL || act == A_EAT;
        /* free time, in a random order: a chat, a walk round the place (parks, fun), a look at something
           (socialising: a chat first) */
        int first = act == A_SOCIAL ? 0 : (int)(act_rnd() % 3);
        for (int t = 0; t < 3; t++) {
            int c = (first + t) % 3;
            if (c == 0 && start_chat(slot, e, who))
                return;
            if (c == 1 && (act == A_PARK || act == A_FUN) && start_stroll(slot, e, who))
                return;
            if (c == 2 && free && start_look(slot, e, who))
                return;
        }
    }
}

/* Their routine moved on (e.g. socialising -> eating at 13:29 -> socialising at 13:32): does what they are using
   still serve it? Then they carry on instead of standing up, and being sent straight back to the same seat a
   second later (that churn, every few game minutes, looked like someone who never gets up). */
static int still_wanted(actor_t *a, int act)
{
    switch (act) {
    case A_WASH:   return a->need == NEED_HYGIENE;
    case A_EAT:    return a->need == NEED_HUNGER || a->need == NEED_COMFORT;
    case A_FUN:
    case A_PARK:
    case A_HOME:   return a->need == NEED_FUN || a->need == NEED_COMFORT;
    case A_SOCIAL: return a->need == NEED_SOCIAL || a->need == NEED_COMFORT;
    case A_SLEEP:  return a->need == NEED_ENERGY || a->need == NEED_COMFORT;
    }
    return 0;
}

/* Someone we sent somewhere (they carry our needs block) still using an object with no actor watching them:
   the actor was dropped while they were briefly in another state (a chat with you, a gesture), and the
   object's own end can take forever for a townsperson (a seat waits for comfort 100). After 10 s like that
   they are told to stand up; if that doesn't take, they're put back to wandering. */
static u32 loose_since[SIM_PEOPLE];

static void watch_loose(void)
{
    for (u8 *e = world_first(); e; e = *(u8 **)e) {
        if (E16(e, 8) != 7)
            continue;
        int who = E16(e, 10), i = who - 31;
        if (i < 0 || i >= SIM_PEOPLE)
            continue;
        /* Up again after a use, they walk back to where they came from: the game's own wandering left them
           standing at the chair for a game hour or more (its random walks start blocked between the chair and
           the table), which looked like someone who never got up. */
        if (off_until[i]) {
            int r = off_result[i];
            s32 x = (s32)E32(e, 0x18), y = (s32)E32(e, 0x1C);
            int dx = (x - came_from[i][0]) >> 16, dy = (y - came_from[i][1]) >> 16;
            /* there, or standing still (they used to wait out the 15 s at the spot: frozen 10-20 game minutes) */
            int still = off_until[i] - act_ticks < 420 && x == off_x[i] && y == off_y[i];
            off_x[i] = x;
            off_y[i] = y;
            if (r == 1 || r == 3 || act_ticks >= off_until[i] || E8(e, 0x105) != ACT_OURS ||
                dx * dx + dy * dy < 8 * 8 || still) {
                if (E8(e, 0x104) == ST_WANDER && E8(e, 0x105) == ACT_OURS) {
                    path_cancel(e);
                    play_anim(e, 4);
                    set_action(e, 2);
                }
                off_until[i] = 0;
            }
        } else if (walk_off[i] && act_ticks >= walk_off[i]) {
            if (E8(e, 0x104) == ST_WANDER && E8(e, 0x105) == 7 && !acting(e) && path_count < 3) {
                off_result[i] = 0;
                if (path_request(e, came_from[i], &off_result[i], 0) == 1) {
                    set_action(e, ACT_OURS);
                    play_anim(e, 0x0A);
                    off_until[i] = act_ticks + 450;
                    npc_act.walked_off++;
                }
                walk_off[i] = 0;
            } else if (act_ticks - walk_off[i] > 300)
                walk_off[i] = 0;                      /* (busy with something else by now) */
        }
        if (E8(e, 0x104) != ST_USING || *(s32 **)(e + 0x114) != needs_block[i] || acting(e)) {
            loose_since[i] = 0;
            continue;
        }
        if (!loose_since[i]) {
            loose_since[i] = act_ticks;
            continue;
        }
        u32 t = act_ticks - loose_since[i];
        if (t >= 300 && t < 316) {                    /* 10 s: stand up (stop byte 3) */
            u8 *s = stop_byte(e);
            if (s)
                *s = 3;
            npc_act.loose++;
        } else if (t >= 600) {                        /* still there: back to wandering, whatever it takes */
            path_cancel(e);
            play_anim(e, 4);
            set_state(e, ST_WANDER);
            set_action(e, 2);
            loose_since[i] = 0;
            npc_act.forced++;
        }
    }
}

/* Someone the game is sending out of the area (entity +0x107 bit 1) walks to the way point toward their next
   place. When the walk fails while they're on screen (you, or someone, standing on the way point), the game
   puts them back to wandering and tries again at its next relocation, for ever: Sue Pirnova stayed in Waters'
   Gym from 6:00 to past 8:30 by the lift you were standing at (the original game does it too; NPC Life's comings
   and goings made it show). The game lets them go at once when the walk fails off screen. Here: after 20 s of
   trying, someone near their way point (64 px) goes through it as if they'd arrived; after 60 s, wherever they
   are. Only people calmly wandering (not talking to you, not in a story scene, not ours). */
#define LEAVE_NEAR  (64 * 64)
static u32 leave_since[SIM_PEOPLE], leave_seen[SIM_PEOPLE];

static void watch_leaving(void)
{
    for (u8 *e = world_first(); e; e = *(u8 **)e) {
        int i = E16(e, 10) - 31;
        if (E16(e, 8) != 7 || i < 0 || i >= SIM_PEOPLE)
            continue;
        if (E8(e, 0x107) & 2) {                       /* the bit goes off after each failed walk: count from the first */
            if (!leave_since[i] || act_ticks - leave_seen[i] > 600)
                leave_since[i] = act_ticks;
            leave_seen[i] = act_ticks;
        } else if (!leave_since[i] || act_ticks - leave_seen[i] > 600) {
            leave_since[i] = 0;                       /* not asked again for 20 s: they stay after all */
            continue;
        }
        u32 t = act_ticks - leave_since[i];
        int a = E8(e, 0x105);
        if (t < 600 || E8(e, 0x104) != ST_WANDER || (a != 2 && a != 7 && a != 0x19) || acting(e))
            continue;
        int dx = ((s32)E32(e, 0x18) - (s32)E32(e, 0x38)) >> 16, dy = ((s32)E32(e, 0x1C) - (s32)E32(e, 0x3C)) >> 16;
        if (!E32(e, 0x38) || (dx * dx + dy * dy > LEAVE_NEAR && t < 1800))
            continue;
        path_cancel(e);                               /* as the game does on arriving at the way point */
        set_state(e, 1);
        walked_out(e);
        leave_since[i] = 0;
        npc_act.let_out++;
    }
}

/* Every tick from mod_on_tick (NPC Life on, city running). */
static void act_tick(void)
{
    act_ticks++;
    if (act_ticks & 15)
        return;
    watch_loose();
    watch_leaving();
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
        int now_act = sim_act_at(&sim, a->who - 31, week_minute());
        if (a->ract != now_act && a->kind != K_CHAT && still_wanted(a, now_act)) {
            a->ract = (u8)now_act;                   /* socialising -> eating at the same table: stay seated */
            npc_act.kept++;
        }
        if (a->ract != now_act) {
            int who = a->who;
            finish(a, 1);                            /* their day moved on (e.g. breakfast time) */
            rest_until[who - 31] = act_ticks + 30;   /* pick the next thing almost at once */
            continue;
        }
        if (a->kind == K_CHAT) {
            chat_tick(a);
            continue;
        }
        if (a->kind == K_LOOK) {
            look_tick(a);
            continue;
        }
        if (a->kind == K_STROLL) {
            stroll_tick(a);
            continue;
        }
        int st = E8(e, 0x104);
        if (E8(e, 0x107) & 2)
            finish(a, 2);                            /* the game wants them elsewhere */
        else if (st == ST_GOTO && act_ticks - a->since > 900)
            finish(a, 3);                            /* 30 s and not there: stuck */
        else if (st == ST_USING && act_ticks >= a->until)
            finish(a, 1);
        else if (st == ST_USING && a->partner) {
            spot_learn(a->partner, e);
            u8 *other = someone_using_at(e, (s32)E32(e, 0x18) >> 16, (s32)E32(e, 0x1C) >> 16);
            int newer = 0;                               /* the other sat down after us: they get up, not us */
            for (int j = 0; j < MAX_ACTORS; j++)
                newer |= other && actors[j].e == other && actors[j].since > a->since;
            if (other && !newer && act_ticks - a->since > 30) {
                npc_act.taken_skips++;                   /* sat down on someone: up again */
                finish(a, 0);
                continue;
            }
        }
        else if (st != ST_GOTO && st != ST_USING) {  /* done by itself (or the use failed) */
            a->e = 0;
            npc_act.finished++;
            rest_until[a->who - 31] = act_ticks + 450 + (act_rnd() % 600);
            walk_off[a->who - 31] = act_ticks + 45;
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
    for (u8 *e = world_first(); e; e = *(u8 **)e) {      /* and anyone walking away from an object */
        int i = E16(e, 10) - 31;
        if (E16(e, 8) == 7 && i >= 0 && i < SIM_PEOPLE && off_until[i] && E8(e, 0x105) == ACT_OURS) {
            path_cancel(e);
            play_anim(e, 4);
            set_action(e, 2);
        }
    }
    for (int i = 0; i < SIM_PEOPLE; i++)
        off_until[i] = walk_off[i] = 0;
    for (int k = 0; k < N_SPOTS; k++)
        spots[k].obj = 0;                            /* another place, other objects */
}

/* A new area: its people are new entities. */
static void act_area_reset(void)
{
    for (int k = 0; k < MAX_ACTORS; k++)
        actors[k].e = 0;
    for (int i = 0; i < SIM_PEOPLE; i++)
        off_until[i] = walk_off[i] = leave_since[i] = 0;
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
