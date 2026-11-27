#!/usr/bin/env python3
"""
Helium Browser Patcher subclass for legacy Mac GPUs.
Helium is an open-source privacy Chromium fork (imputnet/helium-macos).
"""
import os
import plistlib
from .base import safe_copy
from .chromium import ChromiumPatcher


class HeliumPatcher(ChromiumPatcher):
    name = "Helium"
    slug = "helium"
    possible_app_paths = [
        "/Applications/Helium.app",
        os.path.expanduser("~/Applications/Helium.app"),
    ]
    bundle_id = "net.imput.helium"
    app_bundle_name = "Helium.app"
    framework_name = "Helium Framework.framework"
    framework_binary_name = "Helium Framework"
    launcher_name = "Helium"
    launcher_src = "launcher_main.c"
    backup_base_dir = "~/.helium_macpro_backups"

    def get_app_bundle_version(self):
        """Reads CFBundleShortVersionString or CFBundleVersion from Contents/Info.plist."""
        plist_path = os.path.join(self.app_path, "Contents", "Info.plist")
        if os.path.exists(plist_path):
            try:
                with open(plist_path, "rb") as f:
                    pl = plistlib.load(f)
                    return pl.get("CFBundleShortVersionString") or pl.get("CFBundleVersion")
            except Exception:
                pass
        return None

    def get_backup_dir(self, version):
        """Isolate backups per Helium app release (e.g. 153.0.8010.52_0.17.2.2)."""
        app_ver = self.get_app_bundle_version()
        if app_ver and app_ver != version:
            dir_name = f"{version}_{app_ver}"
        else:
            dir_name = version
        return os.path.join(os.path.expanduser(self.backup_base_dir), dir_name)

    def backup_original(self, version):
        backup_dir = self.get_backup_dir(version)
        os.makedirs(backup_dir, exist_ok=True)
        fw_bin = self.get_framework_bin(version)
        fw_bak = os.path.join(backup_dir, f"{self.framework_binary_name}.original")
        launcher_dst = self.get_launcher_dst()
        launcher_bak = os.path.join(backup_dir, f"{self.launcher_name}.original")

        is_patched = self.is_already_patched(version)

        if os.path.exists(fw_bin):
            if not os.path.exists(fw_bak):
                legacy_dir = os.path.join(os.path.expanduser(self.backup_base_dir), version)
                legacy_bak = os.path.join(legacy_dir, f"{self.framework_binary_name}.original")
                migrated = False
                if os.path.exists(legacy_bak):
                    try:
                        with open(legacy_bak, "rb") as f:
                            bak_data = f.read()
                        app_ver = self.get_app_bundle_version()
                        if (app_ver and app_ver.encode("ascii") + b"\x00" in bak_data) and (bytes.fromhex("84 c0 eb 06 90 90 90 90 90 90 48 8b 45 b0") not in bak_data):
                            print(f"[*] Migrating clean original Helium framework from legacy backup {legacy_bak}...")
                            safe_copy(legacy_bak, fw_bak)
                            migrated = True
                    except Exception:
                        pass

                if not migrated:
                    if not is_patched:
                        print(f"[*] Backing up clean original Helium framework to {fw_bak}...")
                        safe_copy(fw_bin, fw_bak)
                    else:
                        print(f"[*] Warning: Helium framework is already patched, saving current state to {fw_bak}...")
                        safe_copy(fw_bin, fw_bak)
            else:
                if not is_patched:
                    fw_bin_size = os.path.getsize(fw_bin)
                    fw_bak_size = os.path.getsize(fw_bak)
                    if fw_bin_size != fw_bak_size:
                        print(f"[*] Detected updated unpatched Helium framework ({fw_bin_size:,} bytes vs backup {fw_bak_size:,} bytes). Updating backup...")
                        safe_copy(fw_bin, fw_bak)

        if os.path.exists(launcher_dst) and not os.path.exists(launcher_bak):
            print(f"[*] Backing up original Helium launcher to {launcher_bak}...")
            safe_copy(launcher_dst, launcher_bak)

    def pre_patch_hook(self, version):
        """Verify Helium Framework matches app bundle version to detect corrupted or downgraded binaries."""
        super().pre_patch_hook(version)
        app_ver = self.get_app_bundle_version()
        fw_bin = self.get_framework_bin(version)
        if app_ver and os.path.exists(fw_bin):
            try:
                with open(fw_bin, "rb") as f:
                    data = f.read()
                    if app_ver.encode("ascii") + b"\x00" not in data:
                        print("\n[!] WARNING: Helium version mismatch detected!")
                        print(f"    Helium.app Info.plist version is '{app_ver}', but '{self.framework_binary_name}'")
                        print(f"    does not contain '{app_ver}' (likely an older build was restored from backup).")
                        print("    This causes Settings (helium://settings) to crash with RESULT_CODE_KILLED_BAD_MESSAGE.")
                        print(f"    To fix: Please download and reinstall Helium {app_ver} from:")
                        print("    https://github.com/imputnet/helium-macos/releases")
                        print("    and run this patcher again.\n")
            except Exception:
                pass

    def restore(self, version):
        backup_dir = self.get_backup_dir(version)
        fw_bak = os.path.join(backup_dir, f"{self.framework_binary_name}.original")
        if not os.path.exists(fw_bak):
            legacy_dir = os.path.join(os.path.expanduser(self.backup_base_dir), version)
            legacy_bak = os.path.join(legacy_dir, f"{self.framework_binary_name}.original")
            if os.path.exists(legacy_bak):
                os.makedirs(backup_dir, exist_ok=True)
                safe_copy(legacy_bak, fw_bak)
                legacy_launcher = os.path.join(legacy_dir, f"{self.launcher_name}.original")
                launcher_bak = os.path.join(backup_dir, f"{self.launcher_name}.original")
                if os.path.exists(legacy_launcher):
                    safe_copy(legacy_launcher, launcher_bak)
        return super().restore(version)
