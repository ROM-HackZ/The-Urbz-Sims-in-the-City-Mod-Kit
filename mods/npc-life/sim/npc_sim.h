/* NPC Life: daily routines for the city's 36 named people.

   Portable C with no game addresses: the same file runs in the game (through the connector
   in ../code) and on a PC (test_sim.c). The connector hands it each person's original weekly
   timetable and gets back live timetables in the same format, which the game then follows.

   Timetables: u8[24 hours][7 weekdays] of area ids, indexed [hour * 7 + weekday]; area 82 =
   out of town. Where: every hour, a person is in the area of their original timetable (nobody
   goes missing from where the game puts them); only the hours the original game has them out
   of town may become visits to places they know (a café at lunch, a club in the evening, a park
   by day). What: an activity from the time of day and the kind of place (sleep at night at home,
   wash in the morning, eat at meal times, work during work hours, ...).

   Nothing is saved: the plan for a week is made from the week number (game day / 7) with a fixed
   seed, so the same week always comes out the same, and each week is a little different. */
#pragma once
#include <stdint.h>

#define SIM_PEOPLE   36
#define SIM_FIRST_ID 31           /* character id of person 0 (Bayou Boo) */
#define SIM_AWAY     82           /* "out of town" in timetables */
#define SIM_WEEK     10080        /* minutes in a week */

enum { A_HOME, A_SLEEP, A_WORK, A_EAT, A_FUN, A_SOCIAL, A_PARK, A_USUAL, A_AWAY, A_WASH, N_ACTS };

typedef struct {
    const uint8_t *orig[SIM_PEOPLE];          /* original timetables (0 = person has none) */
    uint8_t plan[SIM_PEOPLE][24 * 7];        /* live timetables the game reads */
    uint8_t allowed[SIM_PEOPLE][24];         /* distinct areas of the original timetable */
    uint8_t n_allowed[SIM_PEOPLE];
    uint8_t home[SIM_PEOPLE], work[SIM_PEOPLE];   /* from the timetable (0xFF = none) */
    uint32_t week;                           /* the week the plan is for */
    uint32_t visits;                         /* out-of-town hours turned into visits this week */
} sim_t;

/* Connect the original timetables (homes, jobs, allowed areas) and plan week 0. */
void sim_setup(sim_t *sim, const uint8_t *const orig[SIM_PEOPLE]);
/* Plan this week's visits (does nothing if it is already planned). */
void sim_plan_week(sim_t *sim, uint32_t week);
/* Where a person's live timetable says they are at this minute of the week. */
unsigned sim_area_at(const sim_t *sim, int person, unsigned minute_of_week);
/* What they are doing then (A_*). */
int sim_act_at(const sim_t *sim, int person, unsigned minute_of_week);
const char *sim_act_name(int act);
