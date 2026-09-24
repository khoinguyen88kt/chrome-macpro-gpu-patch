#!/usr/bin/env python3
"""
Opera Browser Patcher subclass for legacy Mac GPUs.
Implements the full 8-patch dynamic suite, ANGLE dylib injection,
obsolete bundle version cleanup, and native C launcher.
"""
import os
import re
import struct
import subprocess
from .base import BaseBrowserPatcher, safe_copy, run

class OperaPatcher(BaseBrowserPatcher):
    name = "Opera"
    slug = "opera"
    possible_app_paths = [
        "/Applications/Opera.app",
        os.path.expanduser("~/Applications/Opera.app")
    ]
    bundle_id = "com.operasoftware.Opera"
    app_bundle_name = "Opera.app"
    framework_name = "Opera Framework.framework"
    framework_binary_name = "Opera Framework"
    launcher_name = "Opera"
    launcher_src = "opera_main.c"
    backup_base_dir = "~/.opera_macpro_backups"

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/Opera Helper (GPU).app")

        if not os.path.exists(fw_bin) or not os.path.exists(lib_egl) or not os.path.exists(launcher_dst) or not os.path.exists(gpu_helper):
            return False

        # 1. Check if GPU Helper is signed with LocalCodeSigner
        res = subprocess.run(["codesign", "-dvvv", gpu_helper], capture_output=True, text=True)
        if f"Authority={self.certificate_name}" not in res.stderr and f"Authority={self.certificate_name}" not in res.stdout:
            return False

        # 2. Check if Patch 8 (gl_target_ = 0x84f5) is present in binary
        p8_re = re.compile(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83\x8c\x01\x00\x00")
        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                if not p8_re.search(data):
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
        def patch_p1_allowed_gl(data: bytearray):
            p1_re = re.compile(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09\x0f\x84(....)", re.DOTALL)
            m = p1_re.search(data)
            if m:
                orig_disp = struct.unpack("<i", m.group(1))[0]
                target_addr = (m.start() + 7 + 10) + orig_disp
                new_disp = target_addr - (m.start() + 7 + 5)
                offset = m.start() + 7
                data[offset:offset+10] = b"\xe9" + struct.pack("<i", new_disp) + b"\x90" * 5
                print(f"[+] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) applied successfully at {hex(offset)}!")
                return True
            if re.search(rb"\x48\x89\xc1\x48\xc1\xe9\x20\xe9.{4}\x90{5}", data, re.DOTALL) or data.find(b"\x48\x89\xc1\x48\xc1\xe9\x20\xe9") != -1:
                print("[*] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) is already applied.")
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
            if re.search(rb"\x84\xc0\xe9.{4}\x90\x48\xb8\x09\x00\x00\x00\x03\x00", data, re.DOTALL):
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
                # Force HARDWARE_GL (0x01) instead of FALLBACK_SOFTWARE (0x03)
                offset_val = m.end() - 4
                data[offset_val] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at {hex(offset_jmp)}!")
                return True
            if re.search(rb"\x84\xc0\x90{6}\xc7\x45.\x01\x00\x00\x00", data):
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True
            print("[!] Warning: Patch 3 (GpuMode fallback to HARDWARE_GL) pattern not found!")
            return False

        def patch_p4_gldisplay(data: bytearray):
            p4_re = re.compile(rb"\x84\xc0\x74(.)\x48\x89\xd8\x48\x81\xc4\x38\x01\x00\x00", re.DOTALL)
            m = p4_re.search(data)
            if m:
                offset = m.start() + 2
                data[offset:offset+2] = b"\x90\x90"
                print(f"[+] Patch 4 (GLDisplayEGL Initialization) applied successfully at {hex(offset)}!")
                return True
            if data.find(b"\x84\xc0\x90\x90\x48\x89\xd8\x48\x81\xc4\x38\x01\x00\x00") != -1:
                print("[*] Patch 4 (GLDisplayEGL Initialization) is already applied.")
                return True
            print("[!] Warning: Patch 4 (GLDisplayEGL Initialization) pattern not found!")
            return False

        def patch_p5_gpumain(data: bytearray):
            p5_re = re.compile(rb"\x84\xc0\x0f\x85(....)\x48\xc7\x85\xa8\xfd\xff\xff(.)", re.DOTALL)
            m = p5_re.search(data)
            if m:
                disp = struct.unpack("<i", m.group(1))[0]
                offset = m.start() + 2
                # Replace 0f 85 (disp) with e9 (disp+1) 90
                data[offset:offset+6] = b"\xe9" + struct.pack("<i", disp + 1) + b"\x90"
                print(f"[+] Patch 5 (GpuMain Initialization Bypass) applied successfully at {hex(offset)}!")
                return True
            already_re = re.compile(rb"\x84\xc0\xe9(....)\x90\x48\xc7\x85\xa8\xfd\xff\xff(.)", re.DOTALL)
            if already_re.search(data):
                print("[*] Patch 5 (GpuMain Initialization Bypass) is already applied.")
                return True
            print("[!] Warning: Patch 5 (GpuMain Initialization Bypass) pattern not found!")
            return False

        def patch_p6_iosurface_target(data: bytearray):
            # Try modern Chromium pattern (136+)
            p6_modern_orig = bytes.fromhex("45 8b 47 38 4c 89 6c 24 18 89 44 24 10 0f b6 45 cc 89 44 24 08 c7 04 24 01 00 00 00")
            p6_modern_pat  = bytes.fromhex("41 b8 f5 84 00 00 4c 89 6c 24 18 89 44 24 10 89 04 24 0f b6 45 cc 89 44 24 08 66 90")
            idx = data.find(p6_modern_orig)
            if idx != -1:
                data[idx:idx+len(p6_modern_pat)] = p6_modern_pat
                print(f"[+] Patch 6 (IOSurface Factory Target 0x84f5 - Modern) applied successfully at {hex(idx)}!")
                return True
            if data.find(p6_modern_pat) != -1:
                print("[*] Patch 6 (IOSurface Factory Target 0x84f5 - Modern) is already applied.")
                return True

            # Try legacy pattern (135)
            p6_legacy_orig = bytes.fromhex("41 8b 46 20 45 8b 46 38 89 44 24 10")
            p6_legacy_pat  = bytes.fromhex("45 8b 46 38 c7 44 24 10 f5 84 00 00")
            idx_leg = data.find(p6_legacy_orig)
            if idx_leg != -1:
                data[idx_leg:idx_leg+len(p6_legacy_pat)] = p6_legacy_pat
                print(f"[+] Patch 6 (IOSurface Factory Target 0x84f5 - Legacy) applied successfully at {hex(idx_leg)}!")
                return True
            if data.find(p6_legacy_pat) != -1:
                print("[*] Patch 6 (IOSurface Factory Target 0x84f5 - Legacy) is already applied.")
                return True

            print("[!] Warning: Patch 6 (IOSurface Factory Target 0x84f5) pattern not found!")
            return False

        def patch_p7_validate_target(data: bytearray):
            p7_re = re.compile(rb"\x55\x48\x89\xe5\x85\xf6\x74(.)\x8b\x87\x90\x01\x00\x00", re.DOTALL)
            m = p7_re.search(data)
            if m:
                offset = m.start()
                data[offset:offset+4] = b"\xb0\x01\xc3\x90"
                print(f"[+] Patch 7 (ValidateTarget Always Return True) applied successfully at {hex(offset)}!")
                return True
            if data.find(b"\xb0\x01\xc3\x90\x85\xf6") != -1:
                print("[*] Patch 7 (ValidateTarget Always Return True) is already applied.")
                return True
            print("[!] Warning: Patch 7 (ValidateTarget Always Return True) pattern not found!")
            return False

        def patch_p8_backing_target(data: bytearray):
            p8_re = re.compile(rb"\x8b\x45(.)\x89\x83\x88\x01\x00\x00\x8b\x45(.)\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00\x66\xc7\x83\x94\x01\x00\x00\x00\x00", re.DOTALL)
            m = p8_re.search(data)
            if m:
                reg2 = m.group(2)
                rep = bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45") + reg2 + bytes.fromhex("88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 44 89 b3 94 01 00 00")
                data[m.start():m.end()] = rep
                print(f"[+] Patch 8 (IOSurfaceBacking gl_target_ = 0x84f5) applied successfully at {hex(m.start())}!")
                return True
            p8_applied_re = re.compile(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00\x66\x44\x89\xb3\x94\x01\x00\x00", re.DOTALL)
            if p8_applied_re.search(data):
                print("[*] Patch 8 (IOSurfaceBacking gl_target_ = 0x84f5) is already applied.")
                return True
            print("[!] Warning: Patch 8 (IOSurfaceBacking gl_target_ = 0x84f5) pattern not found!")
            return False

        return [
            ("Patch 1 (GetAllowedGLImplementation)", patch_p1_allowed_gl),
            ("Patch 2 (GetDisplayInitializationParams)", patch_p2_display_init),
            ("Patch 3 (GpuMode fallback to HARDWARE_GL)", patch_p3_gpumode),
            ("Patch 4 (GLDisplayEGL Initialization)", patch_p4_gldisplay),
            ("Patch 5 (GpuMain Initialization Bypass)", patch_p5_gpumain),
            ("Patch 6 (IOSurface Factory Target 0x84f5)", patch_p6_iosurface_target),
            ("Patch 7 (ValidateTarget Always Return True)", patch_p7_validate_target),
            ("Patch 8 (IOSurfaceBacking gl_target_ = 0x84f5)", patch_p8_backing_target)
        ]
