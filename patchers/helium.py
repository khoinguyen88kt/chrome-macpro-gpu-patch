#!/usr/bin/env python3
"""
Helium Browser Patcher subclass for legacy Mac GPUs.
Helium is an open-source privacy Chromium fork (imputnet/helium-macos).
Implements dynamic regex wildcard pattern scanning, ANGLE dylib injection,
and native C launcher.
"""
import os
import plistlib
import re
import struct
import subprocess
from .base import BaseBrowserPatcher, safe_copy, run

class HeliumPatcher(BaseBrowserPatcher):
    name = "Helium"
    slug = "helium"
    possible_app_paths = [
        "/Applications/Helium.app",
        os.path.expanduser("~/Applications/Helium.app")
    ]
    bundle_id = "net.imput.helium"
    app_bundle_name = "Helium.app"
    framework_name = "Helium Framework.framework"
    framework_binary_name = "Helium Framework"
    launcher_name = "Helium"
    launcher_src = "helium_main.c"
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
                # Check if a clean backup matching app_ver exists in legacy backup dir
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
                # If backup exists but installed fw_bin is an unpatched update, update the backup
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
        app_ver = self.get_app_bundle_version()
        fw_bin = self.get_framework_bin(version)
        if app_ver and os.path.exists(fw_bin):
            try:
                with open(fw_bin, "rb") as f:
                    data = f.read()
                    if app_ver.encode("ascii") + b"\x00" not in data:
                        print(f"\n[!] WARNING: Helium version mismatch detected!")
                        print(f"    Helium.app Info.plist version is '{app_ver}', but '{self.framework_binary_name}'")
                        print(f"    does not contain '{app_ver}' (likely an older build was restored from backup).")
                        print(f"    This causes Settings (helium://settings) to crash with RESULT_CODE_KILLED_BAD_MESSAGE.")
                        print(f"    To fix: Please download and reinstall Helium {app_ver} from:")
                        print(f"    https://github.com/imputnet/helium-macos/releases")
                        print(f"    and run this patcher again.\n")
            except Exception:
                pass

    def restore(self, version):
        # Fallback to legacy unversioned backup if versioned backup does not exist
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

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/Helium Helper (GPU).app")

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
                if bytes.fromhex("84 c0 eb 06 90 90 90 90 90 90 48 8b 45 b0") not in data:
                    return False
        except Exception:
            return False

        return True

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
            p1_dyn = re.compile(rb"\x84\xc0\x74(.)\x80\x7d(.)\x00\x74(.)\x48\x8b\x45(.)")
            m2 = p1_dyn.search(data)
            if m2:
                data[m2.start()+2 : m2.start()+10] = bytes.fromhex("eb 06 90 90 90 90 90 90")
                print(f"[+] Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL) applied dynamically at 0x{m2.start():x}!")
                return True
            print("[!] Warning: Patch 1 (GetAllowedGLImplementation) pattern not found!")
            return False

        def patch_p2_display_params(data: bytearray):
            p2_re = re.compile(rb"\x84\xc0\x0f\x85(.{4})\x48\xb8\x09\x00\x00\x00\x03\x00\x00\x00")
            m = p2_re.search(data)
            if m:
                target_disp = struct.unpack("<i", m.group(1))[0]
                new_disp = target_disp + 1
                disp_bytes = struct.pack("<i", new_disp)
                patch = b"\xe9" + disp_bytes + b"\x90"
                data[m.start()+2:m.start()+8] = patch
                print(f"[+] Patch 2 (GetDisplayInitializationParams) applied successfully at 0x{m.start():x}!")
                return True
            elif re.search(rb"\x84\xc0\xe9.{4}\x90\x48\xb8\x09\x00\x00\x00\x03\x00\x00\x00", data):
                print("[*] Patch 2 (GetDisplayInitializationParams) is already applied.")
                return True
            print("[!] Warning: Patch 2 (GetDisplayInitializationParams) pattern not found!")
            return False

        def patch_p3_gpu_mode(data: bytearray):
            p3_re = re.compile(rb"\x84\xc0(\x0f\x84.{4}|\x74.)\xc7\x45(.)\x03\x00\x00\x00\x48\x8b")
            m = p3_re.search(data)
            if m:
                jump_len = len(m.group(1))
                data[m.start()+2 : m.start()+2+jump_len] = b"\x90" * jump_len
                imm_pos = m.start() + 2 + jump_len + 3
                data[imm_pos] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at 0x{m.start():x}!")
                return True
            elif re.search(rb"\x84\xc0(?:\x90{2}|\x90{6})\xc7\x45.\x01\x00\x00\x00\x48\x8b", data):
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True
            print("[!] Warning: Patch 3 (GpuMode fallback to HARDWARE_GL) pattern not found!")
            return False

        def patch_p4_seatbelt(data: bytearray):
            p4_re = re.compile(rb"\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0(\x0f\x84.{4}|\x74.)")
            m = p4_re.search(data)
            if m:
                jump_pos = m.start() + 15
                jump_len = len(m.group(1))
                data[jump_pos : jump_pos + jump_len] = b"\x90" * jump_len
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied successfully at 0x{m.start():x}!")
                return True
            elif re.search(rb"\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0(?:\x90{2}|\x90{6})", data):
                print("[*] Patch 4 (Seatbelt IsSandboxed) is already applied.")
                return True
            print("[!] Warning: Patch 4 (Seatbelt IsSandboxed) pattern not found!")
            return False

        def patch_p5_iosurface_factory(data: bytearray):
            p5_re = re.compile(rb"(\x41\x8b[\x40-\x7f]\x20|\x44\x8b[\x40-\x7f]\x20)(?:\x45\x8b[\x40-\x7f]\x38|\x41\x8b[\x40-\x7f]\x38)(.{0,20}\xc7\x04\x24\x01\x00\x00\x00)")
            m = p5_re.search(data)
            if m:
                first_mov = m.group(1)
                tail = m.group(2)
                tail_patched = tail.replace(b"\xc7\x04\x24\x01\x00\x00\x00", b"\x89\x04\x24\x66\x90")
                replacement = first_mov + b"\x41\xb8\xf5\x84\x00\x00" + tail_patched
                pad = len(m.group(0)) - len(replacement)
                if pad >= 0:
                    replacement += b"\x90" * pad
                    data[m.start() : m.start() + len(m.group(0))] = replacement
                    print(f"[+] Patch 5 (IOSurface Factory Target 0x84f5) applied successfully at 0x{m.start():x}!")
                    return True
            elif b"\x41\xb8\xf5\x84\x00\x00" in data and b"\x89\x04\x24\x66\x90" in data:
                print("[*] Patch 5 (IOSurface Factory Target 0x84f5) is already applied.")
                return True
            print("[!] Warning: Patch 5 (IOSurface Factory Target 0x84f5) pattern not found!")
            return False

        def patch_p6_validate_target(data: bytearray):
            p6_orig = bytes.fromhex("55 48 89 e5 41 56 53 48 81 ec 30 01 00 00 81 fe e1 0d 00 00")
            p6_patched = bytes.fromhex("b0 01 c3 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90")
            idx = data.find(p6_orig)
            if idx != -1:
                data[idx : idx + len(p6_patched)] = p6_patched
                print(f"[+] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied successfully at 0x{idx:x}!")
                return True
            elif data.find(p6_patched) != -1:
                print("[*] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) is already applied.")
                return True
            print("[!] Warning: Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) pattern not found!")
            return False

        def patch_p7_iosurface_backing(data: bytearray):
            p7_re = re.compile(rb"(\x8b\x45(.)\x89\x83\x88\x01\x00\x00\x8b\x45(.)\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00)(\x66\xc7\x83\x94\x01\x00\x00\x00\x00|\x66\x44\x89\xb3\x94\x01\x00\x00)")
            m = p7_re.search(data)
            if m:
                target_reg_offset = m.group(2)
                format_reg_offset = m.group(3)
                p7_patched = (
                    b"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00" +
                    b"\x8a\x45" + format_reg_offset +
                    b"\x88\x83\x8c\x01\x00\x00\x45\x31\xf6\x44\x89\xb3\x90\x01\x00\x00\x66\x44\x89\xb3\x94\x01\x00\x00"
                )
                data[m.start() : m.start() + len(p7_patched)] = p7_patched
                print(f"[+] Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5) applied successfully at 0x{m.start():x}!")
                return True
            elif re.search(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45.\x88\x83\x8c\x01\x00\x00", data):
                print("[*] Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5) is already applied.")
                return True
            print("[!] Warning: Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5) pattern not found!")
            return False

        return [
            ("Patch 1 (GetAllowedGLImplementation - Force Allow OpenGL)", patch_p1_force_allowed_gl),
            ("Patch 2 (GetDisplayInitializationParams)", patch_p2_display_params),
            ("Patch 3 (GpuMode fallback to HARDWARE_GL)", patch_p3_gpu_mode),
            ("Patch 4 (Seatbelt IsSandboxed)", patch_p4_seatbelt),
            ("Patch 5 (IOSurfaceImageBackingFactory target 0x84f5)", patch_p5_iosurface_factory),
            ("Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget)", patch_p6_validate_target),
            ("Patch 7 (IOSurfaceImageBacking gl_target_ = 0x84f5)", patch_p7_iosurface_backing),
        ]
