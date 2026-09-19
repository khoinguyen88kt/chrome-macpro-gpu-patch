"""
Browser patchers package for legacy Mac GPUs (AMD FirePro D700/D500/D300 / Kepler / GCN 1.0)
"""
from .base import BaseBrowserPatcher
from .chrome import ChromePatcher
from .opera import OperaPatcher
from .brave import BravePatcher

AVAILABLE_PATCHERS = {
    "chrome": ChromePatcher,
    "opera": OperaPatcher,
    "brave": BravePatcher,
}

__all__ = ["BaseBrowserPatcher", "ChromePatcher", "OperaPatcher", "BravePatcher", "AVAILABLE_PATCHERS"]
