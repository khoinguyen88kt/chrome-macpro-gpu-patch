#!/usr/bin/env python3
"""
Base Browser Patcher class for Chromium-based browsers on macOS.
Handles common workflows: backup, pattern scanning & patching, launcher compilation,
codesigning with LocalCodeSigner, and signature validation.
"""
import os
import sys
import shutil
import subprocess
import glob
import time

def notify(title, message):
    try:
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}" sound name "Glass"'
        ], capture_output=True)
    except Exception:
        pass

def run(cmd):
    print(f"[RUN] {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0 and res.stderr:
        print(f"[ERR] {res.stderr.strip()}")
    return res

def safe_copy(src, dst):
    subprocess.run(["cp", "-f", src, dst], check=True)

class BaseBrowserPatcher:
    name = "Base Chromium Browser"
    slug = "base"
    possible_app_paths = []
    framework_name = ""
    framework_binary_name = ""
    launcher_name = ""
    launcher_src = ""
    backup_base_dir = ""
    certificate_name = "LocalCodeSigner"

    def __init__(self, repo_root=None):
        if repo_root is None:
            # Fallback to repo root directory (parent of patchers/)
            self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        else:
            self.repo_root = repo_root
        self.app_path = self.find_app()

    def find_app(self):
        for path in self.possible_app_paths:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                return expanded
        if self.possible_app_paths:
            return os.path.expanduser(self.possible_app_paths[0])
        return ""

    def is_installed(self):
        return bool(self.app_path and os.path.exists(self.app_path))

    @property
    def frameworks_dir(self):
        return os.path.join(self.app_path, "Contents/Frameworks")

    @property
    def framework_dir(self):
        return os.path.join(self.frameworks_dir, self.framework_name)

    @property
    def versions_dir(self):
        return os.path.join(self.framework_dir, "Versions")

    @property
    def current_link(self):
        return os.path.join(self.versions_dir, "Current")

    def get_current_version(self):
        if os.path.islink(self.current_link) and os.path.exists(self.current_link):
            return os.path.basename(os.path.realpath(self.current_link))
        if os.path.isdir(self.versions_dir):
            candidates = [
                d for d in os.listdir(self.versions_dir)
                if os.path.isdir(os.path.join(self.versions_dir, d)) and not d.startswith(".") and d != "Current"
            ]
            if candidates:
                candidates.sort(key=lambda s: [int(x) if x.isdigit() else 0 for x in s.split(".")])
                return candidates[-1]
        return None

    def get_ver_dir(self, version):
        return os.path.join(self.versions_dir, version)

    def get_framework_bin(self, version):
        return os.path.join(self.get_ver_dir(version), self.framework_binary_name)

    def get_launcher_dst(self):
        return os.path.join(self.app_path, "Contents/MacOS", self.launcher_name)

    def get_backup_dir(self, version):
        return os.path.join(os.path.expanduser(self.backup_base_dir), version)

    def is_already_patched(self, version):
        """Override in subclasses to provide specific fast verification."""
        raise NotImplementedError

    def backup_original(self, version):
        backup_dir = self.get_backup_dir(version)
        os.makedirs(backup_dir, exist_ok=True)
        fw_bin = self.get_framework_bin(version)
        fw_bak = os.path.join(backup_dir, f"{self.framework_binary_name}.original")
        launcher_dst = self.get_launcher_dst()
        launcher_bak = os.path.join(backup_dir, f"{self.launcher_name}.original")

        if os.path.exists(fw_bin) and not os.path.exists(fw_bak):
            print(f"[*] Backing up original framework to {fw_bak}...")
            safe_copy(fw_bin, fw_bak)

        if os.path.exists(launcher_dst) and not os.path.exists(launcher_bak):
            print(f"[*] Backing up original launcher to {launcher_bak}...")
            safe_copy(launcher_dst, launcher_bak)

    def restore(self, version):
        backup_dir = self.get_backup_dir(version)
        fw_bak = os.path.join(backup_dir, f"{self.framework_binary_name}.original")
        launcher_bak = os.path.join(backup_dir, f"{self.launcher_name}.original")
        fw_bin = self.get_framework_bin(version)
        launcher_dst = self.get_launcher_dst()

        restored = False
        if os.path.exists(fw_bak):
            print(f"[*] Restoring {self.name} Framework from backup...")
            safe_copy(fw_bak, fw_bin)
            run(f'codesign --force --sign "{self.certificate_name}" "{fw_bin}"')
            restored = True
        if os.path.exists(launcher_bak):
            print(f"[*] Restoring {self.name} launcher from backup...")
            safe_copy(launcher_bak, launcher_dst)
            run(f'codesign --force --sign "{self.certificate_name}" "{launcher_dst}"')
            restored = True

        if restored:
            run(f'codesign --force --deep --sign "{self.certificate_name}" "{self.app_path}"')
            print(f"[+] Restored {self.name} {version} successfully from backup!")
            return True
        else:
            print(f"[-] No backup found for {self.name} {version}.")
            return False

    def get_patches(self, version):
        """Return list of (name, orig_bytes, patched_bytes) or regex scanner callable."""
        raise NotImplementedError

    def pre_patch_hook(self, version):
        """Hook called before binary patching (e.g. copying reference dylibs)."""
        pass

    def post_patch_hook(self, version):
        """Hook called after patching before codesigning (e.g. symlink fixes)."""
        pass

    def apply_binary_patches(self, version):
        fw_bin = self.get_framework_bin(version)
        if not os.path.exists(fw_bin):
            print(f"[!] Error: Framework binary not found at {fw_bin}")
            return False

        print(f"[*] Reading {self.name} framework binary ({os.path.getsize(fw_bin):,} bytes)...")
        with open(fw_bin, "rb") as f:
            data = bytearray(f.read())

        patches = self.get_patches(version)
        applied_count = 0

        for item in patches:
            if len(item) == 3:
                p_name, orig, pat = item
                idx = data.find(orig)
                if idx != -1:
                    data[idx:idx+len(pat)] = pat
                    print(f"[+] {p_name} applied successfully at {hex(idx)}!")
                    applied_count += 1
                else:
                    if data.find(pat) != -1:
                        print(f"[*] {p_name} is already applied.")
                        applied_count += 1
                    else:
                        print(f"[!] Warning: {p_name} pattern not found!")
            elif len(item) == 2 and callable(item[1]):
                p_name, custom_func = item
                success = custom_func(data)
                if success:
                    applied_count += 1

        if applied_count == len(patches):
            print(f"[+] All {applied_count}/{len(patches)} patches confirmed/applied. Writing updated binary...")
            with open(fw_bin, "wb") as f:
                f.write(data)
            return True
        else:
            print(f"[!] Patching incomplete ({applied_count}/{len(patches)} applied).")
            return False

    def install_launcher(self, version):
        launcher_src_path = os.path.join(self.repo_root, self.launcher_src)
        launcher_dst = self.get_launcher_dst()

        if not os.path.exists(launcher_src_path):
            print(f"[!] Error: Launcher source not found at {launcher_src_path}")
            return False

        print(f"[*] Compiling native C launcher for {self.name}...")
        res = run(f'clang -O2 "{launcher_src_path}" -o "{launcher_dst}"')
        if res.returncode == 0:
            print(f"[+] {self.name} launcher installed successfully!")
            return True
        else:
            print(f"[!] Failed to compile launcher for {self.name}!")
            return False

    def codesign(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        launcher_dst = self.get_launcher_dst()

        print(f"[*] Stripping quarantine and extended attributes from {self.name}...")
        run(f'xattr -cr "{self.app_path}"')

        print(f"[*] Re-signing {self.name} components with {self.certificate_name}...")

        # 1. Sign all dylibs in Libraries/
        lib_dir = os.path.join(ver_dir, "Libraries")
        if os.path.isdir(lib_dir):
            for f in os.listdir(lib_dir):
                if f.endswith(".dylib"):
                    run(f'codesign --force --sign "{self.certificate_name}" "{os.path.join(lib_dir, f)}"')

        # 2. Sign Helpers
        helpers_dir = os.path.join(ver_dir, "Helpers")
        if os.path.isdir(helpers_dir):
            for h in os.listdir(helpers_dir):
                h_path = os.path.join(helpers_dir, h)
                if h.endswith(".app"):
                    run(f'codesign --force --deep --sign "{self.certificate_name}" "{h_path}"')
                elif os.path.isfile(h_path) and os.access(h_path, os.X_OK):
                    run(f'codesign --force --sign "{self.certificate_name}" "{h_path}"')

        # 3. Sign framework binary, version dir, framework bundle, launcher, and main app
        run(f'codesign --force --sign "{self.certificate_name}" "{fw_bin}"')
        run(f'codesign --force --sign "{self.certificate_name}" "{ver_dir}"')
        run(f'codesign --force --sign "{self.certificate_name}" "{self.framework_dir}"')
        run(f'codesign --force --sign "{self.certificate_name}" "{launcher_dst}"')
        run(f'codesign --force --deep --sign "{self.certificate_name}" "{self.app_path}"')

    def verify_signature(self):
        print(f"[*] Verifying {self.name} code signature...")
        v = run(f'codesign -v "{self.app_path}"')
        if v.returncode == 0:
            print(f"[+] Signature VALID! {self.name} is ready to run.")
            return True
        else:
            print(f"[!] Codesign verification warning: {v.stderr.strip()}")
            return False

    def run_patch(self, auto=False, notify_user=False, check_only=False, restore_mode=False):
        if not self.is_installed():
            print(f"[-] {self.name} is not installed at {self.app_path}.")
            return 1

        current_ver = self.get_current_version()
        if not current_ver:
            print(f"[!] Error: Could not determine {self.name} version.")
            return 1

        print(f"\n{'='*60}")
        print(f" [{self.name}] Target: {self.app_path} (v{current_ver})")
        print(f"{'='*60}")

        if restore_mode:
            success = self.restore(current_ver)
            return 0 if success else 1

        if check_only:
            if self.is_already_patched(current_ver):
                print(f"[+] {self.name} {current_ver} is ALREADY patched.")
                return 0
            else:
                print(f"[-] {self.name} {current_ver} is NOT patched.")
                return 1

        if auto:
            time.sleep(3)
            current_ver = self.get_current_version()
            if self.is_already_patched(current_ver):
                print(f"[*] {self.name} {current_ver} is already patched. Nothing to do.")
                return 0
            print(f"[!] Unpatched {self.name} detected ({current_ver})! Starting auto-patch...")

        # 1. Backup
        self.backup_original(current_ver)

        # 2. Pre-patch hook
        self.pre_patch_hook(current_ver)

        # 3. Binary patching
        ok = self.apply_binary_patches(current_ver)
        if not ok:
            print(f"[!] Binary patching failed for {self.name}. Rolling back to backup...")
            self.restore(current_ver)
            return 1

        # 4. Install launcher
        if not self.install_launcher(current_ver):
            print(f"[!] Launcher installation failed for {self.name}. Rolling back...")
            self.restore(current_ver)
            return 1

        # 5. Post-patch hook
        self.post_patch_hook(current_ver)

        # 6. Codesign
        self.codesign(current_ver)

        # 7. Verification
        if self.verify_signature():
            if notify_user or auto:
                notify(f"{self.name} GPU Patch", f"{self.name} {current_ver} has been patched successfully for your AMD GPU!")
            return 0
        else:
            print(f"[!] Codesign check returned warnings for {self.name}.")
            return 0
