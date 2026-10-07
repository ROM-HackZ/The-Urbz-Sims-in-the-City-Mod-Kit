/* Kit code for pets (built in whenever a mod has pets.json; see urbz_pets.py, docs/systems.md "Pets").

   A pet is a critter of its own kind (the Chicken's machinery). Its object (a copy of object 225) placed at
   home turns into the critter; Phase 9 makes it a real pet:
   - my pets: the placed pets are kept in the mod save data and put back when you come home or load
     (the game forgets critters);
   - actions: its own animation table (urbz_import.ACTIONS: stand, walk, sit, lie, sleep, sniff, play, eat,
     happy, sad, petted, scratch), played by pets_play();
   - a life: pets_behaviour wraps the critter behaviour: it wanders as before, and now and then does
     something (sniff, sit, scratch, lie down, play), sleeps at night, mopes when hungry or unhappy, and
     comes to greet you when you come home;
   - you: walk up to a pet and press A: Pet / Play / Feed / Put in Pocket (the game's own question box);
   - needs: hunger and happiness (0-100), going down with the game clock.

   Phase 10: beds (a pet sleeps in its own bed or cage at night), pets move with you, the Pets page on the
   Mods page, and the strays quest in Urbania Park (strays.inc).

   The builder writes before the (moved) critter behaviour table:
     'PETT', u16 text[n_text] (string numbers, padded to 4), u32 n_text,
     'PETB', {u16 object, u16 kind, u32 actions, u16 bed, u16 0, char name[12]} x n, u32 n;
   actions -> N_ACTIONS x {records (5 facings x 16 bytes), frame script} or 0. */
#include "game.h"
#include "mod.h"

#define PETB 0x42544550                          /* 'PETB' */
#define PETT 0x54544550                          /* 'PETT' */
#define TREATS 396                               /* "Pet Treats" (mods/pets objects.json) */
enum { A_STAND, A_WALK, A_SIT, A_LIE, A_SLEEP, A_SNIFF, A_PLAY, A_EAT, A_HAPPY, A_SAD, A_PETTED, A_SCRATCH,
       A_BEDSLEEP, A_BEDLIE,                     /* sleep / lie drawn onto its bed (urbz_art.BED_ACTIONS) */
       N_ACTIONS };

typedef struct { u16 object, kind; const u32 *actions; u16 bed; u8 flags, pad; char name[12]; s8 spot_x, spot_y;
                 u16 pad2; } pet_t;            /* flags bit 0: a stray; spot: where it lies on its bed */
/* The messages (urbz_pets.TEXT_KEYS, same order). */
enum { T_STRAYS_INTRO, T_STRAY_WARY, T_STRAY_FRIENDLY, T_NO_TREATS, T_FED_FIRST, T_FED_TODAY, T_TRUSTS,
       T_TAKE_HOME, T_ADOPTED, T_OTHER_ADOPTED, T_LEAVE, T_OK, N_TEXT };

#define G(name, type) GAME_FN(ADDR_##name, type)
#define entity_records   G(entity_records, void (*)(void *e, const void *record))
#define entity_script    G(entity_set_script, void (*)(void *e, unsigned script, int start))
#define entity_stop      G(entity_stop, void (*)(void *e))
#define entity_go        G(entity_go, void (*)(void *e))
#define entity_dir_to    G(entity_dir_to, int (*)(void *a, void *b))
#define entity_face      G(entity_face, void (*)(void *e, int dir))
#define entity_faces     G(entity_faces, int (*)(void *a, void *b))
#define entity_clear     G(entity_flag_clear, void (*)(void *e, unsigned bits))
#define entity_anim      G(entity_play_anim, void (*)(void *e, int anim))
#define critter_anim     G(critter_play_anim, void (*)(void *e, int slot))
#define critter_update   G(critter_behaviour, void (*)(void *e))
#define dialog_open      G(dialog_open, void (*)(void))
#define play_sound       G(ui_sound, void (*)(int id))
#define motive_effect    G(motive_apply_effect, void (*)(s32 *motives, int row, int scale))
#define is_home_area     G(is_home_area, unsigned (*)(const void *lots, unsigned area))

struct { u32 magic, spawned, picked, pets; } pets_count = { 0x43544550, 0, 0, 0 };   /* 'PETC' (tests) */

static const pet_t *pet_list(u32 *n)
{
    const u8 *table = *(const u8 **)ADDR_crit_table_lit;
    *n = *(const u32 *)(table - 4);
    const pet_t *p = (const pet_t *)(table - 4 - sizeof(pet_t) * *n);
    if (*n > 64 || *((const u32 *)p - 1) != PETB)
        *n = 0;
    return p;
}

/* A message's string number (0 if the builder wrote none). */
static int text_id(int t)
{
    u32 n;
    const u32 *p = (const u32 *)pet_list(&n);
    u32 nt = p[-2];
    if (p[-1] != PETB || nt > 64 || t >= (int)nt)
        return 0;
    const u16 *ids = (const u16 *)((const u8 *)(p - 2) - ((2 * nt + 3) & ~3u));
    return *((const u32 *)ids - 1) == PETT ? ids[t] : 0;
}

