#!/usr/bin/env bash
# Removes the LaunchAgent and installed scripts. Your config is kept.
set -euo pipefail

LABEL="com.custom.wallpaper-switch"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$AGENT"
rm -rf "$HOME/Library/Scripts/wallpaper-switch"

echo "Uninstalled. Config kept at ~/.config/wallpaper-switch/config.json"
echo "To restore your original wallpaper settings, copy"
echo "  ~/Library/Application Support/com.apple.wallpaper/Store/Index.plist.bak"
echo "over Index.plist, then run: killall WallpaperAgent"
