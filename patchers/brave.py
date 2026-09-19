#!/usr/bin/env python3
"""
Brave Browser Patcher subclass for legacy Mac GPUs.
Implements the 7 binary patches, ANGLE dylib injection, and native C launcher.
"""
import os
import subprocess
from .base import BaseBrowserPatcher, safe_copy, run

class BravePatcher(BaseBrowserPatcher):
    name = "Brave Browser"
    slug = "brave"
    possible_app_paths = [
        "/Applications/Brave Browser.app",
        os.path.expanduser("~/Applications/Brave Browser.app")
    ]
    bundle_id = "com.brave.Browser"
    app_bundle_name = "Brave Browser.app"
    framework_name = "Brave Browser Framework.framework"
    framework_binary_name = "Brave Browser Framework"
    launcher_name = "Brave Browser"
    launcher_src = "brave_main.c"
    backup_base_dir = "~/.brave_macpro_backups"

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/Brave Browser Helper (GPU).app")

        if not os.path.exists(fw_bin) or not os.path.exists(lib_egl) or not os.path.exists(launcher_dst) or not os.path.exists(gpu_helper):
            return False

        # 1. Check if GPU Helper is signed with LocalCodeSigner
        res = subprocess.run(["codesign", "-dvvv", gpu_helper], capture_output=True, text=True)
        if f"Authority={self.certificate_name}" not in res.stderr and f"Authority={self.certificate_name}" not in res.stdout:
            return False

        # 2. Check if Pattern 7 (IOSurfaceImageBacking texture_target 0x84f5) is patched
        p7_patched = bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45 cc 88 83 8c 01 00 00")
        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                if data.find(p7_patched) == -1:
                    return False
        except Exception:
            return False

        return True

    def pre_patch_hook(self, version):
        ver_dir = self.get_ver_dir(version)
        lib_dir = os.path.join(ver_dir, "Libraries")
        os.makedirs(lib_dir, exist_ok=True)
        ref_angle_lib = os.path.join(self.repo_root, "angle_dylibs")

        for dylib in ["libEGL.dylib", "libGLESv2.dylib"]:
            src = os.path.join(ref_angle_lib, dylib)
            dst = os.path.join(lib_dir, dylib)
            if os.path.exists(src):
                print(f"[*] Copying clean {dylib} to {version}...")
                safe_copy(src, dst)
            else:
                print(f"[!] Warning: Reference dylib not found at {src}")

    def post_patch_hook(self, version):
        current_link = os.path.join(self.versions_dir, "Current")
        if not os.path.islink(current_link) or not os.path.exists(current_link):
            print(f"[*] Ensuring Versions/Current symlink points to {version}...")
            run(f'ln -sfn "{version}" "{current_link}"')

    def get_patches(self, version):
        return [
            ("Patch 1 (GetAllowedGLImplementation)",
             bytes.fromhex("84 c0 74 0f 80 7d b8 00 74 cd 48 8b 45 b0"),
             bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")),

            ("Patch 2 (GetDisplayInitializationParams)",
             bytes.fromhex("84 c0 0f 85 06 06 00 00 48 b8 09 00 00 00 03 00"),
             bytes.fromhex("84 c0 e9 07 06 00 00 90 48 b8 09 00 00 00 03 00")),

            ("Patch 3 (GpuMode fallback to HARDWARE_GL)",
             bytes.fromhex("84 c0 0f 84 8b 00 00 00 c7 45 ac 03 00 00 00"),
             bytes.fromhex("84 c0 90 90 90 90 90 90 c7 45 ac 01 00 00 00")),

            ("Patch 4 (Seatbelt IsSandboxed)",
             bytes.fromhex("85 c0 0f 84 a7 00 00 00 48 8b bb 88 00 00 00"),
             bytes.fromhex("85 c0 90 90 90 90 90 90 48 8b bb 88 00 00 00")),

            ("Patch 5 (IOSurfaceImageBackingFactory target 0x84f5)",
             bytes.fromhex("45 8b 47 38 4c 89 6c 24 18 89 44 24 10 0f b6 45 cc 89 44 24 08 c7 04 24 01 00 00 00"),
             bytes.fromhex("41 b8 f5 84 00 00 4c 89 6c 24 18 89 44 24 10 89 04 24 0f b6 45 cc 89 44 24 08 66 90")),

            ("Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget)",
             bytes.fromhex("55 48 89 e5 41 56 53 48 81 ec 30 01 00 00 81 fe e1 0d 00 00"),
             bytes.fromhex("b0 01 c3 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90")),

            ("Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5)",
             bytes.fromhex("8b 45 d0 89 83 88 01 00 00 8b 45 cc 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 c7 83 94 01 00 00 00 00"),
             bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45 cc 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 44 89 b3 94 01 00 00"))
        ]
