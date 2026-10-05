/* Prototype: draw one person (Kris Thistle, 45) with the player's body and animations, in her own
   colours, to judge whether giving everyone the player's ~196 animations would look right.

   How (docs/systems.md "Player body on a person"): after the game's own update each tick, when her
   animation or facing changed, do what the player's graphics update does (player_gfx_refresh):
   player_body_setup(e, look) fills her 4 drawing slots with the player's tables, entity_set_frames
   picks the facing, entity_set_script the frame timing. Her colours: load_look_palette builds the
   player's 2 palette rows from a look of ours into 2 OBJ rows nobody here uses.
   Off by default: switch it on in Options > Mods. */
#include "game.h"
#include "mod.h"

#define KRIS 45
#define body_setup   GAME_FN(ADDR_player_body_setup, void (*)(void *e, const u8 *look))
#define load_palette GAME_FN(ADDR_load_look_palette, void (*)(const u8 *look, int row_a, int row_b))
#define set_frames   GAME_FN(ADDR_entity_set_frames, void (*)(void *e, int anim, int facing))
#define layered      GAME_FN(ADDR_entity_layered, void (*)(void *e))
#define set_script   GAME_FN(ADDR_entity_set_script, void (*)(void *e, u32 script, int start))

/* gender, skin, hair style, hair colour, shirt style, shirt, overshirt, sleeve, pants, shoes.
   Clothing colour c = palette 11542 row c % 16 (shades 1-3, or 4-6 when c >= 16); skin and hair
   colour = rows of 11543 (docs/player-look.md). Close to Kris: brown skin, dark hair, white and denim. */
static const u8 kris_look[10] = { 1, 4, 2, 6, 1, 27, 13, 28, 13, 2 };   /* white top, denim jeans */

struct {
    u32 magic, applied, palettes, unsupported;
    u8 row_a, row_b, last_anim, pad;
    u32 entity, n_layered;
} body = { 0x59444F42 };                                  /* 'BODY' */

static u8 *kris, last_face = 0xFF, last_anim = 0xFF;
static u32 palette_area = 0xFFFFFFFF;

static u8 *find(int id)
{
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e)
        if (*(u16 *)(e + 8) == 7 && *(u16 *)(e + 10) == id)
            return e;
    return 0;
}

/* two OBJ palette rows (9-15: the people's pool) that no entity in the world uses */
static void pick_rows(void)
{
    u32 used = 0x1FF;                                     /* 0-8: the player and street objects */
    for (u8 *e = *(u8 **)ADDR_entity_lists; e; e = *(u8 **)e)
        used |= 1u << (*(u8 *)(e + 0x91) >> 4);
    body.row_a = body.row_b = 0;
    for (int r = 15; r >= 9; r--)
        if (!(used & (1u << r))) {
            if (!body.row_a)
                body.row_a = r;
            else if (!body.row_b) {
                body.row_b = r;
                break;
            }
        }
}

#define play_anim    GAME_FN(ADDR_entity_play_anim, void (*)(void *e, int anim))

/* Switched off: back to her own sprite (one slot, her own palette row) at her next frame. */
void mod_on_disable(void)
{
    u8 *e = find(KRIS);
    if (e && (e[0xC5] & 0x40)) {
        e[0xC5] &= ~0x40;
        for (int k = 1; k < 4; k++)
            *(u32 *)(e + 0xD4 + 12 * k) = 0;               /* the extra slots draw nothing */
        e[0xCD] = e[0x91] >> 4;
        e[0xC7] = 0xFF;                                   /* force the game to set her animation again */
        play_anim(e, 4);
    }
    kris = 0;
    palette_area = 0xFFFFFFFF;
}

void mod_on_area_enter(int area)
{
    (void)area;
    kris = 0;
    palette_area = 0xFFFFFFFF;
}

void mod_on_tick(void)
{
    u8 *e = find(KRIS);
    if (!e) {
        kris = 0;
        return;
    }
    if (e != kris || palette_area != current_area) {
        pick_rows();
        if (!body.row_b)
            return;                                       /* no free rows: leave her as she is */
        load_palette(kris_look, body.row_a, body.row_b);
        palette_area = current_area;
        body.palettes++;
        kris = e;
        body.entity = (u32)e;
        last_anim = last_face = 0xFF;
    }
    u8 anim = e[0xC7], face = e[0x12];
    if (anim == last_anim && face == last_face)
        return;
    const u32 *table = ((const u32 **)ADDR_player_body_tables)[kris_look[0]];
    if (anim >= 196 || !table[anim]) {                   /* the player has no such animation: stand */
        body.unsupported++;
        anim = 4;
        e[0xC7] = 4;
    }
    if (!(e[0xC5] & 0x40)) {
        layered(e);                                       /* draw from 4 slots, like the player */
        body.n_layered++;
    }
    body_setup(e, kris_look);
    for (int k = 0; k < 4; k++)
        e[0xCE + 12 * k] = 4 + k;                         /* the slots' sprite numbers (as the player's) */
    e[0xCD] = body.row_a;                                 /* body + hair: row a; clothes: row b */
    e[0xD9] = body.row_b;
    e[0xE5] = body.row_a;
    set_frames(e, anim, ((const s8 *)ADDR_player_facing_table)[face]);
    set_script(e, ((const u32 *)(kris_look[0] ? ADDR_player_scripts_b : ADDR_player_scripts_a))[anim], 0);
    last_anim = e[0xC7];
    last_face = face;
    body.last_anim = anim;
    body.applied++;
}
