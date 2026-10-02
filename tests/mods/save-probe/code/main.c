#include "mod.h"

/* Counts game minutes (on_minute) and keeps the count in the save (on_save / on_load).
   Tests read this struct (found by its magic 'SVPR'). */
struct {
    u32 magic, minutes, saves, loads, fresh, last_loaded, boots, enables, disables, ticks;
} probe = { 0x52505653 };

void mod_on_boot(void) { probe.boots++; }
void mod_on_tick(void) { probe.ticks++; }
void mod_on_minute(int n) { probe.minutes += n; }
void mod_on_enable(void) { probe.enables++; }
void mod_on_disable(void) { probe.disables++; }

int mod_on_save(u8 *buf, int max)
{
    if (max < 8)
        return -1;
    memcpy(buf, "PRB1", 4);
    memcpy(buf + 4, &probe.minutes, 4);
    probe.saves++;
    return 8;
}

void mod_on_load(const u8 *buf, int len)
{
    if (buf && len == 8 && !memcmp(buf, "PRB1", 4)) {
        memcpy(&probe.minutes, buf + 4, 4);
        probe.last_loaded = probe.minutes;
        probe.loads++;
    } else {
        probe.minutes = 0;
        probe.fresh++;
    }
}
