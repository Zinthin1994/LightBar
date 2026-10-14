import hashlib
import io
import json
import os
import shutil
import tarfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from lightbar import VERSION, paths, updater


def release_tar(version, with_bin=True):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        add('LightBar/app/lightbar/__init__.py', f"VERSION = '{version}'\n".encode())
        if with_bin:
            add('LightBar/app/bin/lightbar', b'#!/bin/sh\n')
        add('LightBar/install.sh', b'ELECTRON_VERSION="31.7.7"\n')
    return buf.getvalue()


class FakeGitHub(BaseHTTPRequestHandler):
    release = None
    asset = b''

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith('/releases/latest'):
            if FakeGitHub.release is None:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(FakeGitHub.release).encode()
        elif self.path == '/asset':
            body = FakeGitHub.asset
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def bump(version, parts=1):
    nums = [int(x) for x in version.split('.')]
    nums[parts - 1] += 1
    return '.'.join(str(n) for n in nums)


class UpdaterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(('127.0.0.1', 0), FakeGitHub)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        cls.old_api = updater.API
        updater.API = cls.base

    @classmethod
    def tearDownClass(cls):
        updater.API = cls.old_api
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        shutil.rmtree(paths.UPDATE_DIR, ignore_errors=True)
        if os.path.exists(paths.UPDATE_STATE):
            os.remove(paths.UPDATE_STATE)
        self.new = bump(VERSION, 2)
        self.publish(self.new)

    def publish(self, version, data=None, digest=True, tag=None, name='LightBar.tar.gz'):
        data = data if data is not None else release_tar(version)
        FakeGitHub.asset = data
        FakeGitHub.release = {
            'tag_name': tag or f'v{version}', 'body': 'Notes here', 'html_url': 'https://example/r',
            'assets': [{'name': name, 'size': len(data), 'browser_download_url': self.base + '/asset',
                        **({'digest': 'sha256:' + hashlib.sha256(data).hexdigest()} if digest else {})}],
        }

    def test_version_compare(self):
        self.assertTrue(updater.newer('1.0.1', '1.0.0'))
        self.assertTrue(updater.newer('v1.10', '1.9.9'))
        self.assertFalse(updater.newer('1.0.0', '1.0.0'))
        self.assertFalse(updater.newer('banana', '1.0.0'))

    def test_up_to_date(self):
        self.publish(VERSION)
        self.assertEqual(updater.Updater().check()['status'], 'uptodate')

    def test_available_then_download_and_stage(self):
        u = updater.Updater()
        snap = u.check()
        self.assertEqual((snap['status'], snap['latest'], snap['notes']), ('available', self.new, 'Notes here'))
        self.assertFalse(os.path.exists(paths.UPDATE_STAGED))
        snap = u.check(download=True)
        self.assertEqual(snap['status'], 'ready')
        self.assertTrue(os.path.isfile(os.path.join(paths.UPDATE_STAGED, 'bin', 'lightbar')))
        self.assertEqual(json.load(open(paths.UPDATE_READY))['version'], self.new)
        # a restarted service remembers the staged update
        self.assertEqual(updater.Updater().snapshot()['status'], 'ready')

    def test_bad_checksum_is_discarded(self):
        self.publish(self.new)
        FakeGitHub.asset = b'something else'
        FakeGitHub.release['assets'][0]['size'] = len(FakeGitHub.asset)
        snap = updater.Updater().check(download=True)
        self.assertEqual(snap['status'], 'error')
        self.assertIn('checksum', snap['error'])
        self.assertFalse(os.path.exists(paths.UPDATE_STAGED))

    def test_missing_digest_is_refused(self):
        self.publish(self.new, digest=False)
        snap = updater.Updater().check(download=True)
        self.assertEqual(snap['status'], 'error')
        self.assertIn('checksum', snap['error'])

    def test_wrong_version_inside_the_archive(self):
        self.publish(self.new, data=release_tar('9.9.9'))
        snap = updater.Updater().check(download=True)
        self.assertEqual(snap['status'], 'error')
        self.assertFalse(os.path.exists(paths.UPDATE_STAGED))

    def test_no_release_yet(self):
        FakeGitHub.release = None
        snap = updater.Updater().check()
        self.assertEqual(snap['status'], 'error')

    def test_rolled_back_version_is_not_offered_again(self):
        os.makedirs(paths.UPDATE_DIR)
        json.dump({'version': self.new}, open(paths.UPDATE_FAILED, 'w'))
        snap = updater.Updater().check()
        self.assertEqual((snap['status'], snap['rolled_back']), ('failed', self.new))

    def test_confirm_ends_the_trial(self):
        os.makedirs(paths.UPDATE_DIR)
        json.dump({'version': VERSION, 'notes': 'n'}, open(paths.UPDATE_TRIAL, 'w'))
        open(paths.UPDATE_TRIES, 'w').write('1')
        self.assertEqual(updater.Updater().confirm()['updated'], VERSION)
        self.assertFalse(os.path.exists(paths.UPDATE_TRIAL))
        self.assertIsNone(updater.Updater().confirm()['updated'])


if __name__ == '__main__':
    unittest.main()
