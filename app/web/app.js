'use strict';
/* LightBar UI - vanilla JS, controller-first (Steam Input gamepad / keyboard / mouse). */

const NUM = 17;
const STEAM_BLUE = '#1a9fff';
// same table as lightbar/looks.py: pattern -> number of colors
const PATTERNS = [
  ['solid', 'Solid', 1], ['gradient', 'Gradient', 2], ['rainbow', 'Rainbow', 0], ['custom', 'Per LED', NUM],
  ['breathe', 'Breathing', 1], ['patrol', 'Patrol', 1], ['wave', 'Color wave', 0], ['off', 'Off', 0],
];
const PATTERN = Object.fromEntries(PATTERNS.map(([id, label, n]) => [id, { label, n }]));
const ANIMATED = new Set(['breathe', 'patrol', 'wave']);
const PRESETS = ['#1a9fff', '#ffffff', '#ffd8a8', '#ff2a1f', '#ff7a00', '#ffd400', '#5cff3a', '#00e5a0',
  '#00e1ff', '#3d5bff', '#9b3dff', '#ff3dc8'];
const PREVIEW_NAMES = { fill: 'Progress fill', blink: 'Blinking', hw: 'Steam effect' };

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

const S = {
  state: null, stateJson: '', view: 'home', edit: null,
  focusedEl: null, focusMem: {}, lastTest: 0, testTimer: null, keepAlive: null,
};

// ================================================================ API
async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch('/api/' + path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

async function poll() {
  try {
    const st = await api('state');
    const json = JSON.stringify(st);
    if (json !== S.stateJson) {
      S.stateJson = json;
      S.state = st;
      renderHeader();
      if (S.view === 'home') renderHome(); else renderEditStatus();
    }
  } catch (e) {
    $('#now').innerHTML = '<span class="pill bad">LightBar service not running</span>';
  }
  setTimeout(poll, 1000);
}

// ================================================================ looks -> LED colors (mirrors looks.py)
const hexRgb = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const rgbHex = (c) => '#' + c.map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0')).join('');
function hsv(h, s, v) {
  h = ((h % 1) + 1) % 1;
  const i = Math.floor(h * 6), f = h * 6 - i, p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i % 6];
  return [r * 255, g * 255, b * 255];
}
function toHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if (d) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [((h / 6) + 1) % 1, mx ? d / mx : 0, mx];
}
function ledColors(look) {
  const cols = (look.colors || []).map(hexRgb);
  const p = look.pattern;
  if (['solid', 'breathe', 'patrol', 'fill', 'blink'].includes(p)) return Array(NUM).fill(cols[0] || hexRgb(STEAM_BLUE));
  if (p === 'gradient') {
    const [a, b] = [cols[0], cols[1] || cols[0]];
    return [...Array(NUM)].map((_, i) => a.map((v, k) => Math.round(v + (b[k] - v) * i / (NUM - 1))));
  }
  if (p === 'rainbow' || p === 'wave') return [...Array(NUM)].map((_, i) => hsv(i / NUM, 1, 1));
  if (p === 'custom' || p === 'hw') return [...Array(NUM)].map((_, i) => cols[i] || cols[cols.length - 1] || [0, 0, 0]);
  return Array(NUM).fill([0, 0, 0]);
}
// The animation is an approximation of the firmware effects: "Test on my Steam Machine" shows the real thing.
function frame(look, t) {
  const p = look.pattern, sp = look.speed || 5;
  const base = ledColors(look);
  const out = [];
  const range = look.range;
  for (let i = 0; i < NUM; i++) {
    let c = base[i], k = 1;
    if (p === 'off') k = 0;
    else if (p === 'breathe') { const per = 1.2 + (10 - sp) * 0.45; k = 0.06 + 0.94 * (0.5 - 0.5 * Math.cos(2 * Math.PI * t / per)); }
    else if (p === 'patrol') {
      const per = 0.7 + (10 - sp) * 0.3, ph = (t / per) % 2, pos = (ph < 1 ? ph : 2 - ph) * (NUM - 1);
      k = Math.max(0.04, 1 - Math.abs(i - pos) / 2.4);
    } else if (p === 'wave') { const per = 1.5 + (10 - sp) * 0.9; c = hsv(i / NUM - t / per, 1, 1); }
    else if (p === 'fill') { const per = 5, n = Math.floor(((t % per) / per) * (NUM + 4)); k = i < n ? 1 : 0.05; }
    else if (p === 'blink') k = (t % 1) < 0.5 ? 1 : 0;
    if (range && (i < range[0] || i > range[1])) k = 0;
    out.push([c, k]);
  }
  return out;
}

