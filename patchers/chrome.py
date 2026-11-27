#!/usr/bin/env python3
"""
Google Chrome Patcher subclass for legacy Mac GPUs.
"""
import os
from .chromium import ChromiumPatcher


class ChromePatcher(ChromiumPatcher):
    name = "Google Chrome"
    slug = "chrome"
    possible_app_paths = [
        "/Applications/Google Chrome.app",
        os.path.expanduser("~/Applications/Google Chrome.app"),
    ]
    bundle_id = "com.google.Chrome"
    app_bundle_name = "Google Chrome.app"
    framework_name = "Google Chrome Framework.framework"
    framework_binary_name = "Google Chrome Framework"
    launcher_name = "Google Chrome"
    launcher_src = "launcher_main.c"
    backup_base_dir = "~/.chrome_macpro_backups"
