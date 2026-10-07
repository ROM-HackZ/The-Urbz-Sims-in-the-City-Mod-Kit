/* The strays quest (Phase 10, docs/plan-phase10.md), included by pets.c.

   Once you are out of jail (goal m0g5 "Find a Place to Live" is active) a stray puppy and a stray kitten
   (the pets marked "stray" in pets.json) hang about in Urbania Park. They are shy: until you have fed one,
   it backs away when you walk up. Press A at one: Feed (one Pet Treats from Pockets) / Leave. Fed on two
   different days, it trusts you and "Take Home" appears: it goes into Pockets as that pet. Then a
   townsperson in the park walks over and adopts the other one, which follows them about until they leave.
   Kept in the save: per stray its trust, the day it was last fed and who adopted it. */

#define URBANIA_PARK 19
#define NO_ONE 0
#define THE_PLAYER 0xFF
enum { SF_GONE = 1, SF_FED = 2 };                /* stray_t.flags */
typedef struct { u8 trust, flags, adopter, pad; u16 fed_day, pad2; } stray_t;
static stray_t strays[2];
static u8 strays_intro;

enum { S_WANDER, S_TALK, S_FLEE, S_HOME, S_SIT, S_APPROACH, S_COMING, S_TO_PERSON, S_FOLLOW, S_LEAVE };
static struct { u8 *e; u8 mode, path, moving, pad; u16 timer; u8 *person; } stray_live[2];
static const s16 stray_home[2][2] = { { 776, 668 }, { 836, 664 } };   /* the path by Gramma Hattie's spot */
static u32 need_strays;
static s16 last_px, last_py;
static u16 player_still;                         /* ticks the player has not moved */

#define set_action   G(entity_set_action, void (*)(void *e, int action))
#define path_request G(path_request, int (*)(void *e, s32 *xy, u8 *result, int flags))
#define path_cancel  G(path_cancel, void (*)(void *e))
#define PATH_COUNT   (*(volatile u8 *)ADDR_path_count)
#define ACT_OURS     0x30                        /* an action the townsperson's wander state ignores */

static const pet_t *stray_pet(int k)
{
    u32 n;
    const pet_t *p = pet_list(&n);
    for (u32 i = 0, seen = 0; i < n; i++)
        if (p[i].flags & 1 && seen++ == (u32)k)
            return &p[i];
    return 0;
}

static const char *stray_name(int k)
{
    const pet_t *p = stray_pet(k);
    return p ? p->name : "";
}

static int quest_open(void)
{
    return *(volatile u8 *)(ADDR_goal_table + 5 * 0xC) != 0;   /* m0g5 active: out of jail */
}

static int stray_alive(int k)
{
    u8 *e = stray_live[k].e;
    const pet_t *p = stray_pet(k);
    return e && p && ENT_TYPE(e) == 9 && ENT_KIND(e) == p->kind && !(ENT_FLAGS(e) & 2);
}

/* Here and free to talk to. */
static int stray_here(int k)
{
    return stray_alive(k) && !(strays[k].flags & SF_GONE) && stray_live[k].mode <= S_APPROACH;
}

static void stray_remove(int k)
{
    if (stray_alive(k))
        ENT_FLAGS(stray_live[k].e) |= 2;        /* the world loop frees it */
    stray_live[k].e = 0;
}

/* dir 1-8 clockwise, 8 = up (entity_face) towards (dx, dy) */
static int dir8(int dx, int dy)
{
    int ax = dx < 0 ? -dx : dx, ay = dy < 0 ? -dy : dy;
    if (ax > 2 * ay)
        return dx > 0 ? 2 : 6;
    if (ay > 2 * ax)
        return dy > 0 ? 4 : 8;
    return dx > 0 ? (dy < 0 ? 1 : 3) : (dy > 0 ? 5 : 7);
}

static int dist2(u8 *a, u8 *b)
{
    int dx = ENT_X(a) - ENT_X(b), dy = ENT_Y(a) - ENT_Y(b);
    return dx * dx + dy * dy;
}

static void person_name(int id, char *out)
{
    copy_name(out, id >= 31 && id < 80 ? text_get(512 + id - 31) : "Someone");
}