// ================================================================ strip rendering
const looksByKey = new Map();
function stripHtml(look, cls = '') {
  const key = JSON.stringify(look || { pattern: 'off' });
  if (looksByKey.size > 400) looksByKey.clear();
  looksByKey.set(key, look || { pattern: 'off' });
  return `<div class="strip ${cls}" data-look="${esc(key)}">${'<i></i>'.repeat(NUM)}</div>`;
}
function paintStrip(el, look, t) {
  const b = (look.brightness == null ? 70 : look.brightness) / 100;
  const vis = b <= 0 ? 0 : 0.3 + 0.7 * b;
  const leds = el.children;
  frame(look, t).forEach(([c, k], i) => {
    const a = k * vis;
    const led = leds[i];
    if (!led) return;
    const [r, g, bl] = c;
    led.style.background = `rgb(${Math.round(22 + (r - 22) * a)},${Math.round(25 + (g - 25) * a)},${Math.round(31 + (bl - 31) * a)})`;
    led.style.boxShadow = a > 0.02 ? `0 0 ${4 + 16 * a}px ${1 + 3 * a}px rgba(${r},${g},${bl},${0.6 * a})` : 'none';
  });
}
let lastPaint = 0;
function animate(ts) {
  if (ts - lastPaint > 33) {
    lastPaint = ts;
    const t = ts / 1000;
    document.querySelectorAll('.strip').forEach((el) => {
      const key = el.dataset.look;
      const look = looksByKey.get(key) || JSON.parse(key);
      const moving = ANIMATED.has(look.pattern) || ['fill', 'blink'].includes(look.pattern);
      if (!moving && el._painted === key) return;
      paintStrip(el, look, t);
      el._painted = key;
    });
  }
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

// ================================================================ focus / navigation
const visible = (el) => el.offsetParent !== null && !el.disabled && !el.classList.contains('disabled');
const topModal = () => modals[modals.length - 1] || null;
const scopeEl = () => (topModal() ? topModal().el : $('#app'));
const viewKey = () => (topModal() ? 'modal:' + topModal().id : S.view + (S.edit ? ':' + S.edit.id : ''));

function setFocus(el, noScroll) {
  if (!el) return;
  if (S.focusedEl && S.focusedEl !== el) S.focusedEl.classList.remove('focused');
  S.focusedEl = el;
  el.classList.add('focused');
  if (el.dataset.fid) S.focusMem[viewKey()] = el.dataset.fid;
  if (!noScroll) el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
  renderHints();
}
function restoreFocus(noScroll) {
  const scope = scopeEl();
  const fid = S.focusMem[viewKey()];
  let el = fid ? scope.querySelector(`[data-fid="${CSS.escape(fid)}"]`) : null;
  if (!el || !visible(el)) {
    const main = topModal() ? scope : $('#main');
    el = main.querySelector('[data-autofocus].focusable') || [...main.querySelectorAll('.focusable')].find(visible)
      || [...scope.querySelectorAll('.focusable')].find(visible);
  }
  if (el) setFocus(el, noScroll);
}
function patch(el, html) {
  const fid = S.focusedEl && el.contains(S.focusedEl) ? S.focusedEl.dataset.fid : null;
  el.innerHTML = html;
  if (fid) {
    const n = el.querySelector(`[data-fid="${CSS.escape(fid)}"]`);
    if (n && visible(n)) setFocus(n, true); else restoreFocus(true);
  } else if (!S.focusedEl || !document.body.contains(S.focusedEl)) restoreFocus(true);
}
function move(dir) {
  const scope = scopeEl();
  const items = [...scope.querySelectorAll('.focusable')].filter(visible);
  const cur = S.focusedEl && scope.contains(S.focusedEl) && visible(S.focusedEl) ? S.focusedEl : null;
  if (!cur) { if (items[0]) setFocus(items[0]); return; }
  const r = cur.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  let best = null, bestScore = Infinity;
  for (const el of items) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect();
    const x = b.left + b.width / 2, y = b.top + b.height / 2;
    let primary, secondary;
    if (dir === 'down') { if (y <= cy + 2 || b.top < r.bottom - r.height * 0.5) continue; primary = Math.max(0, b.top - r.bottom); secondary = Math.abs(x - cx); }
    else if (dir === 'up') { if (y >= cy - 2 || b.bottom > r.top + r.height * 0.5) continue; primary = Math.max(0, r.top - b.bottom); secondary = Math.abs(x - cx); }
    else if (dir === 'right') { if (x <= cx + 2 || b.left < r.right - r.width * 0.5) continue; primary = Math.max(0, b.left - r.right); secondary = Math.abs(y - cy) * 3; }
    else { if (x >= cx - 2 || b.right > r.left + r.width * 0.5) continue; primary = Math.max(0, r.left - b.right); secondary = Math.abs(y - cy) * 3; }
    const score = primary + secondary * 0.8;
    if (score < bestScore) { bestScore = score; best = el; }
  }
  if (best) setFocus(best);
}

// ================================================================ modals + toast
const modals = [];
let modalSeq = 0;
function openModal({ title = '', body = '', foot = '', cls = '', keys = {}, onClose }) {
  const wrap = document.createElement('div');
  wrap.className = 'modal-wrap';
  wrap.innerHTML = `<div class="modal ${cls}">${title ? `<h2>${esc(title)}</h2>` : ''}<div class="body">${body}</div>
    ${foot ? `<div class="foot">${foot}</div>` : ''}</div>`;
  wrap.addEventListener('click', (e) => { if (e.target === wrap) closeModal(); });
  $('#modals').appendChild(wrap);
  const m = { id: 'm' + (++modalSeq), el: wrap, keys, onClose, prevFocus: S.focusedEl, actions: {} };
  modals.push(m);
  restoreFocus(true);
  return m;
}
function closeModal(silent) {
  const m = modals.pop();
  if (!m) return;
  m.el.remove();
  if (!silent && m.onClose) m.onClose();
  if (m.prevFocus && document.body.contains(m.prevFocus)) setFocus(m.prevFocus, true); else restoreFocus(true);
}
function confirmBox(title, msg, ok = 'OK') {
  return new Promise((resolve) => {
    const m = openModal({
      title, body: `<p class="msg">${msg}</p>`,
      foot: `<button class="btn focusable" data-action="m" data-k="no" data-fid="no">Cancel</button>
             <button class="btn primary focusable" data-action="m" data-k="yes" data-fid="yes" data-autofocus>${esc(ok)}</button>`,
      onClose: () => resolve(false),
    });
    m.actions = { yes: () => { closeModal(true); resolve(true); }, no: () => { closeModal(true); resolve(false); } };
  });
}
let toastTimer = null;
function toast(msg, bad) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, 3200);
}

