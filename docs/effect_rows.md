# Motive effect rows

Per-tick need changes applied by `motive_apply_effect(needs, row, quality)` (0x0205DC20).
Table at 0x020CEED4, 8 x s32 (8.24 fixed point) per row; quality multipliers at 0x020EA998
(1.0, 1.0, 1.2, 1.4, 1.6, 2.0). Generated from the ROM; "used by" lists the call sites whose
row is a constant (some sites pass a computed row).

| row | per tick | used by |
|---|---|---|
| 0 | room +0.050 | 0206a42c (in 0206a3f4) |
| 1 | fun +0.100 | 0206a448 (in 0206a3f4) |
| 2 | fun +0.300 |  |
| 3 | room +0.020 | 0200add0 (in 0200a71c) |
| 4 | hunger -0.010, hygiene -0.050, energy -0.030, fun -0.050 | 0201298c (in 020128f0)<br>0206a908 (in 0206a6a0)<br>0206a9a8 (in 0206a6a0)<br>0206a9e4 (in 0206a6a0)<br>020794f4 (in 020793f4) |
| 5 | energy +0.050, social +0.100, comfort +0.050, fun +0.100 |  |
| 6 | energy -0.010, fun +0.050 | 0202c360 (in 0202c154)<br>0202eafc (in 0202e9cc)<br>0206ac64 (in 0206ab4c)<br>020ad150 (in 020ad058) |
| 7 | energy -0.010, social +0.100, fun +0.050 | 0206ac88 (in 0206ab4c) |
| 8 | energy +0.600, social +0.300, bladder -0.300 |  |
| 9 | energy +0.600, comfort +0.300, bladder -0.300 |  |
| 10 | energy +0.600, bladder -0.300, fun +0.300 |  |
| 11 | energy +0.500, bladder -0.300 | 02031690 (in 02031534) |
| 12 | hunger +0.200, bladder -0.080 |  |
| 13 | hunger +0.100, energy +0.050, bladder -0.080 | 020ada48 (in 020ad854) |
| 14 | hunger +0.100, energy +0.250, bladder -0.100 | 0208a348 (in 0208a1ec) |
| 15 | hunger +0.400 |  |
| 16 | hunger +0.400 |  |
| 17 | hunger +0.400 |  |
| 18 | hunger +0.200 |  |
| 19 | hunger +0.500 | 02015ce0 (in 02015b24)<br>02041f80 (in 02041ee0)<br>0204f840 (in 0204f5fc)<br>0209eebc (in 0209ec20) |
| 20 | hunger +0.300 | 020370cc (in 02036f00)<br>0204f898 (in 0204f5fc)<br>02077d00 (in 02077c44)<br>0207a744 (in 0207a5ac)<br>0208a5a8 (in 0208a4fc)<br>020ad7c8 (in 020ad5c4) |
| 21 | hygiene -0.020, energy -0.020, comfort +0.010, room +0.020 |  |
| 22 | fun +0.100, room +0.100 | 02033188 (in 020330e8) |
| 23 | energy +0.050, social +0.030, fun +0.100 | 0202b0b0 (in 0202afbc) |
| 24 | comfort +0.010 |  |
| 25 | hygiene -0.060, energy -0.030, comfort -0.010 |  |
| 26 | comfort +0.020, fun +0.018 | 0200dc00 (in 0200dad0) |
| 27 | fun +0.040 | 0200ecb8 (in 0200e9c4) |
| 28 | social +0.250, fun +0.400 |  |
| 29 | energy -0.020, fun +0.100 | 0206c208 (in 0206c1d0) |
| 30 | hygiene -0.050, fun +0.250 | 0202348c (in 02023398) |
| 31 | fun +0.400 |  |
| 32 | hygiene -0.010, fun +0.100 |  |
| 33 | hygiene -0.060, fun +0.250 | 02061e64 (in 02061d0c) |
| 34 | fun +0.400 |  |
| 35 | fun +0.100 | 020893bc (in 020892c0)<br>0208951c (in 020892c0) |
| 36 | hygiene -0.020, energy -0.010, comfort -0.010 |  |
| 37 | hygiene -0.010, energy -0.020, comfort -0.020, fun +0.080 |  |
| 38 | (none) |  |
| 39 | room +0.025 | 02083d64 (in 02083cb8) |
| 40 | room -0.005 |  |
| 41 | room -0.005 | 02083d90 (in 02083cb8) |
| 42 | fun +0.050 | 0200c34c (in 0200c294)<br>0200c378 (in 0200c294)<br>0200ee34 (in 0200edd8) |
| 43 | energy -0.015 |  |
| 44 | hygiene +0.200 | 02082f40 (in 02082da0) |
| 45 | comfort +0.150 |  |
| 46 | comfort +0.200 | 0206bd50 (in 0206bba4) |
| 47 | comfort +0.300 |  |
| 48 | comfort +0.300 |  |
| 49 | comfort +0.400 |  |
| 50 | hygiene -0.020, energy +0.200, social -0.010, comfort +0.200, bladder -0.020, fun -0.010 | 0206ba68 (in 0206b90c) |
| 51 | hygiene -0.030, energy +0.100, social -0.010, comfort +0.200, bladder -0.020, fun -0.010 | 0206b824 (in 0206b6d0) |
| 52 | hunger -0.800, hygiene -0.400, energy -0.640, social +2.400, comfort -0.960, bladder -1.200, fun -0.240 | 0208e308 (in 0208e2f4) |
| 53 | comfort -0.020, fun +0.010 |  |
| 54 | hunger -0.010, hygiene +0.030, energy -0.030, fun +0.100 | 02007c70 (in 02007a44)<br>02007d50 (in 02007a44) |
| 55 | hygiene -0.010, energy -0.010, comfort +0.010, room +0.010 |  |
| 56 | hunger +0.030, energy +0.030, bladder -0.100 | 02030ad4 (in 02030a44) |
| 57 | fun +0.500 | 0208891c (in 020887a8)<br>020ac948 (in 020ac82c) |
| 58 | hunger +0.150, hygiene +0.150, energy +0.150, social +0.150, comfort +0.150, bladder +0.150, fun +0.150, room +0.150 | 02082a34 (in 02082904) |
| 59 | bladder +0.400 | 020abea4 (in 020abd88) |
| 60 | fun +0.200 |  |
| 61 | fun +0.100 |  |
| 62 | hygiene +0.060 | 020870a4 (in 02086fb0) |
| 63 | fun +0.200 | 020a61c4 (in 020a60cc) |
| 64 | hygiene -0.700, social -0.100, comfort -0.500, bladder +2.000, fun -0.200 | 0200b024 (in 0200a71c) |
| 65 | energy +0.200, comfort -0.100 | 0200b0a4 (in 0200a71c) |
| 66 | hunger +2.000 |  |
| 67 | hygiene +2.000 |  |
| 68 | energy +2.000 |  |
| 69 | social +2.000 |  |

Call sites with a computed row: 020092e4 (in 02009214), 02009320 (in 02009214), 02035fe0 (in 02035e68), 0206b4c0 (in 0206b42c), 0206c048 (in 0206be3c), 0206c3a4 (in 0206c2b8)
