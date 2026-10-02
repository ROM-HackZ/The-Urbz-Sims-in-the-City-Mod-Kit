#!/usr/bin/env python3
"""Mod manager: pick mods, build the ROM and play it, in a window (or from the command line).

  python mod_manager.py                 open the window (Windows: manager.bat)
  python mod_manager.py list            same list as the window, as text
  python mod_manager.py install mod.zip install a mod from a zip into mods/
  python mod_manager.py check           check the enabled mods (conflicts, save space)

The window shows every mod in mods/ with a tick box. Ticked mods are built into the ROM in
the order shown (later mods win where two change the same thing); Up/Down change the order.
Build runs urbz_build.py and shows its output; Play opens the built ROM in the emulator
named in emulator.txt (the full path of its .exe). "Add mod..." installs a mod zip.

It uses the same files and rules as urbz_mod.py (mods.json lists the enabled mods), so the
window and the command line always agree. Mods that can be switched in the game show
"in-game switch": once built in, they can be turned on and off on the Options > Mods page.
"""
import json, os, shutil, subprocess, sys, zipfile

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
MODS = os.path.join(KIT, 'mods')
OUT_ROM = os.path.join(KIT, 'build', 'Urbz Mod.nds')
EMULATOR_TXT = os.path.join(KIT, 'emulator.txt')

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
    return [sys.executable, os.path.join(KIT, 'urbz_build.py')]


def emulator_path():
    if not os.path.exists(EMULATOR_TXT):
        return None
    p = open(EMULATOR_TXT, encoding='utf-8-sig').readline().strip().strip('"')
    return p or None


def play():
    emu = emulator_path()
    if not emu:
        raise ManagerError('no emulator set: put the full path of your emulator .exe in emulator.txt')
    if not os.path.exists(emu):
        raise ManagerError('emulator.txt points to "%s", which does not exist' % emu)
    if not os.path.exists(OUT_ROM):
        raise ManagerError('build the ROM first')
    subprocess.Popen([emu, OUT_ROM], cwd=os.path.dirname(emu))


# ---------------------------------------------------------------- window

def run_window():
    import threading
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title('Urbz mod manager')
    root.geometry('820x560')
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
        try:
            play()
            say('opened %s' % OUT_ROM)
        except ManagerError as e:
            messagebox.showinfo('Play', str(e))

    for text, cmd in (('Use / don\'t use', toggle), ('Up', lambda: move(-1)), ('Down', lambda: move(1)),
                      ('Add mod...', add_mod), ('Build', run_build), ('Play', do_play),
                      ('Build && Play', lambda: run_build(True)), ('Refresh', refresh)):
        ttk.Button(buttons, text=text.replace('&&', '&'), command=cmd).pack(side='left', padx=2)

    tree.bind('<<TreeviewSelect>>', show_details)
    tree.bind('<Double-1>', toggle)
    tree.bind('<space>', toggle)
    refresh()
    if state['mods']:
        tree.selection_set(state['mods'][0]['name'])
    say('Kit: %s' % KIT)
    if not os.path.isdir(os.path.join(KIT, 'project')):
        say('project/ is missing: run extract.bat with your ROM first.')
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