static int stray_menu(int k, u16 *opts, u8 *acts)
{
    int n = 0, t = strays[k].trust;
    if (t) {
        opts[n] = 725;                           /* "Pet" */
        acts[n++] = DO_PET;
    }
    opts[n] = 3632;                              /* "Feed" */
    acts[n++] = DO_FEED;
    if (t >= 2) {
        opts[n] = (u16)text_id(T_TAKE_HOME);
        acts[n++] = DO_TAKE;
    }
    opts[n] = (u16)text_id(T_LEAVE);
    acts[n++] = DO_LEAVE;
    stray_live[k].mode = S_TALK;
    return n;
}

static void stray_resume(int k)
{
    if (!stray_alive(k))
        return;
    stray_live[k].mode = S_WANDER;
    pets_play(stray_live[k].e, A_STAND);
}

static void stray_after(int k)                   /* after Pet / Feed: it sits by you for a bit */
{
    if (!stray_alive(k))
        return;
    stray_live[k].mode = S_SIT;
    stray_live[k].timer = 240;
    pets_play(stray_live[k].e, A_SIT);
}

/* Feed: 1 = it eats (a treat is used), 0 = no (told why). */
static int stray_feed(int k)
{
    stray_t *s = &strays[k];
    u16 today = (u16)game_time.day;
    if (s->flags & SF_FED && s->fed_day == today) {
        say(T_FED_TODAY, stray_name(k), 0);
        return 0;
    }
    if (!pockets_take(TREATS)) {
        play_sound(3);
        say(T_NO_TREATS, stray_name(k), 0);
        return 0;
    }
    if (s->trust < 2)
        s->trust++;
    s->flags |= SF_FED;
    s->fed_day = today;
    say(s->trust >= 2 ? T_TRUSTS : T_FED_FIRST, stray_name(k), 0);
    pets_stats.stray_fed++;
    return 1;
}

static void adopt_start(int o);

static void stray_take(int k)
{
    const pet_t *p = stray_pet(k);
    if (!p || list_add(*(void **)(ADDR_game_state + 0x154), p->object, 0, 0) != 1) {
        play_sound(3);
        stray_resume(k);
        return;                                  /* Pockets full: "Your Pockets are full!" is the game's */
    }
    play_sound(0x13E);                           /* the Chicken's pick-up sound */
    stray_remove(k);
    strays[k].flags |= SF_GONE;
    strays[k].adopter = THE_PLAYER;
    say(T_ADOPTED, stray_name(k), 0);
    pets_stats.quest = 2;
    adopt_start(1 - k);
}

/* ---- the other stray finds a home too ---------------------------------------------------------------- */
static void adopted_by(int o, u8 *person, int id)
{
    char nm[16];
    person_name(id, nm);
    strays[o].flags |= SF_GONE;
    strays[o].adopter = (u8)id;
    pets_stats.adopter = (u32)id;
    say(T_OTHER_ADOPTED, nm, stray_name(o));
    if (stray_alive(o)) {
        pets_play(stray_live[o].e, A_HAPPY);
        stray_live[o].mode = person ? S_FOLLOW : S_LEAVE;
        stray_live[o].timer = 150;
    }
}

static void adopt_start(int o)
{
    if (strays[o].flags & SF_GONE)
        return;
    u8 *best = 0, *se = stray_live[o].e;
    int bd = 500 * 500;
    if (stray_alive(o))
        for (u8 *p = *(u8 **)ADDR_entity_lists; p; p = *(u8 **)p) {
            int id = ENT_KIND(p);
            if (ENT_TYPE(p) != 7 || id < 31 || id >= 80 || p[0x104] != 0x23 || (ENT_FLAGS(p) & 2))
                continue;
            int d = dist2(p, se);
            if (d < bd) {
                bd = d;
                best = p;
            }
        }
    if (!best) {                                 /* nobody about: a park regular took it home */
        adopted_by(o, 0, 43);                    /* Gramma Hattie */
        return;
    }
    stray_live[o].person = best;
    stray_live[o].timer = 600;
    stray_live[o].mode = S_TO_PERSON;            /* it trots over, unless they can walk to it */
    if (PATH_COUNT < 3) {
        s32 xy[2];
        int dx = ENT_X(best) - ENT_X(se), dy = ENT_Y(best) - ENT_Y(se);
        int len = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy);
        if (len < 1)
            len = 1;
        xy[0] = *(s32 *)(se + 0x18) + ((dx * 20 / len) << 16);
        xy[1] = *(s32 *)(se + 0x1C) + ((dy * 20 / len) << 16);
        stray_live[o].path = 0;
        if (path_request(best, xy, &stray_live[o].path, 0) == 1) {
            set_action(best, ACT_OURS);
            entity_anim(best, 0x0A);             /* walk */
            stray_live[o].mode = S_COMING;
            pets_play(se, A_SIT);
            pets_stats.adopt_walk = 1;
            return;
        }
    }
    pets_play(se, A_WALK);
}

