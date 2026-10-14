# LightBar

Set up the light bar on the front of your Steam Machine from Game Mode, with a controller.

- **See every situation at a glance.** Home screen, playing, downloading, Desktop Mode and
  powering on, plus the hardware's own signals (sleep, BIOS update, overheating, hardware
  errors). Each shows what the light bar looks like there right now.
- **Design a look.** Solid, gradient, rainbow, per-LED colors, breathing, patrol, color wave
  or off, with color, brightness and speed. An animated preview shows it in the app.
- **Test it on the real light bar.** While testing, every change shows up on the Steam
  Machine straight away.
- **Presets.** Thirteen built-in looks (Ember, Ocean, Aurora, Candle, ...) plus your own:
  **Save as preset** in the editor stores the current look, **Presets…** applies one.
- **Copy to…** reuses a look for other situations in one go.
- **Night dimming.** Dim your looks, or switch them off, between two times (it can cross
  midnight). It only touches looks LightBar sets; whatever is left to Steam is not touched,
  and a look already dimmer than the night level stays as it is.
- **Updates.** The app checks GitHub for a newer release when it opens and installs it
  after you press Download and Restart; a version that fails to start is rolled back.
- **It stays on.** A small background service (`lightbar.service`) applies your looks when
  the app is closed and after a restart. If Steam changes the light bar during one of your
  looks, LightBar puts it back within a few seconds.

## Install

Copy the `LightBar` folder to the Steam Machine, then in Desktop Mode open Konsole:

```
cd LightBar
bash install.sh
```

The installer:

1. copies LightBar to `~/.local/share/lightbar`;
2. installs a udev rule (`/etc/udev/rules.d/99-lightbar.rules`) so LightBar may write to the
   light bar. The driver only lets root do that by default. This step asks for your
   password; if you never set one, run `passwd` first;
3. downloads Electron (the app window), or copies it from PlayVault if that's installed;
4. starts `lightbar.service`;
5. adds a **LightBar** tile to your Steam library (Steam closes for a moment).

Run `install.sh` again to update; your looks are kept. `bash uninstall.sh` removes
everything and hands the light bar back to Steam.

## How it works

SteamOS's `leds-valve` driver exposes the light bar as 17 RGB LEDs,
`/sys/class/leds/valve-leds[0..16]` (`multi_intensity`, `brightness`, `effect`, `enabled`,
`delay`, plus `multi_intensity_startup` / `brightness_startup` for power-on).

| Situation | How LightBar recognises it | Who decides |
|---|---|---|
| Home screen | Game Mode (gamescope) with Steam running | Steam, or your look |
| Playing a game | a library launch is running (Steam's `reaper … SteamLaunch AppId=`) | Steam, or your look |
| Downloading | Steam's `logs/content_log.txt` shows an update running | Steam, or your look |
| Desktop Mode | KDE Plasma is running, no gamescope | Steam, or your look |
| Powering on | — | color and brightness saved in the light bar's own memory |
| Sleep, off, BIOS, alerts | — | firmware only (shown for reference) |

If two apply at once, playing wins over downloading. When a situation is set to "Steam",
LightBar doesn't touch the light bar there. It records what Steam shows so the app can
display it.

### Limits

- The animated previews of breathing, patrol and color wave are approximations; the
  firmware runs the real animation. Use **Test on my Steam Machine** to see it.
- Download detection reads Steam's log. A download Steam doesn't log won't be noticed.
- Saving a power-on look writes to the light bar's flash memory. Only save when you're
  happy with it.
- Error patterns (red quadrants and so on) are drawn from the published Steam Machine
  light bar meanings and can't be changed.

## Development

Everything except the light bar itself runs on Windows too: without the driver, the service
runs a simulated light bar.

```
python -m unittest discover -s tests -t .        # tests (stdlib only)
set PYTHONPATH=app && python -m lightbar.server  # service + UI on http://127.0.0.1:47831
python tools/package.py                          # dist/LightBar-<version>.tar.gz
powershell -File tools/make_art.ps1              # Steam library artwork
```

Open `http://127.0.0.1:47831/#ready` to jump straight to a situation.
