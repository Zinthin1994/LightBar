import os
import shutil
import tempfile
import unittest

from lightbar import leds, looks


def fake_sysfs(order='red green blue', startup=True, n=17):
    base = tempfile.mkdtemp(prefix='lightbar-sysfs-')
    for i in range(n):
        d = os.path.join(base, f'valve-leds[{i}]')
        os.makedirs(d)
        files = {'brightness': '56', 'max_brightness': '255', 'multi_intensity': '0 0 255', 'multi_index': order,
                 'effect': 'normal', 'effect_index': ' '.join(leds.EFFECTS), 'enabled': '1', 'delay': '0x05',
                 'delay_range': '0-20'}
        if startup:
            files.update({'multi_intensity_startup': '0 0 255', 'brightness_startup': '0x38'})
        for k, v in files.items():
            with open(os.path.join(d, k), 'w') as f:
                f.write(v + '\n')
    os.makedirs(os.path.join(base, 'input3-capslock'))
    return base


def read(base, i, attr):
    with open(os.path.join(base, f'valve-leds[{i}]', attr)) as f:
        return f.read().strip()


class LightBarTest(unittest.TestCase):
    def setUp(self):
        self.base = fake_sysfs()
        self.bar = leds.LightBar(self.base)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_discovery_is_numeric_and_ignores_other_leds(self):
        self.assertEqual(len(self.bar.dirs), 17)
        self.assertTrue(self.bar.dirs[10].endswith('valve-leds[10]'))
        self.assertEqual(self.bar.info['delay_range'], (0, 20))
        self.assertTrue(self.bar.info['writable'])
        self.assertTrue(self.bar.info['startup'])

    def test_apply_gradient(self):
        look = looks.normalize({'pattern': 'gradient', 'colors': ['#ff0000', '#0000ff'], 'brightness': 50})
        self.bar.apply(look)
        self.assertEqual(read(self.base, 0, 'multi_intensity'), '255 0 0')
        self.assertEqual(read(self.base, 16, 'multi_intensity'), '0 0 255')
        self.assertEqual(read(self.base, 5, 'brightness'), '128')
        self.assertEqual(read(self.base, 5, 'effect'), 'manual')
        self.assertEqual(read(self.base, 5, 'enabled'), '1')
        st = self.bar.read_state()
        self.assertEqual(st['colors'][0], '#ff0000')
        self.assertEqual(looks.from_hardware(st, self.bar.info)['pattern'], 'custom')

    def test_apply_breathe_sets_effect_and_delay(self):
        self.bar.apply(looks.normalize({'pattern': 'breathe', 'colors': ['#00ff00'], 'speed': 10}))
        self.assertEqual(read(self.base, 3, 'effect'), 'breath')
        self.assertEqual(read(self.base, 3, 'delay'), '0')
        got = looks.from_hardware(self.bar.read_state(), self.bar.info)
        self.assertEqual((got['pattern'], got['colors'], got['speed']), ('breathe', ['#00ff00'], 10))

    def test_off_disables(self):
        self.bar.apply(looks.normalize({'pattern': 'off'}))
        self.assertEqual(read(self.base, 0, 'enabled'), '0')
        self.assertEqual(looks.from_hardware(self.bar.read_state(), self.bar.info)['pattern'], 'off')

    def test_restore_puts_back_a_state(self):
        before = self.bar.read_state()
        self.bar.apply(looks.normalize({'pattern': 'solid', 'colors': ['#ff00ff']}))
        self.bar.restore(before)
        self.assertEqual(self.bar.read_state(), before)

    def test_color_order(self):
        base = fake_sysfs(order='green red blue')
        try:
            bar = leds.LightBar(base)
            bar.apply(looks.normalize({'pattern': 'solid', 'colors': ['#ff8000']}))
            self.assertEqual(read(base, 0, 'multi_intensity'), '128 255 0')
            self.assertEqual(bar.read_state()['colors'][0], '#ff8000')
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_startup_only_writes_changes_to_led0(self):
        self.assertEqual(self.bar.read_startup(), {'color': '#0000ff', 'brightness': 22})
        self.bar.write_startup('#ff0000', 22)
        self.assertEqual(read(self.base, 0, 'multi_intensity_startup'), '255 0 0')
        self.assertEqual(read(self.base, 0, 'brightness_startup'), '0x38')  # unchanged, not rewritten
        self.assertEqual(read(self.base, 1, 'multi_intensity_startup'), '0 0 255')

    def test_no_startup_attributes(self):
        base = fake_sysfs(startup=False)
        try:
            bar = leds.LightBar(base)
            self.assertIsNone(bar.read_startup())
            with self.assertRaises(ValueError):
                bar.write_startup('#ffffff', 50)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_missing_driver(self):
        bar = leds.LightBar(os.path.join(self.base, 'nothing'))
        self.assertFalse(bar.available)
        self.assertIsNone(bar.read_state())


class SimBarTest(unittest.TestCase):
    def test_round_trip(self):
        bar = leds.SimBar()
        look = looks.normalize({'pattern': 'patrol', 'colors': ['#ffffff'], 'brightness': 100, 'speed': 3})
        bar.apply(look)
        got = looks.from_hardware(bar.read_state(), bar.info)
        self.assertTrue(looks.same(got, look), got)


if __name__ == '__main__':
    unittest.main()
