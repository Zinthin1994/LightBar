// LightBar shell: makes sure the LightBar service is running and shows its UI fullscreen.
// The service (lightbar.service) keeps the light bar looks applied after this window closes.
const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const APP_DIR = process.env.LIGHTBAR_APP || path.resolve(__dirname, '..');
const ROOT = process.env.LIGHTBAR_HOME || path.resolve(APP_DIR, '..');
const PORT = parseInt(process.env.LIGHTBAR_PORT || '47831', 10);
const BASE = `http://127.0.0.1:${PORT}`;

let win = null;

app.commandLine.appendSwitch('disable-gpu-sandbox');
app.commandLine.appendSwitch('enable-gamepad-button-axis-events');

function ping() {
  return new Promise((resolve) => {
    const req = http.get(`${BASE}/api/ping`, { timeout: 2000 }, (res) => { res.resume(); resolve(res.statusCode === 200); });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

async function ensureService() {
  if (await ping()) return true;
  let started = false;
  if (process.platform === 'linux') {
    started = spawnSync('systemctl', ['--user', 'start', 'lightbar.service'], { stdio: 'ignore' }).status === 0;
  }
  if (!started) {
    // not installed as a service (development): run it next to the window
    fs.mkdirSync(path.join(ROOT, 'data', 'logs'), { recursive: true });
    const out = fs.openSync(path.join(ROOT, 'data', 'logs', 'service.stdout.log'), 'a');
    spawn(process.platform === 'win32' ? 'python' : 'python3', ['-m', 'lightbar.server'], {
      cwd: APP_DIR, env: { ...process.env, PYTHONPATH: APP_DIR, LIGHTBAR_HOME: ROOT, PYTHONUNBUFFERED: '1' },
      detached: true, stdio: ['ignore', out, out],
    }).unref();
  }
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 250));
    if (await ping()) return true;
  }
  return false;
}

const isOurs = (url) => typeof url === 'string' && (url === BASE || url.startsWith(`${BASE}/`));

function createWindow() {
  win = new BrowserWindow({
    fullscreen: true, width: 1280, height: 800, backgroundColor: '#0a0c11', autoHideMenuBar: true,
    title: 'LightBar', icon: path.join(APP_DIR, 'art', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  win.setMenuBarVisibility(false);
  win.webContents.on('will-navigate', (e, url) => { if (!isOurs(url)) e.preventDefault(); });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('before-input-event', (e, input) => {
    if (input.type !== 'keyDown') return;
    if (input.key === 'F11') { win.setFullScreen(!win.isFullScreen()); e.preventDefault(); }
    if (input.control && input.key.toLowerCase() === 'q') { e.preventDefault(); app.quit(); }
  });
  win.loadURL(`${BASE}/`);
}

ipcMain.handle('quit', (e) => {
  if (e.senderFrame && isOurs(e.senderFrame.url)) app.quit();
});

app.whenReady().then(async () => {
  const ok = await ensureService();
  createWindow();
  if (!ok) {
    win.loadURL('data:text/html,' + encodeURIComponent(
      '<body style="background:#0a0c11;color:#fff;font:20px sans-serif;padding:60px">' +
      '<h1>LightBar could not start its service</h1><p>Check ~/.local/share/lightbar/data/logs/service.log ' +
      'and re-run install.sh.</p><p>Press Ctrl+Q to close.</p></body>'));
  }
});

app.on('window-all-closed', () => app.quit());
