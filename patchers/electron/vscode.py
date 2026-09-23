#!/usr/bin/env python3
"""
Visual Studio Code Patcher for macOS Legacy GPUs.
Inherits from BaseElectronPatcher.
Uses non-invasive launcher wrapper shim to preserve Microsoft code signature and GitHub Copilot/Keychain tokens.
"""
import os
from .base import BaseElectronPatcher

class VSCodePatcher(BaseElectronPatcher):
    name = "Visual Studio Code"
    slug = "vscode"
    bundle_id = "com.microsoft.VSCode"
    executable_name = "Code"
    possible_app_paths = [
        "/Applications/Visual Studio Code.app",
        os.path.expanduser("~/Applications/Visual Studio Code.app")
    ]

    def _ensure_electron_symlink(self):
        link_path = os.path.join(self.app_path, "Contents/MacOS/Electron")
        if os.path.islink(link_path) or not os.path.exists(link_path):
            try:
                if os.path.islink(link_path):
                    os.unlink(link_path)
                os.symlink("Code", link_path)
            except Exception:
                pass

    def post_wrapper_hook(self):
        self._ensure_electron_symlink()

    def post_restore_hook(self):
        self._ensure_electron_symlink()