// ================================================================ text helpers
function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}
function patternName(look) {
  if (!look) return '';
  if (look.pattern === 'hw') return `Steam effect "${look.effect}"`;
  return (PATTERN[look.pattern] || {}).label || PREVIEW_NAMES[look.pattern] || look.pattern;
}
const startupLook = (cur) => ({ pattern: 'breathe', colors: [cur.color], brightness: cur.brightness, speed: 4 });
// What a situation looks like right now, and where that comes from.
function shownFor(s) {
  if (s.kind === 'firmware') return { look: s.look, src: 'Set by the hardware', tag: 'fw' };
  if (s.kind === 'startup') {
    if (!s.current) return { look: s.steam, src: 'Not available with this driver', tag: 'fw' };
    return { look: startupLook(s.current), src: 'Saved in the light bar', tag: 'mine' };
  }
  const enabled = S.state.enabled;
  if (s.mode === 'custom' && enabled) return { look: s.look, src: 'Your look', tag: 'mine' };
  const paused = s.mode === 'custom' ? ' (LightBar is paused)' : '';
  if (s.observed) return { look: s.observed.look, src: `Steam · seen ${ago(s.observed.seen)}${paused}`, tag: 'steam' };
  if (s.steam) return { look: s.steam, src: `Steam default · not seen yet${paused}`, tag: 'steam' };
  return { look: null, src: `${s.steam_note}${paused}`, tag: 'steam' };
}

// ================================================================ header / hints
function renderHeader() {
  const st = S.state;
  if (!st) return;
  let src = 'Steam';
  if (st.testing) src = 'Testing';
  else if (st.controlling) src = 'Your look';
  const where = st.situation_name || 'Starting up';
  $('#now').innerHTML = `<span class="pill">${stripHtml(st.live, 'tiny')}<b>${esc(where)}</b><span class="muted">· ${esc(src)}</span></span>`;
}
function renderHints() {
  const h = [];
  const el = S.focusedEl;
  if (el && el.classList.contains('slider')) h.push(['◀ ▶', 'Adjust']);
  h.push(['A', 'Select'], ['B', topModal() ? 'Close' : S.view === 'home' ? 'Exit' : 'Back']);
  if (S.view === 'edit' && !topModal()) {
    if (canTest()) h.push(['X', S.edit.testing ? 'Stop test' : 'Test']);
    h.push(['Y', 'Save']);
  }
  $('#hints').innerHTML = h.map(([k, v]) => `<span><kbd>${k}</kbd>${esc(v)}</span>`).join('');
}

// ================================================================ home
function renderHome() {
  const st = S.state;
  if (!st) return;
  const banners = [];
  if (st.simulated) banners.push(['warn', 'No light bar found, so this is a simulation. Previews work, but nothing reaches the hardware. On a Steam Machine this means the <code>leds-valve</code> driver isn\'t loaded.']);
  if (st.error) banners.push(['bad', esc(st.error)]);
  if (!st.enabled) banners.push(['warn', 'LightBar is paused: Steam controls the light bar in every situation.']);
  const sits = st.situations;
  const upd = updateBanner(st.update);
  const card = (s) => {
    const sh = shownFor(s);
    const now = st.situation === s.id;
    return `<div class="card focusable ${now ? 'now' : ''}" data-action="open" data-id="${s.id}" data-fid="card:${s.id}">
      <div class="card-top"><span class="title">${esc(s.name)}</span>${now ? '<span class="badge">NOW</span>' : ''}</div>
      ${sh.look ? stripHtml(sh.look) : '<div class="strip-empty">—</div>'}
      <div class="card-src ${sh.tag}">${esc(sh.src)}${sh.look ? ` · ${esc(patternName(sh.look))}` : ''}</div>
    </div>`;
  };
  const live = st.live || { pattern: 'off' };
  const liveSrc = st.testing ? 'Testing a look' : st.controlling ? 'Your look' : 'Steam\'s look';
  const html = `<div class="page">
    ${upd}
    ${banners.map(([c, m]) => `<div class="banner ${c}">${m}</div>`).join('')}
    <section class="hero">
      <div class="hero-text"><div class="eyebrow">Right now on your Steam Machine</div>
        <div class="hero-title">${esc(st.situation_name || 'Not in Game Mode or Desktop Mode')}</div>
        <div class="muted">${esc(liveSrc)} · ${esc(patternName(live))}${live.pattern !== 'off' ? ` · ${live.brightness}%` : ''}</div></div>
      <div class="machine">${stripHtml(live, 'big')}</div>
    </section>
    <div class="section-title">What the light bar shows <span class="muted">Select one to change it</span></div>
    <div class="grid">${sits.filter((s) => s.kind !== 'firmware').map(card).join('')}</div>
    <div class="section-title">Set by the hardware <span class="muted">Shown for reference, these can't be changed</span></div>
    <div class="grid small">${sits.filter((s) => s.kind === 'firmware').map(card).join('')}</div>
    <div class="section-title">LightBar</div>
    <div class="settings">
      <div class="setting focusable" data-action="toggleEnabled" data-fid="set:enabled"><div class="grow"><div class="t">Use my looks</div>
        <div class="d">Off hands the light bar back to Steam everywhere, without forgetting your looks.</div></div>
        <div class="switch ${st.enabled ? 'on' : ''}"><i></i></div></div>
      <div class="setting focusable" data-action="updateCheck" data-fid="set:update"><div class="grow"><div class="t">Check for updates</div>
        <div class="d">${esc(updateLine(st.update))}</div></div><span class="chev">›</span></div>
      <div class="setting focusable" data-action="about" data-fid="set:about"><div class="grow"><div class="t">About LightBar ${esc(st.version)}</div>
        <div class="d">${st.hardware.found ? `${st.hardware.count} LEDs found · ${st.hardware.writable ? 'writable' : 'no write permission'}` : 'No light bar driver found'}</div></div><span class="chev">›</span></div>
    </div></div>`;
  patch($('#main'), html);
}

