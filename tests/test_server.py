import json
import threading
import unittest
import urllib.error
import urllib.request

from lightbar import controller, leds, paths, server
from tests.test_controller import FakeWatcher, READY

BASE = f'http://127.0.0.1:{paths.PORT}'


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctrl = controller.Controller(leds.SimBar(), watcher=FakeWatcher(), scan=lambda: READY)
        ctrl.tick()
        cls.srv = server.make_server(ctrl)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_ping_state_and_ui(self):
        code, body = self.call('/api/ping')
        self.assertEqual((code, json.loads(body)['ok']), (200, True))
        code, body = self.call('/api/state')
        self.assertEqual(json.loads(body)['situation'], 'ready')
        code, body = self.call('/')
        self.assertIn(b'<title>LightBar</title>', body)

    def test_save_and_test(self):
        look = {'pattern': 'solid', 'colors': ['#ff0000']}
        code, body = self.call('/api/situation', {'id': 'ready', 'mode': 'custom', 'look': look})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['live']['colors'], ['#ff0000'])
        code, body = self.call('/api/test', {'look': {'pattern': 'off'}, 'seconds': 5})
        self.assertEqual(json.loads(body)['ok'], True)
        self.assertEqual(self.call('/api/test/stop', {})[0], 200)
        self.call('/api/situation', {'id': 'ready', 'mode': 'steam'})

    def test_bad_requests(self):
        self.assertEqual(self.call('/api/situation', {'id': 'overheat', 'mode': 'custom', 'look': {'pattern': 'solid'}})[0], 400)
        self.assertEqual(self.call('/api/situation', {'mode': 'custom'})[0], 400)
        self.assertEqual(self.call('/api/nope')[0], 404)

    def test_refuses_other_sites(self):
        self.assertEqual(self.call('/api/state', headers={'Origin': 'http://evil.example'})[0], 403)
        self.assertEqual(self.call('/api/enabled', {'enabled': False}, headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.call('/api/state', headers={'Host': 'evil.example'})[0], 403)


if __name__ == '__main__':
    unittest.main()
