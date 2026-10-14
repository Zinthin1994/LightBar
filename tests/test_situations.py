import os
import shutil
import tempfile
import unittest

from lightbar import paths, situations

GAME_MODE = [('gamescope-wl', b'gamescope\0'), ('steam', b'/home/deck/.local/share/Steam/ubuntu12_32/steam\0')]
REAPER = ('reaper', b'reaper\0SteamLaunch\0AppId=570\0--\0/games/dota2.sh\0')


class DetectTest(unittest.TestCase):
    def test_situations(self):
        self.assertEqual(situations.detect(GAME_MODE, False), 'ready')
        self.assertEqual(situations.detect(GAME_MODE, True), 'downloading')
        self.assertEqual(situations.detect(GAME_MODE + [REAPER], True), 'playing')
        self.assertEqual(situations.detect([('plasmashell', b''), ('steam', b'')], True), 'desktop')
        self.assertIsNone(situations.detect([('gamescope-wl', b'')], False))  # Steam not up yet
        self.assertIsNone(situations.detect([('bash', b'')], False))

    def test_own_tile_is_not_a_game(self):
        own = ('reaper', b'reaper\0SteamLaunch\0AppId=3000000000\0--\0' + paths.APP.encode() + b'/bin/lightbar\0')
        self.assertEqual(situations.detect(GAME_MODE + [own], False), 'ready')

    def test_every_situation_is_described(self):
        for s in situations.SITUATIONS:
            self.assertIn(s['kind'], ('os', 'startup', 'firmware'))
            self.assertTrue(s['name'] and s['desc'])
            if s['kind'] == 'firmware':
                self.assertIn('pattern', s['look'])
        self.assertEqual(situations.CONTROLLABLE, ['ready', 'playing', 'downloading', 'desktop'])


class DownloadWatcherTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.log = os.path.join(self.dir, 'content_log.txt')
        self.w = situations.DownloadWatcher(self.log)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(self, text):
        with open(self.log, 'ab') as f:
            f.write(text.encode())

    def test_follows_states(self):
        self.assertFalse(self.w.poll())  # no log yet
        self.add('[2026-10-13 10:00:00] AppID 570 state changed : Update Required,Update Queued,\n')
        self.assertFalse(self.w.poll())
        self.add('[2026-10-13 10:00:05] AppID 570 state changed : Update Required,Update Running,Update Started,\n')
        self.assertTrue(self.w.poll())
        self.add('[2026-10-13 10:00:06] AppID 570 state changed : Update Required,Update Running,Update Paused,\n')
        self.assertFalse(self.w.poll())
        self.add('[2026-10-13 10:00:07] AppID 570 state changed : Update Required,Update Running,Downloading,\n')
        self.assertTrue(self.w.poll())
        self.add('[2026-10-13 10:09:00] AppID 570 state changed : Fully Installed,\n')
        self.assertFalse(self.w.poll())

    def test_partial_lines_wait_for_the_rest(self):
        self.add('[x] AppID 1 state changed : Update Running,Downl')
        self.assertFalse(self.w.poll())
        self.add('oading,\r\n')
        self.assertTrue(self.w.poll())

    def test_rotated_log(self):
        self.add('[x] AppID 1 state changed : Update Running,\n' * 50)
        self.assertTrue(self.w.poll())
        with open(self.log, 'wb') as f:
            f.write(b'[y] AppID 2 state changed : Fully Installed,\n')
        self.assertFalse(self.w.poll())


if __name__ == '__main__':
    unittest.main()
