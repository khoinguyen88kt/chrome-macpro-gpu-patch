#!/usr/bin/env python3
"""
Brave Browser Patcher subclass for legacy Mac GPUs.
"""
import os
from .chromium import ChromiumPatcher


class BravePatcher(ChromiumPatcher):
    name = "Brave Browser"
    slug = "brave"
    possible_app_paths = [
        "/Applications/Brave Browser.app",
        os.path.expanduser("~/Applications/Brave Browser.app"),
    ]
    bundle_id = "com.brave.Browser"
    app_bundle_name = "Brave Browser.app"
    framework_name = "Brave Browser Framework.framework"
    framework_binary_name = "Brave Browser Framework"
    launcher_name = "Brave Browser"
    launcher_src = "launcher_main.c"
    backup_base_dir = "~/.brave_macpro_backups"
