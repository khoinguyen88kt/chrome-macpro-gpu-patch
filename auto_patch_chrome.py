#!/usr/bin/env python3
"""
Backward-compatibility wrapper for Google Chrome LaunchAgent.
Delegates directly to ChromePatcher from patchers.chrome.
"""
import os
import sys
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from patchers.chrome import ChromePatcher

def main():
    parser = argparse.ArgumentParser(description="Automated Chrome GPU patcher for legacy Mac GPUs")
    parser.add_argument("--check", action="store_true", help="Check if Chrome is already patched")
    parser.add_argument("--auto", action="store_true", help="Background watcher mode (checks and patches only if needed)")
    parser.add_argument("--notify", action="store_true", help="Send macOS notification on completion")
    parser.add_argument("--restore", action="store_true", help="Restore original unpatched Chrome Framework from backup")
    args = parser.parse_args()

    patcher = ChromePatcher(repo_root=SCRIPT_DIR)
    return patcher.run_patch(
        auto=args.auto,
        notify_user=args.notify,
        check_only=args.check,
        restore_mode=args.restore
    )

if __name__ == "__main__":
    sys.exit(main())
