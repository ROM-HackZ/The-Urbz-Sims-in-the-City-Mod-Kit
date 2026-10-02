/* NPC Life routines (see npc_sim.h). Portable C: no game addresses, no C library. */
#include "npc_sim.h"
#include "sim_data.h"

#define NONE 0xFF

static const char *const act_names[N_ACTS] = {
    "at home", "asleep", "at work", "eating", "having fun", "socialising", "in the park",
    "out and about", "out of town", "washing"
};

const char *sim_act_name(int act)
{
    return act >= 0 && act < N_ACTS ? act_names[act] : "?";
}

/* A fixed hash: the same person, week and hour always give the same number. */
static uint32_t mix(uint32_t a, uint32_t b, uint32_t c)
{
    uint32_t x = a * 0x9E3779B1u ^ b * 0x85EBCA77u ^ c * 0xC2B2AE3Du ^ 0x5EED1234u;
    x ^= x >> 15;
    x *= 0x2C1B3C6Du;
    x ^= x >> 12;
    x *= 0x297A2D39u;
    x ^= x >> 15;
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
static int meal(unsigned hour) { return hour == 12 || hour == 13 || hour == 18 || hour == 19; }

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
    sim->n_allowed[i] = 0;
    sim->home[i] = sim->work[i] = NONE;
    if (!t)
        return;
    for (int k = 0; k < 24 * 7; k++) {
        int seen = 0;
        for (int j = 0; j < sim->n_allowed[i]; j++)
            seen |= sim->allowed[i][j] == t[k];
        if (!seen && sim->n_allowed[i] < 24)
            sim->allowed[i][sim->n_allowed[i]++] = t[k];
    }
    sim->home[i] = most_common(t, 0, 6, 7, NONE);
    if (sim->home[i] == NONE)
        sim->home[i] = t[slot(2, 0)];
    sim->work[i] = most_common(t, 9, 17, 5, sim->home[i]);
    if (sim->work[i] == SIM_AWAY)
        sim->work[i] = NONE;
}

void sim_setup(sim_t *sim, const uint8_t *const orig[SIM_PEOPLE])
{
    for (int i = 0; i < SIM_PEOPLE; i++) {
        sim->orig[i] = orig[i];
        derive(sim, i);
    }
    sim->week = 0xFFFFFFFF;
    sim_plan_week(sim, 0);
}

/* ---- visits in free time --------------------------------------------------- */

/* A place this person knows that offers one of `kinds` (0 = none), picked by `r`. */
static unsigned pick_place(const sim_t *sim, int i, unsigned kinds, uint32_t r)
{
    unsigned found[24], n = 0;
    for (int j = 0; j < sim->n_allowed[i]; j++) {
        const sim_place_t *pl = place_of(sim->allowed[i][j]);
        if (pl && (pl->kinds & kinds) && sim->allowed[i][j] != SIM_AWAY)
            found[n++] = sim->allowed[i][j];
    }
    return n ? found[r % n] : 0;
}

/* Out-of-town hours become visits, in 2-hour blocks: lunch and dinner at a food place,
   daytime in a park or with friends, evenings out; nights and early mornings stay away. */
void sim_plan_week(sim_t *sim, uint32_t week)
{
    if (sim->week == week)
        return;
    sim->week = week;
    sim->visits = 0;
    for (int i = 0; i < SIM_PEOPLE; i++) {
        const uint8_t *t = sim->orig[i];
        for (int k = 0; k < 24 * 7; k++)
            sim->plan[i][k] = t ? t[k] : SIM_AWAY;
        if (!t)
            continue;
        for (unsigned wd = 0; wd < 7; wd++)
            for (unsigned h = 0; h < 24; h++) {
                if (t[slot(h, wd)] != SIM_AWAY || h < 8 || h == 23)
                    continue;
                uint32_t r = mix(i, week, wd * 12 + h / 2);
                unsigned kinds = 0, chance = 0;
                if (meal(h)) {
                    kinds = K_FOOD;
                    chance = 70;
                } else if (h >= 20) {
                    kinds = K_FUN | K_SOCIAL;
                    chance = 60;
                } else {
                    kinds = K_PARK | K_SOCIAL | K_FUN | K_GYM;
                    chance = 45;
                }
                if (r % 100 >= chance)
                    continue;
                unsigned a = pick_place(sim, i, kinds, r >> 8);
                if (a) {
                    sim->plan[i][slot(h, wd)] = a;
                    sim->visits++;
                }
            }
    }
}

