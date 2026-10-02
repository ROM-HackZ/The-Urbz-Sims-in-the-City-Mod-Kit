/* The in-game Mods page (Phase 5, A4).

   The bottom-screen menus (Urb Info, Options, ...) are data: menu_table_ptrs holds one
   menu per index, and a menu is a header plus up to 8 buttons {x, y, icon frame; action;
   sub-menu; param; label string}. Action 0 opens the sub-menu named by the button, and the
   game's own code draws icons and labels and tests touches. So the core:
     - copies the 5 menu pointers into a longer array (index 5 = Mods page, 6 = a mod's
       info page) and points the game's 4 literals at it;
     - gives Options a 4th button, "Mods", that opens menu 5 (the same 2 x 2 layout as
       Urb Info: Settings, Save Game / Mods, Quit Game);
     - answers taps on the Mods page itself (menu_hit_call): switch the mod, redraw, stay.
   Labels are string ids; ids from 0xF000 are the core's own text (menu_label_call). */
#include "game.h"
#include "mod.h"
#include "core.h"

typedef struct {
    u32 pos;                  /* x | y << 8 | icon frame << 16 (x, y = icon centre) */
    u32 action;               /* 0 = open sub-menu `sub`; else returned to the game */
    u32 sub, param, label;
} menu_button_t;

typedef struct {
    u32 gfx, layout, z0, z1, pal16, pal256;
    u16 count, pad;
    menu_button_t b[8];
} menu_t;

typedef struct {
    u32 unk0, open, menu, action;
    u16 selected;
} menu_ui_t;

#define menu_ui      (*(menu_ui_t **)ADDR_menu_ui)
#define menu_hit_test  GAME_FN(ADDR_menu_hit_test, int (*)(void))
#define menu_redraw    GAME_FN(ADDR_menu_redraw, void (*)(void))
#define menu_draw_text GAME_FN(ADDR_menu_draw_text, void (*)(void))
#define text_get       GAME_FN(ADDR_text_get, const char *(*)(int))
#define text_draw      GAME_FN(ADDR_text_draw, void (*)(int, int, int, const char *, int))
#define text_font      GAME_FN(ADDR_text_font, void (*)(int, int, int))
#define ui_sound       GAME_FN(ADDR_ui_sound, void (*)(int))
#define set_palette_row GAME_FN(ADDR_set_palette_row, void (*)(void *, int))
#define menu_sprites   ((void **)0x02144D10)        /* 8 button sprites of the open menu */
#define sprite_set_pos GAME_FN(0x02001DAC, void (*)(void *, int, int))   /* (sprite, x << 16, y << 16) */

enum { MENU_OPTIONS = 2, MENU_MODS = 5, MENU_INFO = 6, N_MENUS = 7 };
enum { LABEL_BASE = 0xF000, LABEL_LINE = 0xF010, LABEL_BACK = 0xF00E, LABEL_MODS = 0xF00F };
enum { ACT_ITEM = 0x60, ACT_LINE = 0x7F };        /* 0x60 + button: an item on the Mods page */
#define INFO_LINES 7
enum { IT_TOGGLE, IT_INFO, IT_NEXT };
#define PER_PAGE 6

static const menu_t *menus[N_MENUS];
static menu_t options4, mods_menu, info_menu;
static char labels[8][28];
static char lines[INFO_LINES][32];
static int n_lines;
static struct { u8 kind, mod; } items[8];
static int page, info_mod;

static const char *mod_name(int i, char *out)
{
    const char *n = mod_table->rows[i].name;
    int k = 0;
    while (k < 15 && n[k]) {
        out[k] = n[k];
        k++;
    }
    out[k] = 0;
    return out;
}

static void cat(char *d, const char *s)
{
    while (*d)
        d++;
    while ((*d++ = *s++))
        ;
}

static menu_button_t button(int x, int y, int frame, int action, int sub, int label)
{
    menu_button_t b = { x | y << 8 | frame << 16, action, sub, 0, label };
    return b;
}

