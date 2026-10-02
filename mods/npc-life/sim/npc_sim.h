/* NPC Life: a needs-driven simulation of the city's 36 named people.

   Portable C with no game addresses: the same file runs in the game (through the connector
   in ../code) and on a PC (test_sim.c). The connector hands it each person's original weekly
   timetable and gets back live timetables in the same format, which the game then follows.

   Timetables: u8[24 hours][7 weekdays] of area ids, indexed [hour * 7 + weekday]; area 82 =
   out of town. The sim only ever uses areas from a person's own original timetable, so it
   never sends anyone somewhere the game can't show them.

   Time: minutes of the week (0 .. 10079; weekday = day % 7 as the game counts). Needs, money
   and the current activity change on every game hour; at each hour everyone picks what to do
   next (Sims-style: how urgent each need is x what a place gives, plus their job and their
   usual timetable). */
#pragma once
#include <stdint.h>

#define SIM_PEOPLE   36
#define SIM_FIRST_ID 31           /* character id of person 0 (Bayou Boo) */
#define SIM_AWAY     82           /* "out of town" in timetables */
#define SIM_WEEK     10080        /* minutes in a week */
#define SIM_VERSION  1

enum { N_HUNGER, N_HYGIENE, N_ENERGY, N_SOCIAL, N_COMFORT, N_BLADDER, N_FUN, N_ROOM, N_NEEDS };
enum { A_HOME, A_SLEEP, A_WORK, A_EAT, A_FUN, A_SOCIAL, A_PARK, A_USUAL, A_AWAY, N_ACTS };

typedef struct {                  /* 16 bytes, saved */
    uint8_t need[N_NEEDS];        /* 0..100, the game's order */
    int16_t money;
    uint8_t act;                  /* A_* */
    uint8_t place;                /* area id now (82 = away) */
    uint8_t until;                /* hour of the week (0..167) the activity runs to */
    uint8_t home, work;           /* worked out from the timetable at setup */
    uint8_t flags;                /* bit 0 = hungry and couldn't afford food last time */
} sim_person_t;

typedef struct {                  /* everything that is saved */
    uint16_t version;
    uint16_t clock;               /* minute of the week */
    uint32_t seed;
    sim_person_t p[SIM_PEOPLE];
} sim_state_t;

typedef struct {
    sim_state_t s;
    const uint8_t *orig[SIM_PEOPLE];          /* original timetables (0 = person has none) */
    uint8_t plan[SIM_PEOPLE][24 * 7];        /* live timetables the game reads */
    uint8_t allowed[SIM_PEOPLE][24];         /* distinct areas of the original timetable */
    uint8_t n_allowed[SIM_PEOPLE];
    uint32_t hours;                          /* hours simulated since setup (stats) */
} sim_t;

/* Connect the original timetables (and work out homes, jobs, allowed areas). */
void sim_setup(sim_t *sim, const uint8_t *const orig[SIM_PEOPLE]);
/* Start fresh at this minute of the week (new game, or no saved data). */
void sim_reset(sim_t *sim, unsigned minute_of_week);
/* The game clock moved on: needs, money, activities, plans. */
void sim_advance(sim_t *sim, unsigned minutes);
/* Keep the clock in step without simulating (e.g. after loading a save at another time). */
void sim_set_clock(sim_t *sim, unsigned minute_of_week);
/* Save / load (sizeof(sim_state_t) bytes). Load returns 0 if the data isn't usable. */
int sim_save(const sim_t *sim, uint8_t *buf, int max);
int sim_load(sim_t *sim, const uint8_t *buf, int len);

const char *sim_act_name(int act);
/* Where a person's live timetable says they are at this minute of the week. */
unsigned sim_area_now(const sim_t *sim, int person);
