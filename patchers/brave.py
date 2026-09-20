#!/usr/bin/env python3
"""
Brave Browser Patcher subclass for legacy Mac GPUs.
Implements dynamic regex wildcard pattern scanning, ANGLE dylib injection,
and native C launcher.
"""
import os
import re
import struct
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
        p7_re = re.compile(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83\x8c\x01\x00\x00")
        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                if not p7_re.search(data):
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
        def patch_p1_allowed_gl(data: bytearray):
            p1_re = re.compile(rb"\x84\xc0\x74(.)\x80\x7d(.)\x00\x74(.)\x48\x8b\x45(.)", re.DOTALL)
            m = p1_re.search(data)
            if m:
                offset = m.start() + 2
                data[offset:offset+2] = b"\x90\x90"
                print(f"[+] Patch 1 (GetAllowedGLImplementation) applied successfully at {hex(offset)}!")
                return True
            if data.find(b"\x84\xc0\x90\x90\x80\x7d") != -1:
                print("[*] Patch 1 (GetAllowedGLImplementation) is already applied.")
                return True
            print("[!] Warning: Patch 1 (GetAllowedGLImplementation) pattern not found!")
            return False

        def patch_p2_display_init(data: bytearray):
            p2_re = re.compile(rb"\x84\xc0\x0f\x85(....)\x48\xb8\x09\x00\x00\x00\x03\x00", re.DOTALL)
            m = p2_re.search(data)
            if m:
                disp = struct.unpack("<i", m.group(1))[0]
                offset = m.start() + 2
                data[offset:offset+6] = b"\xe9" + struct.pack("<i", disp + 1) + b"\x90"
                print(f"[+] Patch 2 (GetDisplayInitializationParams) applied successfully at {hex(offset)}!")
                return True
            if data.find(b"\x84\xc0\xe9") != -1 and data.find(b"\x48\xb8\x09\x00\x00\x00\x03\x00") != -1:
                print("[*] Patch 2 (GetDisplayInitializationParams) is already applied.")
                return True
            print("[!] Warning: Patch 2 (GetDisplayInitializationParams) pattern not found!")
            return False

        def patch_p3_gpumode(data: bytearray):
            p3_re = re.compile(rb"\x84\xc0\x0f\x84(....)\xc7\x45(.)\x03\x00\x00\x00", re.DOTALL)
            m = p3_re.search(data)
            if m:
                offset_jmp = m.start() + 2
                data[offset_jmp:offset_jmp+6] = b"\x90" * 6
                # Change 03 to 01 (HARDWARE_GL)
                offset_val = m.end() - 4
                data[offset_val] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at {hex(offset_jmp)}!")
                return True
            if data.find(b"\x84\xc0\x90\x90\x90\x90\x90\x90\xc7\x45") != -1:
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True
            print("[!] Warning: Patch 3 (GpuMode fallback to HARDWARE_GL) pattern not found!")
            return False

        def patch_p4_seatbelt(data: bytearray):
            p4_re = re.compile(rb"\x85\xc0\x0f\x84(....)\x48\x8b\xbb\x88\x00\x00\x00", re.DOTALL)
            m = p4_re.search(data)
            if m:
                offset = m.start() + 2
                data[offset:offset+6] = b"\x90" * 6
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied successfully at {hex(offset)}!")
                return True
            if data.find(b"\x85\xc0\x90\x90\x90\x90\x90\x90\x48\x8b\xbb\x88\x00\x00\x00") != -1:
                print("[*] Patch 4 (Seatbelt IsSandboxed) is already applied.")
                return True
            print("[!] Warning: Patch 4 (Seatbelt IsSandboxed) pattern not found!")
            return False

        def patch_p5_factory_target(data: bytearray):
            p5_re = re.compile(rb"\x45\x8b\x47\x38\x4c\x89\x6c\x24\x18\x89\x44\x24\x10\x0f\xb6\x45(.)\x89\x44\x24\x08\xc7\x04\x24\x01\x00\x00\x00", re.DOTALL)
            m = p5_re.search(data)
            if m:
                reg = m.group(1)
                rep = bytes.fromhex("41 b8 f5 84 00 00 4c 89 6c 24 18 89 44 24 10 89 04 24 0f b6 45") + reg + bytes.fromhex("89 44 24 08 66 90")
                data[m.start():m.end()] = rep
                print(f"[+] Patch 5 (IOSurface Factory Target 0x84f5) applied successfully at {hex(m.start())}!")
                return True
            if data.find(bytes.fromhex("41 b8 f5 84 00 00 4c 89 6c 24 18 89 44 24 10 89 04 24")) != -1:
                print("[*] Patch 5 (IOSurface Factory Target 0x84f5) is already applied.")
                return True
            print("[!] Warning: Patch 5 (IOSurface Factory Target 0x84f5) pattern not found!")
            return False

        def patch_p6_validate_target(data: bytearray):
            p6_re = re.compile(rb"\x55\x48\x89\xe5\x41\x56(?:.|\n){1,20}\x81\xfe\xe1\x0d\x00\x00", re.DOTALL)
            m = p6_re.search(data)
            if m:
                offset = m.start()
                data[offset:offset+4] = b"\xb0\x01\xc3\x90"
                print(f"[+] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied successfully at {hex(offset)}!")
                return True
            if data.find(b"\xb0\x01\xc3\x90\x41\x56") != -1 or data.find(b"\xb0\x01\xc3\x90\x90\x90") != -1:
                print("[*] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) is already applied.")
                return True
            print("[!] Warning: Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) pattern not found!")
            return False

        def patch_p7_backing_target(data: bytearray):
            p7_re = re.compile(rb"\x8b\x45(.)\x89\x83\x88\x01\x00\x00\x8b\x45(.)\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00\x66\xc7\x83\x94\x01\x00\x00\x00\x00", re.DOTALL)
            m = p7_re.search(data)
            if m:
                reg2 = m.group(2)
                rep = bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45") + reg2 + bytes.fromhex("88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 44 89 b3 94 01 00 00")
                data[m.start():m.end()] = rep
                print(f"[+] Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5) applied successfully at {hex(m.start())}!")
                return True
            p7_applied_re = re.compile(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00\x66\x44\x89\xb3\x94\x01\x00\x00", re.DOTALL)
            if p7_applied_re.search(data):
                print("[*] Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5) is already applied.")
                return True
            print("[!] Warning: Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5) pattern not found!")
            return False

        return [
            ("Patch 1 (GetAllowedGLImplementation)", patch_p1_allowed_gl),
            ("Patch 2 (GetDisplayInitializationParams)", patch_p2_display_init),
            ("Patch 3 (GpuMode fallback to HARDWARE_GL)", patch_p3_gpumode),
            ("Patch 4 (Seatbelt IsSandboxed)", patch_p4_seatbelt),
            ("Patch 5 (IOSurfaceImageBackingFactory target 0x84f5)", patch_p5_factory_target),
            ("Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget)", patch_p6_validate_target),
            ("Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5)", patch_p7_backing_target)
        ]