static const pet_t *pet_of_kind(unsigned kind)
{
    u32 n;
    const pet_t *p = pet_list(&n);
    for (u32 i = 0; i < n; i++)
        if (p[i].kind == kind)
            return &p[i];
    return 0;
}

/* The object a pet critter gives back (0 = not a pet). */
unsigned pets_object_of(unsigned kind)
{
    const pet_t *p = pet_of_kind(kind);
    return p ? p->object : 0;
}

/* Play one of a pet's actions (its own table; drawn pets without one: the game's stand/walk slots). */
static void pets_play(u8 *e, int action)
{
    const pet_t *p = pet_of_kind(*(u16 *)(e + 10));
    if (!p || !p->actions) {
        critter_anim(e, action == A_WALK ? 1 : 0);
        return;
    }
    const u8 *records = (const u8 *)p->actions[2 * action];
    unsigned script = p->actions[2 * action + 1];
    u8 dir = ((const u8 *)ADDR_critter_facing_map)[e[0x12] & 7];
    entity_records(e, records + 16 * dir);
    entity_script(e, script, 0);
}

/* ---- my pets: the pets placed at home, kept in the save ------------------------------------------ */
#define MAX_MINE 12
#define SAVE_MAGIC 0x32544550                    /* 'PET2' (Phase 10: + the strays quest) */
#define SAVE_MAGIC_1 0x31544550                  /* 'PET1' (Phase 9 saves load too) */
typedef struct {
    u16 object;                                  /* the pet's object number (what goes back to Pockets) */
    u8 kind, facing;
    s16 x, y;                                    /* where it was last seen, in its home area */
    u8 area, hunger, happy, flags;               /* hunger / happy: 100 = full / very happy */
} mypet_t;

enum { M_WANDER, M_ACT, M_GO, M_TALK, M_BED };   /* what a pet is doing (not saved) */
typedef struct { u8 *e; u8 mode, action; u16 timer, age; u8 *bed; } live_t;

static mypet_t mine[MAX_MINE];
static live_t live[MAX_MINE];
static u32 n_mine, need_spawn, greet;
struct { u32 magic, kept, respawned, forgot, loads, loaded, acts, talks, last_pick, actions_done, a_presses, a_state, a_dx, a_dy, a_faces, mood0, n, act_mask, greets, px, py,
           to_bed, in_bed, bed0, moved, quest, trust, adopter, stray_n, pet0, msgs, stray_fed, adopt_walk, page_lines; }
    pets_stats = { 0x53544550 };                 /* 'PETS' (tests read it) */

#define ENT_TYPE(e)  (*(u16 *)((e) + 8))
#define ENT_KIND(e)  (*(u16 *)((e) + 10))
#define ENT_FLAGS(e) (*(u32 *)((e) + 0xC))
#define ENT_X(e)     ((s16)(*(s32 *)((e) + 0x18) >> 16))
#define ENT_Y(e)     ((s16)(*(s32 *)((e) + 0x1C) >> 16))
#define ANIM_DONE    0x400000

static u32 rnd(u32 n)
{
    static u32 s = 0x2545F491;
    s = s * 1103515245 + 12345;
    return n ? (s >> 16) % n : 0;
}

static int alive(u32 i)
{
    u8 *e = live[i].e;
    return e && ENT_TYPE(e) == 9 && ENT_KIND(e) == mine[i].kind && !(ENT_FLAGS(e) & 2);
}

static int mine_of(u8 *e)
{
    for (u32 i = 0; i < n_mine; i++)
        if (live[i].e == e)
            return (int)i;
    return -1;
}

static void *player_entity(void)
{
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e)
        if (ENT_TYPE(e) == 0)
            return e;
    return 0;
}

void pets_behaviour(u8 *e);

static void take_over(u32 i, u8 *e)
{
    live[i].e = e;
    live[i].mode = M_WANDER;
    live[i].timer = 60 + rnd(120);
    if (e)
        *(void (**)(u8 *))(e + 0x4C) = pets_behaviour;
}

static void pets_keep(u16 object, u8 kind, u8 *e)
{
    if (!e || n_mine >= MAX_MINE)
        return;
    mypet_t *m = &mine[n_mine];
    m->object = object;
    m->kind = kind;
    m->facing = e[0x12];
    m->x = ENT_X(e);
    m->y = ENT_Y(e);
    m->area = (u8)current_area;
    m->hunger = m->happy = 80;
    m->flags = 0;
    take_over(n_mine++, e);
    pets_stats.kept++;
}

static void forget(u32 i)
{
    for (u32 j = i; j + 1 < n_mine; j++) {
        mine[j] = mine[j + 1];
        live[j] = live[j + 1];
    }
    n_mine--;
    pets_stats.forgot++;
}

/* The game's pick-up gave this critter back to Pockets: it is no longer one of mine. */
void pets_forget(u8 *e)
{
    int i = mine_of(e);
    if (i >= 0)
        forget((u32)i);
}

/* ---- a pet's life ------------------------------------------------------------------------------- */
static int night(void)
{
    s8 h = game_time.hour;
    return h >= 22 || h < 7;
}

