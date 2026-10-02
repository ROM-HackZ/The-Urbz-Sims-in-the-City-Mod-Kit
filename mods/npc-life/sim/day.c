/* Print one person's day from the routines: python run_test.py day <id> [week] [weekday]. */
#include <stdio.h>
#include <stdlib.h>
#include "npc_sim.h"
#include "orig_tables.h"

int main(int argc, char **argv)
{
    static sim_t sim;
    const uint8_t *orig[SIM_PEOPLE];
    int id = argc > 1 ? atoi(argv[1]) : 45, week = argc > 2 ? atoi(argv[2]) : 0, wd = argc > 3 ? atoi(argv[3]) : 0;
    for (int i = 0; i < SIM_PEOPLE; i++)
        orig[i] = has_table[i] ? orig_tables[i] : 0;
    sim_setup(&sim, orig);
    sim_plan_week(&sim, week);
    int i = id - SIM_FIRST_ID, last_act = -1;
    unsigned last_area = 0xFFFF;
    printf("%s, week %d, weekday %d\n", names[i], week, wd);
    for (unsigned m = wd * 1440; m < (unsigned)(wd + 1) * 1440; m++) {
        int act = sim_act_at(&sim, i, m);
        unsigned area = sim_area_at(&sim, i, m);
        if (act != last_act || area != last_area)
            printf("%02u:%02u  area %3u  %s\n", m / 60 % 24, m % 60, area, sim_act_name(act));
        last_act = act;
        last_area = area;
    }
    return 0;
}
