/* NPC Life simulation (see npc_sim.h). Portable C: no game addresses, no C library. */
#include "npc_sim.h"
#include "sim_data.h"

#define NONE 0xFF

/* Needs drop this much per game hour while awake (x the person's decay %, from npcs.json). */
static const uint8_t base_decay[N_NEEDS] = { 6, 4, 5, 5, 2, 9, 5, 0 };

/* What an hour of each activity gives back, per need (added after the hourly drop). */
static const int8_t gains[N_ACTS][N_NEEDS] = {
    /*            hung hyg  ener soc  comf blad fun  room */
    [A_HOME]   = { 0,  35,  2,   4,   8,  45,  18,   0 },
    [A_SLEEP]  = { 3,   7, 16,   5,   6,   5,   5,   0 },
    [A_WORK]   = { 0,   0, -1,   7,   0,  25,   2,   0 },
    [A_EAT]    = { 45,  0,  0,   4,   2,  12,   3,   0 },
    [A_FUN]    = { 0,   0,  0,   6,   0,  12,  30,   0 },
    [A_SOCIAL] = { 0,   0,  0,  30,   0,  12,  10,   0 },
    [A_PARK]   = { 0,   0,  1,   8,  10,   6,  15,   0 },
    [A_USUAL]  = { 0,   0,  0,   6,   0,  15,   6,   0 },
    [A_AWAY]   = { 4,   2,  0,   6,   0,   9,   6,   0 },
};

static const char *const act_names[N_ACTS] = {
    "at home", "asleep", "at work", "eating", "having fun", "socialising", "in the park",
    "out and about", "out of town"
};

const char *sim_act_name(int act)
{
    return act >= 0 && act < N_ACTS ? act_names[act] : "?";
}

static uint32_t rnd(sim_t *sim)
{
    uint32_t x = sim->s.seed ? sim->s.seed : 0x9E3779B9u;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    sim->s.seed = x;
    return x;
}

static const sim_place_t *place_of(unsigned area)
{
    for (int i = 0; i < SIM_N_PLACES; i++)
        if (sim_places[i].area == area)
            return &sim_places[i];
    return 0;
}

static unsigned slot(unsigned hour, unsigned wd) { return hour * 7 + wd; }

/* ---- setup --------------------------------------------------------------- */

static uint8_t most_common(const uint8_t *t, int h0, int h1, int wd1, int not)
{
    uint8_t best = NONE;
    int best_n = 0;
    for (int h = h0; h < h1; h++)
        for (int w = 0; w < wd1; w++) {
            uint8_t a = t[slot(h, w)];
            if (a == not)
                continue;
            int n = 0;
            for (int h2 = h0; h2 < h1; h2++)
                for (int w2 = 0; w2 < wd1; w2++)
                    n += t[slot(h2, w2)] == a;
            if (n > best_n) {
                best_n = n;
                best = a;
            }
        }
    return best_n >= 10 ? best : NONE;
}

static void derive(sim_t *sim, int i)
{
    const uint8_t *t = sim->orig[i];
    sim_person_t *p = &sim->s.p[i];
    sim->n_allowed[i] = 0;
    if (!t) {
        p->home = p->work = NONE;
        return;
    }
    for (int k = 0; k < 24 * 7; k++) {
        int seen = 0;
        for (int j = 0; j < sim->n_allowed[i]; j++)
            seen |= sim->allowed[i][j] == t[k];
        if (!seen && sim->n_allowed[i] < 24)
            sim->allowed[i][sim->n_allowed[i]++] = t[k];
    }
    p->home = most_common(t, 0, 6, 7, NONE);
    if (p->home == NONE)
        p->home = t[slot(2, 0)];
    p->work = most_common(t, 9, 17, 5, p->home);
    if (p->work == SIM_AWAY)
        p->work = NONE;
}

