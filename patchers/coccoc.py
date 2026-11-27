#!/usr/bin/env python3
"""
CocCoc Browser Patcher subclass for legacy Mac GPUs.
"""
import os
from .chromium import ChromiumPatcher


class CocCocPatcher(ChromiumPatcher):
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
    launcher_src = "launcher_main.c"
    backup_base_dir = "~/.coccoc_macpro_backups"