static void act(u32 i, int action, int ticks)
{
    u8 *e = live[i].e;
    entity_stop(e);
    live[i].mode = M_ACT;
    live[i].action = (u8)action;
    live[i].timer = (u16)ticks;
    live[i].age = 0;
    pets_play(e, action);
    pets_stats.acts++;
    pets_stats.act_mask |= 1u << action;
}

static void wander(u32 i)
{
    live[i].mode = M_WANDER;
    live[i].bed = 0;
    live[i].timer = 120 + rnd(240);
    pets_play(live[i].e, A_STAND);
}

/* ---- beds: a pet sleeps in its own bed or cage (pets.json "bed") ----------------------------------- */

#define BED_FRONT 20   /* a pet on its bed stands this far in front of the bed's position; its bed actions are
                          drawn higher, onto the bed (urbz_art.BED_FRONT, pets.json "bed_spot") */

/* A placed bed of this pet's type that no other pet has taken (0 = none). */
static u8 *find_bed(u32 i)
{
    const pet_t *p = pet_of_kind(mine[i].kind);
    if (!p || !p->bed)
        return 0;
    for (u8 *node = *(u8 **)ADDR_object_list_head; node; node = *(u8 **)node) {
        u8 *be = *(u8 **)(node + 0x24);
        /* placed for real: node+0x32 = 1 and a position (while you carry one to place it, the list holds a
           preview node (+0x32 = 0) and the object-to-be (no position yet)) */
        if (*(u16 *)(node + 8) != p->bed || !be || node[0x32] != 1 || !*(s32 *)(be + 0x18))
            continue;
        u32 j;
        for (j = 0; j < n_mine; j++)
            if (j != i && live[j].bed == be && alive(j))
                break;
        if (j == n_mine)
            return be;
    }
    return 0;
}

static void go_to_bed(u32 i, u8 *bed, int action)
{
    live[i].mode = M_BED;
    live[i].bed = bed;
    live[i].action = (u8)action;
    live[i].timer = 180;                           /* 6 s to get there, else it sleeps where it is */
    pets_play(live[i].e, A_WALK);
    pets_stats.to_bed++;
}

static void bed_tick(u32 i)
{
    u8 *e = live[i].e, *be = live[i].bed;
    const pet_t *p = pet_of_kind(mine[i].kind);
    int sx = p ? p->spot_x : 0, sy = BED_FRONT;    /* in front of the bed; its bed pictures are drawn up on it */
    int dx = ENT_X(be) + sx - ENT_X(e), dy = ENT_Y(be) + sy - ENT_Y(e);
    int d2 = dx * dx + dy * dy;
    if (d2 > 6 * 6 && live[i].timer) {
        entity_face(e, entity_dir_to(e, be));
        entity_go(e);
        return;
    }
    int a = live[i].action;
    if (d2 <= 40 * 40) {                           /* close enough: lie down on it */
        *(s32 *)(e + 0x18) = *(s32 *)(be + 0x18) + (sx << 16);
        *(s32 *)(e + 0x1C) = *(s32 *)(be + 0x1C) + (sy << 16);
        e[0x12] = 4;                               /* facing you */
        pets_stats.in_bed++;
        act(i, a == A_SLEEP ? A_BEDSLEEP : A_BEDLIE, a == A_SLEEP ? 900 + rnd(900) : 300 + rnd(300));
        live[i].bed = be;
        return;
    }
    act(i, a, a == A_SLEEP ? 900 + rnd(900) : 300 + rnd(300));   /* stuck on the way: here will do */
}

/* What to do next, from the time of day and how it feels. */
static void choose(u32 i)
{
    mypet_t *m = &mine[i];
    if (night()) {
        int a = rnd(4) ? A_SLEEP : A_LIE;
        u8 *bed = find_bed(i);
        if (bed)
            go_to_bed(i, bed, a);
        else
            act(i, a, 600 + rnd(900));
        return;
    }
    if (m->hunger < 25 || m->happy < 25) {          /* moping: sad, sits or lies about */
        static const u8 mope[] = { A_SAD, A_SAD, A_SIT, A_LIE };
        act(i, mope[rnd(4)], 200 + rnd(200));
        return;
    }
    static const u8 idle[] = { A_SNIFF, A_SNIFF, A_SIT, A_SCRATCH, A_LIE, A_PLAY, A_HAPPY, A_SIT };
    int a = idle[rnd(8)];
    u8 *bed = a == A_LIE && rnd(2) ? find_bed(i) : 0;   /* a rest in its bed now and then */
    if (bed)
        go_to_bed(i, bed, A_LIE);
    else
        act(i, a, a == A_LIE ? 300 + rnd(300) : 120 + rnd(150));
}

/* Walk towards the player (greeting), stop when close. */
static void go_to_player(u32 i)
{
    u8 *e = live[i].e, *pl = player_entity();
    if (!pl) {
        wander(i);
        return;
    }
    int dx = ENT_X(pl) - ENT_X(e), dy = ENT_Y(pl) - ENT_Y(e);
    if (dx * dx + dy * dy < 24 * 24 || !live[i].timer) {
        entity_stop(e);
        entity_face(e, entity_dir_to(e, pl));
        act(i, A_HAPPY, 90);
        pets_stats.greets++;
        return;
    }
    entity_face(e, entity_dir_to(e, pl));
    entity_go(e);
}

