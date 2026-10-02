/* NPC Life connector: runs the simulation (../sim) inside the game.

   The game keeps one weekly timetable per person (npc_schedule_table) and reads it through
   5 literal words; hooks.txt points those at live_table instead, so the game's own code
   (walking people in and out every 150 ticks, placing them when an area loads, the phone's
   "where I'll be" lines) follows the simulation. Quest rules are checked before the
   timetable, so the story still wins. Switched off on the Mods page, the core restores the
   5 words and everyone goes back to their usual timetable. */
#include "game.h"
#include "mod.h"
#include "../sim/npc_sim.c"

#define N_TABLE 49                        /* timetables for ids 31..79 (0 after the last) */

static sim_t sim;
#include "act.inc"                        /* visible actions (Phase 6) */
u8 *live_table[N_TABLE + 1];             /* what the game reads instead of npc_schedule_table */

/* Tests read this (magic 'NPCL'), followed by the sim state itself. */
struct {
    u32 magic, attached, ready, resets, loads, saves, minutes, hours;
    sim_t *sim;
} npc_life = { 0x4C43504E, 0, 0, 0, 0, 0, 0, 0, &sim };

static unsigned week_minute(void)
{
    return (unsigned)(game_time.day % 7) * 1440 + game_time.hour * 60 + game_time.minute;
}

static void attach(void)
{
    if (npc_life.attached)
        return;
    u8 **orig = npc_schedule_table;
    const uint8_t *o[SIM_PEOPLE];
    for (int i = 0; i < SIM_PEOPLE; i++)
        o[i] = orig[i];
    sim_setup(&sim, o);
    for (int k = 0; k < N_TABLE; k++)
        live_table[k] = k < SIM_PEOPLE && orig[k] ? sim.plan[k] : orig[k];
    live_table[N_TABLE] = 0;
    npc_life.attached = 1;
}

static void start_fresh(void)
{
    attach();
    sim_reset(&sim, week_minute());
    npc_life.ready = 1;
    npc_life.resets++;
}

void mod_on_boot(void)
{
    attach();
}

void mod_on_load(const u8 *buf, int len)
{
    attach();
    if (buf && sim_load(&sim, buf, len)) {
        sim_set_clock(&sim, week_minute());
        npc_life.ready = 1;
        npc_life.loads++;
    } else
        start_fresh();                        /* new game, vanilla save, or old data */
}

int mod_on_save(u8 *buf, int max)
{
    if (!npc_life.ready)
        return 0;
    npc_life.saves++;
    return sim_save(&sim, buf, max);
}

void mod_on_minute(int n)
{
    if (!npc_life.ready)
        start_fresh();
    /* move to the game's time; never jump forward, or a skipped hour boundary means nobody
       decides that hour (a clock 1 minute behind skipped midnight) */
    unsigned now = week_minute(), ahead = (now + SIM_WEEK - sim.s.clock) % SIM_WEEK;
    if (ahead <= 3 * 1440)
        sim_advance(&sim, ahead);
    else
        sim_set_clock(&sim, now);             /* the clock went back: just follow it */
    npc_life.minutes += n;
    npc_life.hours = sim.hours;
}

void mod_on_tick(void)
{
    if (npc_life.ready)
        act_tick();                           /* people here act out what they're doing */
}

void mod_on_area_enter(int area)
{
    (void)area;
    for (int k = 0; k < MAX_ACTORS; k++)
        actors[k].e = 0;                      /* the old area's people are gone */
}

void mod_on_disable(void)
{
    act_release_all();                        /* everyone goes back to the game's own wandering */
}

void mod_on_enable(void)
{
    if (!npc_life.ready)
        start_fresh();
    else
        sim_set_clock(&sim, week_minute());
}

/* Info page (Options > Mods > "npc-life: info"): who is in this area, and what they're doing. */
static const char *person_name(int i, char *buf)
{
    const char *n = text_get(512 + i);        /* names: string 512 + c */
    int k = 0;
    while (n[k] && n[k] != ' ' && k < 12) {   /* first name is enough here */
        buf[k] = n[k];
        k++;
    }
    buf[k] = 0;
    return buf;
}

void mod_on_page(mod_page_t *p)
{
    char line[48], nm[16], *q;
    unsigned here = current_area;
    int count = 0, shown = 0;
    u8 done[SIM_PEOPLE];
    for (int i = 0; i < SIM_PEOPLE; i++) {
        done[i] = !sim.orig[i];
        count += sim.orig[i] && sim_area_now(&sim, i) == here;
    }
    static const char *const act[N_ACTS] = { "home", "sleep", "work", "eat", "fun", "chat", "park",
                                              "out", "away" };
    q = str_cat(line, "Here: ");
    q = str_int(q, count);
    q = str_cat(q, count ? "  (then hungriest)" : "  Hungriest:");
    p->print(p, line);
    /* the people here, then the hungriest anywhere: name, activity, place, money, food */
    while (shown < 4) {
        int best = -1;
        for (int i = 0; i < SIM_PEOPLE; i++) {
            if (done[i])
                continue;
            int here_i = sim_area_now(&sim, i) == here;
            if (best < 0 || here_i > (sim_area_now(&sim, best) == here) ||
                (here_i == (sim_area_now(&sim, best) == here) &&
                 sim.s.p[i].need[N_HUNGER] < sim.s.p[best].need[N_HUNGER]))
                best = i;
        }
        if (best < 0)
            break;
        done[best] = 1;
        const sim_person_t *s = &sim.s.p[best];
        q = str_cat(line, person_name(best, nm));
        q = str_cat(q, " ");
        const char *doing = act_doing(31 + best);
        if (doing) {                          /* acting it out right here */
            q = str_cat(q, doing);
            q = str_cat(q, " here");
        } else {
            q = str_cat(q, act[s->act]);
            q = str_cat(q, " in ");
            q = str_int(q, s->place);
        }
        q = str_cat(q, " $");
        q = str_int(q, s->money);
        q = str_cat(q, " f");
        q = str_int(q, s->need[N_HUNGER]);
        p->print(p, line);
        shown++;
    }
}
