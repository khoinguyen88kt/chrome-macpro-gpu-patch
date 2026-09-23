#!/usr/bin/env bash
# Helper script to check for Visual Studio Code updates, install them, and automatically re-patch
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
/usr/bin/python3 "$SCRIPT_DIR/patch.py" vscode --update-app