void pets_behaviour(u8 *e)
{
    int i = mine_of(e);
    if (i < 0 || live[i].mode == M_WANDER) {
        critter_update(e);                         /* the game's own wandering (walk / stand) */
        if (i >= 0 && live[i].mode == M_WANDER && !--live[i].timer && e[0x104] != 0x12)
            choose((u32)i);
        return;
    }
    live_t *l = &live[i];
    if (l->timer)
        l->timer--;
    if (l->mode == M_GO) {
        go_to_player((u32)i);
        return;
    }
    if (l->mode == M_TALK)
        return;                                    /* held while you talk to it */
    if (l->mode == M_BED) {
        bed_tick((u32)i);
        return;
    }
    l->age++;
    if (l->action == A_SLEEP && l->age % 150 == 0) {   /* a bed was put down: off to it */
        u8 *bed = find_bed((u32)i);
        if (bed) {
            go_to_bed((u32)i, bed, A_SLEEP);
            return;
        }
    }
    int once = l->action == A_PLAY || l->action == A_EAT || l->action == A_HAPPY || l->action == A_PETTED ||
               l->action == A_SCRATCH;
    if (!l->timer || (once && l->age > 20 && (ENT_FLAGS(e) & ANIM_DONE)))
        wander((u32)i);
}

/* ---- boxes: the game's question / message box (dialog_open) ------------------------------------- */
#define SCREEN (*(volatile u32 *)ADDR_screen_index)
#define KEYS_DOWN (*(volatile u16 *)(ADDR_input_state + 10))
#define TOP_STATE (*(volatile u32 *)0x027C0070)   /* the top screen's state: 1 = the world, 2 = a box */
#define dialog_arg G(dialog_arg, void (*)(const char *text, int slot))   /* @1 = slot 0, @2 = slot 1 */

static void box_args(const char *a1, const char *a2)
{
    dialog_arg(a1 ? a1 : "", 0);
    dialog_arg(a2 ? a2 : "", 1);
}

/* A question: text, then up to 4 options (string ids); the answer comes in dialog_result. */
static void box_question(int question, const u16 *opts, int n)
{
    u32 scr = SCREEN;
    u16 *text = (u16 *)(ADDR_dialog_text + 10 * scr);
    u8 *flags = (u8 *)(ADDR_dialog_flags + 12 * scr);
    text[0] = (u16)question;
    for (int k = 0; k < 4; k++)
        text[1 + k] = k < n ? opts[k] : 0;
    flags[3] = 1;
    flags[4] = 0;
    *(volatile u32 *)(ADDR_dialog_result + 0x8C * scr) = 0;
    dialog_open();
}

/* Messages wait their turn: one box at a time, only while you walk about. */
#define MAX_MSG 4
static struct { u16 text; char a1[16], a2[16]; } msgs[MAX_MSG];
static u32 n_msgs, msg_open, area_ticks;      /* area_ticks: since the area was entered */

static void copy_name(char *dst, const char *src)
{
    int k = 0;
    while (src && src[k] && k < 15) {
        dst[k] = src[k];
        k++;
    }
    dst[k] = 0;
}

static void say(int t, const char *a1, const char *a2)
{
    int id = text_id(t);
    if (!id || n_msgs >= MAX_MSG)
        return;
    msgs[n_msgs].text = (u16)id;
    copy_name(msgs[n_msgs].a1, a1);
    copy_name(msgs[n_msgs].a2, a2);
    n_msgs++;
}

static int talk_busy(void);

static void msg_tick(u8 *pl)
{
    if (msg_open) {                                /* wait for OK (or B), then give the player back */
        if (!*(volatile u32 *)(ADDR_dialog_result + 0x8C * SCREEN) && ++msg_open < 30 * 120)
            return;
        msg_open = 0;
        if (pl && pl[0x104] != 0x10)
            entity_set_state(pl, 0x10);
        return;
    }
    if (!n_msgs || !pl || pl[0x104] != 0x10 || talk_busy() || area_ticks < 300)
        return;                                    /* (a box opened under the load pop-up never shows) */
    /* The game's plain message box doesn't come up when opened like this, so messages are questions with
       one answer, "OK". */
    u16 ok = (u16)text_id(T_OK);
    box_args(msgs[0].a1, msgs[0].a2);
    box_question(msgs[0].text, &ok, 1);
    for (u32 k = 0; k + 1 < n_msgs; k++)
        msgs[k] = msgs[k + 1];
    n_msgs--;
    msg_open = 1;
    pets_stats.msgs++;
}

/* ---- talking to a pet (or a stray): walk up, press A ---------------------------------------------- */
enum { DO_LEAVE, DO_PET, DO_PLAY, DO_FEED, DO_POCKET, DO_TAKE };
#define STRAY0 100                                 /* talk.who: 0.. = my pets, STRAY0 + k = stray k */
static struct { int stage, who, act; u32 timer; u8 *e; u8 acts[4]; } talk;

