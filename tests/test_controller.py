import os
import unittest

from lightbar import controller, leds, paths
from lightbar.situations import BY_ID

READY = [('gamescope-wl', b''), ('steam', b'')]
PLAYING = READY + [('reaper', b'reaper\0SteamLaunch\0AppId=570\0')]
MINE = {'pattern': 'solid', 'colors': ['#ff0000'], 'brightness': 80, 'speed': 5}


class FakeWatcher:
    downloading = False

    def poll(self):
        return self.downloading

    def reset(self):
        pass


class WindowTest(unittest.TestCase):
    def test_in_window(self):
        # same-day window 09:00-17:00
        self.assertTrue(controller.in_window(600, 540, 1020))
        self.assertFalse(controller.in_window(1080, 540, 1020))
        # overnight window 22:00-07:00
        self.assertTrue(controller.in_window(23 * 60, 22 * 60, 7 * 60))
        self.assertTrue(controller.in_window(3 * 60, 22 * 60, 7 * 60))
        self.assertFalse(controller.in_window(12 * 60, 22 * 60, 7 * 60))
        # empty window
        self.assertFalse(controller.in_window(100, 300, 300))


class ControllerTest(unittest.TestCase):
    def setUp(self):
        for p in (paths.CONFIG, paths.OBSERVED):
            if os.path.exists(p):
                os.remove(p)
        self.t = 1000.0
        self.minutes = 12 * 60   # local noon, outside the default night window
        self.procs = READY
        self.bar = leds.SimBar()
        self.steam_look = self.bar.read_state()
        self.c = controller.Controller(self.bar, watcher=FakeWatcher(), scan=lambda: self.procs,
                                       clock=lambda: self.t, wall=lambda: 1_700_000_000,
                                       now_minutes=lambda: self.minutes)

    def tick(self, seconds=1.0):
        self.t += seconds
        self.c.tick()

    def color(self):
        return self.bar.read_state()['colors'][0]

    def test_steam_by_default_and_records_what_steam_shows(self):
        for _ in range(5):
            self.tick()
        self.assertEqual(self.bar.read_state(), self.steam_look)
        snap = self.c.snapshot()
        self.assertEqual(snap['situation'], 'ready')
        self.assertFalse(snap['controlling'])
        ready = next(s for s in snap['situations'] if s['id'] == 'ready')
        self.assertEqual(ready['observed']['look']['colors'], ['#1a9fff'])
        self.assertTrue(os.path.exists(paths.OBSERVED))

    def test_my_look_is_applied_kept_and_survives_a_restart(self):
        self.tick()
        self.c.set_situation('ready', 'custom', MINE)
        self.assertEqual(self.color(), '#ff0000')
        # Steam changes the bar behind our back: LightBar puts the look back
        self.bar.write(0, 'multi_intensity', '0 0 255')
        self.tick(controller.VERIFY_EVERY + 0.1)
        self.assertEqual(self.color(), '#ff0000')
        # config is on disk: a new service picks it up
        again = controller.Controller(self.bar, watcher=FakeWatcher(), scan=lambda: self.procs, clock=lambda: self.t)
        self.assertEqual(again.config['situations']['ready']['mode'], 'custom')
        self.assertEqual(again.config['situations']['ready']['look']['colors'], ['#ff0000'])

    def test_hands_back_to_steam_when_the_situation_changes(self):
        self.tick()
        self.c.set_situation('playing', 'custom', MINE)
        self.assertNotEqual(self.color(), '#ff0000')  # not playing yet
        self.procs = PLAYING
        self.tick()
        self.assertEqual(self.color(), '#ff0000')
        self.assertTrue(self.c.snapshot()['controlling'])
        self.procs = READY
        self.tick()
        self.assertEqual(self.bar.read_state(), self.steam_look)
        self.assertFalse(self.c.snapshot()['controlling'])

    def test_downloading(self):
        self.c.set_situation('downloading', 'custom', {'pattern': 'patrol', 'colors': ['#00ff00']})
        self.c.watcher.downloading = True
        self.tick()
        self.assertEqual(self.c.situation, 'downloading')
        self.assertEqual(self.bar.read_state()['effect'], 'patrol')

    def test_test_overrides_then_ends(self):
        self.tick()
        self.c.start_test({'pattern': 'solid', 'colors': ['#00ff00']}, seconds=5)
        self.assertEqual(self.color(), '#00ff00')
        self.assertTrue(self.c.snapshot()['testing'])
        self.tick(6)
        self.assertEqual(self.bar.read_state(), self.steam_look)
        self.assertFalse(self.c.snapshot()['testing'])

    def test_stop_test_goes_back_to_my_look(self):
        self.tick()
        self.c.set_situation('ready', 'custom', MINE)
        self.c.start_test({'pattern': 'solid', 'colors': ['#00ff00']})
        self.assertEqual(self.color(), '#00ff00')
        self.c.stop_test()
        self.assertEqual(self.color(), '#ff0000')

    def test_pause_and_shutdown_hand_back(self):
        self.tick()
        self.c.set_situation('ready', 'custom', MINE)
        self.c.set_enabled(False)
        self.assertEqual(self.bar.read_state(), self.steam_look)
        self.c.set_enabled(True)
        self.assertEqual(self.color(), '#ff0000')
        self.c.shutdown()
        self.assertEqual(self.bar.read_state(), self.steam_look)

    def test_steam_mode_keeps_my_look_for_later(self):
        self.tick()
        self.c.set_situation('ready', 'custom', MINE)
        self.c.set_situation('ready', 'steam', None)
        self.assertEqual(self.bar.read_state(), self.steam_look)
        self.assertEqual(self.c.config['situations']['ready']['look']['colors'], ['#ff0000'])

    def test_refuses_firmware_situations(self):
        with self.assertRaises(ValueError):
            self.c.set_situation('overheat', 'custom', MINE)
        with self.assertRaises(ValueError):
            self.c.set_situation('ready', 'custom', {'pattern': 'fill'})

    def test_write_errors_are_reported(self):
        def denied(*a):
            raise PermissionError(13, 'Permission denied')
        self.bar.apply = denied
        self.tick()
        self.c.set_situation('ready', 'custom', MINE)
        self.assertIn('permission', self.c.snapshot()['error'].lower())

    def test_startup(self):
        self.c.set_startup('#ffffff', 50)
        self.assertEqual(self.bar.read_startup(), {'color': '#ffffff', 'brightness': 50})
        with self.assertRaises(ValueError):
            self.c.set_startup('white', 50)

    def test_snapshot_lists_everything(self):
        snap = self.c.snapshot()
        self.assertEqual([s['id'] for s in snap['situations']], list(BY_ID))
        start = next(s for s in snap['situations'] if s['id'] == 'startup')
        self.assertEqual(start['current']['color'], '#0000ff')
        self.assertTrue(snap['simulated'])
        self.assertTrue(len(snap['presets']['builtin']) > 5)
        self.assertEqual(snap['presets']['user'], [])
        self.assertFalse(snap['night']['active'])

    # ---------------------------------------------------------------- night dimming
    def brightness(self):
        return self.bar.read_state()['brightness']

    def test_night_dims_my_look(self):
        self.tick()
        self.c.set_situation('ready', 'custom', {**MINE, 'brightness': 80})
        self.assertEqual(self.brightness(), round(80 / 100 * 255))
        self.c.set_night({'enabled': True, 'from': '22:00', 'to': '07:00', 'mode': 'dim', 'brightness': 10})
        self.assertFalse(self.c.snapshot()['night']['active'])  # noon
        self.minutes = 23 * 60   # 11pm
        self.tick()
        self.assertTrue(self.c.snapshot()['night']['active'])
        self.assertEqual(self.brightness(), round(10 / 100 * 255))
        self.assertEqual(self.color(), '#ff0000')  # same look, just dimmer
        # morning: back to full
        self.minutes = 9 * 60
        self.tick()
        self.assertEqual(self.brightness(), round(80 / 100 * 255))

    def test_night_off_mode(self):
        self.tick()
        self.c.set_situation('ready', 'custom', MINE)
        self.c.set_night({'enabled': True, 'from': '00:00', 'to': '23:59', 'mode': 'off'})
        self.tick()
        self.assertFalse(self.bar.read_state()['enabled'])

    def test_night_never_brightens(self):
        self.tick()
        self.c.set_situation('ready', 'custom', {**MINE, 'brightness': 5})
        self.minutes = 23 * 60
        self.c.set_night({'enabled': True, 'from': '22:00', 'to': '07:00', 'mode': 'dim', 'brightness': 40})
        self.tick()
        self.assertEqual(self.brightness(), round(5 / 100 * 255))  # 5% stays 5%, not raised to 40%

    def test_night_only_touches_my_looks(self):
        # ready left to Steam: night mode must not take the bar over
        self.minutes = 23 * 60
        self.c.set_night({'enabled': True, 'from': '22:00', 'to': '07:00', 'mode': 'off'})
        for _ in range(5):
            self.tick()
        self.assertEqual(self.bar.read_state(), self.steam_look)

    def test_night_config_is_validated_and_saved(self):
        self.c.set_night({'enabled': True, 'from': '99:99', 'to': 'nope', 'mode': 'weird', 'brightness': 500})
        n = self.c.config['night']
        self.assertEqual((n['from'], n['to'], n['mode'], n['brightness']), ('22:00', '07:00', 'dim', 100))
        self.assertEqual(controller.Controller(self.bar, scan=lambda: READY).config['night']['enabled'], True)

    # ---------------------------------------------------------------- presets
    def test_save_apply_and_delete_preset(self):
        self.c.save_preset('My Red', MINE)
        users = self.c.snapshot()['presets']['user']
        self.assertEqual(users[0]['name'], 'My Red')
        self.assertEqual(users[0]['look']['colors'], ['#ff0000'])
        # saved presets survive a restart
        again = controller.Controller(self.bar, scan=lambda: READY)
        self.assertEqual(again.config['presets'][0]['name'], 'My Red')
        self.c.delete_preset('My Red')
        self.assertEqual(self.c.snapshot()['presets']['user'], [])

    def test_preset_same_name_replaces_and_moves_to_front(self):
        self.c.save_preset('A', MINE)
        self.c.save_preset('B', MINE)
        self.c.save_preset('a', {'pattern': 'solid', 'colors': ['#00ff00']})
        users = self.c.snapshot()['presets']['user']
        self.assertEqual([u['name'] for u in users], ['a', 'B'])
        self.assertEqual(users[0]['look']['colors'], ['#00ff00'])

    def test_preset_needs_name_and_valid_look(self):
        with self.assertRaises(ValueError):
            self.c.save_preset('  ', MINE)
        with self.assertRaises(ValueError):
            self.c.save_preset('x', {'pattern': 'fill'})

    def test_preset_cap(self):
        for i in range(controller.MAX_PRESETS + 5):
            self.c.save_preset(f'p{i}', MINE)
        self.assertEqual(len(self.c.config['presets']), controller.MAX_PRESETS)


if __name__ == '__main__':
    unittest.main()
