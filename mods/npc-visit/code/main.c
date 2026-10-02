#include "game.h"

/* Bayou Boo visits the King Tower roof (area 70, where a new game starts) from 10:40 to
   11:59 am. We don't spawn him ourselves: we answer the game's own "where should this
   person be?" question (schedule_lookup), and every 150 ticks the game walks people in
   and out of the current area to match. This is the hook NPC Life will use. */
#define VISITOR      31          /* character id: 31 + c (c = 0 Bayou Boo ... 14 Kris ... 35 Sharona) */
#define VISIT_AREA   70          /* "5: Roof" of King Tower */
#define FROM_HOUR    10
#define FROM_MINUTE  40
#define UNTIL_HOUR   11          /* leaves at noon */

struct { u32 magic; u32 answered; } npc_visit = { 0x54495356, 0 };   /* 'VSIT' */

unsigned visit_schedule(unsigned char_id, game_time_t *t)
{
    if (char_id == VISITOR && t->day == 0 &&
        ((t->hour == FROM_HOUR && t->minute >= FROM_MINUTE) ||
         (t->hour > FROM_HOUR && t->hour <= UNTIL_HOUR))) {
        npc_visit.answered++;
        return VISIT_AREA;
    }
    return schedule_lookup(char_id, t);
}
