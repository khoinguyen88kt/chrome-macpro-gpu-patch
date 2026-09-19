#!/usr/bin/env python3
"""
Opera Browser Patcher subclass for legacy Mac GPUs.
Implements the 5 binary patches, obsolete bundle version cleanup, and native C launcher.
"""
import os
import subprocess
from .base import BaseBrowserPatcher, run

class OperaPatcher(BaseBrowserPatcher):
    name = "Opera"
    slug = "opera"
    possible_app_paths = [
        "/Applications/Opera.app",
        os.path.expanduser("~/Applications/Opera.app")
    ]
    framework_name = "Opera Framework.framework"
    framework_binary_name = "Opera Framework"
    launcher_name = "Opera"
    launcher_src = "opera_main.c"
    backup_base_dir = "~/.opera_macpro_backups"

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/Opera Helper (GPU).app")

        if not os.path.exists(fw_bin) or not os.path.exists(launcher_dst) or not os.path.exists(gpu_helper):
            return False

        # 1. Check if GPU Helper is signed with LocalCodeSigner
        res = subprocess.run(["codesign", "-dvvv", gpu_helper], capture_output=True, text=True)
        if f"Authority={self.certificate_name}" not in res.stderr and f"Authority={self.certificate_name}" not in res.stdout:
            return False

        # 2. Check if Patch 4 (gl_target_ = 0x84f5) is present in binary
        p4_patched = bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45 c0 88 83 8c 01 00 00")
        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                if data.find(p4_patched) == -1:
                    return False
        except Exception:
            return False

        return True

    def post_patch_hook(self, version):
        backup_dir = self.get_backup_dir(version)
        # 1. Ensure obsolete versions don't break bundle signature
        if os.path.isdir(self.versions_dir):
            for d in os.listdir(self.versions_dir):
                d_path = os.path.join(self.versions_dir, d)
                if os.path.isdir(d_path) and not d.startswith(".") and d != "Current" and d != version:
                    print(f"[*] Moving obsolete version {d} out of bundle to {backup_dir}...")
                    run(f'mv "{d_path}" "{backup_dir}/"')

        # 2. Ensure Versions/Current symlink points to version
        current_link = os.path.join(self.versions_dir, "Current")
        if not os.path.islink(current_link) or not os.path.exists(current_link):
            print(f"[*] Ensuring Versions/Current symlink points to {version}...")
            run(f'ln -sfn "{version}" "{current_link}"')

    def get_patches(self, version):
        return [
            ("Patch 1 (GLDisplayEGL Initialization)",
             bytes.fromhex("84 c0 74 14 48 89 d8 48 81 c4 38 01 00 00"),
             bytes.fromhex("84 c0 90 90 48 89 d8 48 81 c4 38 01 00 00")),

            ("Patch 2 (Seatbelt Sandbox Bypass)",
             bytes.fromhex("84 c0 0f 85 c9 02 00 00 48 c7 85 a8 fd ff ff 41"),
             bytes.fromhex("84 c0 e9 ca 02 00 00 90 48 c7 85 a8 fd ff ff 41")),

            ("Patch 3 (IOSurface Factory Caller Target 0x84f5)",
             bytes.fromhex("41 8b 46 20 45 8b 46 38 89 44 24 10"),
             bytes.fromhex("45 8b 46 38 c7 44 24 10 f5 84 00 00")),

            ("Patch 4 (IOSurfaceBacking gl_target_ = 0x84f5)",
             bytes.fromhex("8b 45 c4 89 83 88 01 00 00 8b 45 c0 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 c7 83 94 01 00 00 00 00"),
             bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45 c0 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 44 89 b3 94 01 00 00")),

            ("Patch 5 (ValidateTarget Always Return True)",
             bytes.fromhex("55 48 89 e5 85 f6 74 26 8b 87 90 01 00 00"),
             bytes.fromhex("b0 01 c3 90 85 f6 74 26 8b 87 90 01 00 00"))
        ]