void sim_setup(sim_t *sim, const uint8_t *const orig[SIM_PEOPLE])
{
    for (int i = 0; i < SIM_PEOPLE; i++) {
        sim->orig[i] = orig[i];
        for (int k = 0; k < 24 * 7; k++)
            sim->plan[i][k] = orig[i] ? orig[i][k] : SIM_AWAY;
        derive(sim, i);
    }
    sim->hours = 0;
}

/* ---- deciding ------------------------------------------------------------- */

static int allowed(const sim_t *sim, int i, unsigned area)
{
    for (int j = 0; j < sim->n_allowed[i]; j++)
        if (sim->allowed[i][j] == area)
            return 1;
    return 0;
}

static int value(const sim_person_t *p, int act, const sim_tweak_t *tw)
{
    int v = 0;
    for (int n = 0; n < N_NEEDS; n++) {
        int g = gains[act][n] + base_decay[n] * tw->decay[n] / 100;   /* net effect vs. idle */
        if (gains[act][n] > 0 && g > 0) {
            int u = 100 - p->need[n];
            v += u * u / 100 * g;
        }
    }
    return v / 50;
}

typedef struct { uint8_t act, area, cost; int score; } choice_t;

static void consider(choice_t *best, int act, unsigned area, int cost, int score)
{
    if (score > best->score) {
        best->act = act;
        best->area = area;
        best->cost = cost;
        best->score = score;
    }
}

/* Pick what a person does this hour.
   Where: always the area of their original timetable (nobody goes missing from where the game puts them).
   Only in hours the original game has them out of town (82) are they free to visit places they know
   (cafés, clubs, parks, home). What: the activity that area supports and their needs call for. */
static void decide(sim_t *sim, int i, unsigned hour, unsigned wd)
{
    sim_person_t *p = &sim->s.p[i];
    const sim_tweak_t *tw = &sim_tweaks[i];
    const uint8_t *t = sim->orig[i];
    unsigned usual = t[slot(hour, wd)];
    int free = usual == SIM_AWAY;                      /* out of town in the original game: free time */
    int night = hour >= 22 || hour < 6;
    int broke = p->money < 40;
    choice_t best = { free ? A_AWAY : A_USUAL, (uint8_t)usual, 0, -1000 };
    int hungry = p->need[N_HUNGER] < 30 ? 20 : 0;     /* a proper meal comes first */
    p->flags &= ~1;

    /* keep sleeping through the night while tired (if they may stay where they are) */
    if (p->act == A_SLEEP && (night || hour < 8) && p->need[N_ENERGY] < 90 &&
        p->need[N_HUNGER] > 10 && p->need[N_BLADDER] > 10 && (free || p->place == usual)) {
        sim->plan[i][slot(hour, wd)] = p->place;
        return;
    }
#define J (int)(rnd(sim) % 7)
#define MOVE(a) ((a) == p->place ? 6 : -4)
#define HERE(a) (free || (a) == usual)
    /* their usual place this hour (the game's own timetable) */
    if (free)
        consider(&best, A_AWAY, usual, 0, value(p, A_AWAY, tw) + 30 + J);
    else
        consider(&best, A_USUAL, usual, 0, value(p, A_USUAL, tw) + 18 + J);
    /* home */
    if (p->home != NONE && HERE(p->home)) {
        consider(&best, A_HOME, p->home, 0, value(p, A_HOME, tw) + MOVE(p->home) + J);
        consider(&best, A_SLEEP, p->home, 0, value(p, A_SLEEP, tw) + (night ? 25 : -20) +
                 (p->need[N_ENERGY] < 25 ? 40 : 0) + MOVE(p->home) + J);
        consider(&best, A_EAT, p->home, 3, value(p, A_EAT, tw) - 8 + hungry + MOVE(p->home) + J);  /* groceries */
    }
    /* sleep is invisible: at night they rest wherever the game has them */
    if (!free && usual != p->home && (night || p->need[N_ENERGY] < 20))
        consider(&best, A_SLEEP, usual, 0, value(p, A_SLEEP, tw) + (night ? 25 : 0) +
                 (p->need[N_ENERGY] < 25 ? 40 : 0) + J);
    /* their job, during their usual hours there */
    if (p->work != NONE && usual == p->work)
        consider(&best, A_WORK, p->work, 0, value(p, A_WORK, tw) + 60 + (broke ? 30 : 0) + J);
    /* a quick bite where they are (a break at work, a snack while out) */
    if (!free && p->need[N_HUNGER] < 25)
        consider(&best, A_EAT, usual, p->money >= 4 ? 4 : 0, value(p, A_EAT, tw) - 12 + hungry +
                 (p->need[N_HUNGER] < 15 ? 40 : 0) + J);           /* starving beats everything */
    /* places they go to that offer something */
    for (int j = 0; j < sim->n_allowed[i]; j++) {
        unsigned a = sim->allowed[i][j];
        const sim_place_t *pl = place_of(a);
        if (!pl || a == SIM_AWAY || !HERE(a))
            continue;
        int bonus = MOVE(a) + (a == usual ? 10 : 0) + J;
        if (pl->cost > p->money) {
            if (pl->kinds & K_FOOD && p->need[N_HUNGER] < 40)
                p->flags |= 1;                       /* hungry and can't afford to eat out */
            continue;
        }
        if (pl->kinds & K_FOOD)
            consider(&best, A_EAT, a, pl->cost, value(p, A_EAT, tw) + bonus + hungry - (p->money < 60 ? 15 : 0));
        if (pl->kinds & (K_FUN | K_GYM))
            consider(&best, A_FUN, a, pl->cost, value(p, A_FUN, tw) + bonus - (broke ? 15 : 0));
        if (pl->kinds & K_SOCIAL)
            consider(&best, A_SOCIAL, a, 0, value(p, A_SOCIAL, tw) + bonus);
        if (pl->kinds & K_PARK)
            consider(&best, A_PARK, a, 0, value(p, A_PARK, tw) + bonus);
    }
#undef J
#undef MOVE
#undef HERE
    p->act = best.act;
    p->place = best.area;
    p->money -= best.cost;
    sim->plan[i][slot(hour, wd)] = best.area;
    unsigned nh = (hour + 1) % 24, nw = nh ? wd : (wd + 1) % 7;
    sim->plan[i][slot(nh, nw)] = t[slot(nh, nw)];      /* the next hour: their usual (phone lines) */
}

