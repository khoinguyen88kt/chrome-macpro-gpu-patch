#!/usr/bin/env bash
# Uninstall LaunchAgent auto-patch service
set -e

PLIST_NAME="io.github.chrome-macpro-gpu-patch.plist"
TARGET_PLIST="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [ -f "$TARGET_PLIST" ]; then
    launchctl unload "$TARGET_PLIST" 2>/dev/null || true
    mv "$TARGET_PLIST" /tmp/"$PLIST_NAME.bak"
    echo "[+] Auto-patch service stopped and uninstalled."
else
    echo "[!] Auto-patch service is not currently installed."
fi