// ================================================================ updates
function updateLine(u) {
  if (!u) return '';
  const when = u.checked ? ` · checked ${ago(u.checked)}` : '';
  switch (u.status) {
    case 'checking': return 'Checking GitHub...';
    case 'available': return `LightBar ${u.latest} is available (you have ${u.current})`;
    case 'downloading': return `Downloading ${u.latest}... ${u.progress}%`;
    case 'ready': return `LightBar ${u.latest} is ready: restart to install it`;
    case 'needs_installer': return `LightBar ${u.latest} needs install.sh to be run again`;
    case 'failed': return `LightBar ${u.latest} didn't start on this machine and was rolled back`;
    case 'error': return u.error || 'The update check failed';
    case 'uptodate': return `LightBar ${u.current} is the latest version${when}`;
    default: return `LightBar ${u.current}`;
  }
}
function updateBanner(u) {
  if (!u) return '';
  const btn = (action, label, fid, primary) =>
    `<button class="btn small ${primary ? 'primary' : ''} focusable" data-action="${action}" data-fid="${fid}">${label}</button>`;
  const row = (cls, text, buttons = '') => `<div class="banner ${cls} with-actions"><span>${text}</span><span class="acts">${buttons}</span></div>`;
  const notes = u.notes ? btn('updateNotes', 'What\'s new', 'upd:notes') : '';
  if (u.status === 'available') return row('info', `<b>LightBar ${esc(u.latest)}</b> is available.`, notes + btn('updateDownload', 'Download', 'upd:go', true));
  if (u.status === 'downloading') return row('info', `Downloading LightBar ${esc(u.latest)}... ${u.progress}%`);
  if (u.status === 'ready') return row('good', `<b>LightBar ${esc(u.latest)}</b> is ready to install.`, notes + btn('updateRestart', 'Restart now', 'upd:go', true));
  if (u.status === 'needs_installer') return row('warn', `LightBar ${esc(u.latest)} needs a new runtime: run <code>install.sh</code> from the release to update.`);
  if (u.status === 'error' && u.checked !== undefined && S.updateAsked) return row('warn', esc(u.error || 'The update check failed'), btn('updateCheck', 'Retry', 'upd:retry'));
  return '';
}
async function updateDownload() {
  try { await api('update/check', { download: true }); } catch (e) { toast(e.message, true); }
}
async function updateRestart() {
  if (!window.lightbar) return toast('Close and reopen LightBar to install the update');
  const r = await window.lightbar.restart();
  if (r && r.reopen) toast('Open LightBar again from your Steam library to finish the update');
}
function updateNotes() {
  const u = S.state && S.state.update;
  if (!u) return;
  const m = openModal({
    title: `LightBar ${u.latest}`, body: `<p class="msg" style="white-space:pre-wrap">${esc(u.notes || 'No release notes.')}</p>`,
    foot: '<button class="btn primary focusable" data-action="m" data-k="close" data-fid="close" data-autofocus>Close</button>',
  });
  m.actions = { close: () => closeModal() };
}
async function updateCheck() {
  S.updateAsked = true;
  try { await api('update/check', {}); } catch (e) { toast(e.message, true); }
}

