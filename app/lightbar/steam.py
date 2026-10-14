"""The LightBar tile in the Steam library (a non-Steam shortcut with artwork).

Steam rewrites shortcuts.vdf from memory, so the tile is only written while Steam is
closed (install.sh closes it first). Artwork goes straight into userdata/<id>/config/grid.

    python -m lightbar.steam add-self | remove-self
"""
import os
import shutil
import subprocess
import sys
import zlib

from . import paths, vdf

TAG = 'LightBar-App'
STEAMID64_BASE = 76561197960265728


def user_dirs():
    """[userdata path] for every Steam account on this machine, most recent first."""
    root = paths.steam_root()
    ud = os.path.join(root, 'userdata') if root else ''
    if not os.path.isdir(ud):
        return []
    users = [d for d in os.listdir(ud) if d.isdigit() and d != '0']
    recent = None
    try:
        for sid, info in vdf.load_text(os.path.join(root, 'config', 'loginusers.vdf')).get('users', {}).items():
            if str(info.get('MostRecent', '0')) == '1':
                recent = str(int(sid) - STEAMID64_BASE)
    except (OSError, ValueError):
        pass
    users.sort(key=lambda u: (u != recent, -os.path.getmtime(os.path.join(ud, u))))
    return [os.path.join(ud, u) for u in users]


def steam_running():
    try:
        return bool(subprocess.run(['pgrep', '-x', 'steam'], capture_output=True, text=True).stdout.strip())
    except FileNotFoundError:
        return False


def shortcut_appid(exe, name):
    return (zlib.crc32((exe + name).encode('utf-8')) & 0xFFFFFFFF) | 0x80000000


def _get(d, key, default=None):
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return default


def _ours(entry):
    tags = _get(entry, 'tags', {}) or {}
    return TAG in (tags.values() if isinstance(tags, dict) else [])


def _read(userdir):
    p = os.path.join(userdir, 'config', 'shortcuts.vdf')
    if not os.path.exists(p):
        return []
    with open(p, 'rb') as f:
        data = f.read()
    if not data.strip(b'\x00\x08'):
        return []
    parsed = vdf.parse_binary(data)
    key = next((k for k in parsed if k.lower() == 'shortcuts'), None)
    return list((parsed.get(key) or {}).values()) if key else []


def _write(userdir, entries):
    p = os.path.join(userdir, 'config', 'shortcuts.vdf')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p):
        shutil.copy2(p, p + '.lightbar.bak')
    with open(p + '.tmp', 'wb') as f:
        f.write(vdf.dump_binary({'shortcuts': {str(i): e for i, e in enumerate(entries)}}))
    os.replace(p + '.tmp', p)


def entry():
    exe = f'"{paths.APP_SCRIPT}"'
    appid = shortcut_appid(exe, 'LightBar')
    icon = os.path.join(paths.APP_ART, 'icon.png')
    return appid, {
        'appid': appid, 'AppName': 'LightBar', 'Exe': exe, 'StartDir': f'"{paths.APP}"',
        'icon': icon if os.path.exists(icon) else '', 'ShortcutPath': '', 'LaunchOptions': '',
        'IsHidden': 0, 'AllowDesktopConfig': 1, 'AllowOverlay': 1, 'OpenVR': 0, 'Devkit': 0,
        'DevkitGameID': '', 'DevkitOverrideAppID': 0, 'LastPlayTime': 0, 'FlatpakAppID': '',
        'tags': {'0': TAG},
    }


def _art(userdir, appid, remove=False):
    grid = os.path.join(userdir, 'config', 'grid')
    for suffix, name in (('p', 'portrait.png'), ('', 'wide.png'), ('_hero', 'hero.png'), ('_logo', 'logo.png')):
        dst = os.path.join(grid, f'{appid}{suffix}.png')
        src = os.path.join(paths.APP_ART, name)
        if remove:
            if os.path.exists(dst):
                os.remove(dst)
        elif os.path.exists(src):
            os.makedirs(grid, exist_ok=True)
            shutil.copyfile(src, dst)


def add_self():
    users = user_dirs()
    if not users:
        raise RuntimeError('No Steam account found - log into Steam once first')
    appid, e = entry()
    for ud in users:
        kept = [x for x in _read(ud) if not _ours(x)]
        _write(ud, kept + [e])
        _art(ud, appid)
    return len(users)


def remove_self():
    appid, _ = entry()
    for ud in user_dirs():
        entries = _read(ud)
        kept = [x for x in entries if not _ours(x)]
        if len(kept) != len(entries):
            _write(ud, kept)
        _art(ud, appid, remove=True)


def main(argv):
    cmd = argv[0] if argv else ''
    if cmd not in ('add-self', 'remove-self'):
        print('usage: python -m lightbar.steam add-self|remove-self')
        return 2
    if steam_running():
        print('Close Steam first: it overwrites the library shortcuts while it runs')
        return 1
    if cmd == 'add-self':
        print(f'LightBar tile added for {add_self()} Steam account(s)')
    else:
        remove_self()
        print('LightBar tile removed')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
