#!/usr/bin/env python3
"""
Vivaldi Browser Patcher subclass for legacy Mac GPUs.
Implements dynamic regex wildcard pattern scanning, ANGLE dylib injection,
obsolete bundle version cleanup, and native C launcher.
"""
import os
import re
import struct
import subprocess
from .base import BaseBrowserPatcher, safe_copy, run

class VivaldiPatcher(BaseBrowserPatcher):
    name = "Vivaldi"
    slug = "vivaldi"
    possible_app_paths = [
        "/Applications/Vivaldi.app",
        os.path.expanduser("~/Applications/Vivaldi.app")
    ]
    bundle_id = "com.vivaldi.Vivaldi"
    app_bundle_name = "Vivaldi.app"
    framework_name = "Vivaldi Framework.framework"
    framework_binary_name = "Vivaldi Framework"
    launcher_name = "Vivaldi"
    launcher_src = "vivaldi_main.c"
    backup_base_dir = "~/.vivaldi_macpro_backups"

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/Vivaldi Helper (GPU).app")

        if not os.path.exists(fw_bin) or not os.path.exists(lib_egl) or not os.path.exists(launcher_dst) or not os.path.exists(gpu_helper):
            return False

        # 1. Check if GPU Helper is signed with LocalCodeSigner
        res = subprocess.run(["codesign", "-dvvv", gpu_helper], capture_output=True, text=True)
        if f"Authority={self.certificate_name}" not in res.stderr and f"Authority={self.certificate_name}" not in res.stdout:
            return False

        # 2. Check if Pattern 1, Pattern 2, and Patch 8 are patched
        p1_patched = bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")
        p2_patched = re.compile(rb"\x84\xc0\xe9.{4}\x90\x48\xb8\x09\x00\x00\x00\x03\x00", re.DOTALL)
        p8_applied = re.compile(rb"\xc7\x83..\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83..\x00\x00", re.DOTALL)
        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                has_p1 = (data.find(p1_patched) != -1 or 
                          bool(re.search(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09(?:.|\n){1,60}\x84\xc0\x90\x90\x80\x7d(.)\x00", data, re.DOTALL)) or
                          bool(re.search(rb"\x48\x89\xc1\x48\xc1\xe9\x20\xe9.{4}\x90{5}", data, re.DOTALL)))
                if not has_p1:
                    return False
                if not p2_patched.search(data) and not re.search(rb"\x84\xc0\xe9.{4}\x90\x83\x7d.\x00\x0f\x85", data, re.DOTALL):
                    return False
                if not p8_applied.search(data):
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
            # 1. Exact match for je -> nop nop bypass
            p1_exact = bytes.fromhex("84 c0 74 0f 80 7d b8 00 74 cd 48 8b 45 b0")
            idx = data.find(p1_exact)
            if idx != -1:
                data[idx+2 : idx+4] = b"\x90\x90"
                print(f"[+] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) applied successfully at {hex(idx)}!")
                return True
            if data.find(bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")) != -1:
                print("[*] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) is already applied.")
                return True

            # 2. Context-anchored pattern (shr rcx, 0x20; cmp rcx, 9)
            p1_anchor = re.compile(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09(?:.|\n){1,60}\x84\xc0(\x74.)\x80\x7d(.)\x00", re.DOTALL)
            m_anc = p1_anchor.search(data)
            if m_anc:
                sub_idx = data[m_anc.start():m_anc.end()].find(b"\x84\xc0")
                target_offset = m_anc.start() + sub_idx + 2
                data[target_offset : target_offset + 2] = b"\x90\x90"
                print(f"[+] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) applied successfully at {hex(target_offset)}!")
                return True
            if re.search(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09(?:.|\n){1,60}\x84\xc0\x90\x90\x80\x7d(.)\x00", data, re.DOTALL):
                print("[*] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) is already applied.")
                return True

            # 3. Legacy jump pattern for older Chromium builds
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
            # 1. Chromium 136+ with mov rax, 0x300000009
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
            # 2. Earlier Chromium 135 / pre-136 pattern
            p2_re2 = re.compile(rb"\x84\xc0\x0f\x85(....)\x83\x7d(.)\x00\x0f\x85", re.DOTALL)
            m2 = p2_re2.search(data)
            if m2:
                disp = struct.unpack("<i", m2.group(1))[0]
                offset = m2.start() + 2
                data[offset:offset+6] = b"\xe9" + struct.pack("<i", disp + 1) + b"\x90"
                print(f"[+] Patch 2 (GetDisplayInitializationParams - Legacy) applied successfully at {hex(offset)}!")
                return True
            if re.search(rb"\x84\xc0\xe9.{4}\x90\x83\x7d.\x00\x0f\x85", data, re.DOTALL):
                print("[*] Patch 2 (GetDisplayInitializationParams) is already applied.")
                return True
            print("[!] Warning: Patch 2 (GetDisplayInitializationParams) pattern not found!")
            return False

        def patch_p3_gpumode(data: bytearray):
            # 1. Chromium vector-based GpuMode initialization (Vivaldi build)
            p3_vec = re.compile(rb"\x84\xc0(\x0f\x85.{4})\x48\xbf\xfc\xff\xff\xff\xff\xff\xff\x7f", re.DOTALL)
            m_vec = p3_vec.search(data)
            if m_vec:
                jump_pos = m_vec.start() + 2
                data[jump_pos : jump_pos + 6] = b"\x90" * 6
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at {hex(jump_pos)}!")
                return True
            if re.search(rb"\x84\xc0\x90{6}\x48\xbf\xfc\xff\xff\xff\xff\xff\xff\x7f", data):
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True

            # 2. Dynamic scalar fallback (for newer/older Chromium milestones)
            p3_scalar = re.compile(rb"\x84\xc0(\x0f\x84.{4}|\x74.)(.{0,16})\xc7\x45(.)\x03\x00\x00\x00\x48\x8b", re.DOTALL)
            m_sc = p3_scalar.search(data)
            if m_sc:
                jump_pos = m_sc.start() + 2
                jump_len = len(m_sc.group(1))
                data[jump_pos : jump_pos + jump_len] = b"\x90" * jump_len
                val_pos = jump_pos + jump_len + len(m_sc.group(2)) + 3
                data[val_pos] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at {hex(jump_pos)}!")
                return True
            if re.search(rb"\x84\xc0(?:\x90{2}|\x90{6})(.{0,16})\xc7\x45.\x01\x00\x00\x00\x48\x8b", data, re.DOTALL):
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True

            print("[!] Warning: Patch 3 (GpuMode fallback to HARDWARE_GL) pattern not found!")
            return False

        def patch_p4_seatbelt(data: bytearray):
            # Seatbelt IsSandboxed check bypass
            p4_re = re.compile(rb"(\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0)(\x0f\x84.{4}|\x74.)(?:\x48\x8b\xbb\x88\x00\x00\x00|\x48\x8b)", re.DOTALL)
            m = p4_re.search(data)
            if m:
                jump_pos = m.start() + len(m.group(1))
                jump_len = len(m.group(2))
                data[jump_pos : jump_pos + jump_len] = b"\x90" * jump_len
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied successfully at {hex(jump_pos)}!")
                return True
            p4_applied_re = re.compile(rb"\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0(?:\x90{2}|\x90{6})(?:\x48\x8b\xbb\x88\x00\x00\x00|\x48\x8b)", re.DOTALL)
            if p4_applied_re.search(data):
                print("[*] Patch 4 (Seatbelt IsSandboxed) is already applied.")
                return True
            # Static pattern fallback
            p4_static = bytes.fromhex("89 c7 31 f6 31 d2 31 c0 e8 8c fc f4 fe 85 c0 0f 84 8b 00 00 00 48 8b bb 88 00 00 00")
            idx = data.find(p4_static)
            if idx != -1:
                data[idx+14:idx+20] = b"\x90" * 6
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied at {hex(idx)}!")
                return True
            if data.find(bytes.fromhex("89 c7 31 f6 31 d2 31 c0 e8 8c fc f4 fe 85 c0 90 90 90 90 90 90 48 8b bb 88 00 00 00")) != -1:
                print("[*] Patch 4 (Seatbelt IsSandboxed) is already applied.")
                return True
            print("[!] Warning: Patch 4 (Seatbelt IsSandboxed) pattern not found!")
            return False

        def patch_p5_gldisplay(data: bytearray):
            if data.find(b"\x84\xc0\x90\x90\x48\x89\xd8\x48\x81\xc4\x38\x01\x00\x00") != -1:
                print("[*] Patch 5 (GLDisplayEGL Initialization) is already applied.")
                return True
            p5_re = re.compile(rb"\x84\xc0\x74(.)\x48\x89\xd8\x48\x81\xc4\x38\x01\x00\x00", re.DOTALL)
            m = p5_re.search(data)
            if m:
                offset = m.start() + 2
                data[offset:offset+2] = b"\x90\x90"
                print(f"[+] Patch 5 (GLDisplayEGL Initialization) applied successfully at {hex(offset)}!")
                return True
            # If not found in this Chromium build, it's non-fatal
            print("[*] Patch 5 (GLDisplayEGL Initialization) not applicable in this build (skipping).")
            return True

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
            # 1. ScopedEGLSurfaceIOSurface::ValidateTarget return true bypass
            p7_ret_true = re.compile(rb"(\x55\x48\x89\xe5[\x41\x54-\x57]*\x85\xf6\x74.)\x8b\x87", re.DOTALL)
            m = p7_ret_true.search(data)
            if m:
                target_offset = m.start()
                data[target_offset:target_offset+4] = b"\xb0\x01\xc3\x90"
                print(f"[+] Patch 7 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied successfully at {hex(target_offset)}!")
                return True
            if data.find(b"\xb0\x01\xc3\x90\x85\xf6") != -1 or re.search(rb"\xb0\x01\xc3\x90[\x41\x54-\x57]*\x85\xf6", data):
                print("[*] Patch 7 (ScopedEGLSurfaceIOSurface::ValidateTarget) is already applied.")
                return True

            # 2. Direct byte pattern fallback
            p7_exact = bytes.fromhex("55 48 89 e5 85 f6 74 15 8b 87 90 01 00 00")
            idx = data.find(p7_exact)
            if idx != -1:
                data[idx:idx+4] = b"\xb0\x01\xc3\x90"
                print(f"[+] Patch 7 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied at {hex(idx)}!")
                return True

            print("[!] Warning: Patch 7 (ScopedEGLSurfaceIOSurface::ValidateTarget) pattern not found!")
            return False

        def patch_p8_backing_target(data: bytearray):
            # Dynamic struct offset analysis
            p8_orig_re = re.compile(rb"\x8b\x45(.)\x89\x83(..\x00\x00)\x8b\x45(.)\x88\x83(..\x00\x00)\x45\x31\xf6\x44\x89\xb3(..\x00\x00)\x66\xc7\x83(..\x00\x00)\x00\x00", re.DOTALL)
            m = p8_orig_re.search(data)
            if m:
                reg1, off1, reg2, off2, off3, off4 = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
                rep = (
                    bytes.fromhex("c7 83") + off1 + bytes.fromhex("f5 84 00 00 8a 45") +
                    reg2 + bytes.fromhex("88 83") + off2 +
                    bytes.fromhex("45 31 f6 44 89 b3") + off3 +
                    bytes.fromhex("66 44 89 b3") + off4
                )
                data[m.start():m.end()] = rep
                print(f"[+] Patch 8 (IOSurfaceImageBacking gl_target_ = 0x84f5) applied successfully at {hex(m.start())}!")
                return True
            p8_applied_re = re.compile(rb"\xc7\x83..\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83..\x00\x00\x45\x31\xf6\x44\x89\xb3..\x00\x00\x66\x44\x89\xb3..\x00\x00", re.DOTALL)
            if p8_applied_re.search(data):
                print("[*] Patch 8 (IOSurfaceImageBacking gl_target_ = 0x84f5) is already applied.")
                return True
            print("[!] Warning: Patch 8 (IOSurfaceImageBacking gl_target_ = 0x84f5) pattern not found!")
            return False

        return [
            ("Patch 1 (GetAllowedGLImplementation)", patch_p1_allowed_gl),
            ("Patch 2 (GetDisplayInitializationParams)", patch_p2_display_init),
            ("Patch 3 (GpuMode fallback to HARDWARE_GL)", patch_p3_gpumode),
            ("Patch 4 (Seatbelt IsSandboxed)", patch_p4_seatbelt),
            ("Patch 5 (GLDisplayEGL Initialization)", patch_p5_gldisplay),
            ("Patch 6 (IOSurface Factory Target 0x84f5)", patch_p6_iosurface_target),
            ("Patch 7 (ValidateTarget Always Return True)", patch_p7_validate_target),
            ("Patch 8 (IOSurfaceImageBacking gl_target_ = 0x84f5)", patch_p8_backing_target)
        ]