// ================================================================ editor
function openSituation(id) {
  const s = S.state.situations.find((x) => x.id === id);
  if (!s) return;
  if (s.kind === 'firmware') return showFirmware(s);
  if (s.kind === 'startup' && !s.current) {
    return toast('This light bar driver has no power-on settings', true);
  }
  const look = s.kind === 'startup'
    ? { pattern: 'solid', colors: [s.current.color], brightness: s.current.brightness, speed: 5 }
    : JSON.parse(JSON.stringify(s.look));
  S.edit = { id, kind: s.kind, name: s.name, desc: s.desc, mode: s.mode || 'custom', look, dirty: false, testing: false };
  S.view = 'edit';
  renderEdit();
  restoreFocus(true);
}
function editPreviewLook() {
  const e = S.edit;
  if (e.kind === 'startup') return startupLook({ color: e.look.colors[0], brightness: e.look.brightness });
  if (e.mode === 'custom') return e.look;
  const s = S.state.situations.find((x) => x.id === e.id);
  return (s.observed && s.observed.look) || s.steam || { pattern: 'off' };
}
function slider(key, label, val, min, max, unit = '') {
  const pct = ((val - min) / (max - min)) * 100;
  return `<div class="slider focusable" data-slider="${key}" data-min="${min}" data-max="${max}" data-fid="sl:${key}">
    <div class="sl-top"><span>${esc(label)}</span><b>${val}${unit}</b></div>
    <div class="track"><div class="fill" style="width:${pct}%"></div><div class="knob" style="left:${pct}%"></div></div></div>`;
}
function renderEdit() {
  const e = S.edit;
  const lk = e.look;
  const steamMode = e.kind === 'os' && e.mode === 'steam';
  const s = S.state.situations.find((x) => x.id === e.id);
  let controls = '';
  if (e.kind === 'os') {
    controls += `<div class="field"><div class="label">Who decides</div><div class="chips">
      <div class="chip focusable ${e.mode === 'steam' ? 'active' : ''}" data-action="mode" data-mode="steam" data-fid="mode:steam" ${e.mode === 'steam' ? 'data-autofocus' : ''}>Steam</div>
      <div class="chip focusable ${e.mode === 'custom' ? 'active' : ''}" data-action="mode" data-mode="custom" data-fid="mode:custom" ${e.mode === 'custom' ? 'data-autofocus' : ''}>My look</div></div></div>`;
    controls += `<div class="field ${steamMode ? 'dim' : ''}"><div class="label">Pattern</div><div class="chips">
      ${PATTERNS.map(([id, label]) => `<div class="chip focusable ${lk.pattern === id ? 'active' : ''}" data-action="pattern" data-p="${id}" data-fid="pat:${id}">${label}</div>`).join('')}</div></div>`;
  }
  const n = e.kind === 'startup' ? 1 : PATTERN[lk.pattern].n;
  if (n) {
    const sw = lk.colors.slice(0, n).map((c, i) => `<div class="swatch focusable ${n === NUM ? 'led' : ''}" data-action="color" data-i="${i}" data-fid="col:${i}" ${e.kind === 'startup' && !i ? 'data-autofocus' : ''} style="--c:${c}">${n === NUM ? '' : `<span>${c.toUpperCase()}</span>`}</div>`).join('');
    const label = n === NUM ? 'LED colors (left to right)' : n === 2 ? 'Colors (left → right)' : 'Color';
    controls += `<div class="field ${steamMode ? 'dim' : ''}"><div class="label">${label}</div><div class="swatches ${n === NUM ? 'leds' : ''}">${sw}
      ${n === NUM ? `<div class="chip focusable" data-action="fillFrom" data-fid="col:fill">Start from…</div>` : ''}</div></div>`;
  }
  if (lk.pattern !== 'off' || e.kind === 'startup') {
    controls += `<div class="field ${steamMode ? 'dim' : ''}">${slider('brightness', 'Brightness', lk.brightness, 0, 100, '%')}</div>`;
  }
  if (e.kind === 'os' && ANIMATED.has(lk.pattern)) {
    controls += `<div class="field ${steamMode ? 'dim' : ''}">${slider('speed', 'Speed', lk.speed, 1, 10)}</div>`;
  }
  let note = '';
  if (e.kind === 'startup') note = 'Saved into the light bar\'s own memory, so it shows before SteamOS starts. The breathing pattern itself is the firmware\'s.';
  else if (steamMode) note = `Steam decides this one: ${esc(s.steam_note.charAt(0).toLowerCase() + s.steam_note.slice(1))}. Pick "My look" to use your own.`;
  else note = 'Stays on after you close LightBar. The preview shows roughly how the effects move; test it to see the real thing.';
  const testBtn = canTest()
    ? `<button class="btn ${e.testing ? 'good' : ''} focusable" data-action="test" data-fid="ed:test">${e.testing ? '● Testing on the light bar' : 'Test on my Steam Machine'}</button>` : '';
  const html = `<div class="page edit">
    <div class="crumb"><span class="link focusable" data-action="back" data-fid="ed:back">‹ All situations</span></div>
    <div class="edit-grid">
      <div class="edit-left">
        <h1>${esc(e.name)}</h1><p class="muted">${esc(e.desc)}</p>
        <div class="machine">${stripHtml(editPreviewLook(), 'big')}</div>
        <div class="preview-cap muted" id="edit-status"></div>
        <div class="edit-actions">${testBtn}</div>
        <p class="note">${note}</p>
      </div>
      <div class="edit-right">${controls}
        <div class="edit-actions right">
          <button class="btn focusable" data-action="back" data-fid="ed:cancel">Cancel</button>
          <button class="btn primary focusable" data-action="save" data-fid="ed:save">${e.kind === 'startup' ? 'Save to light bar' : 'Save'}</button>
        </div>
      </div>
    </div></div>`;
  patch($('#main'), html);
  renderEditStatus();
  renderHints();
}
// a power-on color is tried as a solid color first: the real thing only shows when powering on
const canTest = () => !!S.edit && (S.edit.kind === 'startup' || S.edit.mode === 'custom');
function renderEditStatus() {
  const el = $('#edit-status');
  if (!el || !S.edit || !S.state) return;
  const now = S.state.situation === S.edit.id;
  const parts = [];
  if (now) parts.push('This is the situation your Steam Machine is in right now.');
  if (S.edit.dirty) parts.push('Not saved yet.');
  el.textContent = parts.join(' ');
}
function changed(redraw = true) {
  const e = S.edit;
  e.dirty = true;
  if (e.kind === 'os' && e.mode === 'steam') { e.mode = 'custom'; redraw = true; } // editing means you want your own look
  if (redraw) renderEdit(); else {
    const strip = $('.edit .machine .strip');
    if (strip) strip.outerHTML = stripHtml(editPreviewLook(), 'big');
    renderEditStatus();
  }
  pushTest();
}
function setPattern(p) {
  const e = S.edit, lk = e.look;
  const n = PATTERN[p].n;
  const prev = ledColors(lk).map(rgbHex);
  let cols = lk.colors.slice();
  if (n === NUM) cols = lk.pattern === 'off' ? Array(NUM).fill(STEAM_BLUE) : prev;
  else if (n) {
    if (!cols.length) cols = [prev[0] === '#000000' ? STEAM_BLUE : prev[0]];
    while (cols.length < n) cols.push(n === 2 ? '#9b3dff' : cols[cols.length - 1]);
    cols = cols.slice(0, Math.max(n, 1));
  }
  lk.pattern = p;
  lk.colors = n ? cols.slice(0, n) : [];
  changed();
}

