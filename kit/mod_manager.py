#!/usr/bin/env python3
"""Mod manager: pick mods, build the ROM and play it, in a window (or from the command line).

  python urbz.py manager                 open the window (Windows: manager.bat)
  python urbz.py manager list            same list as the window, as text
  python urbz.py manager install mod.zip install a mod from a zip into mods/
  python urbz.py manager check           check the enabled mods (conflicts, save space)

The window shows every mod in mods/ with a tick box. Ticked mods are built into the ROM in
the order shown (later mods win where two change the same thing); Up/Down change the order.
Build runs urbz_build.py and shows its output; Play opens the built ROM in your emulator.
"Add mod..." installs a mod zip. "Settings..." picks your Urbz ROM (and unpacks it), your
emulator and, optionally, your other Sims games (it writes emulator.txt and sources.json for
you; the first time, it opens by itself). "Tune..." changes a mod's prices, shops, names and
places without editing its files (kit/urbz_tuning.py).

It uses the same files and rules as urbz_mod.py (mods.json lists the enabled mods), so the
window and the command line always agree. Mods that can be switched in the game show
"in-game switch": once built in, they can be turned on and off on the Options > Mods page.
"""
import json, os, shutil, subprocess, sys, zipfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the repo (this file is in kit/)
sys.path.insert(0, os.path.join(KIT, 'kit'))
MODS = os.path.join(KIT, 'mods')
OUT_ROM = os.path.join(KIT, 'build', 'Urbz DX.nds')
EMULATOR_TXT = os.path.join(KIT, 'emulator.txt')

PROJECT = os.path.join(KIT, 'project')
SOURCES_JSON = os.path.join(KIT, 'sources.json')
URBZ_SHA1 = '3c01cc5cf3491b5d0ab626ccfb5bcad370662f2f'       # The Urbz: Sims in the City (USA)
OTHER_GAMES = [('aptpets', 'The Sims 2: Apartment Pets'), ('sims3', 'The Sims 3'),
               ('castaway', 'The Sims 2: Castaway'), ('sims2', 'The Sims 2')]
DEFAULT_MODS = ['npc-life', 'pets', 'more-furniture', 'bug-fixes']    # ticked on a fresh kit

# Never installed from a zip: game files and emulator files.
BLOCKED_EXT = ('.nds', '.sav', '.dsv', '.dst', '.dsm', '.srm', '.zip', '.7z', '.exe', '.dll', '.bat', '.cmd')
BLOCKED_DIRS = ('project/', 'build/', 'verify/', '__MACOSX/')


class ManagerError(Exception):
    pass


# ---------------------------------------------------------------- model (no window)

def load_cfg():
    import urbz_mod
    return urbz_mod.load_cfg()


def save_enabled(names):
    """Write mods.json: these mods, in this order."""
    import urbz_mod
    cfg = load_cfg()
    cfg['enabled'] = list(names)
    urbz_mod.save_cfg(cfg)


def list_mods():
    """Every mod in mods/: [{name, info, enabled}], enabled ones first in build order."""
    from urbz_code import mod_info
    enabled = [n for n in load_cfg().get('enabled', []) if os.path.isdir(os.path.join(MODS, n))]
    names = sorted(n for n in os.listdir(MODS) if os.path.isdir(os.path.join(MODS, n))) \
        if os.path.isdir(MODS) else []
    order = enabled + [n for n in names if n not in enabled]
    out = []
    for n in order:
        try:
            info = mod_info(os.path.join(MODS, n))
            err = None
        except Exception as e:                          # a broken mod.json: show it, don't crash
            info, err = {'version': '', 'author': '', 'description': '', 'toggle': False,
                         'default': True, 'conflicts': [], 'save_bytes': 0}, str(e)
        out.append({'name': n, 'info': info, 'enabled': n in enabled, 'error': err})
    return out


def check(names):
    """Problems with this set of mods -> (errors, warnings)."""
    from urbz_code import check_mod_set, CodeError
    try:
        return [], check_mod_set([os.path.join(MODS, n) for n in names])
    except CodeError as e:
        return [str(e)], []


