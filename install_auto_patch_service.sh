#!/usr/bin/env bash
# Install LaunchAgent service to automatically patch Chrome whenever Google Chrome updates
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="io.github.chrome-macpro-gpu-patch.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"
LOG_PATH="$HOME/Library/Logs/chrome_macpro_gpu_patch.log"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$HOME/Library/Logs"

# Unload existing service if loaded
launchctl unload "$TARGET_PLIST" 2>/dev/null || true

cat << EOF > "$TARGET_PLIST"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.github.chrome-macpro-gpu-patch</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$SCRIPT_DIR/auto_patch_chrome.py</string>
        <string>--auto</string>
    </array>
    <key>WatchPaths</key>
    <array>
        <string>/Applications/Google Chrome.app/Contents/Frameworks</string>
        <string>/Applications/Google Chrome.app/Contents/MacOS</string>
    </array>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_PATH</string>
    <key>StandardErrorPath</key>
    <string>$LOG_PATH</string>
</dict>
</plist>
EOF

launchctl load "$TARGET_PLIST"

echo "============================================================"
echo " [SUCCESS] Auto-patch LaunchAgent installed successfully!"
echo "============================================================"
echo " - Plist: $TARGET_PLIST"
echo " - Logs:  $LOG_PATH"
echo " - The service runs automatically in the background with zero CPU/RAM."
echo " - Whenever Google Chrome updates and replaces files, it will be"
echo "   automatically patched before you click 'Relaunch'!"
echo "============================================================"
