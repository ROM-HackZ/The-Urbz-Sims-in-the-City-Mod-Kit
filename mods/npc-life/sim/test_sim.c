/* PC test of the NPC Life simulation: 4 weeks of city time in a second.
   Built and run by run_test.py (which makes orig_tables.h from your project/ folder). */
#include <stdio.h>
#include <string.h>
#include "npc_sim.h"
#include "orig_tables.h"            /* orig_tables[36][168], has_table[36], names[36] */

static sim_t sim, sim2;
static int fails;

#define CHECK(c, ...) do { if (!(c)) { fails++; if (fails < 20) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); } } } while (0)

int main(void)
{
    const uint8_t *orig[SIM_PEOPLE];
    for (int i = 0; i < SIM_PEOPLE; i++)
        orig[i] = has_table[i] ? orig_tables[i] : 0;
    sim_setup(&sim, orig);
    sim_reset(&sim, 8 * 60);                    /* Monday 8:00 */
    int lo_money[SIM_PEOPLE], hi_money[SIM_PEOPLE], starving[SIM_PEOPLE], worst_starving[SIM_PEOPLE];
    long need_sum[SIM_PEOPLE][N_NEEDS], acts[SIM_PEOPLE][N_ACTS];
    int hungry_choices = 0, hungry_ate = 0, hours = 0, visits = 0, away_hours = 0;
    memset(need_sum, 0, sizeof need_sum);
    memset(acts, 0, sizeof acts);
    for (int i = 0; i < SIM_PEOPLE; i++) {
        lo_money[i] = hi_money[i] = sim.s.p[i].money;
        starving[i] = worst_starving[i] = 0;
    }
    uint8_t hunger_before[SIM_PEOPLE];
    unsigned total = 4 * SIM_WEEK, done = 0, step = 7;
    while (done < total) {
        for (int i = 0; i < SIM_PEOPLE; i++)
            hunger_before[i] = sim.s.p[i].need[N_HUNGER];
        unsigned h0 = sim.hours;
        sim_advance(&sim, step);
        done += step;
        if (done == 2 * SIM_WEEK + 7 * 100) {   /* save/load in the middle: both copies must agree */
            uint8_t buf[sizeof(sim_state_t)];
            CHECK(sim_save(&sim, buf, sizeof buf) == (int)sizeof buf, "save size");
            sim_setup(&sim2, orig);
            CHECK(sim_load(&sim2, buf, sizeof buf), "load");
        }
        if (sim.hours == h0)
            continue;
        hours++;
        for (int i = 0; i < SIM_PEOPLE; i++) {
            if (!orig[i])
                continue;
            sim_person_t *p = &sim.s.p[i];
            for (int n = 0; n < N_NEEDS; n++) {
                CHECK(p->need[n] <= 100, "%s need %d = %d", names[i], n, p->need[n]);
                need_sum[i][n] += p->need[n];
            }
            acts[i][p->act]++;
            if (p->money < lo_money[i]) lo_money[i] = p->money;
            if (p->money > hi_money[i]) hi_money[i] = p->money;
            unsigned a = sim_area_now(&sim, i);
            int ok = 0;
            for (int k = 0; k < 168; k++)
                ok |= orig[i][k] == a;
            CHECK(ok, "%s sent to area %u, not in their timetable", names[i], a);
            {   /* nobody goes missing: away from the original area only in out-of-town hours */
                unsigned c = sim.s.clock, o = orig[i][(c / 60 % 24) * 7 + c / 1440];
                CHECK(o == SIM_AWAY || a == o, "%s at %u but the game has them at %u", names[i], a, o);
                visits += o == SIM_AWAY && a != SIM_AWAY;
                away_hours += o == SIM_AWAY;
            }
            starving[i] = p->need[N_HUNGER] < 10 ? starving[i] + 1 : 0;
            if (starving[i] > worst_starving[i]) worst_starving[i] = starving[i];
            (void)hunger_before;
            if (p->need[N_HUNGER] < 30 && p->act != A_SLEEP && p->act != A_WORK) {   /* at decision time */
                hungry_choices++;
                hungry_ate += p->act == A_EAT;
            }
        }
    }
    /* the copy loaded mid-way, run one more day alongside */
    sim_advance(&sim2, 0);
    {
        sim_t a = sim;
        (void)a;
    }
    printf("%-22s %4s %4s  %-28s %6s %6s %6s  %s\n", "person", "home", "job", "average needs (hu hy en so co bl fu)",
           "$min", "$max", "$end", "time: home/sleep/work/eat/fun/social/park/usual/away %");
    for (int i = 0; i < SIM_PEOPLE; i++) {
        if (!orig[i])
            continue;
        sim_person_t *p = &sim.s.p[i];
        char needs[64], *q = needs;
        for (int n = 0; n < 7; n++)
            q += sprintf(q, "%2ld ", need_sum[i][n] / hours);
        char ac[80], *r = ac;
        for (int k = 0; k < N_ACTS; k++)
            r += sprintf(r, "%ld/", acts[i][k] * 100 / hours);
        printf("%-22s %4d %4d  %-28s %6d %6d %6d  %s\n", names[i], p->home, p->work == 255 ? -1 : p->work,
               needs, lo_money[i], hi_money[i], p->money, ac);
        CHECK(worst_starving[i] <= 6, "%s was starving for %d hours in a row", names[i], worst_starving[i]);
        CHECK(lo_money[i] > -400, "%s went broke (%d)", names[i], lo_money[i]);
        CHECK(p->money > -200, "%s ended broke (%d)", names[i], p->money);
        if (p->work != 255)
            CHECK(hi_money[i] - lo_money[i] > 50, "%s's money never moved", names[i]);
    }
    printf("\n%d city hours simulated; when hungry (<30) and not asleep or at work, %d%% of choices were to eat (%d/%d)\n",
           hours, hungry_choices ? hungry_ate * 100 / hungry_choices : 0, hungry_ate, hungry_choices);
    CHECK(hungry_choices == 0 || hungry_ate * 100 / hungry_choices >= 50, "hungry people don't eat");
    printf("out-of-town hours turned into visits around the city: %d of %d\n", visits, away_hours);

    /* determinism after save/load: run both for a day from the same state */
    {
        uint8_t buf[sizeof(sim_state_t)];
        sim_save(&sim, buf, sizeof buf);
        sim_setup(&sim2, orig);
        sim_load(&sim2, buf, sizeof buf);
        sim_advance(&sim, 1440);
        sim_advance(&sim2, 1440);
        CHECK(memcmp(&sim.s, &sim2.s, sizeof sim.s) == 0, "a loaded copy behaves differently");
    }
    printf("%s (%d problem(s))\n", fails ? "TEST_SIM FAIL" : "TEST_SIM PASS", fails);
    return fails ? 1 : 0;
}
