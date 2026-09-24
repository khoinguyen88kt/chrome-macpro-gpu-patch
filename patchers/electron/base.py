#!/usr/bin/env python3
"""
Base Electron Patcher for macOS Legacy GPUs.
Inherits from BaseBrowserPatcher and provides Electron-specific handling:
  - Opt-in only enforcement (excluded from default 'all' browser sweep)
  - Versions/A/ bundle directory structure handling
  - Chromium milestone discovery from Electron Framework binary
  - Non-invasive launcher wrapper shim strategy (preserves Team ID, Keychain ACLs, Entitlements)
"""
import os
import re
import shutil
import plistlib
import subprocess
from ..base import BaseBrowserPatcher

class BaseElectronPatcher(BaseBrowserPatcher):
    name = "Base Electron App"
    slug = "base_electron"
    is_opt_in = True  # Must be explicitly requested by user; never touched by 'all'

    framework_name = "Electron Framework.framework"
    framework_binary_name = "Electron Framework"
    version_dir_name = "A"

    executable_name = None  # Override in subclass, e.g. "Code"

    def get_current_version(self):
        """Electron uses Versions/A/ so version is read from Info.plist."""
        info_plist = os.path.join(self.app_path, "Contents/Info.plist")
        if os.path.exists(info_plist):
            try:
                with open(info_plist, "rb") as f:
                    plist = plistlib.load(f)
                return plist.get("CFBundleShortVersionString") or plist.get("CFBundleVersion") or "A"
            except Exception:
                pass
        return "A"

    def get_executable_bin(self):
        name = self.executable_name
        if not name:
            info_plist = os.path.join(self.app_path, "Contents/Info.plist")
            if os.path.exists(info_plist):
                try:
                    with open(info_plist, "rb") as f:
                        plist = plistlib.load(f)
                    name = plist.get("CFBundleExecutable")
                except Exception:
                    pass
        return os.path.join(self.app_path, "Contents/MacOS", name or "Electron")

    def get_executable_real(self):
        return f"{self.get_executable_bin()}.real"

    def get_framework_bin(self, version=None):
        return os.path.join(
            self.app_path,
            "Contents/Frameworks",
            self.framework_name,
            "Versions",
            self.version_dir_name,
            self.framework_binary_name
        )

    def get_chromium_milestone(self):
        """Extracts the underlying Chromium milestone from Electron Framework using chunked scanning."""
        fw_bin = self.get_framework_bin()
        if not os.path.exists(fw_bin):
            return None
        try:
            chunk_size = 8 * 1024 * 1024
            overlap = 64
            with open(fw_bin, "rb") as f:
                prev_tail = b""
                # Scan up to 250MB in 8MB chunks to avoid memory pressure on fat universal binaries
                for _ in range(32):
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    data = prev_tail + chunk
                    m = re.search(rb"Chrome/(\d+)\.", data)
                    if m:
                        return int(m.group(1))
                    prev_tail = chunk[-overlap:]
        except Exception:
            pass
        return None

    def is_already_patched(self, version=None):
        exe_real = self.get_executable_real()
        exe_bin = self.get_executable_bin()
        if not os.path.exists(exe_real) or not os.path.exists(exe_bin):
            return False
        try:
            # If exe_bin is our shell wrapper, it opens as UTF-8 text containing the marker;
            # if unpatched, it is a Mach-O binary and will not contain the string.
            with open(exe_bin, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                return os.path.basename(exe_real) in content and "--use-angle=gl" in content
        except Exception:
            return False

    def restore_wrapper(self):
        exe_bin = self.get_executable_bin()
        exe_real = self.get_executable_real()

        if not os.path.exists(exe_real):
            print(f"[-] No backup ({os.path.basename(exe_real)}) found. {self.name} appears to be already unpatched.")
            return True

        try:
            print(f"[*] Restoring original {self.name} executable from {os.path.basename(exe_real)}...")
            if os.path.exists(exe_bin):
                os.remove(exe_bin)
            shutil.move(exe_real, exe_bin)
            os.chmod(exe_bin, 0o755)
            self.post_restore_hook()
            print(f"[+] {self.name} successfully restored to original binary!")
            return True
        except Exception as e:
            print(f"[!] Error during restore: {e}")
            return False

    def post_restore_hook(self):
        """Optional hook for subclasses (e.g. symlink re-creation)."""
        pass

    def post_wrapper_hook(self):
        """Optional hook for subclasses after wrapper is installed."""
        pass

    def apply_wrapper_patch(self, milestone=None):
        exe_bin = self.get_executable_bin()
        exe_real = self.get_executable_real()
        real_basename = os.path.basename(exe_real)

        print(f"[*] Applying non-invasive launcher wrapper shim (--use-angle=gl)...")
        if milestone:
            print(f"    Detected Chromium milestone: M{milestone}")
            if milestone >= 152:
                print(f"[!] Chromium M{milestone} removed the ANGLE GL backend on macOS (M152, CL 7898546).")
                print("    '--use-angle=gl' would fail GPU initialization rather than be ignored. Refusing to patch.")
                print("    A drop-in CGL-enabled ANGLE dylib replacement will be required for this build.")
                return False
            else:
                print(f"    ANGLE OpenGL is natively supported in M{milestone} (< M152).")
        print(f"    Wrapper strategy preserves original code signature, Team ID,")
        print(f"    and macOS Keychain entitlements (passwords, tokens, credentials).")

        try:
            # 1. Rename original executable to .real
            if not os.path.exists(exe_real):
                if os.path.exists(exe_bin):
                    print(f"[*] Moving original binary to {real_basename}...")
                    shutil.move(exe_bin, exe_real)
                else:
                    print(f"[!] Error: Executable not found at {exe_bin}")
                    return False

            # 2. Write bash wrapper
            print(f"[*] Writing launcher wrapper to {os.path.basename(exe_bin)}...")
            wrapper_script = (
                f"#!/bin/bash\n"
                f'if [ -n "$ELECTRON_RUN_AS_NODE" ]; then\n'
                f'    exec "$(dirname "$0")/{real_basename}" "$@"\n'
                f'else\n'
                f'    exec "$(dirname "$0")/{real_basename}" --use-angle=gl "$@"\n'
                f'fi\n'
            )
            with open(exe_bin, "w", encoding="utf-8") as f:
                f.write(wrapper_script)
            os.chmod(exe_bin, 0o755)

            # 3. Post-wrapper hook
            self.post_wrapper_hook()

            print(f"[+] {self.name} launcher wrapper installed successfully!")
            print(f"[*] Hardware acceleration (OpenGL ANGLE) is now active.")
            return True
        except Exception as e:
            print(f"[!] Failed to apply wrapper patch: {e}")
            return False

    def run_patch(self, auto=False, notify_user=False, check_only=False, restore_mode=False, force=False):
        if not self.is_installed():
            print(f"[-] {self.name} is not installed at {self.app_path}.")
            return 1

        current_ver = self.get_current_version()
        milestone = self.get_chromium_milestone()
        m_str = f" (Chromium M{milestone})" if milestone else ""

        print(f"\n{'='*60}")
        print(f" [{self.name}] Target: {self.app_path} (v{current_ver}){m_str}")
        print(f" Type: Electron App (Opt-In Only)")
        print(f"{'='*60}")

        if restore_mode:
            ok = self.restore_wrapper()
            return 0 if ok else 1

        if check_only:
            if self.is_already_patched(current_ver):
                print(f"[+] {self.name} is ALREADY patched (launcher wrapper active).")
                return 0
            else:
                print(f"[-] {self.name} is NOT patched.")
                return 1

        if not force and self.is_already_patched(current_ver):
            print(f"[+] {self.name} is ALREADY patched. Nothing to do (use --force to re-apply).")
            return 0

        ok = self.apply_wrapper_patch(milestone)
        return 0 if ok else 1
