"""Filesystem layout.

Installed layout (default ROOT = ~/.local/share/lightbar):
    ROOT/app        this code (lightbar/, web/, electron/, bin/, art/)
    ROOT/electron   Electron runtime
    ROOT/data       everything the app writes (config.json, observed.json, logs/)
"""
import os

HOME = os.path.expanduser('~')
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get('LIGHTBAR_HOME') or os.path.dirname(APP)

DATA = os.path.join(ROOT, 'data')
LOGS = os.path.join(DATA, 'logs')
CONFIG = os.path.join(DATA, 'config.json')
OBSERVED = os.path.join(DATA, 'observed.json')
SERVICE_LOG = os.path.join(LOGS, 'service.log')

WEB = os.path.join(APP, 'web')
APP_ART = os.path.join(APP, 'art')
APP_SCRIPT = os.path.join(APP, 'bin', 'lightbar')

SYSFS_LEDS = os.environ.get('LIGHTBAR_SYSFS') or '/sys/class/leds'
PORT = int(os.environ.get('LIGHTBAR_PORT') or '47831')


def steam_root():
    for p in ('~/.local/share/Steam', '~/.steam/steam', '~/.steam/root'):
        p = os.path.realpath(os.path.expanduser(p))
        if os.path.isdir(p):
            return p
    return None


def ensure():
    for d in (DATA, LOGS):
        os.makedirs(d, exist_ok=True)