static int person_alive(u8 *p, int id)
{
    for (u8 *q = *(u8 **)ADDR_entity_lists; q; q = *(u8 **)q)
        if (q == p)
            return ENT_TYPE(p) == 7 && ENT_KIND(p) == id && !(ENT_FLAGS(p) & 2);
    return 0;
}

/* ---- the strays' behaviour (entity +0x4C) ------------------------------------------------------------- */
void strays_behaviour(u8 *e)
{
    int k = stray_live[0].e == e ? 0 : stray_live[1].e == e ? 1 : -1;
    if (k < 0) {
        critter_update(e);
        return;
    }
    u8 *pl = player_entity();
    int hx = stray_home[k][0], hy = stray_home[k][1];
    switch (stray_live[k].mode) {
    case S_TALK:
    case S_COMING:
        return;                                  /* held */
    case S_SIT:
        if (stray_live[k].timer && --stray_live[k].timer)
            return;
        stray_resume(k);
        return;
    case S_APPROACH:                             /* curious: comes up to you while you stand still */
        if (!pl || player_still < 30 || !--stray_live[k].timer) {
            stray_resume(k);
            return;
        }
        if (dist2(e, pl) > 28 * 28) {
            entity_face(e, entity_dir_to(e, pl));
            entity_go(e);
            return;
        }
        entity_stop(e);
        entity_face(e, entity_dir_to(e, pl));
        stray_after(k);                          /* sits in front of you, looking up */
        stray_live[k].timer = 360;
        return;
    case S_FLEE:
        entity_go(e);
        if (--stray_live[k].timer)
            return;
        stray_resume(k);
        return;
    case S_HOME: {
        int dx = hx - ENT_X(e), dy = hy - ENT_Y(e);
        if (dx * dx + dy * dy > 30 * 30 && --stray_live[k].timer) {
            entity_face(e, dir8(dx, dy));
            entity_go(e);
            return;
        }
        stray_resume(k);
        return;
    }
    case S_TO_PERSON:
    case S_FOLLOW: {
        u8 *p = stray_live[k].person;
        int id = stray_live[k].mode == S_FOLLOW ? strays[k].adopter : ENT_KIND(p);
        if (!person_alive(p, id)) {              /* they left the park: so did it */
            if (stray_live[k].mode == S_TO_PERSON)
                adopted_by(k, 0, 43);
            else
                stray_remove(k);
            return;
        }
        int d = dist2(e, p);
        if (stray_live[k].mode == S_TO_PERSON && (d < 30 * 30 || !--stray_live[k].timer)) {
            entity_stop(e);
            entity_face(p, entity_dir_to(p, e));
            adopted_by(k, p, ENT_KIND(p));
            return;
        }
        if (d > 26 * 26) {                       /* keep up with them */
            if (!stray_live[k].moving)
                pets_play(e, A_WALK);
            stray_live[k].moving = 1;
            entity_face(e, entity_dir_to(e, p));
            entity_go(e);
        } else {
            if (stray_live[k].moving)
                pets_play(e, A_STAND);
            stray_live[k].moving = 0;
            entity_stop(e);
            entity_face(e, entity_dir_to(e, p));
        }
        return;
    }
    case S_LEAVE:                                /* trots off out of the park */
        entity_face(e, 7);
        entity_go(e);
        if (!stray_live[k].timer || !--stray_live[k].timer)
            stray_remove(k);
        return;
    }
    critter_update(e);                           /* S_WANDER: the game's own wandering */
    int dx = hx - ENT_X(e), dy = hy - ENT_Y(e);
    if (dx * dx + dy * dy > 110 * 110) {         /* strayed too far: back to its spot */
        stray_live[k].mode = S_HOME;
        stray_live[k].timer = 240;
        pets_play(e, A_WALK);
        entity_face(e, dir8(dx, dy));
        return;
    }
    if (!pl)
        return;
    int d = dist2(e, pl);
    if (!strays[k].trust && player_still < 10 && d < 64 * 64) {   /* shy: backs away while you move */
        entity_face(e, dir8(ENT_X(e) - ENT_X(pl), ENT_Y(e) - ENT_Y(pl)));
        pets_play(e, A_WALK);
        stray_live[k].mode = S_FLEE;
        stray_live[k].timer = 20;
    } else if (player_still >= 60 && d < 120 * 120 && d > 32 * 32) {  /* stand still: it comes to you */
        pets_play(e, A_WALK);
        stray_live[k].mode = S_APPROACH;
        stray_live[k].timer = 240;
    }
}

