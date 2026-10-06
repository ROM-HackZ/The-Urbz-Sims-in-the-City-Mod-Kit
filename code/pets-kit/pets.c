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

   The builder writes before the (moved) critter behaviour table: 'PETA', {u16 object, u16 kind, u32 actions}
   x n, u32 n; actions -> N_ACTIONS x {records (5 facings x 16 bytes), frame script} or 0. */
#include "game.h"
#include "mod.h"

#define PETA 0x41544550                          /* 'PETA' */
#define TREATS 396                               /* "Pet Treats" (mods/pets objects.json) */
enum { A_STAND, A_WALK, A_SIT, A_LIE, A_SLEEP, A_SNIFF, A_PLAY, A_EAT, A_HAPPY, A_SAD, A_PETTED, A_SCRATCH,
       N_ACTIONS };

typedef struct { u16 object, kind; const u32 *actions; } pet_t;

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
    const pet_t *p = (const pet_t *)(table - 4 - 8 * *n);
    if (*n > 64 || *((const u32 *)p - 1) != PETA)
        *n = 0;
    return p;
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
#define SAVE_MAGIC 0x31544550                    /* 'PET1' */
typedef struct {
    u16 object;                                  /* the pet's object number (what goes back to Pockets) */
    u8 kind, facing;
    s16 x, y;                                    /* where it was last seen, in its home area */
    u8 area, hunger, happy, flags;               /* hunger / happy: 100 = full / very happy */
} mypet_t;

enum { M_WANDER, M_ACT, M_GO, M_TALK };          /* what a pet is doing (not saved) */
typedef struct { u8 *e; u8 mode, action; u16 timer, age; } live_t;

static mypet_t mine[MAX_MINE];
static live_t live[MAX_MINE];
static u32 n_mine, need_spawn, greet;
struct { u32 magic, kept, respawned, forgot, loads, loaded, acts, talks, last_pick, actions_done, a_presses, a_state, a_dx, a_dy, a_faces, mood0, n, act_mask, greets, px, py; }
    pets_stats = { 0x53544550, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 };   /* 'PETS' (tests) */

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
    live[i].timer = 120 + rnd(240);
    pets_play(live[i].e, A_STAND);
}

/* What to do next, from the time of day and how it feels. */
static void choose(u32 i)
{
    mypet_t *m = &mine[i];
    if (night()) {
        act(i, rnd(4) ? A_SLEEP : A_LIE, 600 + rnd(900));
        return;
    }
    if (m->hunger < 25 || m->happy < 25) {          /* moping: sad, sits or lies about */
        static const u8 mope[] = { A_SAD, A_SAD, A_SIT, A_LIE };
        act(i, mope[rnd(4)], 200 + rnd(200));
        return;
    }
    static const u8 idle[] = { A_SNIFF, A_SNIFF, A_SIT, A_SCRATCH, A_LIE, A_PLAY, A_HAPPY, A_SIT };
    int a = idle[rnd(8)];
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
    l->age++;
    int once = l->action == A_PLAY || l->action == A_EAT || l->action == A_HAPPY || l->action == A_PETTED ||
               l->action == A_SCRATCH;
    if (!l->timer || (once && l->age > 20 && (ENT_FLAGS(e) & ANIM_DONE)))
        wander((u32)i);
}

/* ---- talking to a pet: walk up, press A --------------------------------------------------------- */
enum { OPT_PET = 1, OPT_PLAY, OPT_FEED, OPT_POCKET };
static struct { int stage; u32 pet; u32 timer; int choice; } talk;

#define SCREEN (*(volatile u32 *)ADDR_screen_index)
#define KEYS_DOWN (*(volatile u16 *)(ADDR_input_state + 10))