/* ---- now ------------------------------------------------------------------ */

unsigned sim_area_at(const sim_t *sim, int i, unsigned m)
{
    m %= SIM_WEEK;
    return sim->plan[i][slot(m / 60 % 24, m / 1440)];
}

/* A person's day, in minutes after midnight. Habits are fixed per person (early bird or night owl,
   shower in the morning or the evening, early or late eater); every day then shifts them a little,
   and now and then a meal is skipped. So nobody does the same thing at the same time every day. */
typedef struct { int wake, bed, wash, lunch, lunch_len, dinner, dinner_len; } day_t;

static day_t day_of(const sim_t *sim, int i, unsigned wd)
{
    uint32_t hb = mix(i, 0xAB1E, 7), r = mix(i, sim->week, wd + 100);
    day_t d;
    d.wake = 300 + (int)(hb % 180) + (int)(r % 91) - 45;                 /* 5:00-8:00, +-45 min */
    d.bed = d.wake + 930 + (int)((hb >> 8) % 120) + (int)((r >> 6) % 41) - 20;   /* awake 15.5-17.5 h */
    d.wash = (hb >> 16) & 1 ? d.bed - 50 : d.wake;                       /* evening or morning */
    d.lunch = 690 + (int)((hb >> 20) % 90) + (int)((r >> 12) % 81) - 40; /* 11:30-13:00, +-40 min */
    d.lunch_len = (r >> 18) % 8 == 0 ? 0 : 35 + (int)((r >> 21) % 35);  /* skipped 1 day in 8 */
    d.dinner = 1050 + (int)((hb >> 24) % 120) + (int)((r >> 23) % 81) - 40;  /* 17:30-19:30, +-40 min */
    d.dinner_len = 45 + (int)((r >> 27) % 30);
    return d;
}

static int in(int t, int from, int len) { return t >= from && t < from + len; }

int sim_act_at(const sim_t *sim, int i, unsigned m)
{
    m %= SIM_WEEK;
    unsigned h = m / 60 % 24, wd = m / 1440, area = sim->plan[i][slot(h, wd)];
    if (!sim->orig[i] || area == SIM_AWAY)
        return A_AWAY;
    const sim_place_t *pl = place_of(area);
    uint32_t r = mix(i, sim->week, wd * 24 + h);
    int t = (int)(m % 1440);
    day_t d = day_of(sim, i, wd);
    int asleep = t < d.wake || t >= d.bed;
    if (d.bed >= 1440)                                  /* night owls go to bed after midnight */
        asleep = t >= d.bed - 1440 && t < d.wake;
    if (area == sim->home[i]) {
        if (asleep)
            return A_SLEEP;
        if (in(t, d.wash, 25))
            return A_WASH;
        if (in(t, d.wake + 25, 30) || in(t, d.lunch, d.lunch_len) || in(t, d.dinner, d.dinner_len))
            return A_EAT;
        return A_HOME;
    }
    if (area == sim->work[i] && sim->orig[i][slot(h, wd)] == area) {
        if (in(t, d.lunch, d.lunch_len) && pl && (pl->kinds & K_FOOD))
            return A_EAT;                            /* lunch break where they work */
        return A_WORK;
    }
    if (pl) {
        unsigned ph = (h + 23) % 24, pw = h ? wd : (wd + 6) % 7;
        int settling = sim->plan[i][slot(ph, pw)] != area && (int)(t % 60) < (int)(r % 41);   /* just arrived */
        if ((pl->kinds & K_FOOD) && !settling &&
            (in(t, d.lunch, d.lunch_len + 30) || in(t, d.dinner, d.dinner_len + 30)))
            return A_EAT;
        if (pl->kinds & (K_FUN | K_GYM))
            return (pl->kinds & K_SOCIAL) && (r & 3) == 0 ? A_SOCIAL : A_FUN;
        if (pl->kinds & K_PARK)
            return A_PARK;
        if (pl->kinds & (K_SOCIAL | K_FOOD))
            return A_SOCIAL;
    }
    return (r & 3) == 0 ? A_SOCIAL : A_USUAL;        /* now and then they stop for a chat */
}
