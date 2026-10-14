#!/usr/bin/env bash
# Removes LightBar. The light bar goes back to Steam's control.
#   bash uninstall.sh
set -uo pipefail

ROOT="${LIGHTBAR_HOME:-$HOME/.local/share/lightbar}"
RULE=/etc/udev/rules.d/99-lightbar.rules

echo "==> Stopping LightBar"
pkill -f "$ROOT/electron/electron" 2>/dev/null
systemctl --user disable --now lightbar.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/lightbar.service"
systemctl --user daemon-reload 2>/dev/null

echo "==> Removing the Steam tile"
if pgrep -x steam >/dev/null; then
  echo "   Steam is running: close Steam and run this again to remove the tile (or remove it in Steam)."
else
  LIGHTBAR_HOME="$ROOT" PYTHONPATH="$ROOT/app" python3 -m lightbar.steam remove-self 2>/dev/null
fi

if [ -f "$RULE" ]; then
  echo "==> Removing the light bar permission rule (asks for your password)"
  sudo rm -f "$RULE" && sudo udevadm control --reload
fi

rm -f "$HOME/.local/share/applications/lightbar.desktop"
rm -rf "$ROOT"
echo "LightBar removed. The power-on color stays saved in the light bar until you change it."
