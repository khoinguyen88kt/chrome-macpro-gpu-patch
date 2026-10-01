#!/usr/bin/env python3
"""
Thorium Browser Patcher subclass for legacy Mac GPUs.
Thorium is a compiler-optimized Chromium fork for macOS (Alex313031/Thorium-MacOS).
Implements AVX/Clang-optimized opcode pattern scanning, ANGLE dylib injection,
and native C launcher.
"""
import os
import plistlib
import re
import struct
import subprocess
from .base import BaseBrowserPatcher, safe_copy, run

class ThoriumPatcher(BaseBrowserPatcher):
    name = "Thorium"
    slug = "thorium"
    possible_app_paths = [
        "/Applications/Thorium.app",
        os.path.expanduser("~/Applications/Thorium.app")
    ]
    bundle_id = "org.chromium.Thorium"
    app_bundle_name = "Thorium.app"
    framework_name = "Thorium Framework.framework"
    framework_binary_name = "Thorium Framework"
    launcher_name = "Thorium"
    launcher_src = "thorium_main.c"
    backup_base_dir = "~/.thorium_macpro_backups"

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/Thorium Helper (GPU).app")

        if not os.path.exists(fw_bin) or not os.path.exists(lib_egl) or not os.path.exists(launcher_dst) or not os.path.exists(gpu_helper):
            return False

        # 1. Check if GPU Helper is signed with LocalCodeSigner
        res = subprocess.run(["codesign", "-dvvv", gpu_helper], capture_output=True, text=True)
        if f"Authority={self.certificate_name}" not in res.stderr and f"Authority={self.certificate_name}" not in res.stdout:
            return False

        # 2. Check if GetAllowedGLImplementation bypass is applied
        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                if (bytes.fromhex("84 c0 eb 06 90 90 90 90 90 90 48 8b 45 b0") not in data
                        and not re.search(rb"\x84\xc0\xeb\x06\x90{6}\x48\x8b\x45.", data, re.DOTALL)):
                    return False
                if not re.search(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45.\x88\x83\x8c\x01\x00\x00", data, re.DOTALL):
                    return False
        except Exception:
            return False

        return True

    def pre_patch_hook(self, version):
        """Inject clean ANGLE dylibs into Libraries/ and check AVX2 support."""
        # 1. Check if host CPU supports AVX2 (Haswell+)
        try:
            res = subprocess.run(["sysctl", "-n", "machdep.cpu.leaf7_features"], capture_output=True, text=True)
            if "AVX2" not in res.stdout:
                print(f"[!] NOTICE: Host CPU does not support AVX2 instruction set.")
                print(f"    Note: Upstream Thorium for macOS is compiled with -march=haswell and will crash with SIGILL")
                print(f"    on pre-Haswell CPUs (Mac Pro 6,1 Ivy Bridge supports AVX 1.0 only).")
        except Exception:
            pass

        ver_dir = self.get_ver_dir(version)
        lib_dir = os.path.join(ver_dir, "Libraries")
        os.makedirs(lib_dir, exist_ok=True)
        ref_angle_lib = os.path.join(self.repo_root, "angle_dylibs")

        for dylib in ["libEGL.dylib", "libGLESv2.dylib"]:
            src = os.path.join(ref_angle_lib, dylib)
            dst = os.path.join(lib_dir, dylib)
            if not os.path.exists(dst):
                if os.path.exists(src):
                    print(f"[*] Copying clean {dylib} to Thorium {version}...")
                    safe_copy(src, dst)
                else:
                    print(f"[!] Warning: Reference dylib not found at {src}")
            else:
                print(f"[*] Thorium {version} has native {dylib}, keeping original.")

    def get_patches(self, version):
        # Patch 1: GetAllowedGLImplementation (Force Allow OpenGL on macOS)
        def patch_p1_force_allowed_gl(data: bytearray):
            p1_re = re.compile(rb"\x84\xc0\x74\x0f\x80\x7d\xb8\x00\x74\xcd\x48\x8b\x45\xb0")
            m = p1_re.search(data)
            if m:
                data[m.start()+2 : m.start()+10] = bytes.fromhex("eb 06 90 90 90 90 90 90")
                print(f"[+] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) applied successfully at 0x{m.start():x}!")
                return True
            if data.find(bytes.fromhex("84 c0 eb 06 90 90 90 90 90 90 48 8b 45 b0")) != -1:
                print("[*] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) is already applied.")
                return True
            p1_dyn = re.compile(rb"\x84\xc0\x74(.)\x80\x7d(.)\x00\x74(.)\x48\x8b\x45(.)", re.DOTALL)
            m2 = p1_dyn.search(data)
            if m2:
                data[m2.start()+2 : m2.start()+10] = bytes.fromhex("eb 06 90 90 90 90 90 90")
                print(f"[+] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) applied dynamically at 0x{m2.start():x}!")
                return True
            print("[!] Warning: Patch 1 (GetAllowedGLImplementation) pattern not found!")
            return False

        # Patch 2: GetDisplayInitializationParams (Force Display params to include OpenGL)
        def patch_p2_display_params(data: bytearray):
            # 1. Thorium AVX-optimized pattern (test r13b, r13b; ...; jz over 0x300000009)
            p2_thorium = re.compile(rb"((?:\x84\xc0|\x45\x84[\xc0-\xff]).{1,30})(\x0f\x84.{4})(.{1,60}\x48\xb8\x09\x00\x00\x00\x03\x00\x00\x00)", re.DOTALL)
            m = p2_thorium.search(data)
            if m:
                jump_pos = m.start() + len(m.group(1))
                jump_len = len(m.group(2))
                data[jump_pos : jump_pos + jump_len] = b"\x90" * jump_len
                print(f"[+] Patch 2 (GetDisplayInitializationParams - NOP jz) applied successfully at 0x{jump_pos:x}!")
                return True
            # Check already applied Thorium pattern
            p2_th_applied = re.compile(rb"(?:\x84\xc0|\x45\x84[\xc0-\xff]).{1,30}\x90{6}.{1,60}\x48\xb8\x09\x00\x00\x00\x03\x00\x00\x00", re.DOTALL)
            if p2_th_applied.search(data):
                print("[*] Patch 2 (GetDisplayInitializationParams) is already applied.")
                return True
            # 2. Standard Chromium 153+ pattern (replace jne with jmp)
            p2_re1 = re.compile(rb"\x84\xc0\x0f\x85(....)\x48\xb8\x09\x00\x00\x00\x03\x00", re.DOTALL)
            m1 = p2_re1.search(data)
            if m1:
                disp = struct.unpack("<i", m1.group(1))[0]
                offset = m1.start() + 2
                data[offset:offset+6] = b"\xe9" + struct.pack("<i", disp + 1) + b"\x90"
                print(f"[+] Patch 2 (GetDisplayInitializationParams - jmp) applied successfully at 0x{offset:x}!")
                return True
            if re.search(rb"\x84\xc0\xe9.{4}\x90\x48\xb8\x09\x00\x00\x00\x03\x00", data, re.DOTALL):
                print("[*] Patch 2 (GetDisplayInitializationParams) is already applied.")
                return True
            print("[!] Warning: Patch 2 (GetDisplayInitializationParams) pattern not found!")
            return False

        # Patch 3: GpuMode fallback to HARDWARE_GL
        def patch_p3_gpu_mode(data: bytearray):
            p3_re = re.compile(rb"\x84\xc0(\x0f\x84.{4}|\x74.)\xc7\x45(.)\x03\x00\x00\x00\x48\x8b", re.DOTALL)
            m = p3_re.search(data)
            if m:
                jump_len = len(m.group(1))
                data[m.start()+2 : m.start()+2+jump_len] = b"\x90" * jump_len
                imm_pos = m.start() + 2 + jump_len + 3
                data[imm_pos] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at 0x{m.start():x}!")
                return True
            elif re.search(rb"\x84\xc0(?:\x90{2}|\x90{6})\xc7\x45.\x01\x00\x00\x00\x48\x8b", data, re.DOTALL):
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True
            print("[!] Warning: Patch 3 (GpuMode fallback to HARDWARE_GL) pattern not found!")
            return False

        # Patch 4: Seatbelt IsSandboxed check bypass
        def patch_p4_seatbelt(data: bytearray):
            p4_re = re.compile(rb"(\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0)(\x0f\x84.{4}|\x74.)(?:\x48\x8b\xbb\x88\x00\x00\x00|\x48\x8b)", re.DOTALL)
            m = p4_re.search(data)
            if m:
                jump_pos = m.start() + len(m.group(1))
                jump_len = len(m.group(2))
                data[jump_pos : jump_pos + jump_len] = b"\x90" * jump_len
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied successfully at 0x{jump_pos:x}!")
                return True
            elif re.search(rb"\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0(?:\x90{2}|\x90{6})(?:\x48\x8b\xbb\x88\x00\x00\x00|\x48\x8b)", data, re.DOTALL):
                print("[*] Patch 4 (Seatbelt IsSandboxed) is already applied.")
                return True
            print("[!] Warning: Patch 4 (Seatbelt IsSandboxed) pattern not found!")
            return False

        # Patch 5: ScopedEGLSurfaceIOSurface::ValidateTarget (Force return true)
        def patch_p5_validate_target(data: bytearray):
            p6_153_pat = bytes.fromhex("b0 01 c3 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90")
            p6_pre_pat = bytes.fromhex("b0 01 c3 90 41 56 41 55 41 54 53 48 83 ec 10 49 89 fd 48 8b 07")
            if data.find(p6_153_pat) != -1 or data.find(p6_pre_pat) != -1:
                print("[*] Patch 5 (ScopedEGLSurfaceIOSurface::ValidateTarget) is already applied.")
                return True
            p6_applied_re = re.compile(rb"\xb0\x01\xc3\x90(?:\x41[\x50-\x57]|[\x50-\x57]){0,4}\x48\x81\xec\x30\x01\x00\x00", re.DOTALL)
            if p6_applied_re.search(data):
                print("[*] Patch 5 (ScopedEGLSurfaceIOSurface::ValidateTarget) is already applied.")
                return True

            p6_153_orig = bytes.fromhex("55 48 89 e5 41 56 53 48 81 ec 30 01 00 00 81 fe e1 0d 00 00")
            idx = data.find(p6_153_orig)
            if idx != -1:
                data[idx : idx + len(p6_153_pat)] = p6_153_pat
                print(f"[+] Patch 5 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied successfully at 0x{idx:x}!")
                return True

            p6_re = re.compile(rb"\x55\x48\x89\xe5(?:\x41[\x50-\x57]|[\x50-\x57]){1,4}\x48\x81\xec\x30\x01\x00\x00\x81\xfe\xe1\x0d\x00\x00", re.DOTALL)
            m = p6_re.search(data)
            if m:
                offset = m.start()
                data[offset : offset + 20] = p6_153_pat
                print(f"[+] Patch 5 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied dynamically at 0x{offset:x}!")
                return True

            print("[!] Warning: Patch 5 (ScopedEGLSurfaceIOSurface::ValidateTarget) pattern not found!")
            return False

        # Patch 6: IOSurfaceImageBacking constructor (gl_target_ = 0x84f5)
        def patch_p6_iosurface_backing(data: bytearray):
            p7_re = re.compile(rb"(\x8b\x45(.)\x89\x83\x88\x01\x00\x00\x8b\x45(.)\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00)(\x66\xc7\x83\x94\x01\x00\x00\x00\x00|\x66\x44\x89\xb3\x94\x01\x00\x00)", re.DOTALL)
            m = p7_re.search(data)
            if m:
                format_reg_offset = m.group(3)
                p7_patched = (
                    b"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00" +
                    b"\x8a\x45" + format_reg_offset +
                    b"\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00\x66\x44\x89\xb3\x94\x01\x00\x00"
                )
                data[m.start() : m.start() + len(p7_patched)] = p7_patched
                print(f"[+] Patch 6 (IOSurfaceImageBacking gl_target_ = 0x84f5) applied successfully at 0x{m.start():x}!")
                return True
            elif re.search(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45.\x88\x83\x8c\x01\x00\x00", data):
                print("[*] Patch 6 (IOSurfaceImageBacking gl_target_ = 0x84f5) is already applied.")
                return True
            print("[!] Warning: Patch 6 (IOSurfaceImageBacking gl_target_ = 0x84f5) pattern not found!")
            return False

        return [
            ("Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL)", patch_p1_force_allowed_gl),
            ("Patch 2 (GetDisplayInitializationParams)", patch_p2_display_params),
            ("Patch 3 (GpuMode fallback to HARDWARE_GL)", patch_p3_gpu_mode),
            ("Patch 4 (Seatbelt IsSandboxed)", patch_p4_seatbelt),
            ("Patch 5 (ScopedEGLSurfaceIOSurface::ValidateTarget)", patch_p5_validate_target),
            ("Patch 6 (IOSurfaceImageBacking gl_target_ = 0x84f5)", patch_p6_iosurface_backing),
        ]
