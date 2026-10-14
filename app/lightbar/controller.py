"""Keeps the light bar showing your look for each situation, with or without the app open.

Every second: work out the situation (situations.detect), then
  * your look is set for it  -> write it, and put it back if something else (Steam)
                                changes the bar afterwards;
  * Steam's look is wanted   -> if LightBar had taken over, hand the bar back the way Steam
                                left it, then just watch and remember what Steam shows
                                there (observed.json), so the app can show it.
A test from the app overrides all of that until it ends.
"""
import threading
import time
from collections import deque

from . import VERSION, paths, presets
from .looks import DEFAULT_LOOK, from_hardware, normalize, same, HEX
from .situations import BY_ID, CONTROLLABLE, SITUATIONS, DownloadWatcher, detect, scan_processes
from .util import log, read_json, write_json

TICK = 1.0
VERIFY_EVERY = 3.0
SLOW_VERIFY = 20.0       # when something keeps changing the bar back
STABLE_FOR = 3.0         # seconds in a situation before Steam's look there is recorded
MAX_TEST_SECONDS = 120
MAX_PRESETS = 30
DEFAULT_NIGHT = {'enabled': False, 'from': '22:00', 'to': '07:00', 'mode': 'dim', 'brightness': 15}


def _hhmm(value, default):
    """Validate a 'HH:MM' string, else the default."""
    try:
        h, m = str(value).split(':')
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return f'{h:02d}:{m:02d}'
    except (ValueError, AttributeError):
        pass
    return default


def _minutes(hhmm):
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)


def _local_minutes(ts):
    lt = time.localtime(ts)
    return lt.tm_hour * 60 + lt.tm_min


def in_window(now, start, end):
    """now within [start, end) in minutes-since-midnight, with a window that may cross midnight."""
    if start == end:
        return False
    return start <= now < end if start < end else (now >= start or now < end)


