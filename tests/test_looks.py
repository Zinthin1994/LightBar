import unittest

from lightbar import looks


class NormalizeTest(unittest.TestCase):
    def test_pads_and_trims_colors(self):
        self.assertEqual(looks.normalize({'pattern': 'gradient', 'colors': ['#FF0000']})['colors'], ['#ff0000', '#ff0000'])
        self.assertEqual(looks.normalize({'pattern': 'solid', 'colors': ['#ff0000', '#00ff00']})['colors'], ['#ff0000'])
        self.assertEqual(len(looks.normalize({'pattern': 'custom', 'colors': ['#ff0000']})['colors']), 17)
        self.assertEqual(looks.normalize({'pattern': 'wave', 'colors': ['#ff0000']})['colors'], [])

    def test_drops_bad_colors_and_clamps(self):
        n = looks.normalize({'pattern': 'solid', 'colors': ['red', '#12345'], 'brightness': 400, 'speed': -3})
        self.assertEqual(n['colors'], [looks.STEAM_BLUE])
        self.assertEqual((n['brightness'], n['speed']), (100, 1))

    def test_rejects_unknown_and_preview_only_patterns(self):
        for bad in ('fill', 'hw', 'nope', None):
            with self.assertRaises(ValueError):
                looks.normalize({'pattern': bad})
        with self.assertRaises(ValueError):
            looks.normalize('solid')


class ColorsTest(unittest.TestCase):
    def test_gradient_ends(self):
        c = looks.led_colors(looks.normalize({'pattern': 'gradient', 'colors': ['#ff0000', '#0000ff']}))
        self.assertEqual(len(c), 17)
        self.assertEqual((c[0], c[-1]), ((255, 0, 0), (0, 0, 255)))

    def test_rainbow_and_off(self):
        self.assertEqual(len(set(looks.led_colors({'pattern': 'rainbow', 'colors': []}))), 17)
        self.assertEqual(set(looks.led_colors({'pattern': 'off', 'colors': []})), {(0, 0, 0)})

    def test_speed_delay_round_trip(self):
        for s in range(1, 11):
            self.assertEqual(looks.delay_to_speed(looks.speed_to_delay(s, (0, 20)), (0, 20)), s)
        self.assertEqual(looks.speed_to_delay(10, (0, 20)), 0)


class FromHardwareTest(unittest.TestCase):
    info = {'max_brightness': 255, 'delay_range': (0, 20)}

    def state(self, **kw):
        s = {'enabled': True, 'effect': 'manual', 'brightness': 255, 'delay': 0, 'colors': ['#112233'] * 17}
        s.update(kw)
        return s

    def test_kinds(self):
        self.assertEqual(looks.from_hardware(self.state(), self.info)['pattern'], 'solid')
        self.assertEqual(looks.from_hardware(self.state(colors=['#000000'] + ['#ffffff'] * 16), self.info)['pattern'], 'custom')
        self.assertEqual(looks.from_hardware(self.state(effect='breath'), self.info)['pattern'], 'breathe')
        self.assertEqual(looks.from_hardware(self.state(effect='rainbow'), self.info)['pattern'], 'wave')
        self.assertEqual(looks.from_hardware(self.state(enabled=False), self.info)['pattern'], 'off')
        hw = looks.from_hardware(self.state(effect='normal'), self.info)
        self.assertEqual((hw['pattern'], hw['effect']), ('hw', 'normal'))
        self.assertIsNone(looks.from_hardware(None, self.info))

    def test_brightness_percent(self):
        self.assertEqual(looks.from_hardware(self.state(brightness=128), self.info)['brightness'], 50)


if __name__ == '__main__':
    unittest.main()
