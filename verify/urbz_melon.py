#!/usr/bin/env python3
"""Run a build in melonDS (a second, stricter emulator than DeSmuME) on a virtual screen.

  python verify/urbz_melon.py boot <rom>                   boot for 20 s: does it reach the EA logo?
  python verify/urbz_melon.py play <rom> --script s.json [--sav file.sav]
                                                           input script (same steps as urbz_verify)
Linux only: needs melonDS built by verify/melonds_setup.sh (or MELONDS=/path/to/melonDS),
plus xvfb-run, openbox, xdotool and imagemagick. Screenshots go to verify/evidence/<time>-melon-*/.

Why: DeSmuME starts with zeroed memory and accepts some things real hardware doesn't. A Phase 5
build that read the game's fonts before they were loaded ran fine in DeSmuME but showed a white
screen in melonDS (and on Jonathan's handheld).

Script steps: ["wait", frames] ["press", KEY, hold?] ["touch", x, y, hold?] ["shot", name].
Frames are timed at 60 per second of real time. Keys: A B X Y L R START SELECT UP DOWN LEFT RIGHT.
melonDS takes the first D-pad press on the title menu (DeSmuME drops it): one DOWN = Load-an-Urb.
"""
import json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
MELON = os.environ.get('MELONDS') or os.path.join(HERE, 'melonds', 'melonDS')
CONFIG = os.path.expanduser('~/.config/melonDS/melonDS.toml')
# Qt key codes for the DS buttons, and the xdotool names that press them
QT_KEYS = {'A': 0x58, 'B': 0x5A, 'Select': 0x01000003, 'Start': 0x01000004, 'Right': 0x01000014,
           'Left': 0x01000012, 'Up': 0x01000013, 'Down': 0x01000015, 'R': 0x53, 'L': 0x41, 'X': 0x44, 'Y': 0x43}
XKEYS = {'A': 'x', 'B': 'z', 'START': 'Return', 'SELECT': 'BackSpace', 'UP': 'Up', 'DOWN': 'Down',
         'LEFT': 'Left', 'RIGHT': 'Right', 'R': 's', 'L': 'a', 'X': 'd', 'Y': 'c'}
MENU_BAR = 20                # melonDS's menu bar above the screens (measured at run time)


def available():
    return os.path.exists(MELON) and all(shutil.which(t) for t in ('xvfb-run', 'xdotool', 'import', 'openbox'))


def _config():
    """Map the DS buttons to keys in melonDS's config (its default leaves them unset)."""
    if not os.path.exists(CONFIG):            # first run: let melonDS write its default config
        _run_raw(None, [], quick=True)
    if not os.path.exists(CONFIG):
        return
    s = open(CONFIG).read()
    i = s.find('[Instance0.Keyboard]')
    if i < 0:
        return
    j = s.find('\n[', i + 1)
    j = len(s) if j < 0 else j
    body = s[i:j]
    for k, v in QT_KEYS.items():
        body = re.sub(r'(?m)^%s = -?\d+$' % k, '%s = %d' % (k, v), body)
    open(CONFIG, 'w').write(s[:i] + body + s[j:])


