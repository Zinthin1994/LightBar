"""Looks: what the light bar shows.

A look is the small dict the UI edits, the config stores and the controller writes:

    {'pattern': 'solid', 'colors': ['#1a9fff'], 'brightness': 60, 'speed': 5}

brightness is 0-100 %, speed 1 (slow) - 10 (fast). web/app.js has the same pattern list
and the same ledColors() so the in-app preview matches what is written to the LEDs.
"""
import colorsys
import re

NUM_LEDS = 17
STEAM_BLUE = '#1a9fff'

# pattern -> (colors it uses, hardware effect). The per-LED colors are always written
# first; the effects that animate (breath, patrol, rainbow) run on top of them.
PATTERNS = {
    'solid': (1, 'manual'),
    'gradient': (2, 'manual'),
    'rainbow': (0, 'manual'),
    'custom': (NUM_LEDS, 'manual'),
    'breathe': (1, 'breath'),
    'patrol': (1, 'patrol'),
    'wave': (0, 'rainbow'),
    'off': (0, 'manual'),
}
ANIMATED = {'breathe', 'patrol', 'wave'}
# Only shown in previews (Steam's download fill, the firmware's error and boot patterns).
PREVIEW_ONLY = {'fill', 'blink', 'hw'}

DEFAULT_LOOK = {'pattern': 'solid', 'colors': [STEAM_BLUE], 'brightness': 60, 'speed': 5}
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


def normalize(look):
    """A validated copy of a look from the UI or the config. Raises ValueError."""
    if not isinstance(look, dict):
        raise ValueError('look must be an object')
    pattern = look.get('pattern')
    if pattern not in PATTERNS:
        raise ValueError(f'Unknown pattern: {str(pattern)[:20]!r}')
    count = PATTERNS[pattern][0]
    colors = [c.lower() for c in (look.get('colors') or []) if isinstance(c, str) and HEX.match(c)]
    if count:
        colors = (colors or [STEAM_BLUE])[:count]
        while len(colors) < count:
            colors.append(colors[-1])
    else:
        colors = []
    return {
        'pattern': pattern,
        'colors': colors,
        'brightness': _int(look.get('brightness'), 0, 100, 60),
        'speed': _int(look.get('speed'), 1, 10, 5),
    }


def hex_to_rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(c))) for c in rgb)


def hue_rgb(h):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, 1.0)
    return round(r * 255), round(g * 255), round(b * 255)


def led_colors(look):
    """The 17 (r, g, b) colors written to the LEDs for a look (left to right)."""
    p = look['pattern']
    cols = [hex_to_rgb(c) for c in look.get('colors') or []]
    if p in ('solid', 'breathe', 'patrol'):
        return [cols[0]] * NUM_LEDS
    if p == 'gradient':
        a, b = cols[0], cols[1]
        return [tuple(round(a[k] + (b[k] - a[k]) * i / (NUM_LEDS - 1)) for k in range(3)) for i in range(NUM_LEDS)]
    if p in ('rainbow', 'wave'):
        return [hue_rgb(i / NUM_LEDS) for i in range(NUM_LEDS)]
    if p == 'custom':
        return cols[:NUM_LEDS]
    return [(0, 0, 0)] * NUM_LEDS


def speed_to_delay(speed, delay_range):
    """speed 10 = fastest = the smallest delay."""
    lo, hi = delay_range
    return lo + round((10 - speed) / 9 * (hi - lo))


def delay_to_speed(delay, delay_range):
    lo, hi = delay_range
    if hi <= lo:
        return 5
    return _int(10 - (delay - lo) / (hi - lo) * 9, 1, 10, 5)


def from_hardware(state, info):
    """Turn what the LEDs report back (leds.LightBar.read_state) into a look."""
    if not state:
        return None
    maxb = info.get('max_brightness') or 255
    pct = round(state['brightness'] / maxb * 100) if maxb else 0
    speed = delay_to_speed(state.get('delay', 0), info.get('delay_range') or (0, 20))
    colors = state['colors']
    effect = state.get('effect') or 'manual'
    base = {'brightness': pct, 'speed': speed}
    if not state['enabled'] or effect == 'off' or pct == 0:
        return {'pattern': 'off', 'colors': [], **base}
    if effect == 'breath':
        return {'pattern': 'breathe', 'colors': colors[:1], **base}
    if effect == 'patrol':
        return {'pattern': 'patrol', 'colors': colors[:1], **base}
    if effect == 'rainbow':
        return {'pattern': 'wave', 'colors': [], **base}
    if effect != 'manual':
        # normal / factory / demo: Steam's or the firmware's own modes
        return {'pattern': 'hw', 'effect': effect, 'colors': colors, **base}
    if all(c == colors[0] for c in colors):
        return {'pattern': 'solid', 'colors': colors[:1], **base}
    return {'pattern': 'custom', 'colors': colors, **base}


def same(a, b):
    if not a or not b:
        return a == b
    keys = ('pattern', 'colors', 'brightness', 'effect')
    if a.get('pattern') in ANIMATED or b.get('pattern') in ANIMATED:
        keys += ('speed',)
    return all(a.get(k) == b.get(k) for k in keys)