/* ---- the hour ------------------------------------------------------------- */

static void live_hour(sim_t *sim, int i)
{
    sim_person_t *p = &sim->s.p[i];
    const sim_tweak_t *tw = &sim_tweaks[i];
    for (int n = 0; n < N_NEEDS; n++) {
        int v = p->need[n] - base_decay[n] * tw->decay[n] / 100 + gains[p->act][n];
        if (p->act == A_FUN && n == N_ENERGY) {
            const sim_place_t *pl = place_of(p->place);
            if (pl && pl->kinds & K_GYM)
                v -= 4;                              /* a workout is tiring */
        }
        if (n == N_ROOM)
            v += (70 - v) / 4;                       /* their surroundings: fairly constant */
        p->need[n] = v < 0 ? 0 : v > 100 ? 100 : v;
    }
    if (p->act == A_WORK && p->money < 30000)
        p->money += tw->pay;
}

static void hour_tick(sim_t *sim)
{
    unsigned clock = sim->s.clock, wd = clock / 1440, hour = clock / 60 % 24;
    sim->hours++;
    for (int i = 0; i < SIM_PEOPLE; i++) {
        if (!sim->orig[i])
            continue;
        live_hour(sim, i);
        sim_person_t *p = &sim->s.p[i];
        if (clock == 0) {                            /* Monday 00:00: rent */
            int shift = 0;
            for (int k = 0; k < 24 * 7; k++)
                shift += p->work != NONE && sim->orig[i][k] == p->work;
            int rent = sim_tweaks[i].rent_div5 * 5, afford = shift * sim_tweaks[i].pay / 3;
            if (p->work != NONE)
                p->money -= rent < afford ? rent : afford;   /* rent fits what the job pays */
            else
                p->money += 60;                      /* no job: family helps out */
        }
        decide(sim, i, hour, wd);
    }
}

