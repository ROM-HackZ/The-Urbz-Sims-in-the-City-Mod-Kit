#include "game.h"
#include "mod.h"

/* Test (proof npc-pose-gallery): townspeople lo..hi are put in `area` (everyone else kept out of it), stood in
   a row in front of you, facing `dir`, and play `anim` over and over (every `every` ticks). The proof pokes
   the struct between screenshots. The poses come from poses.json (a copy of NPC Life's). */
#define set_action GAME_FN(ADDR_entity_set_action, void (*)(void *e, int action))
#define play_anim  GAME_FN(ADDR_entity_play_anim, void (*)(void *e, int anim))
#define face       GAME_FN(ADDR_entity_face, void (*)(void *e, int dir))
#define spawn_npc  GAME_FN(ADDR_spawn_npc, void *(*)(int id, int facing, s32 x, s32 y))
#define set_mirror GAME_FN(ADDR_entity_set_mirror, void (*)(void *e, int n))

struct {
    u32 magic;
    u32 area;                      /* 0xFFFFFFFF: off */
    u8 lo, hi, anim, dir;
    s16 dx, dy;                    /* the row: first person at you + (dx, dy), then every 36 px to the right */
    u16 every;
    u32 placed, played, ticks, spawned;
} gallery = { 0x594C4147, 0xFFFFFFFF, 0, 0, 4, 4, -90, 40, 90 };   /* 'GALY' */

unsigned gallery_schedule(unsigned char_id, game_time_t *t)
{
    if (gallery.area != 0xFFFFFFFF) {
        if (char_id >= gallery.lo && char_id <= gallery.hi)
            return gallery.area;
        unsigned r = schedule_lookup(char_id, t);
        return r == gallery.area ? 82 : r;          /* (82: somewhere far away) */
    }
    return schedule_lookup(char_id, t);
}

static u8 last_anim = 0xFF;

void mod_on_tick(void)
{
    if (gallery.area == 0xFFFFFFFF || current_area != gallery.area)
        return;
    gallery.ticks++;
    u8 *me = 0;
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e)
        if (*(u16 *)(e + 8) == 0)
            me = e;
    if (!me)
        return;
    if (gallery.ticks % 120 == 60) {                 /* someone the game won't bring here (quest rules): spawn them */
        u32 here = 0;
        for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e)
            if (*(u16 *)(e + 8) == 7 && *(u16 *)(e + 10) >= gallery.lo && *(u16 *)(e + 10) <= gallery.hi)
                here |= 1u << (*(u16 *)(e + 10) - gallery.lo);
        for (int k = 0; k <= gallery.hi - gallery.lo; k++)
            if (!(here & (1u << k)) && gallery.ticks > 600) {
                spawn_npc(gallery.lo + k, 3, *(s32 *)(me + 0x18), *(s32 *)(me + 0x1C));
                gallery.spawned++;
            }
    }
    int again = gallery.anim != last_anim || gallery.ticks % gallery.every == 0;
    last_anim = gallery.anim;
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e) {
        if (*(u16 *)(e + 8) != 7)
            continue;
        int who = *(u16 *)(e + 10);
        if (who < gallery.lo || who > gallery.hi)
            continue;
        int k = who - gallery.lo;
        set_action(e, 0x30);                         /* the wander state leaves them be */
        *(s32 *)(e + 0x18) = *(s32 *)(me + 0x18) + (gallery.dx + 36 * k) * 0x10000;
        *(s32 *)(e + 0x1C) = *(s32 *)(me + 0x1C) + gallery.dy * 0x10000;
        gallery.placed++;
        if (again) {
            face(e, gallery.dir);
            set_mirror(e, 4);
            play_anim(e, gallery.anim);
            gallery.played++;
        }
    }
}