static int talk_busy(void)
{
    return talk.stage != 0;
}

static int pockets_take(unsigned object)         /* remove one object from Pockets; 1 if there was one */
{
    u8 *list = (u8 *)ADDR_pockets_list;
    u8 *slots = *(u8 **)(list + 4);
    for (u32 k = 0; k < list[0]; k++) {
        if (*(u16 *)(slots + 6 * k) != object)
            continue;
        for (u32 j = k; j + 1 < list[0]; j++)
            for (u32 b = 0; b < 6; b++)
                slots[6 * j + b] = slots[6 * j + 6 + b];
        list[0]--;
        *(u16 *)(slots + 6 * list[0]) = 0x184;
        return 1;
    }
    return 0;
}

static int pockets_has(unsigned object)
{
    u8 *list = (u8 *)ADDR_pockets_list;
    u8 *slots = *(u8 **)(list + 4);
    for (u32 k = 0; k < list[0]; k++)
        if (*(u16 *)(slots + 6 * k) == object)
            return 1;
    return 0;
}

static u8 bump(u8 v, int d)
{
    int x = v + d;
    return (u8)(x < 0 ? 0 : x > 100 ? 100 : x);
}

/* The player gets his controls back: after the question box he is left in state 0 (the game's own boxes
   set 0x10 again themselves, e.g. the rent sign), where he can't walk, open the menu again, save or quit. */
static void talk_done(u8 *pl)
{
    if (pl && pl[0x104] != 0x10)
        entity_set_state(pl, 0x10);
    talk.stage = 0;
}

#include "strays.inc"

static void talk_open(int who, u8 *e, u8 *pl)
{
    static const u16 mine_opts[] = { 725, 3657, 3632, 3654 };   /* Pet, Play, Feed, Put in Pocket */
    entity_stop(e);
    entity_face(e, entity_dir_to(e, pl));
    entity_face(pl, entity_dir_to(pl, e));
    pets_play(e, A_STAND);
    talk.who = who;
    talk.e = e;
    if (who >= STRAY0) {
        u16 opts[4];
        int n = stray_menu(who - STRAY0, opts, talk.acts);
        box_args(stray_name(who - STRAY0), 0);
        box_question(text_id(strays[who - STRAY0].trust ? T_STRAY_FRIENDLY : T_STRAY_WARY), opts, n);
    } else {
        live[who].mode = M_TALK;
        talk.acts[0] = DO_PET;
        talk.acts[1] = DO_PLAY;
        talk.acts[2] = DO_FEED;
        talk.acts[3] = DO_POCKET;
        box_question(292, mine_opts, 4);           /* "What do you want to do?" */
    }
    talk.stage = 1;
    pets_stats.talks++;
}

static int near_and_facing(u8 *pl, u8 *e)
{
    int dx = ENT_X(e) - ENT_X(pl), dy = ENT_Y(e) - ENT_Y(pl);
    return dx * dx + dy * dy <= 56 * 56 && entity_faces(pl, e);
}

