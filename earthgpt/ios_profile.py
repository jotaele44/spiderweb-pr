"""
EarthGPT iOS — iOS / a-Shell runtime profile.

Detects available libraries and sets safe execution parameters
for the constrained a-Shell environment.
"""

import sys
import platform
from .log_utils import log


def detect_profile() -> dict:
    """
    Detect the runtime environment and return a profile dict.

    Keys:
        ios_mode       bool   running on iOS / a-Shell heuristic
        has_pillow     bool   Pillow available
        has_numpy      bool   numpy available
        has_folium     bool   folium available
        python_version str
    """
    profile = {
        "ios_mode": False,
        "has_pillow": False,
        "has_numpy": False,
        "has_folium": False,
        "python_version": sys.version,
        "platform": platform.system(),
    }

    # Heuristic: a-Shell sets TERM and runs on Darwin
    if platform.system() == "Darwin" and sys.platform == "ios":
        profile["ios_mode"] = True
    # Also respect env var
    try:
        from . import config
        profile["ios_mode"] = config.IOS_MODE
    except Exception:
        pass

    try:
        import PIL  # noqa: F401
        profile["has_pillow"] = True
    except ImportError:
        pass

    try:
        import numpy  # noqa: F401
        profile["has_numpy"] = True
    except ImportError:
        pass

    try:
        import folium  # noqa: F401
        profile["has_folium"] = True
    except ImportError:
        pass

    return profile


def print_profile() -> None:
    p = detect_profile()
    log(f"Platform : {p['platform']}")
    log(f"Python   : {p['python_version'].split()[0]}")
    log(f"iOS mode : {p['ios_mode']}")
    log(f"Pillow   : {p['has_pillow']}")
    log(f"numpy    : {p['has_numpy']}")
    log(f"folium   : {p['has_folium']}")


class IOSProfile:
    """Device-specific iOS memory and resource profile."""

    def __init__(self) -> None:
        self._memory_budget_mb: int = 512
        self.device_model: str = "unknown"

    @property
    def memory_budget_mb(self) -> int:
        """Enforce tile loading within device memory budget."""
        return getattr(self, "_memory_budget_mb", 512)

    @memory_budget_mb.setter
    def memory_budget_mb(self, value: int) -> None:
        self._memory_budget_mb = value

    @classmethod
    def for_device(cls, model: str) -> "IOSProfile":
        """Factory for iPhone-specific memory limits."""
        budgets = {
            "iPhone 12": 256, "iPhone 13": 384, "iPhone 14": 512,
            "iPhone 15": 768, "iPhone 15 Pro": 1024, "iPhone 16": 1024,
        }
        profile = cls()
        profile.memory_budget_mb = budgets.get(model, 512)
        profile.device_model = model
        return profile


# ── Standalone module-level API (for test_earthgpt_pipeline.py) ────────────────

_DEVICE_BUDGETS = {
    "iphone_12": 1536 // 2,
    "iphone_13": 2048 // 2,
    "iphone_14": 3072 // 2,
    "iphone_15": 4096 // 2,
    "iphone_15_pro": 6144 // 2,
    "iphone_16": 6144 // 2,
    "ipad_pro": 4096 // 2,
    "ipad_air": 2048 // 2,
}

_DEFAULT_BUDGET = 2048 // 2


def memory_budget_mb(device_name: str) -> int:
    """Return the tile memory budget (MB) for a named iOS device."""
    return _DEVICE_BUDGETS.get(device_name.lower().replace(" ", "_"), _DEFAULT_BUDGET)


def for_device(device_name: str) -> dict:
    """Return a device profile dict for the named iOS device."""
    budget = memory_budget_mb(device_name)
    return {
        "device": device_name,
        "memory_budget_mb": budget,
        "tile_cache_limit": max(1, budget // 4),
    }
