"""The Steam Machine light bar through the valve-leds kernel driver.

SteamOS exposes the bar as 17 multicolor LEDs, /sys/class/leds/valve-leds[0..16], each with:
    brightness, max_brightness       LED class brightness
    multi_intensity, multi_index     "R G B" color (order given by multi_index)
    effect, effect_index             patrol breath factory normal off rainbow demo manual
    enabled, delay, delay_range      strip on/off, animation step delay (lower = faster)
    multi_intensity_startup,         power-on color / brightness, kept by the embedded
    brightness_startup               controller (every write is saved to its flash)
effect, enabled and delay are shared registers, so every LED reports the same value.
Writing needs the udev rule from install.sh (the nodes are root-only by default).

SimBar stands in when there is no light bar (development on a PC, or the driver missing),
so the app still runs and previews; the UI says it's a simulation.
"""
import os
import re
import threading

from .looks import NUM_LEDS, PATTERNS, led_colors, speed_to_delay, rgb_to_hex, hex_to_rgb
from .util import log

PREFIX = 'valve-leds'
EFFECTS = ['patrol', 'breath', 'factory', 'normal', 'off', 'rainbow', 'demo', 'manual']
DEFAULT_DELAY_RANGE = (0, 20)


def _num(s, default=0):
    try:
        return int(str(s).strip(), 0)
    except (TypeError, ValueError):
        return default


class LightBar:
    simulated = False

    def __init__(self, base):
        self.base = base
        self.lock = threading.RLock()
        self.dirs = self._discover()
        self.info = self._info()

    def _discover(self):
        found = []
        try:
            names = os.listdir(self.base)
        except OSError:
            return []
        for name in names:
            if not name.startswith(PREFIX):
                continue
            m = re.search(r'(\d+)\D*$', name)
            if m:
                found.append((int(m.group(1)), os.path.join(self.base, name)))
        return [d for _, d in sorted(found)]

    @property
    def available(self):
        return bool(self.dirs)

    # ------------------------------------------------------------ raw access
    def path(self, i, attr):
        return os.path.join(self.dirs[i], attr)

    def read(self, i, attr):
        try:
            with open(self.path(i, attr), 'r') as f:
                return f.read().strip()
        except OSError:
            return None

    def write(self, i, attr, value):
        with open(self.path(i, attr), 'w') as f:
            f.write(str(value))

    def has(self, attr):
        return bool(self.dirs) and os.path.exists(self.path(0, attr))

    def _info(self):
        if not self.dirs:
            return {'found': False, 'count': 0, 'writable': False}
        rng = re.findall(r'\d+', self.read(0, 'delay_range') or '')
        effects = (self.read(0, 'effect_index') or '').split() or EFFECTS
        order = (self.read(0, 'multi_index') or 'red green blue').split()
        return {
            'found': True,
            'count': len(self.dirs),
            'writable': os.access(self.path(0, 'multi_intensity'), os.W_OK)
                        and os.access(self.path(0, 'effect'), os.W_OK),
            'max_brightness': _num(self.read(0, 'max_brightness'), 255) or 255,
            'delay_range': (int(rng[0]), int(rng[1])) if len(rng) == 2 else DEFAULT_DELAY_RANGE,
            'effects': effects,
            'color_order': order,
            'startup': self.has('multi_intensity_startup') and self.has('brightness_startup'),
        }

    def refresh_info(self):
        self.info = self._info()
        return self.info

    def _to_hw(self, rgb):
        named = dict(zip(('red', 'green', 'blue'), rgb))
        return ' '.join(str(named.get(c, 0)) for c in self.info['color_order'])

    def _from_hw(self, text):
        vals = [_num(v) for v in (text or '').split()]
        named = dict(zip(self.info['color_order'], vals))
        return tuple(max(0, min(255, named.get(c, 0))) for c in ('red', 'green', 'blue'))

    # ------------------------------------------------------------ state
    def read_state(self):
        """What the LEDs are showing right now, or None without a light bar."""
        if not self.dirs:
            return None
        with self.lock:
            colors = [rgb_to_hex(self._from_hw(self.read(i, 'multi_intensity'))) for i in range(len(self.dirs))]
            effect = (self.read(0, 'effect') or 'manual').strip('[]')
            return {
                'enabled': _num(self.read(0, 'enabled'), 1) != 0,
                'effect': effect,
                'brightness': _num(self.read(0, 'brightness')),
                'delay': _num(self.read(0, 'delay')),
                'colors': colors,
            }

    def apply(self, look):
        """Write a (normalized) look to the LEDs."""
        if not self.dirs:
            return
        info = self.info
        n = len(self.dirs)
        with self.lock:
            if look['pattern'] == 'off':
                for i in range(n):
                    self.write(i, 'enabled', 0)
                return
            colors = led_colors(look)
            raw = round(look['brightness'] / 100 * info['max_brightness'])
            if look['brightness'] > 0:
                raw = max(1, raw)
            delay = speed_to_delay(look['speed'], info['delay_range'])
            effect = PATTERNS[look['pattern']][1]
            for i in range(n):
                self.write(i, 'enabled', 1)
                self.write(i, 'multi_intensity', self._to_hw(colors[i % len(colors)]))
                self.write(i, 'brightness', raw)
            for i in range(n):
                self.write(i, 'delay', delay)
                # the driver re-sends the per-LED colors after an effect change
                self.write(i, 'effect', effect)

    def restore(self, state):
        """Put back a state from read_state() (Steam's own look, before LightBar took over)."""
        if not self.dirs or not state:
            return
        n = len(self.dirs)
        with self.lock:
            for i in range(n):
                self.write(i, 'multi_intensity', self._to_hw(hex_to_rgb(state['colors'][i % len(state['colors'])])))
                self.write(i, 'brightness', state['brightness'])
            for i in range(n):
                self.write(i, 'delay', state['delay'])
                if state['effect'] in self.info['effects']:
                    self.write(i, 'effect', state['effect'])
                self.write(i, 'enabled', 1 if state['enabled'] else 0)

    # ------------------------------------------------------------ power-on (EC flash)
    def read_startup(self):
        if not self.info.get('startup'):
            return None
        rgb = [_num(v) for v in (self.read(0, 'multi_intensity_startup') or '').split()]
        if len(rgb) != 3:
            return None
        maxb = self.info['max_brightness']
        return {'color': rgb_to_hex(rgb), 'brightness': round(_num(self.read(0, 'brightness_startup')) / maxb * 100)}

    def write_startup(self, color, brightness):
        """Saves to the embedded controller's flash, so only changed values are written
        (the color and brightness registers are shared: LED 0 is enough)."""
        if not self.info.get('startup'):
            raise ValueError('This light bar driver has no power-on settings')
        cur = self.read_startup() or {}
        with self.lock:
            if color.lower() != cur.get('color'):
                self.write(0, 'multi_intensity_startup', ' '.join(str(c) for c in hex_to_rgb(color)))
            if brightness != cur.get('brightness'):
                raw = max(1, round(brightness / 100 * self.info['max_brightness'])) if brightness else 0
                self.write(0, 'brightness_startup', raw)
        log.info('Power-on look saved to the light bar: %s at %d%%', color, brightness)