// live test: every change is sent to the light bar while testing (throttled)
function pushTest(force) {
  const e = S.edit;
  if (!e || !e.testing) return;
  const send = () => {
    S.lastTest = Date.now();
    api('test', { look: e.look, seconds: 30 }).then((r) => { if (r.error) toast(r.error, true); }).catch((err) => toast(err.message, true));
  };
  clearTimeout(S.testTimer);
  const wait = 150 - (Date.now() - S.lastTest);
  if (force || wait <= 0) send(); else S.testTimer = setTimeout(send, wait);
}
function setTesting(on) {
  const e = S.edit;
  if (!e) return;
  e.testing = on;
  clearInterval(S.keepAlive);
  if (on) {
    pushTest(true);
    S.keepAlive = setInterval(() => pushTest(true), 20000);
  } else {
    clearTimeout(S.testTimer);
    api('test/stop', {}).catch(() => {});
  }
}
async function save() {
  const e = S.edit;
  try {
    if (e.kind === 'startup') {
      if (!await confirmBox('Save to the light bar?', 'This is written into the light bar\'s own memory. Only save when you\'re happy with it, not on every small change.', 'Save')) return;
      await api('startup', { color: e.look.colors[0], brightness: e.look.brightness });
      toast('Saved: your Steam Machine powers on in this color');
    } else {
      await api('situation', { id: e.id, mode: e.mode, look: e.look });
      toast(e.mode === 'custom' ? 'Saved. It stays on after you close LightBar.' : 'Saved. Steam decides this one again.');
    }
    e.dirty = false;
    leaveEdit(true);
  } catch (err) { toast(err.message, true); }
}
async function leaveEdit(saved) {
  const e = S.edit;
  if (!e) return;
  if (!saved && e.dirty && !await confirmBox('Discard changes?', `Your changes to "${esc(e.name)}" haven't been saved.`, 'Discard')) return;
  if (e.testing) setTesting(false);
  S.edit = null;
  S.view = 'home';
  S.stateJson = '';
  renderHome();
  restoreFocus(true);
  poll1();
}
async function poll1() { try { S.state = await api('state'); S.stateJson = JSON.stringify(S.state); renderHeader(); if (S.view === 'home') renderHome(); } catch (e) { /* poll() reports it */ } }