def _run_raw(rom, script, out=None, quick=False):
    """Inside a virtual X display: start a window manager and melonDS, run the script."""
    env = dict(os.environ, SDL_AUDIODRIVER='dummy', QT_QPA_PLATFORM='xcb')
    wm = subprocess.Popen(['openbox'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    log = open(os.path.join(out, 'melon.log'), 'w') if out else subprocess.DEVNULL
    p = subprocess.Popen([MELON] + ([rom] if rom else []), env=env, stdout=log, stderr=subprocess.STDOUT)
    x = lambda *a: subprocess.run(['xdotool'] + [str(v) for v in a], capture_output=True, text=True)
    wid = None
    for _ in range(30):                       # wait for the window (a slow start gave blank shots)
        time.sleep(0.5)
        w = x('search', '--name', 'melonDS').stdout.split()
        if w:
            wid = w[-1]
            break
    time.sleep(1.5)
    menu_bar = MENU_BAR
    if wid:
        # the menu bar's height varies with fonts: the screens are the window's bottom 384 rows
        g = re.search(r'Geometry: (\d+)x(\d+)', x('getwindowgeometry', wid).stdout)
        if g and 384 < int(g.group(2)) < 384 + 60:
            menu_bar = int(g.group(2)) - 384
        x('windowmove', wid, 0, 0)
        x('windowactivate', '--sync', wid)
        time.sleep(0.5)
    frames = lambda n: time.sleep(n / 60.0)
    shots = []
    for s in ([] if quick else script):
        if s[0] == 'wait':
            frames(s[1])
        elif s[0] == 'press':
            k = XKEYS[s[1].upper()]
            x('keydown', k)
            frames(s[2] if len(s) > 2 else 6)
            x('keyup', k)
            frames(10)
        elif s[0] == 'touch':
            # relative to melonDS's window, so the window manager's frame doesn't matter
            x('mousemove', '--window', wid, s[1], s[2] + menu_bar + 192)
            x('mousedown', 1)
            frames(s[3] if len(s) > 3 else 6)
            x('mouseup', 1)
            frames(10)
        elif s[0] == 'shot':
            f = os.path.join(out, 'melon_%s.png' % s[1])
            subprocess.run(['import', '-window', wid or 'root', '-crop', '256x384+0+%d' % menu_bar, '+repage', f])
            shots.append((s[1], f))
        else:
            raise ValueError('unknown step %r' % (s,))
    p.terminate()
    time.sleep(1)
    p.kill()
    wm.kill()
    return shots


def run(rom, script, sav=None, out=None):
    """Play an input script in melonDS -> [(shot name, png path)]. `sav` = a raw .sav to start with."""
    if not available():
        raise RuntimeError('melonDS is not set up: run verify/melonds_setup.sh (Linux)')
    _config()
    out = out or os.path.join(HERE, 'evidence', time.strftime('%Y%m%d-%H%M%S') + '-melon')
    os.makedirs(out, exist_ok=True)
    work = os.path.join(out, 'game.nds')             # melonDS keeps the save next to the ROM
    shutil.copy(rom, work)
    save = os.path.join(out, 'game.sav')
    if sav:
        shutil.copy(sav, save)
    elif os.path.exists(save):
        os.remove(save)
    job = json.dumps({'rom': work, 'script': script, 'out': out})
    p = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 800x900x24', sys.executable,
                        os.path.abspath(__file__), '_child', job], capture_output=True, text=True,
                       timeout=60 + sum(s[1] for s in script if s[0] == 'wait') // 30)
    for line in p.stdout.splitlines():
        if line.startswith('RESULT '):
            return json.loads(line[7:])
    raise RuntimeError('melonDS run failed:\n' + p.stdout[-1500:] + p.stderr[-1500:])


def screen_stats(png, bottom=False):
    """(mean brightness, spread) of one DS screen in a shot: white or black screens have no spread."""
    from PIL import Image
    im = Image.open(png).convert('L').crop((0, 192 if bottom else 0, 256, 384 if bottom else 192))
    px = list(im.tobytes())
    mean = sum(px) / len(px)
    return mean, (sum((v - mean) ** 2 for v in px) / len(px)) ** 0.5


BOOT_SCRIPT = [['wait', 300], ['shot', 'boot-5s'], ['wait', 900], ['shot', 'boot-20s']]


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    if argv[0] == '_child':
        job = json.loads(argv[1])
        print('RESULT ' + json.dumps(_run_raw(job['rom'], job['script'], job['out'])), flush=True)
        os._exit(0)
    rom = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(HERE), 'build', 'Urbz Mod.nds')
    if argv[0] == 'boot':
        shots = dict(run(rom, BOOT_SCRIPT))
        mean, spread = screen_stats(shots['boot-20s'])
        ok = spread > 10
        print('melonDS boot: %s (top screen after 20 s: brightness %.0f, detail %.0f)  %s'
              % ('OK' if ok else 'FAILED (blank screen)', mean, spread, os.path.dirname(shots['boot-20s'])))
        sys.exit(0 if ok else 1)
    if argv[0] == 'play':
        a = argv[2:]
        opt = lambda n: a[a.index(n) + 1] if n in a else None
        if not opt('--script'):
            sys.exit('usage: urbz_melon.py play <rom> --script s.json [--sav file.sav]')
        for name, f in run(rom, json.load(open(opt('--script'))), sav=opt('--sav')):
            print('%-16s %s' % (name, f))
        return
    sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
