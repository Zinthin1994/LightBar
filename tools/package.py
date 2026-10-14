"""Builds dist/LightBar-<version>.tar.gz (LF line endings, executable scripts).
    python tools/package.py
"""
import io
import os
import re
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = re.search(r"VERSION = '([^']+)'", open(os.path.join(ROOT, 'app', 'lightbar', '__init__.py')).read()).group(1)
OUT = os.path.join(ROOT, 'dist', f'LightBar-{VERSION}.tar.gz')
TEXT = ('.py', '.js', '.json', '.html', '.css', '.sh', '.md', '.rules', '')  # '' = extensionless (bin/, LICENSE)
INCLUDE = ['install.sh', 'uninstall.sh', 'README.md', 'LICENSE', 'app']


def add(tar, path, arc):
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if name == '__pycache__':
                continue
            add(tar, os.path.join(path, name), f'{arc}/{name}')
        return
    data = open(path, 'rb').read()
    ext = os.path.splitext(path)[1]
    if ext in TEXT and b'\0' not in data[:1024]:
        data = data.replace(b'\r\n', b'\n')
    info = tarfile.TarInfo(arc)
    info.size = len(data)
    executable = arc.endswith('.sh') or '/bin/' in arc
    info.mode = 0o755 if executable else 0o644
    info.mtime = int(os.path.getmtime(path))
    tar.addfile(info, io.BytesIO(data))


os.makedirs(os.path.dirname(OUT), exist_ok=True)
with tarfile.open(OUT, 'w:gz') as tar:
    for item in INCLUDE:
        add(tar, os.path.join(ROOT, item), f'LightBar/{item}')
print(OUT, os.path.getsize(OUT), 'bytes')

# The app's updater downloads the release asset named LightBar.tar.gz (same file, stable name).
LATEST = os.path.join(os.path.dirname(OUT), 'LightBar.tar.gz')
with open(OUT, 'rb') as src, open(LATEST, 'wb') as dst:
    dst.write(src.read())
print(LATEST)