static void talk_tick(void)
{
    u8 *pl = player_entity();
    if (talk.stage == 0) {
        if (!pl || !(KEYS_DOWN & 1) || n_msgs || msg_open)
            return;
        pets_stats.a_presses++;
        pets_stats.a_state = pl[0x104];
        if (n_mine && alive(0)) {
            pets_stats.a_dx = (u32)(ENT_X(live[0].e) - ENT_X(pl));
            pets_stats.a_dy = (u32)(ENT_Y(live[0].e) - ENT_Y(pl));
            pets_stats.a_faces = (u32)entity_faces(pl, live[0].e);
        }
        if (pl[0x104] != 0x10)
            return;
        for (u32 i = 0; i < n_mine; i++)
            if (alive(i) && live[i].mode != M_TALK && near_and_facing(pl, live[i].e)) {
                talk_open((int)i, live[i].e, pl);
                return;
            }
        for (int k = 0; k < 2; k++)                /* strays: close by is enough (they sit at your feet) */
            if (stray_here(k) && (near_and_facing(pl, stray_live[k].e) || dist2(pl, stray_live[k].e) < 40 * 40)) {
                talk_open(STRAY0 + k, stray_live[k].e, pl);
                return;
            }
        return;
    }
    int stray = talk.who >= STRAY0 ? talk.who - STRAY0 : -1;
    u8 *e = talk.e;
    if (!pl || (stray < 0 ? (talk.who >= (int)n_mine || !alive((u32)talk.who) || live[talk.who].e != e)
                          : !stray_here(stray))) {
        talk_done(pl);
        return;
    }
    mypet_t *m = stray < 0 ? &mine[talk.who] : 0;
    if (talk.stage == 1) {                          /* waiting for the question box */
        u32 r = *(volatile u32 *)(ADDR_dialog_result + 0x8C * SCREEN);
        if (!r)
            return;
        talk.act = (r >= 1 && r <= 4) ? talk.acts[r - 1] : DO_LEAVE;
        talk.timer = 0;
        pets_stats.last_pick = (u32)talk.act;
        talk.stage = 3;                             /* first it comes up to you (not to be pocketed) */
        if (talk.act == DO_PET || talk.act == DO_PLAY || talk.act == DO_FEED)
            pets_play(e, A_WALK);
        else
            talk.timer = 90;
    }
    if (talk.stage == 3) {                          /* coming up to you */
        int dx = ENT_X(pl) - ENT_X(e), dy = ENT_Y(pl) - ENT_Y(e);
        if (dx * dx + dy * dy > 20 * 20 && ++talk.timer < 90) {
            entity_face(e, entity_dir_to(e, pl));
            entity_go(e);
            return;
        }
        entity_stop(e);
        entity_face(e, entity_dir_to(e, pl));
        entity_face(pl, entity_dir_to(pl, e));
        talk.stage = 2;
        talk.timer = 0;
        switch (talk.act) {
        case DO_PET:
            entity_set_state(pl, 0);
            entity_anim(pl, 0x4E);                  /* the game's petting (Splicer pets) */
            pets_play(e, A_PETTED);
            break;
        case DO_PLAY:
            pets_play(e, A_PLAY);
            break;
        case DO_FEED:
            if (stray >= 0) {
                if (!stray_feed(stray)) {
                    talk_done(pl);
                    stray_resume(stray);
                    return;
                }
                pets_play(e, A_EAT);
            } else if (pockets_take(TREATS)) {
                pets_play(e, A_EAT);
                m->hunger = bump(m->hunger, 45);
                m->happy = bump(m->happy, 5);
            } else {
                play_sound(3);                      /* refused: no treats */
                pets_play(e, A_SAD);
                talk.timer = 120;
            }
            break;
        case DO_POCKET:
            if (list_add(*(void **)(ADDR_game_state + 0x154), m->object, 0, 0) == 1) {
                play_sound(0x13E);                  /* the Chicken's pick-up sound */
                ENT_FLAGS(e) |= 2;                  /* the world loop frees entities marked 2 */
                forget((u32)talk.who);
                pets_count.picked++;
            } else
                play_sound(3);                      /* Pockets full */
            talk_done(pl);
            return;
        case DO_TAKE:
            stray_take(stray);
            talk_done(pl);
            return;
        default:                                    /* cancelled / Leave */
            if (stray >= 0)
                stray_resume(stray);
            else
                wander((u32)talk.who);
            talk_done(pl);
            return;
        }
        return;
    }
    if (talk.stage != 2)
        return;
    /* stage 2: the action plays out */
    talk.timer++;
    if (talk.act == DO_PET) {
        if (talk.timer == 20)
            entity_anim(pl, 0x4F);
        if (talk.timer % 15 == 0)
            motive_effect((s32 *)ADDR_player_motives, 0x1A, 1);   /* what petting does for you (row 26) */
        if (talk.timer == 95)
            entity_anim(pl, 0x50);
        if (talk.timer < 115)
            return;
        if (m)
            m->happy = bump(m->happy, 20);
    } else if (talk.act == DO_PLAY) {
        if (talk.timer < 120)
            return;
        m->happy = bump(m->happy, 30);
        m->hunger = bump(m->hunger, -8);
    } else if (talk.timer < 120) {
        return;
    }
    pets_stats.actions_done++;
    if (stray >= 0)
        stray_after(stray);
    else
        act((u32)talk.who, A_SIT, 300);            /* it stays by you a little while (10 s) */
    talk_done(pl);
}

/* ---- the game's hooks and the mod events ---------------------------------------------------------- */
#define obj_removed_orig GAME_FN(ADDR_pet_object_removed, void (*)(u8 *obj))

/* Class +0x14 of every pet object: what the Chicken's does, with the pet's kind. */
void pets_removed(u8 *obj)
{
    u32 n;
    const pet_t *p = pet_list(&n);
    u8 *e = *(u8 **)(obj + 0x24);
    for (u32 i = 0; i < n; i++) {
        if (p[i].object != *(u16 *)(obj + 8))
            continue;
        if (*(u32 *)(e + 0xC) & 2)
            return;
        u8 *c = spawn_critter(p[i].kind, e[0x12], obj[0x4A], (s16)(*(s32 *)(e + 0x18) >> 16),
                              (s16)(*(s32 *)(e + 0x1C) >> 16));
        pets_keep(p[i].object, (u8)p[i].kind, c);
        pets_count.spawned++;
        entity_set_state(e, 1);
        return;
    }
    obj_removed_orig(obj);
}

/* critter_pickup (state 0x12, action 0x0E) after the Chicken case: r0 = kind, r5 = 0 (result), r6 = critter. */
__attribute__((naked)) void pets_pick_stub(void)
{
    __asm__ volatile(
        "cmp r0, #5\n"
        "ldreq pc, =0x0202A2E0\n"          /* the Nutria: the game's own code */
        "bl pets_object_of\n"
        "cmp r0, #0\n"
        "ldreq pc, =0x0202A2FC\n"          /* not a pet: nothing to give back */
        "mov r1, r0\n"
        "ldr r0, =0x02141274\n"            /* pockets_ptr */
        "ldr r0, [r0]\n"
        "mov r2, #0\n"
        "mov r3, #0\n"
        "ldr ip, =0x0203D0CC\n"            /* list_add */
        "blx ip\n"
        "mov r5, r0\n"
        "cmp r0, #1\n"
        "moveq r0, r6\n"                   /* r6 = the critter */
        "bleq pets_forget\n"
        "ldr r0, =pets_count\n"
        "ldr r1, [r0, #8]\n"
        "add r1, r1, #1\n"
        "str r1, [r0, #8]\n"
        "ldr pc, =0x0202A2FC\n"            /* "cmp r5, #1": in Pockets -> the critter goes */
        ".ltorg\n");
}

