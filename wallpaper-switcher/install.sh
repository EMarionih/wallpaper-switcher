#!/usr/bin/env bash
# Installs the wallpaper switcher for the current user and loads its LaunchAgent.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer only works on macOS." >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-/usr/bin/python3}"
LABEL="com.custom.wallpaper-switch"
INSTALL_DIR="$HOME/Library/Scripts/wallpaper-switch"
CONFIG_DIR="$HOME/.config/wallpaper-switch"
CONFIG="$CONFIG_DIR/config.json"
AGENT_DIR="$HOME/Library/LaunchAgents"
AGENT="$AGENT_DIR/$LABEL.plist"

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$AGENT_DIR" "$HOME/Library/Logs"

install -m 755 "$SRC/wallpaper_switch.py" "$INSTALL_DIR/wallpaper_switch.py"
install -m 755 "$SRC/list_aerials.py" "$INSTALL_DIR/list_aerials.py"

if [[ ! -f "$CONFIG" ]]; then
  cp "$SRC/config.example.json" "$CONFIG"
  echo "Created $CONFIG"
fi

if grep -q "YOUR_" "$CONFIG"; then
  echo
  echo "Next step: put real wallpaper IDs in $CONFIG, then run ./install.sh again."
  echo "To get an ID: choose an Aerial wallpaper in System Settings > Wallpaper, then run:"
  echo "  $PYTHON $INSTALL_DIR/list_aerials.py"
  exit 0
fi

# Generate the LaunchAgent from the config so the schedule lives in one place.
"$PYTHON" "$INSTALL_DIR/wallpaper_switch.py" --print-launch-agent > "$AGENT.tmp"
mv "$AGENT.tmp" "$AGENT"
plutil -lint "$AGENT" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT"

echo "Installed. The wallpaper updates at login and at each start time in $CONFIG."
echo "Log: $HOME/Library/Logs/wallpaper-switch.log"
