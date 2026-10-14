"""The situations in which the light bar behaves differently, and how to tell which one is on.

Three kinds:
  os        SteamOS is running. Steam drives the bar; LightBar can put your own look on top
            (home screen, playing, downloading, Desktop Mode).
  startup   power-on, before SteamOS loads. Only a color and brightness, kept in the light
            bar's own memory (EC flash).
  firmware  standby, BIOS and hardware alerts. The firmware drives the bar there; LightBar
            only explains what they look like.

The firmware patterns follow the published Steam Machine light bar meanings (quadrants
counted from the left; with 17 LEDs they're drawn as 4/4/1/4/4). They're illustrations:
the exact timing is the firmware's.
"""
import os
import re

from . import paths
from .looks import STEAM_BLUE

WHITE = '#ffffff'
RED = '#ff2a1f'


def _look(pattern, colors=(), brightness=70, speed=5, **extra):
    return {'pattern': pattern, 'colors': list(colors), 'brightness': brightness, 'speed': speed, **extra}


SITUATIONS = [
    {'id': 'ready', 'kind': 'os', 'name': 'Home screen',
     'desc': 'Game Mode, nothing playing or downloading.',
     'steam': _look('solid', [STEAM_BLUE]), 'steam_note': 'Solid, in the color picked in Steam'},
    {'id': 'playing', 'kind': 'os', 'name': 'Playing a game',
     'desc': 'A game or app started from your Steam library is running.',
     'steam': _look('solid', [STEAM_BLUE]), 'steam_note': 'Same as the home screen'},
    {'id': 'downloading', 'kind': 'os', 'name': 'Downloading',
     'desc': 'Steam is downloading or updating a game.',
     'steam': _look('fill', [STEAM_BLUE]), 'steam_note': 'Fills left to right with the download progress'},
    {'id': 'desktop', 'kind': 'os', 'name': 'Desktop Mode',
     'desc': 'The KDE desktop. Steam\'s light bar settings don\'t apply here.',
     'steam': None, 'steam_note': 'Keeps whatever was showing before'},
    {'id': 'startup', 'kind': 'startup', 'name': 'Powering on',
     'desc': 'From the power button until SteamOS loads. Saved in the light bar itself.',
     'steam': _look('breathe', [WHITE], speed=4), 'steam_note': 'Breathing, in the power-on color'},
    {'id': 'sleep', 'kind': 'firmware', 'name': 'Sleep',
     'desc': 'Standby. The bar is off; the small power LED stays white.', 'look': _look('off')},
    {'id': 'off', 'kind': 'firmware', 'name': 'Powered off',
     'desc': 'Everything is off.', 'look': _look('off')},
    {'id': 'bios_update', 'kind': 'firmware', 'name': 'BIOS update',
     'desc': 'Fills left to right while the BIOS updates. Don\'t power off.',
     'look': _look('fill', [STEAM_BLUE], speed=3)},
    {'id': 'bios_recovery', 'kind': 'firmware', 'name': 'BIOS recovery',
     'desc': 'Blinking white while the BIOS recovers itself.', 'look': _look('blink', [WHITE])},
    {'id': 'overheat', 'kind': 'firmware', 'name': 'Overheating',
     'desc': 'Solid red: the CPU or GPU is too hot. Give it room to breathe.', 'look': _look('solid', [RED], 90)},
    {'id': 'err_memtrain', 'kind': 'firmware', 'name': 'Memory training failed',
     'desc': 'Left half breathing red.', 'look': _look('breathe', [RED], 90, 4, range=[0, 8])},
    {'id': 'err_ssd', 'kind': 'firmware', 'name': 'SSD not detected',
     'desc': 'Second quadrant breathing red.', 'look': _look('breathe', [RED], 90, 4, range=[4, 7])},
    {'id': 'err_gpu', 'kind': 'firmware', 'name': 'GPU failure',
     'desc': 'Right half breathing red.', 'look': _look('breathe', [RED], 90, 4, range=[9, 16])},
    {'id': 'err_ram', 'kind': 'firmware', 'name': 'RAM not detected',
     'desc': 'Fourth quadrant breathing red.', 'look': _look('breathe', [RED], 90, 4, range=[13, 16])},
]
BY_ID = {s['id']: s for s in SITUATIONS}
CONTROLLABLE = [s['id'] for s in SITUATIONS if s['kind'] == 'os']

