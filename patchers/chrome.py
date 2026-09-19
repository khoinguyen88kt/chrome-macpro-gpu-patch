#!/usr/bin/env python3
"""
Google Chrome Patcher subclass for legacy Mac GPUs.
Implements the 7 binary patches, ANGLE dylib injection, and native C launcher.
"""
import os
import re
import subprocess
from .base import BaseBrowserPatcher, safe_copy

class ChromePatcher(BaseBrowserPatcher):
    name = "Google Chrome"
    slug = "chrome"
    possible_app_paths = [
        "/Applications/Google Chrome.app",
        os.path.expanduser("~/Applications/Google Chrome.app")
    ]
    framework_name = "Google Chrome Framework.framework"
    framework_binary_name = "Google Chrome Framework"
    launcher_name = "Google Chrome"
    launcher_src = "chrome_main.c"
    backup_base_dir = "~/.chrome_macpro_backups"

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/Google Chrome Helper (GPU).app")

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
                f.seek(0x4000)
                data = f.read(0x10051c10)
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

    def get_patches(self, version):
        def patch_pattern_4_seatbelt(data: bytearray):
            pattern_regex = re.compile(rb'\xe8....\x85\xc0\x0f\x84(....)', re.DOTALL)
            m = pattern_regex.search(data)
            if m:
                # Replace \x0f\x84.... with 6 NOPs (\x90 * 6)
                offset = m.start() + 7
                data[offset:offset+6] = b'\x90' * 6
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied successfully at {hex(offset)}!")
                return True
            else:
                # Check if already patched
                already_patched_regex = re.compile(rb'\xe8....\x85\xc0\x90\x90\x90\x90\x90\x90', re.DOTALL)
                if already_patched_regex.search(data):
                    print("[*] Patch 4 (Seatbelt IsSandboxed) already applied.")
                    return True
                else:
                    print("[!] Warning: Patch 4 (Seatbelt IsSandboxed) pattern not found!")
                    return False

        # Version check: Chromium 153+ vs earlier
        is_v153_plus = False
        try:
            major = int(version.split(".")[0])
            if major >= 153:
                is_v153_plus = True
        except Exception:
            pass

        if is_v153_plus:
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

        return [
            ("Patch 1 (GetAllowedGLImplementation)",
             bytes.fromhex("84 c0 74 0f 80 7d b8 00 74 cd 48 8b 45 b0"),
             bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")),

            ("Patch 2 (GetDisplayInitializationParams)",
             bytes.fromhex("84 c0 0f 85 06 06 00 00 83 7d a8 00 0f 85 f9 05 00 00"),
             bytes.fromhex("84 c0 e9 07 06 00 00 90 83 7d a8 00 0f 85 f9 05 00 00")),

            ("Patch 3 (GpuMode fallback to HARDWARE_GL)",
             bytes.fromhex("c7 45 ac 03 00 00 00"),
             bytes.fromhex("c7 45 ac 01 00 00 00")),

            ("Patch 4 (Seatbelt IsSandboxed)", patch_pattern_4_seatbelt),

            ("Patch 5 (IOSurfaceImageBackingFactory target 0x84f5)",
             bytes.fromhex("48 8d b5 78 ff ff ff 48 89 df 48 89 44 24 08 89 44 24 10"),
             bytes.fromhex("48 8d b5 78 ff ff ff 48 89 df 48 89 44 24 08 41 b8 f5 84 00 00")),

            ("Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget)",
             bytes.fromhex("55 48 89 e5 41 56 41 55 41 54 53 48 83 ec 10 49 89 fd 48 8b 07"),
             bytes.fromhex("b0 01 c3 90 41 56 41 55 41 54 53 48 83 ec 10 49 89 fd 48 8b 07")),

            ("Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5)",
             bytes.fromhex("8b 45 d0 89 83 88 01 00 00 8b 45 cc 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 c7 83 94 01 00 00 00 00"),
             bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45 cc 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 44 89 b3 94 01 00 00"))
        ]