/* (Re)build the Mods page from the mod table: 2 columns x 3 rows. */
static void build_mods_page(void)
{
    mod_table_t *t = mod_table;
    int n = 0, skip = page * (PER_PAGE - 1), more = 0, k = 0;
    /* the list: each mod's switch, then "info" for mods with an info page */
    for (int i = 0; i < t->count; i++) {
        for (int kind = IT_TOGGLE; kind <= IT_INFO; kind++) {
            if (kind == IT_INFO && !t->rows[i].ev[EV_PAGE])
                continue;
            if (k++ < skip)
                continue;
            if (n == PER_PAGE) {
                more = 1;
                continue;
            }
            items[n].kind = kind;
            items[n].mod = i;
            n++;
        }
    }
    if (more) {                                     /* last slot: next page */
        n = PER_PAGE - 1;
        items[n].kind = IT_NEXT;
        n++;
    } else if (page && n < PER_PAGE) {             /* last page: back to the first */
        items[n].kind = IT_NEXT;
        n++;
    }
    mods_menu = options4;                            /* same icons and colours */
    mods_menu.count = n;
    for (int s = 0; s < n; s++) {
        int x = s & 1 ? 192 : 64, y = 28 + 46 * (s >> 1), frame;
        char nm[16];
        labels[s][0] = 0;
        if (items[s].kind == IT_NEXT) {
            cat(labels[s], more ? "More mods" : "First page");
            frame = 0;
        } else {
            mod_row_t *r = &t->rows[items[s].mod];
            cat(labels[s], mod_name(items[s].mod, nm));
            if (items[s].kind == IT_INFO) {
                cat(labels[s], ": info");
                frame = 0;
            } else if (!(r->flags & MODF_TOGGLE)) {
                cat(labels[s], ": always on");
                frame = 1;
            } else {
                cat(labels[s], r->on ? ": ON" : ": OFF");
                if (r->runtime & 1)
                    cat(labels[s], " (save full)");
                frame = r->on ? 1 : 2;               /* bright arrow = on, grey = off */
            }
        }
        mods_menu.b[s] = button(x, y, frame, ACT_ITEM + s, 0, LABEL_BASE + s);
    }
}

void core_page_init(void)
{
    const menu_t *const *orig = (const menu_t *const *)ADDR_menu_table_ptrs;
    const menu_t *opt = (const menu_t *)ADDR_options_menu;
    for (int i = 0; i < 5; i++)
        menus[i] = orig[i];
    /* Options: Settings, Save Game / Mods, Quit Game (the Urb Info layout) */
    options4 = *opt;
    options4.count = 4;
    options4.b[0] = opt->b[0];
    options4.b[1] = opt->b[1];
    options4.b[2] = button(61, 120, 1, 0, MENU_MODS, LABEL_MODS);
    options4.b[3] = opt->b[2];
    options4.b[3].pos = 198 | 120 << 8 | (opt->b[2].pos & 0xFF0000);
    menus[MENU_OPTIONS] = &options4;
    build_mods_page();
    menus[MENU_MODS] = &mods_menu;
    info_menu = options4;
    info_menu.count = 1;
    info_menu.b[0] = button(226, 120, 3, 0, MENU_MODS, LABEL_BACK);
    menus[MENU_INFO] = &info_menu;
    static const u32 lits[4] = { ADDR_menu_ptr_lit_1, ADDR_menu_ptr_lit_2, ADDR_menu_ptr_lit_3,
                                 ADDR_menu_ptr_lit_4 };
    for (int i = 0; i < 4; i++) {
        *(volatile u32 *)lits[i] = (u32)menus;
        DC_FlushRange((void *)lits[i], 4);
    }
    DC_WaitWriteBufferEmpty();
    core.page_ready = 1;
}

