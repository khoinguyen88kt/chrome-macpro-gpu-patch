#!/usr/bin/env python3
"""
CocCoc Browser Patcher subclass for legacy Mac GPUs.
Implements dynamic pattern scanning, ANGLE dylib injection,
and native C launcher for Cốc Cốc browser on macOS.
"""
import os
import re
import struct
import subprocess
from .base import BaseBrowserPatcher, safe_copy, run


class CocCocPatcher(BaseBrowserPatcher):
    name = "CocCoc"
    slug = "coccoc"
    possible_app_paths = [
        "/Applications/CocCoc.app",
        os.path.expanduser("~/Applications/CocCoc.app"),
    ]
    bundle_id = "com.coccoc.Coccoc"
    app_bundle_name = "CocCoc.app"
    framework_name = "CocCoc Framework.framework"
    framework_binary_name = "CocCoc Framework"
    launcher_name = "CocCoc"
    launcher_src = "coccoc_main.c"
    backup_base_dir = "~/.coccoc_macpro_backups"

    def is_already_patched(self, version):
        ver_dir = self.get_ver_dir(version)
        fw_bin = self.get_framework_bin(version)
        lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
        launcher_dst = self.get_launcher_dst()
        gpu_helper = os.path.join(ver_dir, "Helpers/CocCoc Helper (GPU).app")

        if not os.path.exists(fw_bin) or not os.path.exists(lib_egl) or not os.path.exists(launcher_dst) or not os.path.exists(gpu_helper):
            return False

        # 1. Check if GPU Helper is signed with LocalCodeSigner
        res = subprocess.run(["codesign", "-dvvv", gpu_helper], capture_output=True, text=True)
        if f"Authority={self.certificate_name}" not in res.stderr and f"Authority={self.certificate_name}" not in res.stdout:
            return False

        # 2. Check binary patch marks
        p1_applied = re.compile(rb"\x48\x89\xc1\x48\xc1\xe9\x20\x48\x83\xf9\x09(?:.|\n){1,60}\x84\xc0\x90\x90\x80\x7d(.)\x00", re.DOTALL)
        p3_applied = re.compile(rb"\x4c\x8d\xa3\x30\x07\x00\x00(?:.|\n){1,80}\x84\xc0\xe9.{4}\x90", re.DOTALL)
        p7_applied = re.compile(rb"\xc7\x83\x88\x01\x00\x00\xf5\x84\x00\x00\x8a\x45(.)\x88\x83\x8c\x01\x00\x00", re.DOTALL)

        try:
            with open(fw_bin, "rb") as f:
                data = f.read()
                if not p1_applied.search(data):
                    return False
                if not p3_applied.search(data):
                    return False
                if not p7_applied.search(data):
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
            if not os.path.exists(dst):
                if os.path.exists(src):
                    print(f"[*] Copying clean {dylib} to {version}...")
                    safe_copy(src, dst)
                else:
                    print(f"[!] Warning: Reference dylib not found at {src}")
            else:
                print(f"[*] Native {dylib} found, ensuring clean copy...")
                safe_copy(src, dst)

    def get_patches(self, version):
        def patch_p1_allowed_gl(data: bytearray):
            # 1. Exact pattern for Chromium / macOS x86_64
            p1_exact = bytes.fromhex("84 c0 74 0f 80 7d b8 00 74 cd 48 8b 45 b0")
            idx = data.find(p1_exact)
            if idx != -1:
                data[idx+2 : idx+4] = b"\x90\x90"
                print(f"[+] Patch 1 (GetAllowedGLImplementation) applied successfully at {hex(idx)}!")
                return True
            if data.find(bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")) != -1:
                print("[*] Patch 1 (GetAllowedGLImplementation) is already applied.")
                return True

            # 2. Context-anchored pattern (shr rcx, 0x20; cmp rcx, 9)
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
            # Earlier Chromium 152 pattern
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
            # Check already applied
            p3_applied = re.compile(rb"\x4c\x8d\xa3\x30\x07\x00\x00(?:.|\n){1,80}\x84\xc0\xe9.{4}\x90", re.DOTALL)
            if p3_applied.search(data):
                print("[*] Patch 3 (GpuMode fallback to HARDWARE_GL) is already applied.")
                return True

            # CocCoc Chromium vector GpuMode pattern: anchor at lea r12, [rbx + 0x730]
            p3_anchor = re.compile(rb"(\x4c\x8d\xa3\x30\x07\x00\x00(?:.|\n){1,80}\x84\xc0)\x0f\x84(....)", re.DOTALL)
            m = p3_anchor.search(data)
            if m:
                disp = struct.unpack("<i", m.group(2))[0]
                jump_offset = m.start() + len(m.group(1))
                data[jump_offset : jump_offset + 6] = b"\xe9" + struct.pack("<i", disp + 1) + b"\x90"
                for push_m in re.finditer(rb"\x41\xc7\x07\x03\x00\x00\x00", data[jump_offset : jump_offset + 600]):
                    idx = jump_offset + push_m.start() + 4
                    data[idx] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at {hex(jump_offset)}!")
                return True

            # Fallback to Chromium 153+ scalar pattern if upgraded
            p3_re153 = re.compile(rb"\x84\xc0(\x0f\x84.{4}|\x74.)(.{0,16})\xc7\x45(.)\x03\x00\x00\x00\x48\x8b\x83", re.DOTALL)
            m2 = p3_re153.search(data)
            if m2:
                jump_pos = m2.start() + 2
                jump_len = len(m2.group(1))
                data[jump_pos : jump_pos + jump_len] = b"\x90" * jump_len
                val_pos = jump_pos + jump_len + len(m2.group(2)) + 3
                data[val_pos] = 0x01
                print(f"[+] Patch 3 (GpuMode fallback to HARDWARE_GL) applied successfully at {hex(jump_pos)}!")
                return True

            print("[!] Warning: Patch 3 (GpuMode fallback to HARDWARE_GL) pattern not found!")
            return False

        def patch_p4_seatbelt(data: bytearray):
            p4_re = re.compile(rb"(\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0)(\x0f\x84.{4}|\x74.)(?:\x48\x8b\xbb\x88\x00\x00\x00|\x48\x8b)", re.DOTALL)
            m = p4_re.search(data)
            if m:
                jump_pos = m.start() + len(m.group(1))
                jump_len = len(m.group(2))
                data[jump_pos : jump_pos + jump_len] = b"\x90" * jump_len
                print(f"[+] Patch 4 (Seatbelt IsSandboxed) applied successfully at {hex(jump_pos)}!")
                return True
            p4_applied = re.compile(rb"\x89\xc7\x31\xf6\x31\xd2\x31\xc0\xe8.{4}\x85\xc0(?:\x90{2}|\x90{6})\x48\x8b", re.DOTALL)
            if p4_applied.search(data):
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
            p6_153_pat = bytes.fromhex("b0 01 c3 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90")
            p6_pre_pat = bytes.fromhex("b0 01 c3 90 41 56 41 55 41 54 53 48 83 ec 10 49 89 fd 48 8b 07")
            if data.find(p6_153_pat) != -1 or data.find(p6_pre_pat) != -1:
                print("[*] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) is already applied.")
                return True
            p6_applied_re = re.compile(rb"\xb0\x01\xc3\x90(?:\x41[\x50-\x57]|[\x50-\x57]){0,4}\x48\x81\xec\x30\x01\x00\x00", re.DOTALL)
            if p6_applied_re.search(data):
                print("[*] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) is already applied.")
                return True

            # Chromium 153+ exact pattern
            p6_153_orig = bytes.fromhex("55 48 89 e5 41 56 53 48 81 ec 30 01 00 00 81 fe e1 0d 00 00")
            idx = data.find(p6_153_orig)
            if idx != -1:
                data[idx : idx + len(p6_153_pat)] = p6_153_pat
                print(f"[+] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied successfully at {hex(idx)}!")
                return True

            # Dynamic pattern
            p6_re = re.compile(rb"\x55\x48\x89\xe5(?:\x41[\x50-\x57]|[\x50-\x57]){1,4}\x48\x81\xec\x30\x01\x00\x00\x81\xfe\xe1\x0d\x00\x00", re.DOTALL)
            m = p6_re.search(data)
            if m:
                offset = m.start()
                data[offset : offset + 20] = p6_153_pat
                print(f"[+] Patch 6 (ScopedEGLSurfaceIOSurface::ValidateTarget) applied dynamically at {hex(offset)}!")
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

    def probe_gpu_status(self):
        """Overrides probe to isolate CocCoc from any already-running profile instance."""
        launcher_dst = self.get_launcher_dst()
        if not os.path.exists(launcher_dst):
            return "NOT_FOUND", f"Executable not found at {launcher_dst}"

        import base64, subprocess, re
        probe_html = (
            "<!DOCTYPE html><html><body><div id=\"gpu_result\">WAITING</div><script>\n"
            "try {\n"
            "  const c = document.createElement('canvas');\n"
            "  const gl = c.getContext('webgl') || c.getContext('experimental-webgl');\n"
            "  if (!gl) {\n"
            "    document.getElementById('gpu_result').innerText = 'DISABLED';\n"
            "  } else {\n"
            "    const ext = gl.getExtension('WEBGL_debug_renderer_info');\n"
            "    const r = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'ENABLED_NO_INFO';\n"
            "    document.getElementById('gpu_result').innerText = r;\n"
            "  }\n"
            "} catch(e) {\n"
            "  document.getElementById('gpu_result').innerText = 'ERROR:' + e.message;\n"
            "}\n"
            "</script></body></html>"
        )
        b64 = base64.b64encode(probe_html.encode("utf-8")).decode("ascii")
        data_uri = f"data:text/html;base64,{b64}"

        cmd = [
            launcher_dst,
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--user-data-dir=/tmp/coccoc_gpu_probe",
            "--dump-dom",
            data_uri
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            m = re.search(r"<div id=\"gpu_result\">(.*?)</div>", res.stdout)
            if m:
                renderer = m.group(1).strip()
                if renderer == "DISABLED":
                    return "DISABLED", "Hardware acceleration / WebGL is disabled by Chromium"
                elif any(s in renderer for s in ["SwiftShader", "Software", "llvmpipe"]):
                    return "SOFTWARE", renderer
                elif renderer.startswith("ERROR:"):
                    return "ERROR", renderer
                else:
                    return "HARDWARE", renderer
            return "UNKNOWN", "Could not parse probe output"
        except subprocess.TimeoutExpired:
            return "TIMEOUT", "Process timed out during GPU probe"
        except Exception as e:
            return "ERROR", str(e)

