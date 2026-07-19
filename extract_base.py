"""Extract the base quest files from YOUR game installation into base/.

The repository does not ship any game data (copyright). Run this once before
building quests:

    python extract_base.py ["<game dir>"]

It pulls
    Scripts\\Quests\\TwoWorldsQuests.qtx   out of  WDFiles\\Update16.wd
    Language\\TwoWorldsQuests.lan          out of  WDFiles\\Language.wd

Update16 is the newest shipped .qtx (patches 1.1-1.6 overwrote the original);
the loose 1.0 copies floating around the net are stale - do not use them.
"""

import os
import sys

import tw1_wd

DEFAULT_GAME = r'F:\SteamLibrary\steamapps\common\Two Worlds - Epic Edition'

WANTED = {
    os.path.join('WDFiles', 'Update16.wd'):
        ('Scripts\\Quests\\TwoWorldsQuests.qtx', 'base/TwoWorldsQuests.qtx'),
    os.path.join('WDFiles', 'Language.wd'):
        ('Language\\TwoWorldsQuests.lan', 'base/TwoWorldsQuests.lan'),
}


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GAME
    if not os.path.isdir(os.path.join(game, 'WDFiles')):
        sys.exit(f'No WDFiles\\ under: {game}\n'
                 f'Usage: python extract_base.py "<game dir>"')
    os.makedirs('base', exist_ok=True)
    for arc, (inner, dest) in WANTED.items():
        path = os.path.join(game, arc)
        entry = next((e for e in tw1_wd.read(path) if e.path == inner), None)
        if entry is None:
            sys.exit(f'{inner} not found in {path}')
        open(dest, 'wb').write(entry.data)
        print(f'{dest}  {len(entry.data):,} B  (from {arc})')
    print('Base files ready.')


if __name__ == '__main__':
    main()