/* critter_behaviour switches to the walk animation (slot 1) when a critter starts moving and back to
   stand (slot 0) when it stops, but only for kind 1 (the Chicken); the pick-up handler only takes kinds 1-2.
   Pets count as kind 1 for these tests. */
unsigned pets_anim_kind(unsigned kind)
{
    return kind == 1 || pets_object_of(kind) ? 1 : kind;
}

__attribute__((naked)) void pets_walk_stub(void)
{
    __asm__ volatile(
        "ldrh r0, [r4, #0xA]\n"
        "bl pets_anim_kind\n"
        "cmp r0, #1\n"
        "ldr pc, =0x0202A744\n"
        ".ltorg\n");
}

__attribute__((naked)) void pets_stop_stub(void)
{
    __asm__ volatile(
        "ldrh r0, [r4, #0xA]\n"
        "bl pets_anim_kind\n"
        "cmp r0, #1\n"
        "ldr pc, =0x0202A768\n"
        ".ltorg\n");
}

/* The game's own pick-up (walking into a critter): pets count as the Chicken, but not the strays (they are
   taken home through the quest). */
unsigned pets_tap_kind(u8 *e)
{
    if (stray_live[0].e == e || stray_live[1].e == e)
        return 0xFF;
    return pets_anim_kind(ENT_KIND(e));
}

__attribute__((naked)) void pets_tap_stub(void)
{
    __asm__ volatile(
        "push {r0, r3, ip, lr}\n"
        "mov r0, r5\n"
        "bl pets_tap_kind\n"
        "mov r2, r0\n"
        "pop {r0, r3, ip, lr}\n"
        "ldr r1, =0xFFFF\n"
        "ldr pc, =0x0202A578\n"
        ".ltorg\n");
}

static void spawn_mine(int area)
{
    u8 *pl = player_entity();
    for (u32 i = 0; i < n_mine; i++) {
        mypet_t *m = &mine[i];
        if (alive(i))
            continue;
        if (m->area != (u8)area) {
            if (is_home_area((const void *)ADDR_home_lot, m->area))
                continue;                          /* in another room of this home */
            /* you moved house (move_home): it comes along, and appears next to you */
            pets_stats.moved++;
            m->x = pl ? ENT_X(pl) + 16 * (int)(i % 3) - 16 : 128;
            m->y = pl ? ENT_Y(pl) + 12 + 8 * (int)(i / 3) : 128;
            m->area = (u8)area;
        }
        take_over(i, spawn_critter(m->kind, m->facing, 0, m->x, m->y));
        if (greet && live[i].e && !night()) {     /* coming home: they come to say hello */
            live[i].mode = M_GO;
            live[i].timer = 240;
            pets_play(live[i].e, A_WALK);
        }
        pets_stats.respawned++;
    }
    greet = 0;
}

void mod_on_tick(void)
{
    static u32 t;
    if (need_spawn) {
        need_spawn = 0;
        if (n_mine && is_home_area((const void *)ADDR_home_lot, current_area))
            spawn_mine((int)current_area);
        need_strays |= current_area == URBANIA_PARK;
    }
    u8 *pl = player_entity();
    area_ticks++;
    strays_tick(pl);
    talk_tick();
    msg_tick(pl);
    if (++t % 30)
        return;
    pets_stats.n = n_mine;
    {
        u8 *pl = player_entity();                  /* where you are (tests walk you to places) */
        pets_stats.px = pl ? (u32)ENT_X(pl) : 0;
        pets_stats.py = pl ? (u32)ENT_Y(pl) : 0;
    }
    if (n_mine && alive(0)) {
        u8 *b = live[0].bed, *e0 = live[0].e;
        pets_stats.bed0 = b ? (u32)(u16)ENT_X(b) | (u32)(u16)ENT_Y(b) << 16 : 0;
        pets_stats.pet0 = (u32)(u16)ENT_X(e0) | (u32)(u16)ENT_Y(e0) << 16;
    }
    pets_stats.mood0 = n_mine ? mine[0].hunger | mine[0].happy << 8 | (u32)live[0].mode << 16 |
                                (u32)live[0].action << 24 : 0;
    for (u32 i = 0; i < n_mine; i++) {
        if (!alive(i)) {
            live[i].e = 0;
            continue;
        }
        mine[i].x = ENT_X(live[i].e);
        mine[i].y = ENT_Y(live[i].e);
        mine[i].facing = live[i].e[0x12];
    }
}