class SimBar(LightBar):
    """In-memory light bar with the real driver's behaviour, for running without hardware."""
    simulated = True

    def __init__(self):
        self.base = None
        self.lock = threading.RLock()
        self.dirs = [f'sim{i}' for i in range(NUM_LEDS)]
        self.attrs = {i: {'brightness': '56', 'max_brightness': '255', 'multi_intensity': '26 159 255',
                          'multi_index': 'red green blue', 'effect': 'manual', 'effect_index': ' '.join(EFFECTS),
                          'enabled': '1', 'delay': '0x05', 'delay_range': '0-20',
                          'multi_intensity_startup': '0 0 255', 'brightness_startup': '0x38'}
                      for i in range(NUM_LEDS)}
        self.info = self._info()

    def path(self, i, attr):
        return f'sim{i}/{attr}'

    def read(self, i, attr):
        return self.attrs[i].get(attr)

    def write(self, i, attr, value):
        if attr == 'effect' and str(value) not in EFFECTS:
            raise OSError(22, 'Invalid argument')
        # shared registers, as on the real controller
        targets = range(NUM_LEDS) if attr in ('effect', 'enabled', 'delay', 'multi_intensity_startup',
                                              'brightness_startup') else (i,)
        for t in targets:
            self.attrs[t][attr] = str(value)

    def has(self, attr):
        return attr in self.attrs[0]

    def _info(self):
        info = super()._info()
        info['writable'] = True
        return info


def open_bar():
    from . import paths
    bar = LightBar(paths.SYSFS_LEDS)
    if bar.available:
        log.info('Light bar found: %d LEDs, writable=%s, info=%s', bar.info['count'], bar.info['writable'], bar.info)
        return bar
    if os.environ.get('LIGHTBAR_SIMULATE', '1') != '0':
        log.warning('No valve-leds light bar under %s - running in simulation', paths.SYSFS_LEDS)
        return SimBar()
    return bar
