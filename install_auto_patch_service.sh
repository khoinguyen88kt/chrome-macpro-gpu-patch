#!/usr/bin/env bash
# Install LaunchAgent service to automatically patch browsers (Chrome, Opera, Brave) whenever they update
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

# Generate WatchPaths XML entries dynamically from installed browsers
WATCH_PATHS_XML=$(/usr/bin/python3 -c '
import os, sys
sys.path.insert(0, "'"$SCRIPT_DIR"'")
from patchers import AVAILABLE_PATCHERS

watch_paths = []
for slug, cls in AVAILABLE_PATCHERS.items():
    p = cls(repo_root="'"$SCRIPT_DIR"'")
    if p.is_installed():
        watch_paths.append(os.path.join(p.app_path, "Contents/Frameworks"))
        watch_paths.append(os.path.join(p.app_path, "Contents/MacOS"))

for wp in watch_paths:
    print(f"        <string>{wp}</string>")
')

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
        <string>$SCRIPT_DIR/patch.py</string>
        <string>all</string>
        <string>--auto</string>
        <string>--notify</string>
    </array>
    <key>WatchPaths</key>
    <array>
$WATCH_PATHS_XML
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
echo " [SUCCESS] Multi-Browser Auto-Patch LaunchAgent installed!"
echo "============================================================"
echo " - Plist: $TARGET_PLIST"
echo " - Logs:  $LOG_PATH"
echo " - The service runs automatically in the background with zero CPU/RAM."
echo " - Monitored browsers (Chrome, Opera, Brave) will be automatically"
echo "   patched in the background whenever updates are downloaded."
echo "============================================================"
