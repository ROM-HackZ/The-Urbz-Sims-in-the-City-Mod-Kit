"""The Urbz DS mod kit: one command for every tool.

  python urbz.py                     list the commands
  python urbz.py <command> [args]    run one (e.g. python urbz.py build, python urbz.py mod list)
  python urbz.py <command> --help    that command's own help

The tools themselves are in kit/ (kit/urbz_<command>.py); this only finds and runs them."""
import os
import runpy
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(KIT, 'kit')

# command -> file in kit/ (most are kit/urbz_<command>.py)
COMMANDS = {
    'extract': 'urbz_extract.py',      # unpack your ROM into project/
    'build': 'urbz_build.py',          # build a ROM from project/ + mods
    'manager': 'mod_manager.py',       # the mod manager window (and list / install / check)
    'mod': 'urbz_mod.py',              # make and edit mods
    'text': 'urbz_text.py',            # the game's text
    'png': 'urbz_png.py',              # pictures as PNG
    'palette': 'urbz_palette.py',      # recolouring
    'font': 'urbz_font.py',            # fonts
    'save': 'urbz_save.py',            # save files
    'patch': 'urbz_patch.py',          # build C code mods
    'code': 'urbz_code.py',            # the code-mod builder library (checks)
    'anims': 'urbz_anims.py',          # new animations for townspeople
    'art': 'urbz_art.py',              # art for pets and furniture
    'poses': 'urbz_poses.py',          # borrowed poses (preview)
    'pets': 'urbz_pets.py',            # pets.json builder
    'objects': 'urbz_objects.py',      # objects.json builder
    'seats': 'urbz_seats.py',          # seats.json: extra seats in places
    'import': 'urbz_import.py',        # models from other Sims DS games
    'models': 'urbz_models.py',        # the kit's own models (pets, beds, furniture)
    'tuning': 'urbz_tuning.py',        # your own settings for the mods (the manager's Tune window)
    'catalog': 'urbz_catalog.py',      # the asset catalog (catalog/index.html)
    'classify': 'urbz_classify.py',    # asset types
    'sprites': 'urbz_sprites.py',      # sprite layouts
    'gfx': 'urbz_gfx.py',              # tile graphics
    'composite': 'urbz_composite.py',  # composite sprites
    'fullfat': 'urbz_fullfat.py',      # The Sims 2: Apartment Pets / Castaway reader
    'nsbmd': 'urbz_nsbmd.py',          # The Sims 2 DS model reader
    'sims3': 'urbz_sims3.py',          # The Sims 3 DS reader
    'compress': 'urbzcomp.py',         # the game's compression
    'scan': 'scan_chunks.py',          # scan chunk headers
}


def describe(path):
    """The first line of a tool's docstring."""
    try:
        src = open(path, encoding='utf-8').read()
    except OSError:
        return ''
    for q in ('"""', "'''"):
        i = src.find(q)
        if i >= 0:
            return src[i + 3:src.find(q, i + 3)].strip().splitlines()[0] if src[i + 3:].strip() else ''
    return ''


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        print('Commands:')
        for name, f in COMMANDS.items():
            print('  %-10s %s' % (name, describe(os.path.join(TOOLS, f))[:90]))
        return 0
    name = argv[0]
    if name not in COMMANDS:
        print('unknown command %r (python urbz.py lists them)' % name)
        return 2
    path = os.path.join(TOOLS, COMMANDS[name])
    sys.path.insert(0, TOOLS)
    sys.argv = [path] + argv[1:]
    runpy.run_path(path, run_name='__main__')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