class Controller:
    def __init__(self, bar, watcher=None, scan=scan_processes, clock=time.monotonic, wall=time.time,
                 now_minutes=None):
        self.bar = bar
        self.watcher = watcher if watcher is not None else DownloadWatcher()
        self.scan = scan
        self.clock = clock
        self.wall = wall
        # minutes since local midnight, injectable so tests don't depend on the clock/timezone
        self.now_minutes = now_minutes or (lambda: _local_minutes(self.wall()))
        self.lock = threading.RLock()
        self.config = self._load_config()
        self.observed = read_json(paths.OBSERVED, {}) or {}
        self.situation = None
        self.since = clock()
        self.applied = None      # the look LightBar has on the bar (None: the bar is Steam's)
        self.expected = None     # what the bar reported right after LightBar wrote it
        self.steam_state = None  # the bar as Steam left it, before LightBar took over
        self.test = None         # {'look': ..., 'until': ...}
        self.last_verify = 0.0
        self.fights = deque(maxlen=6)
        self.error = None

    # ------------------------------------------------------------ config
    def _load_config(self):
        raw = read_json(paths.CONFIG, {}) or {}
        sits = {}
        for sid in CONTROLLABLE:
            e = (raw.get('situations') or {}).get(sid) or {}
            try:
                look = normalize(e['look']) if e.get('look') else None
            except ValueError:
                look = None
            sits[sid] = {'mode': 'custom' if e.get('mode') == 'custom' and look else 'steam',
                         'look': look or dict(DEFAULT_LOOK)}
        user_presets = []
        for e in (raw.get('presets') or [])[:MAX_PRESETS]:
            try:
                user_presets.append({'name': str(e['name'])[:40], 'look': normalize(e['look'])})
            except (KeyError, TypeError, ValueError):
                pass
        return {'enabled': raw.get('enabled', True) is not False, 'situations': sits,
                'presets': user_presets, 'night': self._clean_night(raw.get('night'))}

    @staticmethod
    def _clean_night(raw):
        raw = raw or {}
        n = dict(DEFAULT_NIGHT)
        n['enabled'] = bool(raw.get('enabled'))
        n['from'] = _hhmm(raw.get('from'), DEFAULT_NIGHT['from'])
        n['to'] = _hhmm(raw.get('to'), DEFAULT_NIGHT['to'])
        if raw.get('mode') in ('dim', 'off'):
            n['mode'] = raw['mode']
        try:
            n['brightness'] = max(0, min(100, int(raw.get('brightness', DEFAULT_NIGHT['brightness']))))
        except (TypeError, ValueError):
            pass
        return n

    def _save_config(self):
        write_json(paths.CONFIG, self.config)

    def _night_active(self):
        n = self.config['night']
        return bool(n['enabled']) and in_window(self.now_minutes(), _minutes(n['from']), _minutes(n['to']))

    def _apply_night(self, look):
        """At night, dim or turn off a look LightBar is about to show."""
        if not self._night_active():
            return look
        n = self.config['night']
        if n['mode'] == 'off':
            return {'pattern': 'off', 'colors': [], 'brightness': 0, 'speed': look['speed']}
        if look['brightness'] <= n['brightness']:
            return look
        return {**look, 'colors': list(look['colors']), 'brightness': n['brightness']}

    def target(self, sid):
        """The look LightBar should show for a situation, or None to leave it to Steam."""
        if not sid or not self.config['enabled']:
            return None
        e = self.config['situations'].get(sid)
        return e['look'] if e and e['mode'] == 'custom' else None

    # ------------------------------------------------------------ loop
    def run(self):
        while True:
            try:
                self.tick()
            except Exception:
                log.exception('Controller tick failed')
            time.sleep(TICK)

    def tick(self):
        with self.lock:
            now = self.clock()
            procs = self.scan()
            downloading = self.watcher.poll()
            if 'steam' not in {c for c, _ in procs}:
                self.watcher.reset()
                downloading = False
            sit = detect(procs, downloading)
            if sit != self.situation:
                log.info('Situation: %s -> %s', self.situation, sit)
                self.situation, self.since = sit, now
            if self.test:
                if now < self.test['until']:
                    self._show(self.test['look'], now)
                    return
                log.info('Test finished')
                self.test = None
            self._settle(now)

    def _settle(self, now):
        look = self.target(self.situation)
        if look:
            self._show(self._apply_night(look), now)
        elif self.applied is not None:
            self._hand_back()
        elif self.situation and now - self.since >= STABLE_FOR:
            self._observe(self.situation)

    # ------------------------------------------------------------ writing
    def _write(self, fn, *args):
        try:
            fn(*args)
            if self.error:
                log.info('Light bar writable again')
            self.error = None
            return True
        except OSError as e:
            msg = ('LightBar isn\'t allowed to change the light bar. Re-run install.sh to fix the permissions.'
                   if isinstance(e, PermissionError) else f'Writing to the light bar failed: {e}')
            if msg != self.error:
                log.error('%s (%r)', msg, e)
            self.error = msg
            return False

    def _show(self, look, now):
        if self.applied is None and self.steam_state is None:
            self.steam_state = self.bar.read_state()
        if not same(look, self.applied):
            self._put(look, now)
            return
        wait = SLOW_VERIFY if len(self.fights) == self.fights.maxlen and now - self.fights[0] < 60 else VERIFY_EVERY
        if now - self.last_verify < wait:
            return
        self.last_verify = now
        if self.expected is None:
            self._put(look, now)  # the last write failed: retry quietly
        elif not self._matches(self.bar.read_state()):
            log.info('Something else changed the light bar - putting %s back', look['pattern'])
            self.fights.append(now)
            self._put(look, now)

    def _put(self, look, now):
        self.applied = look
        self.last_verify = now
        self.expected = self.bar.read_state() if self._write(self.bar.apply, look) else None

    def _matches(self, cur):
        exp = self.expected
        if not exp or not cur:
            return False
        if not exp['enabled']:
            return not cur['enabled']
        keys = ('enabled', 'effect', 'brightness') + (('colors',) if exp['effect'] == 'manual' else ())
        return all(cur[k] == exp[k] for k in keys)

    def _hand_back(self):
        state, self.steam_state = self.steam_state, None
        self.applied = self.expected = None
        if state:
            log.info('Handing the light bar back to Steam')
            self._write(self.bar.restore, state)

    def _observe(self, sid):
        look = from_hardware(self.bar.read_state(), self.bar.info)
        if not look:
            return
        prev = self.observed.get(sid) or {}
        self.observed[sid] = {'look': look, 'seen': self.wall()}
        if not same(look, prev.get('look')):
            log.info('Steam shows %s for %s', look['pattern'], sid)
            write_json(paths.OBSERVED, self.observed)

    # ------------------------------------------------------------ API
    def set_situation(self, sid, mode, look):
        if sid not in CONTROLLABLE:
            raise ValueError(f'{sid!r} can\'t be changed by LightBar')
        if mode not in ('steam', 'custom'):
            raise ValueError('mode must be steam or custom')
        with self.lock:
            e = self.config['situations'][sid]
            if look is not None:
                e['look'] = normalize(look)
            e['mode'] = mode
            self._save_config()
            log.info('Saved %s: %s %s', sid, mode, e['look'])
            if not self.test:
                self._settle(self.clock())

    def set_enabled(self, enabled):
        with self.lock:
            self.config['enabled'] = bool(enabled)
            self._save_config()
            if not self.test:
                self._settle(self.clock())

    def set_night(self, cfg):
        with self.lock:
            self.config['night'] = self._clean_night(cfg)
            log.info('Night dimming: %s', self.config['night'])
            self._save_config()
            if not self.test:
                self._settle(self.clock())
            return self.config['night']

    def save_preset(self, name, look):
        name = str(name or '').strip()[:40]
        if not name:
            raise ValueError('A preset needs a name')
        look = normalize(look)
        with self.lock:
            p = [x for x in self.config['presets'] if x['name'].lower() != name.lower()]
            p.insert(0, {'name': name, 'look': look})
            self.config['presets'] = p[:MAX_PRESETS]
            self._save_config()
            log.info('Saved preset %r', name)
        return {'ok': True, 'name': name}

    def delete_preset(self, name):
        with self.lock:
            self.config['presets'] = [x for x in self.config['presets'] if x['name'] != name]
            self._save_config()

    def start_test(self, look, seconds=20):
        look = normalize(look)
        seconds = max(1, min(MAX_TEST_SECONDS, int(seconds or 20)))
        with self.lock:
            now = self.clock()
            self.test = {'look': look, 'until': now + seconds}
            self._show(look, now)
        return {'ok': self.error is None, 'error': self.error}

    def stop_test(self):
        with self.lock:
            if self.test:
                self.test = None
                self._settle(self.clock())

    def shutdown(self):
        """The service is stopping (uninstall, or LightBar turned off): give the bar back to Steam."""
        with self.lock:
            self.test = None
            if self.applied is not None:
                self._hand_back()

    def set_startup(self, color, brightness):
        if not isinstance(color, str) or not HEX.match(color):
            raise ValueError('color must be #rrggbb')
        brightness = max(0, min(100, int(brightness)))
        with self.lock:
            if not self._write(self.bar.write_startup, color, brightness):
                raise ValueError(self.error)

    def snapshot(self):
        with self.lock:
            info = self.bar.info
            sits = []
            for s in SITUATIONS:
                d = {k: s[k] for k in ('id', 'kind', 'name', 'desc')}
                if s['kind'] == 'os':
                    cfg = self.config['situations'][s['id']]
                    d.update(mode=cfg['mode'], look=cfg['look'], steam=s['steam'], steam_note=s['steam_note'],
                             observed=self.observed.get(s['id']))
                elif s['kind'] == 'startup':
                    d.update(steam=s['steam'], steam_note=s['steam_note'], current=self.bar.read_startup())
                else:
                    d['look'] = s['look']
                sits.append(d)
            return {
                'version': VERSION,
                'simulated': self.bar.simulated,
                'hardware': {k: info.get(k) for k in ('found', 'count', 'writable', 'startup')},
                'error': self.error,
                'enabled': self.config['enabled'],
                'situation': self.situation,
                'situation_name': BY_ID[self.situation]['name'] if self.situation else None,
                'testing': bool(self.test),
                'controlling': self.applied is not None and not self.test,
                'live': from_hardware(self.bar.read_state(), info),
                'situations': sits,
                'presets': {'builtin': presets.BUILTIN, 'user': self.config['presets']},
                'night': {**self.config['night'], 'active': self._night_active()},
            }