// ================================================================ color picker
function pickColor(start, onPick, extra = '') {
  let [h, s, v] = toHsv(hexRgb(start));
  let cur = start;
  const body = () => {
    cur = rgbHex(hsv(h, s, v));
    return `<div class="picker">
      <div class="presets">${PRESETS.map((c, i) => `<div class="swatch round focusable ${c === cur ? 'sel' : ''}" data-action="m" data-k="preset" data-c="${c}" data-fid="pre:${i}" style="--c:${c}"></div>`).join('')}</div>
      <div class="picked"><div class="big-sw" style="--c:${cur}"></div><b>${cur.toUpperCase()}</b></div>
      ${slider('hue', 'Hue', Math.round(h * 360), 0, 359, '°')}
      ${slider('sat', 'Saturation', Math.round(s * 100), 0, 100, '%')}
      ${slider('val', 'Brightness of this color', Math.round(v * 100), 0, 100, '%')}
      ${extra}</div>`;
  };
  const m = openModal({
    title: 'Pick a color', body: body(), cls: 'wide',
    foot: `<button class="btn focusable" data-action="m" data-k="cancel" data-fid="cancel">Cancel</button>
           <button class="btn primary focusable" data-action="m" data-k="done" data-fid="done">Use this color</button>`,
  });
  const redraw = () => patch($('.body', m.el), body());
  m.slide = (key, val) => {
    if (key === 'hue') h = val / 360; else if (key === 'sat') s = val / 100; else v = val / 100;
    redraw();
  };
  m.actions = {
    preset: (d) => { [h, s, v] = toHsv(hexRgb(d.c)); redraw(); },
    cancel: () => closeModal(),
    done: () => { closeModal(true); onPick(cur); },
  };
  setTimeout(() => {
    const sel = $('.presets .sel', m.el);
    if (sel) setFocus(sel, true);
  });
  return m;
}
function editColor(i) {
  const e = S.edit;
  const custom = e.kind === 'os' && e.look.pattern === 'custom';
  const m = pickColor(e.look.colors[i], (c) => { e.look.colors[i] = c; changed(); },
    custom ? `<button class="btn small focusable" data-action="m" data-k="all" data-fid="all">Use for all 17 LEDs</button>` : '');
  if (custom) {
    m.actions.all = () => {
      const c = $('.picked b', m.el).textContent.toLowerCase();
      closeModal(true);
      e.look.colors = Array(NUM).fill(c);
      changed();
    };
  }
}
function fillFrom() {
  const e = S.edit;
  const opts = [['rainbow', 'Rainbow'], ['gradient', 'Blue → purple gradient'], ['alt', 'Alternate two colors'], ['ends', 'Bright ends, dim middle']];
  const m = openModal({
    title: 'Start from', body: `<div class="opts">${opts.map(([k, l], i) => `<div class="opt focusable" data-action="m" data-k="pick" data-v="${k}" data-fid="o${i}" ${i ? '' : 'data-autofocus'}>${l}</div>`).join('')}</div>`,
  });
  m.actions = {
    pick: (d) => {
      closeModal(true);
      const a = e.look.colors[0] || STEAM_BLUE;
      if (d.v === 'rainbow') e.look.colors = ledColors({ pattern: 'rainbow' }).map(rgbHex);
      else if (d.v === 'gradient') e.look.colors = ledColors({ pattern: 'gradient', colors: [STEAM_BLUE, '#9b3dff'] }).map(rgbHex);
      else if (d.v === 'alt') e.look.colors = [...Array(NUM)].map((_, i) => (i % 2 ? '#ffffff' : a));
      else e.look.colors = [...Array(NUM)].map((_, i) => { const k = Math.abs(i - 8) / 8; return rgbHex(hexRgb(a).map((x) => x * (0.15 + 0.85 * k))); });
      changed();
    },
  };
}

// ================================================================ firmware / about
function showFirmware(s) {
  const m = openModal({
    title: s.name, cls: 'wide',
    body: `<div class="machine">${stripHtml(s.look, 'big')}</div><p class="msg">${esc(s.desc)}</p>
      <p class="note">The Steam Machine's firmware shows this by itself, even when SteamOS isn't running, so it can't be changed. The animation is an illustration.</p>`,
    foot: '<button class="btn primary focusable" data-action="m" data-k="close" data-fid="close" data-autofocus>Close</button>',
  });
  m.actions = { close: () => closeModal() };
}
function about() {
  const st = S.state;
  const m = openModal({
    title: `LightBar ${st.version}`,
    body: `<p class="msg">LightBar runs as a small background service, so your looks stay on after you close the app and come back after a restart.</p>
      <p class="note">It works out the situation from what's running: a game started from your library counts as playing, and downloads come from Steam's download log.
      When Steam changes the light bar during one of your looks, LightBar puts your look back within a few seconds.</p>
      <p class="note">Driver: ${st.hardware.found ? `valve-leds, ${st.hardware.count} LEDs, ${st.hardware.writable ? 'writable' : 'not writable (re-run install.sh)'}, power-on settings ${st.hardware.startup ? 'available' : 'not available'}` : 'not found'}${st.simulated ? ' (simulation)' : ''}.<br>
      Logs: ~/.local/share/lightbar/data/logs/service.log</p>`,
    foot: '<button class="btn primary focusable" data-action="m" data-k="close" data-fid="close" data-autofocus>Close</button>',
  });
  m.actions = { close: () => closeModal() };
}

// ================================================================ actions
const ACTIONS = {
  open: (d) => openSituation(d.id),
  back: () => back(),
  exit: () => confirmExit(),
  about: () => about(),
  updateCheck: () => updateCheck(),
  updateDownload: () => updateDownload(),
  updateRestart: () => updateRestart(),
  updateNotes: () => updateNotes(),
  toggleEnabled: async () => {
    try { S.state = await api('enabled', { enabled: !S.state.enabled }); S.stateJson = ''; renderHome(); } catch (e) { toast(e.message, true); }
  },
  mode: (d) => { S.edit.mode = d.mode; S.edit.dirty = true; if (d.mode === 'steam' && S.edit.testing) setTesting(false); renderEdit(); },
  pattern: (d) => setPattern(d.p),
  color: (d) => editColor(+d.i),
  fillFrom: () => fillFrom(),
  test: () => { setTesting(!S.edit.testing); renderEdit(); },
  save: () => save(),
  m: (d) => { const m = topModal(); if (m && m.actions[d.k]) m.actions[d.k](d); },
};
function runAction(el) { const fn = ACTIONS[el.dataset.action]; if (fn) fn(el.dataset, el); }