GAME_MODE_PROCS = {'gamescope', 'gamescope-wl', 'gamescopereaper'}
DESKTOP_PROCS = {'plasmashell', 'kwin_wayland', 'kwin_x11'}


# ---------------------------------------------------------------- processes

def scan_processes(proc='/proc'):
    """[(comm, cmdline bytes)] for every process we can read."""
    out = []
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return out
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, 'comm'), 'rb') as f:
                comm = f.read().strip().decode('utf-8', 'replace')
            with open(os.path.join(proc, pid, 'cmdline'), 'rb') as f:
                cmd = f.read()
        except OSError:
            continue
        out.append((comm, cmd))
    return out


def game_running(procs, own_app=paths.APP):
    """Steam starts every library launch (games and non-Steam shortcuts) through its reaper
    with SteamLaunch AppId=<id>. LightBar's own tile is one of those, so it's ignored."""
    own = own_app.encode('utf-8')
    for comm, cmd in procs:
        if b'SteamLaunch' in cmd and b'AppId=' in cmd and own not in cmd:
            return True
    return False


def detect(procs, downloading):
    """The current situation id, or None while nothing we know of is on screen
    (booting, Steam starting, or not a Steam Machine session at all)."""
    comms = {c for c, _ in procs}
    if not comms & GAME_MODE_PROCS:
        return 'desktop' if comms & DESKTOP_PROCS else None
    if 'steam' not in comms:
        return None
    if game_running(procs):
        return 'playing'
    if downloading:
        return 'downloading'
    return 'ready'


# ---------------------------------------------------------------- downloads

STATE_LINE = re.compile(r'AppID (\d+) state changed : (.*)$')
ACTIVE = {'Update Running', 'Downloading'}
INACTIVE = {'Update Paused', 'Update Suspended'}
MAX_BACKLOG = 256 * 1024


class DownloadWatcher:
    """Follows Steam's logs/content_log.txt, where every app's install state change is logged:
        [..] AppID 570 state changed : Update Required,Update Running,Update Started,Downloading,
    A download is running while any app's latest state is running and not paused."""

    def __init__(self, path=None):
        if path is None:
            root = paths.steam_root()
            path = os.path.join(root, 'logs', 'content_log.txt') if root else ''
        self.path = path
        self.pos = 0
        self.ident = None
        self.partial = b''
        self.states = {}

    def reset(self):
        self.states.clear()

    def poll(self):
        try:
            st = os.stat(self.path)
        except OSError:
            self.states.clear()
            self.ident = None
            return False
        ident = (st.st_dev, st.st_ino)
        if ident != self.ident or st.st_size < self.pos:
            # new or rotated log: start from its recent part
            self.ident = ident
            self.pos = max(0, st.st_size - MAX_BACKLOG)
            self.partial = b''
            self.states.clear()
        if st.st_size > self.pos:
            with open(self.path, 'rb') as f:
                f.seek(self.pos)
                data = f.read(4 * MAX_BACKLOG)
            self.pos += len(data)
            lines = (self.partial + data).split(b'\n')
            self.partial = lines.pop()
            for raw in lines:
                m = STATE_LINE.search(raw.decode('utf-8', 'replace').rstrip('\r'))
                if m:
                    self.states[m.group(1)] = {f.strip() for f in m.group(2).split(',') if f.strip()}
        return self.downloading()

    def downloading(self):
        return any(flags & ACTIVE and not flags & INACTIVE for flags in self.states.values())
