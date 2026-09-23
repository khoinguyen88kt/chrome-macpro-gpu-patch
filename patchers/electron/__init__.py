"""
Electron application patchers for legacy Mac GPUs.
All patchers in this package are OPT-IN only and skipped by the default 'all' browser sweep.
"""
from .base import BaseElectronPatcher
from .vscode import VSCodePatcher

ELECTRON_PATCHERS = {
    "vscode": VSCodePatcher,
}

__all__ = ["BaseElectronPatcher", "VSCodePatcher", "ELECTRON_PATCHERS"]