static void strays_spawn(void)
{
    if (current_area != URBANIA_PARK || !quest_open())
        return;
    for (int k = 0; k < 2; k++) {
        const pet_t *p = stray_pet(k);
        if (!p || strays[k].flags & SF_GONE || stray_alive(k))
            continue;
        u8 *e = spawn_critter(p->kind, 4, 0, stray_home[k][0], stray_home[k][1]);
        stray_live[k].e = e;
        stray_live[k].mode = S_WANDER;
        if (e)
            *(void (**)(u8 *))(e + 0x4C) = strays_behaviour;
        pets_stats.stray_n++;
    }
    if (!strays_intro && stray_pet(0) && !((strays[0].flags & strays[1].flags) & SF_GONE)) {
        strays_intro = 1;
        say(T_STRAYS_INTRO, 0, 0);
        pets_stats.quest = 1;
    }
}

static void strays_tick(u8 *pl)
{
    if (need_strays) {
        need_strays = 0;
        strays_spawn();
    }
    if (pl) {
        if (ENT_X(pl) == last_px && ENT_Y(pl) == last_py) {
            if (player_still < 0xFFFF)
                player_still++;
        } else
            player_still = 0;
        last_px = ENT_X(pl);
        last_py = ENT_Y(pl);
    }
    for (int k = 0; k < 2; k++) {                /* a townsperson walking up to adopt a stray */
        if (stray_live[k].mode != S_COMING)
            continue;
        u8 *p = stray_live[k].person, *e = stray_live[k].e;
        int id = person_alive(p, ENT_KIND(p)) ? ENT_KIND(p) : 0;
        if (!id || !stray_alive(k)) {
            if (stray_alive(k))
                adopted_by(k, 0, 43);
            continue;
        }
        if (stray_live[k].path == 1 || dist2(p, e) < 36 * 36 || stray_live[k].path == 3 ||
            !--stray_live[k].timer) {
            path_cancel(p);
            entity_anim(p, 4);
            entity_face(p, entity_dir_to(p, e));
            entity_face(e, entity_dir_to(e, p));
            set_action(p, 2);                    /* back to their own wandering */
            adopted_by(k, p, id);
        }
    }
    pets_stats.trust = strays[0].trust | strays[1].trust << 8 | strays[0].flags << 16 | strays[1].flags << 24;
}

static void strays_area_enter(int area)
{
    for (int k = 0; k < 2; k++)
        stray_live[k].e = 0;
    need_strays = area == URBANIA_PARK;
}

/* The Pets page lines for the quest (once you have met the strays). */
static void strays_page(mod_page_t *pg)
{
    char line[48], nm[16], *q;
    if (!strays_intro || !stray_pet(0))
        return;
    for (int k = 0; k < 2; k++) {
        stray_t *s = &strays[k];
        if (s->adopter == THE_PLAYER)
            continue;                            /* yours: it has its own line (once let loose at home) */
        if (s->flags & SF_GONE) {                /* "Kitten: with Crystal" */
            person_name(s->adopter, nm);
            q = str_cat(line, stray_name(k));
            q = str_cat(q, ": with ");
            q = str_cat(q, nm);
        } else {
            q = str_cat(line, "Stray ");
            q = str_cat(q, stray_name(k));
            q = str_cat(q, s->trust >= 2 ? ": trusts you" : s->trust ? ": fed once (1/2)" : ": in Urbania Park");
        }
        pg->print(pg, line);
    }
}