/* Needs drift with the game clock: hungry after about 8 hours, bored after about 12. */
void mod_on_minute(int minutes)
{
    static int mh, mf;
    mh += minutes;
    mf += minutes;
    int dh = mh / 5, df = mf / 7;
    mh %= 5;
    mf %= 7;
    for (u32 i = 0; i < n_mine; i++) {
        mine[i].hunger = bump(mine[i].hunger, -dh);
        mine[i].happy = bump(mine[i].happy, -df);
    }
}

void mod_on_area_enter(int area)
{
    for (u32 i = 0; i < n_mine; i++)
        live[i].e = 0;                            /* leaving an area frees its critters */
    talk.stage = 0;
    greet = n_mine && is_home_area((const void *)ADDR_home_lot, area);
    need_spawn = 1;
    strays_area_enter(area);
    n_msgs = msg_open = area_ticks = 0;
}

/* The core hands us unaligned buffers (6-byte block headers): bytes only. */
static void put_bytes(u8 *dst, const void *src, u32 n)
{
    const u8 *s = src;
    while (n--)
        *dst++ = *s++;
}

/* Save: 'PET2', n, my pets, then the strays quest {u8 intro, 3 x 0, stray_t x 2}. */
int mod_on_save(u8 *buf, int max)
{
    int len = 8 + (int)n_mine * (int)sizeof(mypet_t);
    if (len + 4 + (int)sizeof(strays) > max)
        return -1;
    u32 head[2] = { SAVE_MAGIC, n_mine };
    put_bytes(buf, head, 8);
    put_bytes(buf + 8, mine, (u32)len - 8);
    u8 q[4] = { strays_intro, 0, 0, 0 };
    put_bytes(buf + len, q, 4);
    put_bytes(buf + len + 4, strays, sizeof(strays));
    return len + 4 + (int)sizeof(strays);
}

void mod_on_load(const u8 *buf, int len)
{
    pets_stats.loads++;
    n_mine = 0;
    talk.stage = 0;
    for (u32 i = 0; i < MAX_MINE; i++)
        live[i].e = 0;
    strays_intro = 0;
    memset(strays, 0, sizeof(strays));
    for (int k = 0; k < 2; k++)
        stray_live[k].e = 0;
    u32 head[2];
    if (!buf || len < 8)
        return;
    put_bytes((u8 *)head, buf, 8);
    if ((head[0] != SAVE_MAGIC && head[0] != SAVE_MAGIC_1) || head[1] > MAX_MINE ||
        8 + head[1] * sizeof(mypet_t) > (u32)len)
        return;
    put_bytes((u8 *)mine, buf + 8, head[1] * sizeof(mypet_t));
    n_mine = head[1];
    u32 at = 8 + head[1] * sizeof(mypet_t);
    if (head[0] == SAVE_MAGIC && at + 4 + sizeof(strays) <= (u32)len) {
        strays_intro = buf[at];
        put_bytes((u8 *)strays, buf + at + 4, sizeof(strays));
    }
    need_strays = 1;
    pets_stats.loaded = n_mine;
    need_spawn = 1;
}

/* ---- the Pets page (Options > Mods > Pets) --------------------------------------------------------- */
static const char *doing(u32 i)
{
    static const char *const names[N_ACTIONS] = { "about", "walking", "sitting", "lying down", "asleep",
        "sniffing", "playing", "eating", "happy", "sulking", "petted", "scratching", "in bed", "in bed" };
    if (!alive(i))
        return mine[i].area == (u8)current_area ? "about" : "at home";
    if (live[i].mode == M_GO)
        return "coming";
    if (live[i].mode == M_BED)
        return "off to bed";
    if (live[i].mode == M_ACT && live[i].action < N_ACTIONS)
        return names[live[i].action];
    return "about";
}

static void (*page_print)(mod_page_t *, const char *);

static void count_print(mod_page_t *pg, const char *text)
{
    pets_stats.page_lines++;
    page_print(pg, text);
}

void mod_on_page(mod_page_t *pg)
{
    char line[48], *q;
    if (pg->print != count_print) {                /* count the lines (tests) */
        page_print = pg->print;
        pg->print = count_print;
    }
    if (!n_mine && !strays_intro)
        pg->print(pg, "No pets at home yet.");
    if (n_mine)
        pg->print(pg, "Pet: doing, food/fun");
    for (u32 i = 0; i < n_mine; i++) {             /* "Puppy: in bed, 72/80" (lines show ~28 letters) */
        const pet_t *p = pet_of_kind(mine[i].kind);
        q = str_cat(line, p ? p->name : "Pet");
        q = str_cat(q, ": ");
        q = str_cat(q, doing(i));
        q = str_cat(q, ", ");
        q = str_int(q, mine[i].hunger);
        q = str_cat(q, "/");
        q = str_int(q, mine[i].happy);
        pg->print(pg, line);
    }
    strays_page(pg);
}

void mod_on_boot(void)
{
    u32 n;
    const pet_t *p = pet_list(&n);
    u8 *cls = *(u8 **)ADDR_obj_class_lit;               /* the (moved) object class table */
    for (u32 i = 0; i < n; i++)
        *(void (**)(u8 *))(cls + p[i].object * 0x24 + 0x14) = pets_removed;
    pets_count.pets = n;
}
