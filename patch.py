#!/usr/bin/env python3
"""
Multi-Browser GPU Patcher for Legacy Mac GPUs (Mac Pro 6,1 / Kepler / GCN 1.0)
Restores hardware acceleration (Compositing, WebGL, WebGPU) on modern Chromium browsers.
"""
import os
import sys
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from patchers import AVAILABLE_PATCHERS

def get_installed_patchers():
    installed = {}
    for slug, patcher_cls in AVAILABLE_PATCHERS.items():
        p = patcher_cls(repo_root=SCRIPT_DIR)
        if p.is_installed():
            installed[slug] = p
    return installed

def main():
    parser = argparse.ArgumentParser(
        description="Multi-Browser GPU Patcher for Legacy Mac GPUs (Chrome, Opera, etc.)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 patch.py              # Auto-detect and patch all installed browsers
  python3 patch.py chrome       # Patch Google Chrome only
  python3 patch.py opera        # Patch Opera only
  python3 patch.py --list       # List supported and detected browsers
  python3 patch.py --check all  # Check patch status for all browsers
  python3 patch.py --restore all# Restore original binaries from backup
"""
    )
    parser.add_argument("target", nargs="?", default="all",
                        help="Browser to patch: 'chrome', 'opera', or 'all' (default: all installed)")
    parser.add_argument("--app-path", type=str, default=None,
                        help="Explicit path to the .app bundle (e.g. /Applications/Brave Browser.app)")
    parser.add_argument("--list", action="store_true", help="List supported and detected browsers")
    parser.add_argument("--check", action="store_true", help="Check if target browser(s) are already patched")
    parser.add_argument("--restore", action="store_true", help="Restore original binaries from backup")
    parser.add_argument("--auto", action="store_true", help="Background watcher mode (skips if already patched)")
    parser.add_argument("--notify", action="store_true", help="Send macOS system notification on success")

    args = parser.parse_args()

    if args.list:
        print("Supported Browsers & Installation Paths:")
        for slug, cls in AVAILABLE_PATCHERS.items():
            p = cls(repo_root=SCRIPT_DIR, app_path=args.app_path if args.target == slug else None)
            installed = "INSTALLED" if p.is_installed() else "Not found"
            ver = p.get_current_version() if p.is_installed() else ""
            ver_str = f"(v{ver})" if ver else ""
            path_str = f"-> {p.app_path}" if p.is_installed() else f"(Searched: {p.app_path})"
            print(f"  - {slug:8} : {p.name:16} [{installed:9}] {ver_str:16} {path_str}")
        return 0

    if args.app_path and args.target == "all":
        print("[!] Error: --app-path can only be specified when targeting a specific browser (e.g. 'python3 patch.py brave --app-path ...').")
        return 1

    target = args.target.lower()
    targets_to_run = []

    if target == "all":
        installed = get_installed_patchers()
        if not installed:
            print("[!] No supported browsers found installed on this system.")
            return 1
        targets_to_run = list(installed.values())
    elif target in AVAILABLE_PATCHERS:
        p = AVAILABLE_PATCHERS[target](repo_root=SCRIPT_DIR, app_path=args.app_path)
        if not p.is_installed():
            print(f"[!] {p.name} is not found at '{p.app_path}'. Use --app-path to specify its location.")
            return 1
        targets_to_run = [p]
    else:
        print(f"[!] Unknown browser target: '{target}'. Available targets: {', '.join(AVAILABLE_PATCHERS.keys())}, all")
        return 1

    overall_exit_code = 0
    for patcher in targets_to_run:
        code = patcher.run_patch(
            auto=args.auto,
            notify_user=args.notify,
            check_only=args.check,
            restore_mode=args.restore
        )
        if code != 0:
            overall_exit_code = code

    return overall_exit_code

if __name__ == "__main__":
    sys.exit(main())
