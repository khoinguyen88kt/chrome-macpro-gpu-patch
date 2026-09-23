"""
Browser & Electron patchers package for legacy Mac GPUs (AMD FirePro D700/D500/D300 / Kepler / GCN 1.0)
"""
from .base import BaseBrowserPatcher
from .chrome import ChromePatcher
from .opera import OperaPatcher
from .brave import BravePatcher
from .helium import HeliumPatcher
from .electron import BaseElectronPatcher, VSCodePatcher, ELECTRON_PATCHERS

# Browsers supported in default / automatic 'all' sweep
AVAILABLE_PATCHERS = {
    "chrome": ChromePatcher,
    "opera": OperaPatcher,
    "brave": BravePatcher,
    "helium": HeliumPatcher,
}

# Opt-in only applications (skipped by 'all')
OPT_IN_PATCHERS = dict(ELECTRON_PATCHERS)

# All valid targets
ALL_PATCHERS = {**AVAILABLE_PATCHERS, **OPT_IN_PATCHERS}

__all__ = [
    "BaseBrowserPatcher",
    "ChromePatcher",
    "OperaPatcher",
    "BravePatcher",
    "HeliumPatcher",
    "BaseElectronPatcher",
    "VSCodePatcher",
    "AVAILABLE_PATCHERS",
    "ELECTRON_PATCHERS",
    "OPT_IN_PATCHERS",
    "ALL_PATCHERS",
]