function adjustSlider(el, dir, absolute) {
  const key = el.dataset.slider, min = +el.dataset.min, max = +el.dataset.max;
  const m = topModal();
  const cur = +el.querySelector('b').textContent.replace(/[^\d-]/g, '');
  const step = key === 'speed' ? 1 : key === 'hue' ? 6 : 5;
  const val = clamp(absolute != null ? absolute : cur + dir * step, min, max);
  if (val === cur) return;
  if (m && m.slide) return m.slide(key, val);
  if (!S.edit) return;
  S.edit.look[key] = val;
  const pct = ((val - min) / (max - min)) * 100;
  el.querySelector('b').textContent = val + (key === 'brightness' ? '%' : '');
  el.querySelector('.fill').style.width = pct + '%';
  el.querySelector('.knob').style.left = pct + '%';
  changed(false);
}
function sliderFromPointer(el, x) {
  const tr = el.querySelector('.track').getBoundingClientRect();
  const min = +el.dataset.min, max = +el.dataset.max;
  adjustSlider(el, 0, Math.round(min + clamp((x - tr.left) / tr.width, 0, 1) * (max - min)));
}

let dragging = null;
document.addEventListener('pointerdown', (e) => {
  const sl = e.target.closest('.slider');
  if (sl && e.target.closest('.track')) { dragging = sl; setFocus(sl, true); sliderFromPointer(sl, e.clientX); }
});
document.addEventListener('pointermove', (e) => {
  document.body.classList.add('mouse');
  if (dragging) {
    // the picker redraws its sliders: follow the new element with the same id
    if (!document.body.contains(dragging)) dragging = document.querySelector(`[data-fid="${CSS.escape(dragging.dataset.fid)}"]`);
    if (dragging) sliderFromPointer(dragging, e.clientX);
  }
}, { passive: true });
document.addEventListener('pointerup', () => { dragging = null; });
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  if (el.classList.contains('focusable')) setFocus(el, true);
  runAction(el);
});

function back() {
  if (topModal()) return closeModal();
  if (S.view === 'edit') return leaveEdit(false);
  confirmExit();
}
async function confirmExit() {
  if (topModal()) return;
  if (await confirmBox('Exit LightBar?', 'Your looks stay on: LightBar keeps running in the background.', 'Exit')) doQuit();
}
function doQuit() { if (window.lightbar) window.lightbar.quit(); else window.close(); }

// ================================================================ input: gamepad + keyboard
const BTN = { 0: 'a', 1: 'b', 2: 'x', 3: 'y', 12: 'up', 13: 'down', 14: 'left', 15: 'right' };
const DIRS = ['up', 'down', 'left', 'right'];
let gpPrev = {}, gpNext = {};
function gpLoop(ts) {
  const pads = navigator.getGamepads ? Array.from(navigator.getGamepads()).filter(Boolean) : [];
  const now = {};
  for (const p of pads) {
    p.buttons.forEach((b, i) => { if (b && b.pressed && BTN[i]) now[BTN[i]] = true; });
    const ax = p.axes[0] || 0, ay = p.axes[1] || 0;
    if (ay < -0.6) now.up = true; if (ay > 0.6) now.down = true;
    if (ax < -0.6) now.left = true; if (ax > 0.6) now.right = true;
  }
  for (const k of Object.keys(now)) {
    if (!gpPrev[k]) { press(k); gpNext[k] = ts + 380; }
    else if (DIRS.includes(k) && ts >= gpNext[k]) { press(k); gpNext[k] = ts + 70; }
  }
  gpPrev = now;
  requestAnimationFrame(gpLoop);
}
requestAnimationFrame(gpLoop);

function press(k) {
  document.body.classList.remove('mouse');
  const el = S.focusedEl;
  if ((k === 'left' || k === 'right') && el && el.classList.contains('slider') && document.body.contains(el)) {
    return adjustSlider(el, k === 'left' ? -1 : 1);
  }
  if (DIRS.includes(k)) return move(k);
  if (k === 'a') { if (el && document.body.contains(el)) runAction(el); return; }
  if (k === 'b') return back();
  if (topModal() || S.view !== 'edit') return;
  if (k === 'x' && canTest()) { setTesting(!S.edit.testing); renderEdit(); }
  if (k === 'y') save();
}
document.addEventListener('keydown', (e) => {
  const map = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'a', ' ': 'a',
    Escape: 'b', Backspace: 'b', x: 'x', t: 'x', y: 'y', s: 'y' };
  const k = map[e.key];
  if (k) { e.preventDefault(); press(k); }
});

window.addEventListener('beforeunload', () => {
  if (S.edit && S.edit.testing) fetch('/api/test/stop', { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: '{}' });
});

// #<situation id> opens that situation directly (the desktop entry or a script can link to one)
(async () => {
  await poll1();
  // opening the app: tell the service this version started fine (ends an update's trial run),
  // then look for a newer release on GitHub once. The service does the work in the background.
  try {
    const r = await api('update/confirm', {});
    if (r.updated) toast(`Updated to LightBar ${r.updated}`);
    await api('update/check', {});
  } catch (e) { /* offline or an old service: the settings row shows the status */ }
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && S.state && S.state.situations.some((s) => s.id === id)) openSituation(id);
  setTimeout(poll, 1000);
})();
renderHints();
