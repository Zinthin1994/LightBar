"""Ready-made looks the user can apply to any situation with one press.

These are the built-in presets. The user's own saved looks live in the config
(controller: config['presets']) and are returned alongside these.
"""
from .looks import normalize

_RAW = [
    ('Steam Blue', {'pattern': 'solid', 'colors': ['#1a9fff']}),
    ('Warm White', {'pattern': 'solid', 'colors': ['#ffd8a8'], 'brightness': 55}),
    ('Deep Purple', {'pattern': 'solid', 'colors': ['#9b3dff']}),
    ('Ember', {'pattern': 'gradient', 'colors': ['#ff7a00', '#ff2a1f']}),
    ('Ocean', {'pattern': 'gradient', 'colors': ['#00e1ff', '#3d5bff']}),
    ('Aurora', {'pattern': 'gradient', 'colors': ['#00e5a0', '#9b3dff']}),
    ('Sunset', {'pattern': 'gradient', 'colors': ['#ff3dc8', '#ff7a00']}),
    ('Forest', {'pattern': 'gradient', 'colors': ['#5cff3a', '#00e5a0']}),
    ('Rainbow', {'pattern': 'rainbow', 'colors': []}),
    ('Color wave', {'pattern': 'wave', 'colors': [], 'speed': 4}),
    ('Candle', {'pattern': 'breathe', 'colors': ['#ff7a00'], 'brightness': 55, 'speed': 3}),
    ('Pulse', {'pattern': 'breathe', 'colors': ['#1a9fff'], 'speed': 4}),
    ('Scanner', {'pattern': 'patrol', 'colors': ['#ff2a1f'], 'speed': 6}),
]

BUILTIN = [{'name': name, 'look': normalize(look)} for name, look in _RAW]
