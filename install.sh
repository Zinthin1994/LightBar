#!/usr/bin/env bash
# LightBar installer for SteamOS (Steam Machine).
# Run from Desktop Mode in Konsole:   bash install.sh
# Re-running it updates LightBar and keeps your looks.
#
# Options:  --no-steam   don't add the LightBar tile to Steam
set -euo pipefail

ELECTRON_VERSION="31.7.7"

SRC="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT="${LIGHTBAR_HOME:-$HOME/.local/share/lightbar}"
UNIT_DIR="$HOME/.config/systemd/user"
RULE=/etc/udev/rules.d/99-lightbar.rules
ADD_STEAM=1
for a in "$@"; do
  case "$a" in
    --no-steam) ADD_STEAM=0 ;;
  esac
done

bold() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx %s\033[0m\n' "$*"; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "Run this on the Steam Machine (Linux), not on Windows."
command -v python3 >/dev/null || die "python3 not found"
command -v curl >/dev/null || die "curl not found"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

bold "Installing LightBar into $ROOT"
mkdir -p "$ROOT/data/logs"
pkill -f "$ROOT/electron/electron" 2>/dev/null || true
systemctl --user stop lightbar.service 2>/dev/null || true

# ------------------------------------------------------------------ app files
bold "Copying app files"
rm -rf "$ROOT/app.new"
cp -r "$SRC/app" "$ROOT/app.new"
# strip Windows line endings in case the folder came via a Windows PC
find "$ROOT/app.new" -type f \( -name '*.py' -o -name '*.js' -o -name '*.json' -o -name '*.html' -o -name '*.css' -o -name '*.rules' \) \
  -exec sed -i 's/\r$//' {} +
sed -i 's/\r$//' "$ROOT/app.new/bin/"*
chmod +x "$ROOT/app.new/bin/"*
rm -rf "$ROOT/app"
mv "$ROOT/app.new" "$ROOT/app"

# ------------------------------------------------------------------ light bar access
bold "Checking the light bar"
LED0="$(ls -d /sys/class/leds/valve-leds* 2>/dev/null | head -n1 || true)"
if [ -z "$LED0" ]; then
  warn "No light bar found (/sys/class/leds/valve-leds*). LightBar will run as a simulation."
  warn "On a Steam Machine this means the leds-valve driver isn't loaded - try updating SteamOS."
elif [ -w "$LED0/multi_intensity" ] && [ -w "$LED0/effect" ]; then
  echo "    $(ls -d /sys/class/leds/valve-leds* | wc -l) LEDs, already writable"
else
  echo "LightBar needs permission to change the light bar. This installs a udev rule"
  echo "($RULE) and asks for your password (sudo). If you never set one, run 'passwd' first."
  if sudo install -m 644 "$ROOT/app/udev/99-lightbar.rules" "$RULE"; then
    sudo udevadm control --reload || true
    sudo udevadm trigger --subsystem-match=leds --action=change || true
    sleep 1
    if [ -w "$LED0/multi_intensity" ]; then
      echo "    the light bar is writable now"
    else
      warn "The rule is installed but the light bar is still not writable. A reboot should fix it."
    fi
  else
    warn "Could not install the udev rule - LightBar can show the light bar but not change it."
    warn "Run this installer again after setting a password with 'passwd'."
  fi
fi

# ------------------------------------------------------------------ electron
if [ "$(cat "$ROOT/electron/.version" 2>/dev/null || true)" != "$ELECTRON_VERSION" ]; then
  PV="$HOME/.local/share/playvault/electron"
  if [ "$(cat "$PV/.version" 2>/dev/null || true)" = "$ELECTRON_VERSION" ]; then
    bold "Copying Electron $ELECTRON_VERSION from PlayVault"
    rm -rf "$ROOT/electron"
    cp -r "$PV" "$ROOT/electron"
  else
    bold "Downloading Electron $ELECTRON_VERSION (UI runtime, ~100 MB)"
    curl -fL --progress-bar \
      "https://github.com/electron/electron/releases/download/v${ELECTRON_VERSION}/electron-v${ELECTRON_VERSION}-linux-x64.zip" \
      -o "$TMP/electron.zip" || die "Downloading Electron failed"
    rm -rf "$ROOT/electron"
    mkdir -p "$ROOT/electron"
    python3 - "$TMP/electron.zip" "$ROOT/electron" <<'EOF'
import os, sys, zipfile
src, dst = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(src) as z:
    for info in z.infolist():
        z.extract(info, dst)
        mode = (info.external_attr >> 16) & 0o777
        if mode:
            os.chmod(os.path.join(dst, info.filename), mode)
EOF
    chmod +x "$ROOT/electron/electron" "$ROOT/electron/chrome_crashpad_handler" 2>/dev/null || true
    echo "$ELECTRON_VERSION" > "$ROOT/electron/.version"
  fi
else
  bold "Electron $ELECTRON_VERSION already installed"
fi

# ------------------------------------------------------------------ background service
bold "Starting the LightBar service (keeps your looks on when the app is closed)"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/lightbar.service" <<EOF
[Unit]
Description=LightBar - Steam Machine light bar looks

[Service]
Environment=PYTHONPATH=$ROOT/app
Environment=LIGHTBAR_HOME=$ROOT
Environment=PYTHONUNBUFFERED=1
ExecStart=$(command -v python3) -m lightbar.server
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now lightbar.service || true
sleep 1
systemctl --user is-active --quiet lightbar.service || warn "The service did not start: journalctl --user -u lightbar"

# ------------------------------------------------------------------ desktop entry
bold "Creating desktop menu entry"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/lightbar.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=LightBar
Comment=Steam Machine light bar looks
Exec=$ROOT/app/bin/lightbar
Icon=$ROOT/app/art/icon.png
Categories=Settings;
Terminal=false
EOF

# ------------------------------------------------------------------ Steam tile
STEAM_PY() { LIGHTBAR_HOME="$ROOT" PYTHONPATH="$ROOT/app" python3 -m lightbar.steam "$@"; }
if [ "$ADD_STEAM" = "1" ]; then
  bold "Adding LightBar to your Steam library"
  RESTART_STEAM=0
  ADD=1
  if pgrep -x steam >/dev/null; then
    echo "Steam has to close for a moment so the library tile sticks."
    read -r -p "Close Steam now? [Y/n] " ans || ans="y"
    if [ -z "$ans" ] || [[ "$ans" =~ ^[Yy] ]]; then
      steam -shutdown >/dev/null 2>&1 || true
      for _ in $(seq 1 60); do pgrep -x steam >/dev/null || break; sleep 1; done
      RESTART_STEAM=1
    else
      ADD=0
      warn "Skipped. Re-run the installer with Steam closed to add the tile."
    fi
  fi
  if [ "$ADD" = "1" ]; then
    STEAM_PY add-self || warn "Could not add the Steam tile (log into Steam once, then re-run the installer)"
  fi
  if [ "$RESTART_STEAM" = "1" ]; then
    (setsid steam >/dev/null 2>&1 &)
  fi
fi

bold "Done!"
cat <<EOF

  LightBar is installed.

  * Game Mode:     find "LightBar" in your Library (Non-Steam tab).
  * Desktop Mode:  Application menu > Settings > LightBar
  * Your looks stay on after you close the app (service: lightbar.service).

  Logs: $ROOT/data/logs
  Update later by running this installer again.
EOF
