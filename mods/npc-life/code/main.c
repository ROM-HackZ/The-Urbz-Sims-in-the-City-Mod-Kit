/* NPC Life connector: runs the routines (../sim) inside the game.

   The game keeps one weekly timetable per person (npc_schedule_table) and reads it through
   5 literal words; hooks.txt points those at live_table instead, so the game's own code
   (walking people in and out every 150 ticks, placing them when an area loads, the phone's
   "where I'll be" lines) follows the live timetables. Quest rules are checked before the
   timetable, so the story still wins. Switched off on the Mods page, the core restores the
   5 words and everyone goes back to their usual timetable.

   Nothing is saved: each week's plan comes from the game's week number (day / 7). */
#include "game.h"
#include "mod.h"
#include "../sim/npc_sim.c"

#define N_TABLE 49                        /* timetables for ids 31..79 (0 after the last) */

static sim_t sim;

static unsigned week_minute(void)
{
    return (unsigned)(game_time.day % 7) * 1440 + game_time.hour * 60 + game_time.minute;
}

#include "act.inc"                        /* visible actions (Phase 6) */
u8 *live_table[N_TABLE + 1];             /* what the game reads instead of npc_schedule_table */

/* Tests read this (magic 'NPCL'). */
struct {
    u32 magic, attached, plans, minutes, week, visits;
    sim_t *sim;
} npc_life = { 0x4C43504E, 0, 0, 0, 0, 0, &sim };

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

/* Plan the game's current week (cheap when it is already planned). */
static void follow_week(void)
{
    attach();
    u32 week = (u32)game_time.day / 7;
    if (sim.week != week) {
        sim_plan_week(&sim, week);
        npc_life.plans++;
    }
    npc_life.week = sim.week;
    npc_life.visits = sim.visits;
}

void mod_on_boot(void)
{
    attach();
}

void mod_on_load(const u8 *buf, int len)
{
    (void)buf;
    (void)len;
    follow_week();                            /* a loaded game or a new one: its own week */
}

void mod_on_minute(int n)
{
    follow_week();
    npc_life.minutes += n;
}

void mod_on_tick(void)
{
    if (npc_life.attached)
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
    follow_week();
}

/* Info page (Options > Mods > "npc-life: info"): who is in this area and what they're doing,
   then who is due here next. */
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
    unsigned here = current_area, now = week_minute();
    int count = 0, shown = 0;
    for (int i = 0; i < SIM_PEOPLE; i++)
        count += sim.orig[i] && sim_area_at(&sim, i, now) == here;
    q = str_cat(line, "Here: ");
    q = str_int(q, count);
    q = str_cat(q, count ? "" : "  Next here:");
    p->print(p, line);
    for (int i = 0; i < SIM_PEOPLE && shown < 4; i++) {          /* the people here */
        if (!sim.orig[i] || sim_area_at(&sim, i, now) != here)
            continue;
        const char *doing = act_doing(31 + i);
        q = str_cat(line, person_name(i, nm));
        q = str_cat(q, " ");
        q = str_cat(q, doing ? doing : sim_act_name(sim_act_at(&sim, i, now)));
        p->print(p, line);
        shown++;
    }
    for (int h = 1; h < 24 && shown < 4; h++)                    /* then who comes next */
        for (int i = 0; i < SIM_PEOPLE && shown < 4; i++) {
            unsigned m = now + 60 * h;
            if (!sim.orig[i] || sim_area_at(&sim, i, m) != here || sim_area_at(&sim, i, m - 60) == here)
                continue;
            q = str_cat(line, person_name(i, nm));
            q = str_cat(q, " at ");
            q = str_int(q, (game_time.hour + h) % 24);
            q = str_cat(q, ":00");
            p->print(p, line);
            shown++;
        }
}
