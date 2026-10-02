/* Tiny freestanding runtime linked into every code mod (unused parts are dropped). */
void *memcpy(void *d, const void *s, unsigned n)
{
    unsigned char *a = d; const unsigned char *b = s;
    while (n--) *a++ = *b++;
    return d;
}

void *memset(void *d, int c, unsigned n)
{
    unsigned char *a = d;
    while (n--) *a++ = (unsigned char)c;
    return d;
}

/* ARMv5 has no divide instruction; the compiler calls these. */
unsigned __aeabi_uidiv(unsigned n, unsigned d)
{
    unsigned q = 0, bit = 1;
    if (!d) return 0;
    while ((int)d > 0 && d < n) { d <<= 1; bit <<= 1; }
    while (bit) { if (n >= d) { n -= d; q |= bit; } d >>= 1; bit >>= 1; }
    return q;
}

int __aeabi_idiv(int n, int d)
{
    int neg = (n < 0) ^ (d < 0);
    unsigned q = __aeabi_uidiv(n < 0 ? -n : n, d < 0 ? -d : d);
    return neg ? -(int)q : (int)q;
}

__attribute__((naked)) void __aeabi_uidivmod(void)
{
    __asm__("push {r0, r1, lr}\n bl __aeabi_uidiv\n pop {r1, r2, lr}\n"
            "mul r3, r0, r2\n sub r1, r1, r3\n bx lr");
}

__attribute__((naked)) void __aeabi_idivmod(void)
{
    __asm__("push {r0, r1, lr}\n bl __aeabi_idiv\n pop {r1, r2, lr}\n"
            "mul r3, r0, r2\n sub r1, r1, r3\n bx lr");
}

/* ARM EABI names the compiler uses for struct copies and clears. */
void __aeabi_memcpy(void *d, const void *s, unsigned n) { memcpy(d, s, n); }
void __aeabi_memcpy4(void *d, const void *s, unsigned n) { memcpy(d, s, n); }
void __aeabi_memcpy8(void *d, const void *s, unsigned n) { memcpy(d, s, n); }
void __aeabi_memmove(void *d, const void *s, unsigned n)
{
    unsigned char *a = d; const unsigned char *b = s;
    if (a < b) while (n--) *a++ = *b++;
    else { a += n; b += n; while (n--) *--a = *--b; }
}
void __aeabi_memset(void *d, unsigned n, int c) { memset(d, c, n); }
void __aeabi_memset4(void *d, unsigned n, int c) { memset(d, c, n); }
void __aeabi_memclr(void *d, unsigned n) { memset(d, 0, n); }
void __aeabi_memclr4(void *d, unsigned n) { memset(d, 0, n); }
