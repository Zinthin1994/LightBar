"""LightBar service: keeps the light bar looks applied and serves the app (127.0.0.1 only).

Runs all the time as the systemd user unit lightbar.service, so your looks stay on after
the app is closed. The Electron app is just a window onto this.
"""
import json
import logging
import logging.handlers
import mimetypes
import os
import signal
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION, paths
from .controller import Controller
from .leds import open_bar
from .updater import Updater
from .util import log

ALLOWED_HOSTS = {f'127.0.0.1:{paths.PORT}', f'localhost:{paths.PORT}'}
ALLOWED_ORIGINS = {f'http://{h}' for h in ALLOWED_HOSTS}
CTRL = None
UPDATER = None


def route(method, parts, body):
    c = CTRL
    if method == 'GET' and parts == ['ping']:
        return {'ok': True, 'version': VERSION}
    if method == 'GET' and parts == ['state']:
        return {**c.snapshot(), 'update': UPDATER.snapshot()}
    if method != 'POST':
        return None
    if parts == ['update', 'check']:
        # runs in the background; the UI sees progress through /api/state
        UPDATER.check_async(bool(body.get('download')))
        return {**UPDATER.snapshot(), 'status': 'checking' if UPDATER.status != 'ready' else 'ready'}
    if parts == ['update', 'confirm']:
        return UPDATER.confirm()
    if parts == ['situation']:
        c.set_situation(str(body['id']), body['mode'], body.get('look'))
        return c.snapshot()
    if parts == ['test']:
        return c.start_test(body['look'], body.get('seconds', 20))
    if parts == ['test', 'stop']:
        c.stop_test()
        return {'ok': True}
    if parts == ['startup']:
        c.set_startup(body['color'], body['brightness'])
        return c.snapshot()
    if parts == ['enabled']:
        c.set_enabled(body['enabled'])
        return c.snapshot()
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = 'LightBar'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if not n:
            return {}
        try:
            data = json.loads(self.rfile.read(min(n, 1 << 20)) or b'{}')
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _static(self, path):
        rel = path.lstrip('/') or 'index.html'
        web = os.path.realpath(paths.WEB)
        full = os.path.realpath(os.path.join(web, rel))
        if not full.startswith(web + os.sep) or not os.path.isfile(full):
            full = os.path.join(paths.WEB, 'index.html')
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if full.endswith('.js'):
            ctype = 'application/javascript'
        with open(full, 'rb') as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def _allowed(self, api):
        """Only LightBar's own window and local scripts may use the API, not web pages
        open in a browser: the Host must be ours (no DNS rebinding) and cross-site
        requests (Origin / Sec-Fetch-Site) are refused."""
        host = (self.headers.get('Host') or '').lower()
        if host not in ALLOWED_HOSTS:
            return False
        if not api:
            return True
        origin = self.headers.get('Origin')
        if origin is not None and origin.lower() not in ALLOWED_ORIGINS:
            return False
        site = (self.headers.get('Sec-Fetch-Site') or '').lower()
        return site in ('', 'same-origin', 'none')

    def _dispatch(self, method):
        url = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.split('/') if p]
        if not self._allowed(bool(parts) and parts[0] == 'api'):
            log.warning('Refused %s %s (Host=%r Origin=%r)', method, url.path,
                        self.headers.get('Host'), self.headers.get('Origin'))
            return self._send(403, {'error': 'forbidden'})
        if not parts or parts[0] != 'api':
            if method == 'GET':
                return self._static(url.path)
            return self._send(404, {'error': 'not found'})
        try:
            res = route(method, parts[1:], self._body() if method == 'POST' else {})
            if res is None:
                return self._send(404, {'error': 'not found'})
            self._send(200, res)
        except ValueError as e:
            self._send(400, {'error': str(e)})
        except KeyError as e:
            self._send(400, {'error': f'Missing field: {e.args[0] if e.args else "?"}'})
        except Exception as e:
            log.exception('API error on %s', self.path)
            self._send(500, {'error': str(e)})


def make_server(controller, port=None, updater=None):
    global CTRL, UPDATER
    CTRL = controller
    UPDATER = updater or Updater()
    srv = ThreadingHTTPServer(('127.0.0.1', paths.PORT if port is None else port), Handler)
    srv.daemon_threads = True
    return srv


def main():
    paths.ensure()
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.handlers.RotatingFileHandler(paths.SERVICE_LOG, maxBytes=1 << 20, backupCount=2,
                                                       encoding='utf-8'),
                  logging.StreamHandler(sys.stdout)])
    ctrl = Controller(open_bar())

    def stop(signum, _frame):
        log.info('Stopping (signal %d)', signum)
        ctrl.shutdown()
        os._exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=ctrl.run, daemon=True).start()
    srv = make_server(ctrl)
    log.info('LightBar %s listening on http://127.0.0.1:%d', VERSION, paths.PORT)
    srv.serve_forever()


if __name__ == '__main__':
    main()