def describe(m):
    """Plain-language details for one mod."""
    info = m['info']
    lines = [m['name'] + ('  v' + info['version'] if info['version'] else '')]
    if info['author']:
        lines.append('by ' + info['author'])
    if info['description']:
        lines.append(info['description'])
    if info['toggle']:
        lines.append('Can be switched on/off in the game (Options > Mods); starts %s.'
                     % ('on' if info['default'] else 'off'))
    if info['save_bytes']:
        lines.append('Keeps up to %d bytes in each save.' % info['save_bytes'])
    if info['conflicts']:
        lines.append("Can't be used with: " + ', '.join(info['conflicts']))
    if m.get('error'):
        lines.append('Problem: ' + m['error'])
    return '\n'.join(lines)


def _zip_root(names):
    """The folder inside the zip that holds mod.json ('' = the zip's top level)."""
    roots = sorted({n[:-len('mod.json')] for n in names if n == 'mod.json' or n.endswith('/mod.json')},
                   key=len)
    if not roots:
        raise ManagerError('this zip has no mod.json, so it is not a mod')
    return roots[0]


def install_zip(path, replace=False):
    """Install a mod zip into mods/<name>/ -> name. Refuses game files and odd paths."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ManagerError('not a zip file: %s' % e)
    with z:
        names = [i.filename.replace('\\', '/') for i in z.infolist() if not i.is_dir()]
        root = _zip_root(names)
        for n in names:
            low = n.lower()
            if n.startswith('/') or '..' in n.split('/') or ':' in n:
                raise ManagerError('the zip has an unsafe path: %s' % n)
            if low.endswith(BLOCKED_EXT) or any(low.startswith(d) or ('/' + d) in low for d in BLOCKED_DIRS):
                raise ManagerError('the zip contains %s; mods must not include game, save or '
                                   'program files' % n)
        try:
            info = json.loads(z.read(root + 'mod.json').decode('utf-8-sig'))
        except ValueError as e:
            raise ManagerError('mod.json in the zip is not valid JSON: %s' % e)
        name = root.strip('/').split('/')[-1] if root else \
            info.get('name') or os.path.splitext(os.path.basename(path))[0]
        if not name or any(c in name for c in '/\\:*?"<>|') or name.startswith('.'):
            raise ManagerError('bad mod name "%s"' % name)
        dest = os.path.join(MODS, name)
        if os.path.exists(dest):
            if not replace:
                raise ManagerError('a mod named "%s" is already installed' % name)
            shutil.rmtree(dest)
        os.makedirs(dest)
        for n in names:
            if not n.startswith(root):
                continue
            rel = n[len(root):]
            out = os.path.join(dest, *rel.split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, 'wb') as dst:
                shutil.copyfileobj(src, dst)
    return name


def build_command():
    return [sys.executable, os.path.join(KIT, 'kit', 'urbz_build.py')]


# ---------------------------------------------------------------- settings (the Settings window)

def project_ready():
    return os.path.exists(os.path.join(PROJECT, 'manifest.json'))


def rom_check(path):
    """(sha1, is it the USA ROM the kit is made for) of a .nds or a .zip holding one."""
    import hashlib
    h = hashlib.sha1()
    if path.lower().endswith('.zip'):
        with zipfile.ZipFile(path) as z:
            nds = [n for n in z.namelist() if n.lower().endswith('.nds')]
            if not nds:
                raise ManagerError('there is no .nds file in that zip')
            with z.open(nds[0]) as f:
                for b in iter(lambda: f.read(1 << 20), b''):
                    h.update(b)
    else:
        with open(path, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
    return h.hexdigest(), h.hexdigest() == URBZ_SHA1


def extract_command(rom):
    """The command that unpacks your ROM into project/ (a zipped ROM is unpacked into build/ first)."""
    if rom.lower().endswith('.zip'):
        with zipfile.ZipFile(rom) as z:
            nds = [n for n in z.namelist() if n.lower().endswith('.nds')][0]
            os.makedirs(os.path.join(KIT, 'build'), exist_ok=True)
            out = os.path.join(KIT, 'build', 'urbz-rom.nds')
            with z.open(nds) as f, open(out, 'wb') as o:
                shutil.copyfileobj(f, o)
        rom = out
    return [sys.executable, os.path.join(KIT, 'kit', 'urbz_extract.py'), rom, PROJECT]


def set_emulator(path):
    if path and not os.path.exists(path):
        raise ManagerError('"%s" does not exist' % path)
    if path:
        open(EMULATOR_TXT, 'w', encoding='utf-8').write(path + '\n')
    elif os.path.exists(EMULATOR_TXT):
        os.remove(EMULATOR_TXT)


def other_games():
    """{key: path} from sources.json (your other Sims games, optional)."""
    try:
        return json.load(open(SOURCES_JSON, encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def set_other_game(key, path):
    """Remember (path) or forget (None) one of your other Sims games."""
    games = other_games()
    if path:
        if not os.path.exists(path):
            raise ManagerError('"%s" does not exist' % path)
        games[key] = path.replace('\\', '/')
    else:
        games.pop(key, None)
    if games:
        json.dump(games, open(SOURCES_JSON, 'w', encoding='utf-8'), indent=1)
    elif os.path.exists(SOURCES_JSON):
        os.remove(SOURCES_JSON)


def tunable_files(name):
    """The files of a mod the Tune window can change."""
    import urbz_tuning
    return [f for f in urbz_tuning.FILES if os.path.exists(os.path.join(MODS, name, f))]


def emulator_path():
    if not os.path.exists(EMULATOR_TXT):
        return None
    p = open(EMULATOR_TXT, encoding='utf-8-sig').readline().strip().strip('"')
    return p or None


def play():
    emu = emulator_path()
    if not emu:
        raise ManagerError('no emulator set yet: pick it in Settings')
    if not os.path.exists(emu):
        raise ManagerError('emulator.txt points to "%s", which does not exist' % emu)
    if not os.path.exists(OUT_ROM):
        raise ManagerError('build the ROM first')
    subprocess.Popen([emu, OUT_ROM], cwd=os.path.dirname(emu))



# ---------------------------------------------------------------- Settings and Tune windows

def settings_window(root, say, on_change, first_run=False):
    """Your Urbz ROM (unpacked into project/), your emulator, your other Sims games (optional)."""
    import threading
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    win = tk.Toplevel(root)
    win.title('Settings')
    win.transient(root)
    f = ttk.Frame(win, padding=12)
    f.pack(fill='both', expand=True)
    f.columnconfigure(1, weight=1)
    row = [0]

    def heading(text, note=None):
        ttk.Label(f, text=text, font=('TkDefaultFont', 10, 'bold')).grid(row=row[0], column=0, columnspan=3,
                                                                         sticky='w', pady=(10, 0))
        row[0] += 1
        if note:
            ttk.Label(f, text=note, foreground='#555', wraplength=520, justify='left').grid(
                row=row[0], column=0, columnspan=3, sticky='w')
            row[0] += 1

    if first_run:
        ttk.Label(f, text='Welcome! Two things to set up, once: your Urbz ROM and your emulator.',
                  font=('TkDefaultFont', 11, 'bold')).grid(row=row[0], column=0, columnspan=3, sticky='w')
        row[0] += 1

    heading('1. Your Urbz ROM', 'The Urbz: Sims in the City (USA), a .nds or a .zip holding one. The kit unpacks '
            'it into the project folder (about a minute, once). It is never changed or shared.')
    rom_state = ttk.Label(f, text='')
    rom_state.grid(row=row[0], column=0, columnspan=2, sticky='w')
    rom_btn = ttk.Button(f, text='Choose ROM...')
    rom_btn.grid(row=row[0], column=2, sticky='e')
    row[0] += 1
    bar = ttk.Progressbar(f, mode='indeterminate')

    def show_rom():
        rom_state.config(text='Ready: your ROM is unpacked.' if project_ready() else 'Not set up yet.',
                         foreground='#1a7f37' if project_ready() else '#b42318')

    def choose_rom():
        p = filedialog.askopenfilename(parent=win, title='Your Urbz ROM',
                                       filetypes=[('DS ROM', '*.nds *.zip'), ('All files', '*.*')])
        if not p:
            return
        try:
            sha, usa = rom_check(p)
        except (ManagerError, OSError, zipfile.BadZipFile) as e:
            messagebox.showerror('Not a ROM', str(e), parent=win)
            return
        if not usa and not messagebox.askyesno(
                'Different ROM', 'This is not the USA ROM the kit is made for (its SHA1 is %s, the kit expects '
                '%s). Mods may not work with it. Use it anyway?' % (sha, URBZ_SHA1), parent=win):
            return
        if project_ready() and not messagebox.askyesno(
                'Unpack again?', 'Your ROM is unpacked already. Unpack this one instead? (Your mods, saves and '
                'settings are kept.)', parent=win):
            return
        rom_btn.state(['disabled'])
        bar.grid(row=row_bar, column=0, columnspan=3, sticky='ew', pady=4)
        bar.start(12)
        rom_state.config(text='Unpacking... (about a minute)', foreground='')
        say('--- unpacking %s' % p)

        def work():
            ok = False
            try:
                if os.path.isdir(PROJECT):
                    shutil.rmtree(PROJECT)
                pr = subprocess.Popen(extract_command(p), cwd=KIT, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True)
                for line in pr.stdout:
                    root.after(0, say, line.rstrip())
                ok = pr.wait() == 0
            except Exception as e:                     # shown, never a crash
                root.after(0, say, 'error: %s' % e)
            root.after(0, unpacked, ok)
        threading.Thread(target=work, daemon=True).start()

    def unpacked(ok):
        bar.stop()
        bar.grid_remove()
        rom_btn.state(['!disabled'])
        say('--- unpacking %s' % ('finished' if ok else 'FAILED'))
        show_rom()
        on_change()
        if not ok:
            messagebox.showerror('Unpacking failed', 'See the log in the main window.', parent=win)
    rom_btn.config(command=choose_rom)
    row_bar = row[0]
    row[0] += 1

    heading('2. Your emulator', 'The program that plays the game: melonDS is what the mods are tested on '
            '(melonds.kuribo64.net). Pick its .exe.')
    emu = tk.StringVar(value=emulator_path() or '')
    ttk.Entry(f, textvariable=emu, state='readonly').grid(row=row[0], column=0, columnspan=2, sticky='ew')

    def choose_emu():
        p = filedialog.askopenfilename(parent=win, title='Your emulator',
                                       filetypes=[('Program', '*.exe'), ('All files', '*.*')])
        if p:
            set_emulator(p)
            emu.set(p)
            say('emulator: %s' % p)
    ttk.Button(f, text='Choose...', command=choose_emu).grid(row=row[0], column=2, sticky='e', padx=(6, 0))
    row[0] += 1

    heading('3. Other Sims games (optional)', 'Not needed. If you own these DS games, the pets and furniture '
            'can be drawn from their models instead of the kit\'s own. Takes effect at the next build.')
    games = other_games()
    for key, title in OTHER_GAMES:
        var = tk.StringVar(value=games.get(key, ''))
        ttk.Label(f, text=title).grid(row=row[0], column=0, sticky='w')
        ttk.Entry(f, textvariable=var, state='readonly', width=46).grid(row=row[0], column=1, sticky='ew', padx=6)
        btns = ttk.Frame(f)
        btns.grid(row=row[0], column=2, sticky='e')

        def pick(key=key, var=var, title=title):
            p = filedialog.askopenfilename(parent=win, title=title, filetypes=[('DS ROM', '*.nds *.zip')])
            if p:
                set_other_game(key, p)
                var.set(p)

        def clear(key=key, var=var):
            set_other_game(key, None)
            var.set('')
        ttk.Button(btns, text='Choose...', command=pick).pack(side='left')
        ttk.Button(btns, text='Clear', command=clear).pack(side='left', padx=(4, 0))
        row[0] += 1

    ttk.Button(f, text='Done', command=win.destroy).grid(row=row[0], column=2, sticky='e', pady=(14, 0))
    show_rom()
    return win


def tune_window(root, name, say):
    """Change a mod's names, prices, descriptions, quality and shops, and NPC Life's places, without editing
    its files: kept in tuning/<mod>.json (urbz_tuning.py) and used at the next build."""
    import tkinter as tk
    from tkinter import ttk, messagebox
    import urbz_tuning as T
    md = os.path.join(MODS, name)
    win = tk.Toplevel(root)
    win.title('Tune %s' % name)
    win.geometry('960x540')
    win.transient(root)
    ttk.Label(win, text='Changes are used the next time you build. They are kept apart from the mod '
              '(tuning\\%s.json), so updating it never loses them. * = changed by you.' % name,
              wraplength=820, padding=(10, 8, 10, 0)).pack(fill='x')
    nb = ttk.Notebook(win)
    nb.pack(fill='both', expand=True, padx=10, pady=8)
    choices = ['not sold'] + list(T.RARITY)

    def items_tab(fname, title):
        own = json.load(open(os.path.join(md, fname), encoding='utf-8'))
        own_items = dict(T.entries(own, fname))
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text=title)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        tree = ttk.Treeview(tab, columns=('price', 'shops', 'changed'), show='tree headings', height=16)
        tree.heading('#0', text='Name')
        tree.heading('price', text='Price')
        tree.heading('shops', text='Sold at')
        tree.heading('changed', text='')
        tree.column('#0', width=150, stretch=False)
        tree.column('price', width=50, anchor='e', stretch=False)
        tree.column('shops', width=170)
        tree.column('changed', width=20, anchor='center', stretch=False)
        tree.grid(row=0, column=0, sticky='nsew')
        tab.columnconfigure(0, weight=1, minsize=400)
        form = ttk.Frame(tab, padding=(12, 0, 0, 0))
        form.grid(row=0, column=1, sticky='nsew')
        v_name, v_price, v_quality = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(form, text='Name').grid(row=0, column=0, sticky='w')
        ttk.Entry(form, textvariable=v_name, width=32).grid(row=0, column=1, sticky='w')
        ttk.Label(form, text='Price ($)').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Spinbox(form, from_=1, to=99999, textvariable=v_price, width=8).grid(row=1, column=1, sticky='w')
        has_quality = fname == 'objects.json'
        if has_quality:
            ttk.Label(form, text='Quality').grid(row=2, column=0, sticky='w')
            ttk.Combobox(form, textvariable=v_quality, values=['1', '2', '3', '4', '5'], width=4,
                         state='readonly').grid(row=2, column=1, sticky='w')
            ttk.Label(form, text='(1-5: how fast it fills needs)', foreground='#555').grid(row=2, column=1,
                                                                                     sticky='w', padx=(50, 0))
        ttk.Label(form, text='Description').grid(row=3, column=0, sticky='nw', pady=4)
        desc = tk.Text(form, width=36, height=3, wrap='word')
        desc.grid(row=3, column=1, sticky='w', pady=4)
        ttk.Label(form, text='Sold at', font=('TkDefaultFont', 9, 'bold')).grid(row=4, column=0, sticky='w',
                                                                                pady=(8, 0))
        shop_vars = {}
        r = 5
        for lst, shop in sorted(T.SHOPS.items()):
            ttk.Label(form, text=shop).grid(row=r, column=0, columnspan=1, sticky='w')
            v = tk.StringVar()
            ttk.Combobox(form, textvariable=v, values=choices, width=10, state='readonly').grid(row=r, column=1,
                                                                                               sticky='w')
            shop_vars[str(lst)] = v
            r += 1
        ttk.Label(form, text='common / uncommon / rare: how often it is on the shelf.', foreground='#555'
                  ).grid(row=r, column=0, columnspan=2, sticky='w', pady=(2, 8))
        btns = ttk.Frame(form)
        btns.grid(row=r + 1, column=0, columnspan=2, sticky='w')
        cur = {'key': None}

        def tuned(key):
            return T.apply(name, fname, own)

        def current(key):
            return dict(T.entries(T.apply(name, fname, own), fname))[key]

        def fill():
            tree.delete(*tree.get_children())
            changed = T.overrides(name).get(fname, {})
            for key, e in T.entries(T.apply(name, fname, own), fname):
                shops = ', '.join('%s (%s)' % (T.SHOPS.get(int(k), 'list %s' % k).split(' (')[0], v)
                                  for k, v in sorted(e.get('sell', {}).items(), key=lambda kv: int(kv[0])))
                tree.insert('', 'end', iid=key, text=e.get('name', key), values=(e.get('price', ''), shops,
                                                                              '*' if changed.get(key) else ''))
            if cur['key'] and tree.exists(cur['key']):
                tree.selection_set(cur['key'])

        def show(_=None):
            sel = tree.selection()
            if not sel:
                return
            key = cur['key'] = sel[0]
            e = current(key)
            v_name.set(e.get('name', ''))
            v_price.set(str(e.get('price', '')))
            v_quality.set(str(e.get('quality', '')) if e.get('quality') else '')
            desc.delete('1.0', 'end')
            desc.insert('1.0', e.get('description', ''))
            for lst, v in shop_vars.items():
                v.set(e.get('sell', {}).get(lst, 'not sold'))

        def save():
            key = cur['key']
            if key is None:
                return
            o = own_items[key]
            sell = {k: v for k, v in current(key).get('sell', {}).items() if k not in shop_vars}  # other lists
            sell.update({k: v.get() for k, v in shop_vars.items() if v.get() in T.RARITY})
            values = [('name', v_name.get()), ('price', v_price.get()), ('description', desc.get('1.0', 'end')),
                      ('sell', sell)]
            if has_quality and v_quality.get():
                values.append(('quality', v_quality.get()))
            try:
                for field, value in values:
                    T.check(fname, field, value)
                for field, value in values:
                    T.set_value(name, fname, key, field, value, o.get(field))
            except T.TuningError as e:
                messagebox.showerror('Not saved', str(e), parent=win)
                return
            say('tuned %s: %s' % (name, v_name.get()))
            fill()

        def reset_one():
            if cur['key'] is not None:
                T.reset(name, fname, cur['key'])
                fill()
                show()
        ttk.Button(btns, text='Save', command=save).pack(side='left')
        ttk.Button(btns, text="Back to the mod's own", command=reset_one).pack(side='left', padx=6)
        tree.bind('<<TreeviewSelect>>', show)
        fill()
        kids = tree.get_children()
        if kids:
            tree.selection_set(kids[0])
        return fill

    def places_tab():
        own = json.load(open(os.path.join(md, 'places.json'), encoding='utf-8'))
        own_items = dict(T.entries(own, 'places.json'))
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text='Places')
        ttk.Label(tab, text='What each place offers the townspeople in their free time. Click a box to change '
                  'it.', padding=(0, 0, 0, 6)).pack(fill='x')
        cols = list(T.KINDS) + ['changed']
        tree = ttk.Treeview(tab, columns=cols, show='tree headings', height=16)
        tree.heading('#0', text='Place')
        tree.column('#0', width=260)
        for k in T.KINDS:
            tree.heading(k, text=k)
            tree.column(k, width=70, anchor='center')
        tree.heading('changed', text='')
        tree.column('changed', width=20, anchor='center')
        sb = ttk.Scrollbar(tab, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='left', fill='y')

        def fill():
            changed = T.overrides(name).get('places.json', {})
            sel = tree.selection()
            tree.delete(*tree.get_children())
            for key, p in sorted(T.entries(T.apply(name, 'places.json', own), 'places.json'), key=lambda kv: int(kv[0])):
                tree.insert('', 'end', iid=key, text=p.get('name', key),
                            values=['[x]' if k in p['kinds'] else '[ ]' for k in T.KINDS] +
                            ['*' if changed.get(key) else ''])
            if sel and tree.exists(sel[0]):
                tree.selection_set(sel[0])

        def click(ev):
            key, col = tree.identify_row(ev.y), tree.identify_column(ev.x)
            if not key or col in ('#0', '') or int(col[1:]) > len(T.KINDS):
                return
            kind = T.KINDS[int(col[1:]) - 1]
            kinds = list(dict(T.entries(T.apply(name, 'places.json', own), 'places.json'))[key]['kinds'])
            kinds = [k for k in kinds if k != kind] if kind in kinds else kinds + [kind]
            if not kinds:
                messagebox.showinfo('Places', 'A place offers at least one thing.', parent=win)
                return
            T.set_value(name, 'places.json', key, 'kinds', kinds, own_items[key]['kinds'])
            fill()
        tree.bind('<Button-1>', click)
        fill()
        return fill

    fills = []
    files = tunable_files(name)
    if 'pets.json' in files:
        fills.append(items_tab('pets.json', 'Pets'))
    if 'objects.json' in files:
        fills.append(items_tab('objects.json', 'Things to buy'))
    if 'places.json' in files:
        fills.append(places_tab())
    bottom = ttk.Frame(win, padding=(10, 0, 10, 10))
    bottom.pack(fill='x')

    def reset_all():
        if messagebox.askyesno('Reset', 'Forget everything you changed in %s?' % name, parent=win):
            T.reset(name)
            for f_ in fills:
                f_()
            say('tuning of %s reset' % name)
    ttk.Button(bottom, text='Reset everything', command=reset_all).pack(side='left')
    ttk.Button(bottom, text='Close', command=win.destroy).pack(side='right')
    return win


# ---------------------------------------------------------------- window

def run_window():
    import threading
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title('Urbz DX mod manager')
    root.geometry('960x580')
    root.minsize(640, 420)
    state = {'mods': [], 'busy': False}

    top = ttk.Frame(root, padding=8)
    top.pack(fill='both', expand=True)
    top.columnconfigure(0, weight=3)
    top.columnconfigure(1, weight=2)
    top.rowconfigure(1, weight=1)
    ttk.Label(top, text='Tick the mods to build into the game (top = built first; later mods win):'
              ).grid(row=0, column=0, columnspan=2, sticky='w')

    tree = ttk.Treeview(top, columns=('on', 'version', 'switch'), show='tree headings', height=14)
    tree.heading('#0', text='Mod')
    tree.heading('on', text='Use')
    tree.heading('version', text='Version')
    tree.heading('switch', text='In-game switch')
    tree.column('#0', width=200)
    tree.column('on', width=50, anchor='center')
    tree.column('version', width=70, anchor='center')
    tree.column('switch', width=110, anchor='center')
    tree.grid(row=1, column=0, sticky='nsew')

    details = tk.Text(top, wrap='word', height=10, width=36, relief='flat', background=root.cget('bg'))
    details.grid(row=1, column=1, sticky='nsew', padx=(8, 0))

    buttons = ttk.Frame(top)
    buttons.grid(row=2, column=0, columnspan=2, sticky='ew', pady=6)
    log = tk.Text(top, height=9, wrap='none')
    log.grid(row=3, column=0, columnspan=2, sticky='nsew')
    top.rowconfigure(3, weight=1)
    status = ttk.Label(top, text='')
    status.grid(row=4, column=0, columnspan=2, sticky='w')

    def say(text):
        log.insert('end', text + '\n')
        log.see('end')

    def selected():
        sel = tree.selection()
        return sel[0] if sel else None

    def refresh(keep=None):
        state['mods'] = list_mods()
        tree.delete(*tree.get_children())
        for m in state['mods']:
            info = m['info']
            tree.insert('', 'end', iid=m['name'], text=m['name'],
                        values=('[x]' if m['enabled'] else '[ ]', info['version'] or '-',
                                ('yes, starts ' + ('on' if info['default'] else 'off')) if info['toggle']
                                else '-'))
        if keep and tree.exists(keep):
            tree.selection_set(keep)
        update_status()

    def enabled_names():
        return [m['name'] for m in state['mods'] if m['enabled']]

    def update_status():
        errs, warns = check(enabled_names())
        n = len(enabled_names())
        status.config(text=('%d mod(s) ticked. ' % n) + (' '.join(errs + warns) or 'Ready to build.'),
                      foreground='red' if errs else '')

    def show_details(_=None):
        name = selected()
        details.delete('1.0', 'end')
        for m in state['mods']:
            if m['name'] == name:
                details.insert('end', describe(m))

    def toggle(_=None):
        name = selected()
        if not name:
            return
        for m in state['mods']:
            if m['name'] == name:
                m['enabled'] = not m['enabled']
        save_enabled(enabled_names())
        refresh(name)

    def move(d):
        name = selected()
        names = enabled_names()
        if name not in names:
            return
        i = names.index(name)
        j = max(0, min(len(names) - 1, i + d))
        names[i], names[j] = names[j], names[i]
        save_enabled(names)
        refresh(name)

    def add_mod():
        p = filedialog.askopenfilename(title='Choose a mod zip', filetypes=[('Mod zip', '*.zip')])
        if not p:
            return
        try:
            name = install_zip(p)
        except ManagerError as e:
            if 'already installed' in str(e) and messagebox.askyesno('Replace mod?', str(e) + '. Replace it?'):
                name = install_zip(p, replace=True)
            else:
                messagebox.showerror('Could not add the mod', str(e))
                return
        say('installed mod "%s"' % name)
        refresh(name)

    def run_build(then_play=False):
        if state['busy']:
            return
        if not project_ready():
            messagebox.showinfo('Build', 'First choose your Urbz ROM in Settings.')
            do_settings(True)
            return
        errs, _ = check(enabled_names())
        if errs:
            messagebox.showerror('Cannot build', '\n'.join(errs))
            return
        state['busy'] = True
        say('--- building with: %s' % (', '.join(enabled_names()) or 'no mods (original game)'))

        def work():
            p = subprocess.Popen(build_command(), cwd=KIT, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                root.after(0, say, line.rstrip())
            ok = p.wait() == 0
            root.after(0, done, ok, then_play)
        threading.Thread(target=work, daemon=True).start()

    def done(ok, then_play):
        state['busy'] = False
        say('--- build %s' % ('finished' if ok else 'FAILED (nothing was written)'))
        if ok and then_play:
            do_play()

    def do_play():
        if not emulator_path():
            messagebox.showinfo('Play', 'First choose your emulator in Settings.')
            do_settings()
            return
        try:
            play()
            say('opened %s' % OUT_ROM)
        except ManagerError as e:
            messagebox.showinfo('Play', str(e))

    def do_tune():
        name = selected()
        if not name:
            return
        if not tunable_files(name):
            messagebox.showinfo('Tune', '%s has nothing to tune.' % name)
            return
        tune_window(root, name, say)

    def do_settings(first=False):
        settings_window(root, say, refresh, first)

    for text, cmd in (('Use / don\'t use', toggle), ('Up', lambda: move(-1)), ('Down', lambda: move(1)),
                      ('Tune...', do_tune), ('Add mod...', add_mod)):
        ttk.Button(buttons, text=text, command=cmd).pack(side='left', padx=2)
    for text, cmd in (('Build && Play', lambda: run_build(True)), ('Play', do_play), ('Build', run_build),
                      ('Settings...', do_settings)):
        ttk.Button(buttons, text=text.replace('&&', '&'), command=cmd).pack(side='right', padx=2)

    tree.bind('<<TreeviewSelect>>', show_details)
    tree.bind('<Double-1>', toggle)
    import urbz_mod
    if not os.path.exists(urbz_mod.CFG):              # a fresh kit: Urbz DX's mods ticked
        save_enabled([n for n in DEFAULT_MODS if os.path.isdir(os.path.join(MODS, n))])
    tree.bind('<space>', toggle)
    refresh()
    if state['mods']:
        tree.selection_set(state['mods'][0]['name'])
    say('Kit: %s' % KIT)
    if not project_ready() or not emulator_path():
        root.after(300, do_settings, True)            # the first time: set up the ROM and the emulator
    root.mainloop()


def main(argv):
    if argv and argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    try:
        if not argv:
            run_window()
        elif argv[0] == 'list':
            for m in list_mods():
                print('%s %-24s %s' % ('[x]' if m['enabled'] else '[ ]', m['name'],
                                       describe(m).split('\n', 1)[-1].replace('\n', ' | ')))
        elif argv[0] == 'install' and len(argv) > 1:
            print('installed mod "%s"' % install_zip(argv[1], replace='--replace' in argv))
        elif argv[0] == 'check':
            errs, warns = check([m['name'] for m in list_mods() if m['enabled']])
            print('\n'.join(errs + warns) or 'OK')
            sys.exit(1 if errs else 0)
        else:
            sys.exit(__doc__)
    except ManagerError as e:
        sys.exit('error: ' + str(e))


if __name__ == '__main__':
    main(sys.argv[1:])
