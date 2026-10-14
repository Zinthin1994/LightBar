"""Filesystem layout.

Installed layout (default ROOT = ~/.local/share/lightbar):
    ROOT/app        this code (lightbar/, web/, electron/, bin/, art/)
    ROOT/electron   Electron runtime
    ROOT/data       everything the app writes (config.json, observed.json, logs/)
    ROOT/update     a downloaded LightBar update waiting to be installed (see updater.py)
    ROOT/app.prev   the previous version, kept for rollback after an update
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

UPDATE_DIR = os.path.join(ROOT, 'update')
UPDATE_STAGED = os.path.join(UPDATE_DIR, 'app')          # unpacked app/ of the new version
UPDATE_READY = os.path.join(UPDATE_DIR, 'ready.json')    # staged and verified: bin/lightbar swaps it in
UPDATE_TRIAL = os.path.join(UPDATE_DIR, 'trial.json')    # swapped in, not yet confirmed working
UPDATE_TRIES = os.path.join(UPDATE_DIR, 'trial.tries')
UPDATE_FAILED = os.path.join(UPDATE_DIR, 'failed.json')  # rolled back: don't offer this version again
UPDATE_STATE = os.path.join(DATA, 'update.json')
ELECTRON_VERSION_FILE = os.path.join(ROOT, 'electron', '.version')

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
