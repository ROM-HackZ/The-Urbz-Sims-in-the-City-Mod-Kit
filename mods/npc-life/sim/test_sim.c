/* PC test of the NPC Life routines: 4 weeks of city time in a second.
   Built and run by run_test.py (which makes orig_tables.h from your project/ folder). */
#include <stdio.h>
#include <string.h>
#include "npc_sim.h"
#include "orig_tables.h"            /* orig_tables[36][168], has_table[36], names[36] */

static sim_t sim;
static uint8_t week1[SIM_PEOPLE][168];
static int fails;

#define CHECK(c, ...) do { if (!(c)) { fails++; if (fails < 20) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); } } } while (0)

int main(void)
{
    const uint8_t *orig[SIM_PEOPLE];
    for (int i = 0; i < SIM_PEOPLE; i++)
        orig[i] = has_table[i] ? orig_tables[i] : 0;
    sim_setup(&sim, orig);
    long acts[N_ACTS] = { 0 }, by_hour[24][N_ACTS];
    static int first_eat[SIM_PEOPLE][28], first_wake[SIM_PEOPLE][28];
    memset(first_eat, -1, sizeof first_eat);
    memset(first_wake, -1, sizeof first_wake);
    int away = 0, visits = 0, differ = 0;
    memset(by_hour, 0, sizeof by_hour);
    for (uint32_t w = 0; w < 4; w++) {
        sim_plan_week(&sim, w);
        if (w == 1)
            memcpy(week1, sim.plan, sizeof week1);
        if (w == 2)
            differ = memcmp(week1, sim.plan, sizeof week1) != 0;
        for (unsigned m = 2; m < SIM_WEEK; m += 5)
            for (int i = 0; i < SIM_PEOPLE; i++) {
                if (!orig[i])
                    continue;
                unsigned h = m / 60 % 24, wd = m / 1440, o = orig[i][h * 7 + wd], a = sim_area_at(&sim, i, m);
                int act = sim_act_at(&sim, i, m);
                CHECK(o == SIM_AWAY || a == o, "%s week %u day %u %02u:00 in %u, the game has them in %u",
                      names[i], w, wd, h, a, o);                  /* nobody goes missing */
                CHECK(act >= 0 && act < N_ACTS, "activity %d", act);
                CHECK((a == SIM_AWAY) == (act == A_AWAY), "%s away in %u but activity %d", names[i], a, act);
                int known = 0;
                for (int k = 0; k < 168; k++)
                    known |= orig[i][k] == a;
                CHECK(known, "%s sent to %u, not in their timetable", names[i], a);
                acts[act]++;
                int day = w * 7 + wd, t = m % 1440;
                if (act == A_EAT && t >= 600 && first_eat[i][day] < 0)
                    first_eat[i][day] = t;                         /* when lunch started */
                if (act != A_SLEEP && act != A_AWAY && t >= 240 && first_wake[i][day] < 0 && a == sim.home[i])
                    first_wake[i][day] = t;
                by_hour[h][act]++;
                if (h >= 8 && h < 23 && m % 60 == 2) {   /* per hour; nights out of town stay away (asleep) */
                    away += o == SIM_AWAY;
                    visits += o == SIM_AWAY && a != SIM_AWAY;
                }
            }
    }
    /* the same week planned again comes out the same */
    sim_plan_week(&sim, 1);
    CHECK(!memcmp(week1, sim.plan, sizeof week1), "week 1 planned twice differs");
    CHECK(differ, "weeks 1 and 2 are identical (no variety)");
    CHECK(visits * 3 > away, "only %d of %d out-of-town hours became visits", visits, away);
    CHECK(by_hour[3][A_SLEEP] > 0 && by_hour[3][A_EAT] == 0, "night: nobody asleep, or someone eating at 3 am");
    CHECK(by_hour[12][A_EAT] > 0 && by_hour[19][A_EAT] > 0, "nobody eats at 12 or 19");
    CHECK(by_hour[10][A_WORK] > 0, "nobody works at 10");

    /* nobody eats lunch at the same minute every day */
    int same = 0, people = 0;
    for (int i = 0; i < SIM_PEOPLE; i++) {
        int lo = 1440, hi = -1, n = 0;
        for (int day = 0; day < 28; day++)
            if (first_eat[i][day] >= 0) {
                n++;
                if (first_eat[i][day] < lo) lo = first_eat[i][day];
                if (first_eat[i][day] > hi) hi = first_eat[i][day];
            }
        if (n >= 5) {
            people++;
            same += hi - lo < 30;
        }
    }
    CHECK(people > 10 && same == 0, "%d of %d people eat at the same time every day", same, people);
    printf("lunch/dinner start varies day to day for all %d people who eat out or at home\n", people);
    printf("example, %s: first meal after 10:00 on days 1-7:", names[23]);
    for (int day = 0; day < 7; day++)
        if (first_eat[23][day] >= 0)
            printf(" %d:%02d", first_eat[23][day] / 60, first_eat[23][day] % 60);
        else
            printf(" -");
    printf("\n4 weeks, 36 people: activities (person-hours)\n");
    for (int a = 0; a < N_ACTS; a++)
        printf("  %-14s %6ld\n", sim_act_name(a), acts[a] / 12);
    printf("by hour (sleep/wash/eat/work/out):\n");
    for (int h = 0; h < 24; h += 3)
        printf("  %02d:00  %3ld %3ld %3ld %3ld %3ld\n", h, by_hour[h][A_SLEEP] / 12, by_hour[h][A_WASH] / 12,
               by_hour[h][A_EAT] / 12, by_hour[h][A_WORK] / 12, by_hour[h][A_AWAY] / 12);
    printf("daytime out-of-town hours (8-23) turned into visits around the city: %d of %d\n", visits, away);
    printf("%s (%d problem(s))\n", fails ? "TEST_SIM FAIL" : "TEST_SIM PASS", fails);
    return fails ? 1 : 0;
}
