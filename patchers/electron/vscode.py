#!/usr/bin/env python3
"""
Visual Studio Code Patcher for macOS Legacy GPUs.
Inherits from BaseElectronPatcher.
Uses non-invasive launcher wrapper shim to preserve Microsoft code signature and GitHub Copilot/Keychain tokens.
Includes automated upstream update downloader and patcher.
"""
import os
import json
import subprocess
import shutil
import time
from .base import BaseElectronPatcher

class VSCodePatcher(BaseElectronPatcher):
    name = "Visual Studio Code"
    slug = "vscode"
    bundle_id = "com.microsoft.VSCode"
    executable_name = "Code"
    possible_app_paths = [
        "/Applications/Visual Studio Code.app",
        os.path.expanduser("~/Applications/Visual Studio Code.app")
    ]

    def _ensure_electron_symlink(self):
        link_path = os.path.join(self.app_path, "Contents/MacOS/Electron")
        if os.path.islink(link_path) or not os.path.exists(link_path):
            try:
                if os.path.islink(link_path):
                    os.unlink(link_path)
                os.symlink("Code", link_path)
            except Exception:
                pass

    def _clean_stale_node_modules(self):
        """
        VS Code bundles all core dependencies inside node_modules.asar.
        If a stray physical node_modules directory exists alongside node_modules.asar,
        Node's ESM resolver will load stale packages from the directory instead of asar,
        causing crashes in extensionHostProcess (e.g. missing named exports in @vscode/proxy-agent).
        """
        app_res_dir = os.path.join(self.app_path, "Contents/Resources/app")
        nm_dir = os.path.join(app_res_dir, "node_modules")
        asar_path = os.path.join(app_res_dir, "node_modules.asar")

        if os.path.exists(asar_path) and os.path.isdir(nm_dir):
            bak_path = os.path.join(app_res_dir, "node_modules.bak_stale")
            print(f"⚠️  Detected stale unbundled '{nm_dir}' alongside 'node_modules.asar'.")
            print(f"    Moving to '{bak_path}' to avoid ESM resolution conflicts in Extension Host...")
            try:
                if os.path.exists(bak_path):
                    bak_path = os.path.join(app_res_dir, f"node_modules.bak_{int(time.time())}")
                shutil.move(nm_dir, bak_path)
                print(f"[+] Moved stale node_modules out of the way -> {os.path.basename(bak_path)}")
            except Exception as e:
                print(f"[!] Warning: Could not move stale node_modules: {e}")

    def post_wrapper_hook(self):
        self._ensure_electron_symlink()
        self._clean_stale_node_modules()

    def post_restore_hook(self):
        self._ensure_electron_symlink()

    def update_app(self):
        """Checks Microsoft API for the latest VS Code release, downloads, installs, and re-patches."""
        if not os.path.exists(self.app_path):
            print(f"[!] {self.name} is not installed at '{self.app_path}'.")
            return 1

        # Check write permissions on VS Code bundle
        macos_dir = os.path.join(self.app_path, "Contents/MacOS")
        if not os.access(macos_dir, os.W_OK):
            print(f"⚠️  Permission denied on '{macos_dir}'. Attempting to reclaim ownership...")
            user = os.environ.get("USER", "")
            if user:
                res = subprocess.run(["sudo", "chown", "-R", f"{user}:admin", self.app_path])
                if res.returncode != 0:
                    print(f"[!] Failed to set write permissions on '{self.app_path}'.")
                    return 1

        product_json = os.path.join(self.app_path, "Contents/Resources/app/product.json")
        current_commit = "none"
        if os.path.exists(product_json):
            try:
                with open(product_json, "r") as f:
                    data = json.load(f)
                    current_commit = data.get("commit", "none")
            except Exception:
                pass

        print(f"🔍 Checking for Visual Studio Code updates (Current commit: {current_commit[:7] if current_commit != 'none' else 'none'})...")
        api_url = f"https://update.code.visualstudio.com/api/update/darwin-universal/stable/{current_commit}"

        res = subprocess.run(["/usr/bin/curl", "-s", "-w", "\n%{http_code}", api_url], capture_output=True, text=True)
        lines = res.stdout.strip().split("\n")
        http_code = lines[-1] if lines else ""
        body = "\n".join(lines[:-1]) if len(lines) > 1 else ""

        if http_code == "204" or not body.strip():
            print("✅ You are already using the latest version of Visual Studio Code! (No update needed)")
            return 0

        try:
            update_data = json.loads(body)
        except Exception:
            print(f"[!] Unexpected response from update server (HTTP {http_code}).")
            return 1

        download_url = update_data.get("url")
        new_version = update_data.get("name") or "Latest"
        if not download_url:
            download_url = "https://update.code.visualstudio.com/latest/darwin-universal/stable"

        print(f"🚀 New version available ({new_version})! Downloading update package...")
        zip_path = "/tmp/vscode_update.zip"

        dl_res = subprocess.run(["/usr/bin/curl", "-L", download_url, "-o", zip_path, "--progress-bar"])
        if dl_res.returncode != 0 or not os.path.exists(zip_path):
            print("[!] Failed to download update package.")
            return 1

        print("📦 Extracting and installing update into /Applications...")
        dest_dir = os.path.dirname(os.path.abspath(self.app_path))
        ext_res = subprocess.run(["ditto", "-xk", zip_path, dest_dir])
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass

        if ext_res.returncode != 0:
            print("[!] Failed to extract update archive using ditto.")
            return 1

        print("[+] Visual Studio Code updated successfully!")
        print("[*] Re-applying hardware acceleration launcher wrapper...")
        patch_res = self.run_patch(force=True)
        if patch_res == 0:
            print("🎉 Visual Studio Code update and GPU patch completed successfully!")
        return patch_res