void sim_reset(sim_t *sim, unsigned minute_of_week)
{
    sim->s.version = SIM_VERSION;
    sim->s.clock = minute_of_week % SIM_WEEK;
    sim->s.seed = 0x5EED1234u ^ minute_of_week;
    unsigned hour = sim->s.clock / 60 % 24, wd = sim->s.clock / 1440;
    for (int i = 0; i < SIM_PEOPLE; i++) {
        sim_person_t *p = &sim->s.p[i];
        static const uint8_t start[N_NEEDS] = { 70, 75, 70, 65, 70, 80, 65, 70 };
        for (int n = 0; n < N_NEEDS; n++)
            p->need[n] = start[n] - (rnd(sim) % 15);
        p->money = sim_tweaks[i].start_money;
        p->flags = 0;
        p->until = 0;
        derive(sim, i);
        if (!sim->orig[i]) {
            p->act = A_AWAY;
            p->place = SIM_AWAY;
            continue;
        }
        p->place = sim->orig[i][slot(hour, wd)];
        p->act = p->place == SIM_AWAY ? A_AWAY : A_USUAL;
        for (int k = 0; k < 24 * 7; k++)
            sim->plan[i][k] = sim->orig[i][k];
        decide(sim, i, hour, wd);
    }
}

void sim_set_clock(sim_t *sim, unsigned minute_of_week)
{
    sim->s.clock = minute_of_week % SIM_WEEK;
}

void sim_advance(sim_t *sim, unsigned minutes)
{
    if (minutes > 3 * 1440)
        minutes = 3 * 1440;                          /* a huge jump: don't stall the game */
    while (minutes) {
        unsigned to_hour = 60 - sim->s.clock % 60, step = minutes < to_hour ? minutes : to_hour;
        sim->s.clock = (sim->s.clock + step) % SIM_WEEK;
        minutes -= step;
        if (sim->s.clock % 60 == 0)
            hour_tick(sim);
    }
}

unsigned sim_area_now(const sim_t *sim, int i)
{
    unsigned c = sim->s.clock;
    return sim->plan[i][slot(c / 60 % 24, c / 1440)];
}

/* ---- save ------------------------------------------------------------------ */

int sim_save(const sim_t *sim, uint8_t *buf, int max)
{
    int n = sizeof(sim_state_t);
    if (max < n)
        return -1;
    const uint8_t *s = (const uint8_t *)&sim->s;
    for (int k = 0; k < n; k++)
        buf[k] = s[k];
    return n;
}

int sim_load(sim_t *sim, const uint8_t *buf, int len)
{
    sim_state_t tmp;
    uint8_t *d = (uint8_t *)&tmp;
    if (len != (int)sizeof(sim_state_t))
        return 0;
    for (int k = 0; k < len; k++)
        d[k] = buf[k];
    if (tmp.version != SIM_VERSION || tmp.clock >= SIM_WEEK)
        return 0;
    sim->s = tmp;
    unsigned hour = sim->s.clock / 60 % 24, wd = sim->s.clock / 1440;
    for (int i = 0; i < SIM_PEOPLE; i++) {
        sim_person_t *p = &sim->s.p[i];
        for (int n = 0; n < N_NEEDS; n++)
            if (p->need[n] > 100)
                p->need[n] = 100;
        if (p->act >= N_ACTS)
            p->act = A_USUAL;
        derive(sim, i);                              /* home / job / allowed come from the timetable */
        if (!sim->orig[i])
            continue;
        if (!allowed(sim, i, p->place))
            p->place = sim->orig[i][slot(hour, wd)];
        for (int k = 0; k < 24 * 7; k++)
            sim->plan[i][k] = sim->orig[i][k];
        sim->plan[i][slot(hour, wd)] = p->place;    /* where they are now */
    }
    return 1;
}
