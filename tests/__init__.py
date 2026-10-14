import os
import socket
import sys
import tempfile

# Every test runs against a throwaway LIGHTBAR_HOME and a free port, set before lightbar is imported.
_home = tempfile.mkdtemp(prefix='lightbar-test-')
os.environ['LIGHTBAR_HOME'] = _home
os.environ['LIGHTBAR_SYSFS'] = os.path.join(_home, 'no-sysfs')
with socket.socket() as _s:
    _s.bind(('127.0.0.1', 0))
    os.environ['LIGHTBAR_PORT'] = str(_s.getsockname()[1])
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
