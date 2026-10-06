"""Walk the player to a point with real D-pad presses (savestate steps), reading where they are from
code/pets-kit's counters. Usage: walkto.py ROM START.dst X Y OUT.dst"""
import json, os, struct, sys, tempfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, 'tests'))
import proofs as P


def pos(rom, state):
    out = P.run(P.VERIFY + ['ram', rom, '--state', state, '--frames', '31', '--read', P.HEAP_SCAN])
    st = P._pets_stats(bytes.fromhex([l for l in out.splitlines() if ' = ' in l][0].split(' = ')[1].strip()))
    s16 = lambda v: v - 0x10000 if v & 0x8000 else v
    return s16(st['px'] & 0xFFFF), s16(st['py'] & 0xFFFF)


def step(rom, state, keys, frames, out):
    p = os.path.join(tempfile.mkdtemp(), 's.json')
    json.dump([['press', k, frames] for k in keys] + [['wait', 5]], open(p, 'w'))
    P.run(P.VERIFY + ['play', rom, '--state', state, '--script', p, '--save', out])


def walk(rom, state, x, y, out, tries=14):
    cur = state
    for n in range(tries):
        px, py = pos(rom, cur)
        dx, dy = x - px, y - py
        print('at', px, py, 'to go', dx, dy)
        if abs(dx) < 10 and abs(dy) < 10:
            break
        keys = (['RIGHT'] if dx > 8 else ['LEFT'] if dx < -8 else []) + (['DOWN'] if dy > 8 else ['UP'] if dy < -8 else [])
        frames = max(6, min(90, int(max(abs(dx), abs(dy)) / 1.4)))
        nxt = os.path.join(tempfile.mkdtemp(), 'w.dst')
        step(rom, cur, keys[:1] if n % 2 == 0 or len(keys) == 1 else keys[1:], frames, nxt)
        cur = nxt
    import shutil
    shutil.copy(cur, out)
    return pos(rom, out)


if __name__ == '__main__':
    print(walk(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]))
