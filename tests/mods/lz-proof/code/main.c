#include "game.h"
/* Test only: load asset 00150 (game id 151) and decode its LZ77 chunk at +0x274 with the
   game's own decoder. tests/proofs.py writes that chunk (random bytes, so the LZ77 stream
   grows) and compares what the game decoded. */
struct { u32 magic, state, size; u8 out[64]; } lz_proof = { 0x50525A4C, 0, 0, {0} };   /* 'LZRP' */

void lz_proof_tick(void)
{
    if (lz_proof.state)
        return;
    lz_proof.state = 1;
    u8 *a = get_asset(151, 0, 0);
    if (!a) { lz_proof.state = 2; return; }
    lz_proof.size = decode_chunk(a + 0x274, lz_proof.out);
    lz_proof.state = 4;
}