static void open_menu(u32 i, u8 *pl)
{
    u8 *e = live[i].e;
    u32 scr = SCREEN;
    u16 *text = (u16 *)(ADDR_dialog_text + 10 * scr);
    u8 *flags = (u8 *)(ADDR_dialog_flags + 12 * scr);
    text[0] = 292;                                 /* "What do you want to do?" */
    text[1] = 725;                                 /* "Pet" */
    text[2] = 3657;                                /* "Play" */
    text[3] = 3632;                                /* "Feed" */
    text[4] = 3654;                                /* "Put in Pocket" */
    flags[3] = 1;
    flags[4] = 0;
    *(volatile u32 *)(ADDR_dialog_result + 0x8C * scr) = 0;
    entity_stop(e);
    entity_face(e, entity_dir_to(e, pl));
    entity_face(pl, entity_dir_to(pl, e));
    live[i].mode = M_TALK;
    pets_play(e, A_STAND);
    dialog_open();
    talk.stage = 1;
    talk.pet = i;
    pets_stats.talks++;
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

static u8 bump(u8 v, int d)
{
    int x = v + d;
    return (u8)(x < 0 ? 0 : x > 100 ? 100 : x);
}

static void talk_tick(void)
{
    u8 *pl = player_entity();
    if (talk.stage == 0) {
        if (!pl || !(KEYS_DOWN & 1))
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
        for (u32 i = 0; i < n_mine; i++) {
            if (!alive(i) || live[i].mode == M_TALK)
                continue;
            u8 *e = live[i].e;
            int dx = ENT_X(e) - ENT_X(pl), dy = ENT_Y(e) - ENT_Y(pl);
            if (dx * dx + dy * dy <= 56 * 56 && entity_faces(pl, e)) {
                open_menu(i, pl);
                return;
            }
        }
        return;
    }
    u32 i = talk.pet;
    if (i >= n_mine || !alive(i) || !pl) {
        talk.stage = 0;
        return;
    }
    u8 *e = live[i].e;
    mypet_t *m = &mine[i];
    if (talk.stage == 1) {                          /* waiting for the question box */
        u32 r = *(volatile u32 *)(ADDR_dialog_result + 0x8C * SCREEN);
        if (!r)
            return;
        talk.choice = (r >= 1 && r <= 4) ? (int)r : 0;
        talk.timer = 0;
        pets_stats.last_pick = (u32)talk.choice;
        talk.stage = 3;                             /* first it comes up to you (not to be pocketed) */
        if (talk.choice >= OPT_PET && talk.choice <= OPT_FEED)
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
        switch (talk.choice) {
        case OPT_PET:
            entity_set_state(pl, 0);
            entity_anim(pl, 0x4E);                  /* the game's petting (Splicer pets) */
            pets_play(e, A_PETTED);
            break;
        case OPT_PLAY:
            pets_play(e, A_PLAY);
            break;
        case OPT_FEED:
            if (pockets_take(TREATS)) {
                pets_play(e, A_EAT);
                m->hunger = bump(m->hunger, 45);
                m->happy = bump(m->happy, 5);
            } else {
                play_sound(3);                      /* refused: no treats */
                pets_play(e, A_SAD);
                talk.timer = 200;
            }
            break;
        case OPT_POCKET:
            if (list_add(*(void **)(ADDR_game_state + 0x154), m->object, 0, 0) == 1) {
                play_sound(0x13E);                  /* the Chicken's pick-up sound */
                ENT_FLAGS(e) |= 2;                  /* the world loop frees entities marked 2 */
                forget(i);
                pets_count.picked++;
            } else
                play_sound(3);                      /* Pockets full */
            talk.stage = 0;
            return;
        default:                                    /* cancelled */
            wander(i);
            talk.stage = 0;
            return;
        }
        return;
    }
    if (talk.stage != 2)
        return;
    /* stage 2: the action plays out */
    talk.timer++;
    if (talk.choice == OPT_PET) {
        if (talk.timer == 30)
            entity_anim(pl, 0x4F);
        if (talk.timer % 30 == 0)
            motive_effect((s32 *)ADDR_player_motives, 0x1A, 1);   /* what petting does for you (row 26) */
        if (talk.timer == 150)
            entity_anim(pl, 0x50);
        if (talk.timer < 180)
            return;
        entity_set_state(pl, pl[0x10A]);
        m->happy = bump(m->happy, 20);
    } else if (talk.choice == OPT_PLAY) {
        if (talk.timer < 180)
            return;
        m->happy = bump(m->happy, 30);
        m->hunger = bump(m->hunger, -8);
    } else if (talk.timer < 200) {
        return;
    }
    pets_stats.actions_done++;
    wander(i);
    talk.stage = 0;
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

__attribute__((naked)) void pets_tap_stub(void)
{
    __asm__ volatile(
        "push {r0, r3, ip, lr}\n"
        "ldrh r0, [r5, #0xA]\n"
        "bl pets_anim_kind\n"
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
        if (m->area != (u8)area) {                /* a new home: next to the player */
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
    }
    talk_tick();
    if (++t % 30)
        return;
    pets_stats.n = n_mine;
    {
        u8 *pl = player_entity();                  /* where you are (tests walk you to places) */
        pets_stats.px = pl ? (u32)ENT_X(pl) : 0;
        pets_stats.py = pl ? (u32)ENT_Y(pl) : 0;
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
}

/* The core hands us unaligned buffers (6-byte block headers): bytes only. */
static void put_bytes(u8 *dst, const void *src, u32 n)
{
    const u8 *s = src;
    while (n--)
        *dst++ = *s++;
}

int mod_on_save(u8 *buf, int max)
{
    int len = 8 + (int)n_mine * (int)sizeof(mypet_t);
    if (len > max)
        return -1;
    u32 head[2] = { SAVE_MAGIC, n_mine };
    put_bytes(buf, head, 8);
    put_bytes(buf + 8, mine, (u32)len - 8);
    return len;
}

void mod_on_load(const u8 *buf, int len)
{
    pets_stats.loads++;
    n_mine = 0;
    talk.stage = 0;
    for (u32 i = 0; i < MAX_MINE; i++)
        live[i].e = 0;
    u32 head[2];
    if (!buf || len < 8)
        return;
    put_bytes((u8 *)head, buf, 8);
    if (head[0] != SAVE_MAGIC || head[1] > MAX_MINE || 8 + head[1] * sizeof(mypet_t) > (u32)len)
        return;
    put_bytes((u8 *)mine, buf + 8, head[1] * sizeof(mypet_t));
    n_mine = head[1];
    pets_stats.loaded = n_mine;
    need_spawn = 1;
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