/* Button labels: the core's own text for ids from 0xF000. */
const char *core_label(int id)
{
    if (id == LABEL_MODS)
        return "Mods";
    if (id == LABEL_BACK)
        return "Back";
    if (id >= LABEL_LINE && id < LABEL_LINE + INFO_LINES)
        return lines[id - LABEL_LINE];
    if (id >= LABEL_BASE && id < LABEL_BASE + 8)
        return labels[id - LABEL_BASE];
    return text_get(id);
}

/* An info page line (mod_on_page's print): each line is a button label (the game draws and
   clears those itself); the buttons' icons are moved off-screen. */
static void page_print(mod_page_t *p, const char *s)
{
    int k = p->line++ - p->scroll;
    if (k < 0 || k >= INFO_LINES)
        return;
    int n = 0;
    while (n < 31 && s[n]) {
        lines[k][n] = s[n];
        n++;
    }
    lines[k][n] = 0;
    if (k >= n_lines)
        n_lines = k + 1;
}

static void build_info_page(int mod)
{
    mod_row_t *r = &mod_table->rows[mod];
    mod_page_t p = { page_print, 0, 0, 0, 0 };
    n_lines = 0;
    if (r->ev[EV_PAGE])
        ((void (*)(mod_page_t *))r->ev[EV_PAGE])(&p);
    info_menu.count = 1 + n_lines;
    for (int k = 0; k < n_lines; k++)
        info_menu.b[1 + k] = button(128, 8 + 16 * k, 0, ACT_LINE, 0, LABEL_LINE + k);
}

/* After the game drew a menu's text: titles and info lines for our menus, icon colours. */
void core_menu_text(void)
{
    menu_draw_text();
    menu_ui_t *m = menu_ui;
    int idx = m ? (int)m->menu : -1;
    if (idx == MENU_OPTIONS || idx == MENU_MODS || idx == MENU_INFO) {
        const menu_t *mn = menus[idx];
        for (int i = 0; i < mn->count; i++)         /* icon frame k uses palette row k */
            if (menu_sprites[i])
                set_palette_row(menu_sprites[i], (mn->b[i].pos >> 16) & 0xFF);
    }
    if (idx == MENU_MODS) {
        text_font(3, 0, -1);
        text_draw(1, 128, 8, "Mods", 1);          /* where the game draws menu titles */
        text_font(1, 0, -1);
    } else if (idx == MENU_INFO) {
        char nm[16];
        text_font(3, 0, -1);
        text_draw(1, 128, 8, mod_name(info_mod, nm), 1);
        text_font(1, 0, -1);
        for (int i = 1; i < info_menu.count; i++)   /* text lines: no icons */
            if (menu_sprites[i])
                sprite_set_pos(menu_sprites[i], 0, 208 << 16);
    }
}

/* A touch on the open menu: the Mods page's buttons are handled here. */
int core_menu_hit(void)
{
    int r = menu_hit_test();
    menu_ui_t *m = menu_ui;
    if (m && m->menu == MENU_INFO && r == ACT_LINE)
        return -1;                                   /* a text line: nothing to do */
    if (!m || m->menu != MENU_MODS || r < ACT_ITEM || r >= ACT_ITEM + 8)
        return r;
    int s = r - ACT_ITEM;
    core.page_taps++;
    if (items[s].kind == IT_NEXT) {
        mod_table_t *t = mod_table;
        int total = 0;
        for (int i = 0; i < t->count; i++)
            total += 1 + (t->rows[i].ev[EV_PAGE] != 0);
        page = (page + 1) * (PER_PAGE - 1) < total ? page + 1 : 0;
    } else if (items[s].kind == IT_INFO) {
        info_mod = items[s].mod;
        build_info_page(info_mod);
        m->menu = MENU_INFO;
        menu_redraw();
        ui_sound(4);
        return -1;
    } else {
        mod_row_t *row = &mod_table->rows[items[s].mod];
        if (row->flags & MODF_TOGGLE)
            core_set(items[s].mod, !row->on);
        else
            ui_sound(3);
    }
    build_mods_page();
    menu_redraw();
    return -1;
}
