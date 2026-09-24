#!/usr/bin/env python3
"""
Google Chrome Patcher subclass for legacy Mac GPUs.
Implements the 7 binary patches, ANGLE dylib injection, and native C launcher.
"""
import os
import re
import struct
import subprocess
from .base import BaseBrowserPatcher, safe_copy

class ChromePatcher(BaseBrowserPatcher):
    name = "Google Chrome"
    slug = "chrome"
    possible_app_paths = [
        "/Applications/Google Chrome.app",
        os.path.expanduser("~/Applications/Google Chrome.app")
    ]
    bundle_id = "com.google.Chrome"
    app_bundle_name = "Google Chrome.app"
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

        # 2. Check if Pattern 1 (GetAllowedGLImplementation), Pattern 2 (GetDisplayInitializationParams), and Pattern 7 (IOSurfaceImageBacking texture_target 0x84f5) are patched
        p1_patched = bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")
        p2_patched = re.compile(rb"\x84\xc0\xe9.{4}\x90\x48\xb8\x09\x00\x00\x00\x03\x00", re.DOTALL)
        p7_patched = bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45 cc 88 83 8c 01 00 00")
        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                if data.find(p1_patched) == -1 and not re.search(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09(?:.|\n){1,60}\x84\xc0\x90\x90\x80\x7d(.)\x00", data, re.DOTALL):
                    return False
                if not p2_patched.search(data) and not re.search(rb"\x84\xc0\xe9.{4}\x90\x83\x7d.\x00\x0f\x85", data, re.DOTALL):
                    return False
                if data.find(p7_patched) == -1 and not re.search(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83\x8c\x01\x00\x00", data, re.DOTALL):
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
            # 1. Exact pattern for Chromium 153.x / macOS x86_64
            p1_exact = bytes.fromhex("84 c0 74 0f 80 7d b8 00 74 cd 48 8b 45 b0")
            idx = data.find(p1_exact)
            if idx != -1:
                data[idx+2 : idx+4] = b"\x90\x90"
                print(f"[+] Patch 1 (GetAllowedGLImplementation) applied successfully at {hex(idx)}!")
                return True
            if data.find(bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")) != -1:
                print("[*] Patch 1 (GetAllowedGLImplementation) is already applied.")
                return True

            # 2. Context-anchored pattern (shr rcx, 0x20; cmp rcx, 9) to ensure we are in GetAllowedGLImplementation
            p1_anchor = re.compile(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09(?:.|\n){1,60}\x84\xc0(\x74.)\x80\x7d(.)\x00", re.DOTALL)
            m = p1_anchor.search(data)
            if m:
                sub_idx = data[m.start():m.end()].find(b"\x84\xc0")
                target_offset = m.start() + sub_idx + 2
                data[target_offset:target_offset+2] = b"\x90\x90"
                print(f"[+] Patch 1 (GetAllowedGLImplementation) applied dynamically at {hex(target_offset)}!")
                return True
            if re.search(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09(?:.|\n){1,60}\x84\xc0\x90\x90\x80\x7d(.)\x00", data, re.DOTALL):
                print("[*] Patch 1 (GetAllowedGLImplementation) is already applied.")
                return True

            print("[!] Warning: Patch 1 (GetAllowedGLImplementation) pattern not found!")
            return False

        def patch_p2_display_init(data: bytearray):
            # 1. Chromium 153+ with mov rax, 0x300000009
            p2_re1 = re.compile(rb"\x84\xc0\x0f\x85(....)\x48\xb8\x09\x00\x00\x00\x03\x00", re.DOTALL)
            m1 = p2_re1.search(data)
            if m1:
                disp = struct.unpack("<i", m1.group(1))[0]
                offset = m1.start() + 2
                data[offset:offset+6] = b"\xe9" + struct.pack("<i", disp + 1) + b"\x90"
                print(f"[+] Patch 2 (GetDisplayInitializationParams) applied successfully at {hex(offset)}!")
                return True
            if re.search(rb"\x84\xc0\xe9.{4}\x90\x48\xb8\x09\x00\x00\x00\x03\x00", data, re.DOTALL):
                print("[*] Patch 2 (GetDisplayInitializationParams) is already applied.")
                return True
            # 2. Earlier Chromium 152 / pre-153 pattern
            p2_re2 = re.compile(rb"\x84\xc0\x0f\x85(....)\x83\x7d(.)\x00\x0f\x85", re.DOTALL)
            m2 = p2_re2.search(data)
            if m2:
                disp = struct.unpack("<i", m2.group(1))[0]
                offset = m2.start() + 2
                data[offset:offset+6] = b"\xe9" + struct.pack("<i", disp + 1) + b"\x90"
                print(f"[+] Patch 2 (GetDisplayInitializationParams) applied successfully at {hex(offset)}!")
                return True
            if re.search(rb"\x84\xc0\xe9.{4}\x90\x83\x7d.\x00\x0f\x85", data, re.DOTALL):
                print("[*] Patch 2 (GetDisplayInitializationParams) is already applied.")
                return True
            print("[!] Warning: Patch 2 (GetDisplayInitializationParams) pattern not found!")
            return False

        def patch_p3_gpumode(data: bytearray):
            # 1. Anchored dynamic pattern (with mov rax, [rbx+...])
            p3_anchor = re.compile(rb"\x84\xc0(?:\x0f\x84....|\x90{6})\xc7\x45(.)[\x01\x03]\x00\x00\x00\x48\x8b\x83", re.DOTALL)
            m = p3_anchor.search(data)
            if m:
                offset_jmp = m.start() + 2
                data[offset_jmp:offset_jmp+6] = b"\x90" * 6
                offset_val = m.start() + 11
                data[offset_val] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at {hex(offset_jmp)}!")
                return True
            # 2. Static pre-153 fallback
            p3_static = bytes.fromhex("84 c0 0f 84 8b 00 00 00 c7 45 ac 03 00 00 00 48 8b 83 38 07 00 00")
            idx = data.find(p3_static)
            if idx != -1:
                data[idx+2:idx+8] = b"\x90" * 6
                data[idx+14] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied at {hex(idx)}!")
                return True
            if data.find(bytes.fromhex("84 c0 90 90 90 90 90 90 c7 45 ac 01 00 00 00 48 8b 83 38 07 00 00")) != -1:
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True
            print("[!] Warning: Patch 3 (GpuMode fallback to HARDWARE_GL) pattern not found!")
            return False

        def patch_p4_seatbelt(data: bytearray):
            # 1. Chromium 153+ with mov rdi, [rbx + 0x88] (any jump displacement)
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
            # 2. Broader Seatbelt check in GpuMain (any register)
            p4_re2 = re.compile(rb"\x85\xc0\x0f\x84(....)\x48\x8b", re.DOTALL)
            m2 = p4_re2.search(data)
            if m2:
                offset = m2.start() + 2
                data[offset:offset+6] = b"\x90" * 6
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied dynamically at {hex(offset)}!")
                return True
            # 3. Pre-153 Seatbelt check pattern (\xe8....\x85\xc0\x0f\x84....)
            p4_re3 = re.compile(rb"\xe8....\x85\xc0\x0f\x84(....)", re.DOTALL)
            m3 = p4_re3.search(data)
            if m3:
                offset = m3.start() + 7
                data[offset:offset+6] = b"\x90" * 6
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied successfully at {hex(offset)}!")
                return True
            if re.search(rb"\xe8....\x85\xc0\x90\x90\x90\x90\x90\x90", data, re.DOTALL):
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
            # Pre-153 static pattern
            p5_pre153_orig = bytes.fromhex("48 8d b5 78 ff ff ff 48 89 df 48 89 44 24 08 89 44 24 10")
            p5_pre153_pat = bytes.fromhex("48 8d b5 78 ff ff ff 48 89 df 48 89 44 24 08 41 b8 f5 84 00 00")
            idx = data.find(p5_pre153_orig)
            if idx != -1:
                data[idx:idx+len(p5_pre153_pat)] = p5_pre153_pat
                print(f"[+] Patch 5 (IOSurface Factory Target 0x84f5) applied successfully at {hex(idx)}!")
                return True
            if data.find(p5_pre153_pat) != -1:
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
            # Pre-153 static pattern
            p6_pre_orig = bytes.fromhex("55 48 89 e5 41 56 41 55 41 54 53 48 83 ec 10 49 89 fd 48 8b 07")
            p6_pre_pat = bytes.fromhex("b0 01 c3 90 41 56 41 55 41 54 53 48 83 ec 10 49 89 fd 48 8b 07")
            idx = data.find(p6_pre_orig)
            if idx != -1:
                data[idx:idx+len(p6_pre_pat)] = p6_pre_pat
                print(f"[+] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied successfully at {hex(idx)}!")
                return True
            if data.find(p6_pre_pat) != -1:
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
            ("Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5)", patch_p7_backing_target),
        ]
