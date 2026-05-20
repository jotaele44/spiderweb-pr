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


_DEVICE_MEMORY_MB: dict = {
    "iphone_6s":   1024,
    "iphone_7":    2048,
    "iphone_8":    2048,
    "iphone_x":    3072,
    "iphone_12":   4096,
    "iphone_14":   6144,
    "iphone_15":   6144,
    "ipad_air":    4096,
    "ipad_pro":    8192,
    "default":     2048,
}


def memory_budget_mb(device: str = "default") -> int:
    """Return the safe tile-loading memory budget in MiB for *device*.

    Parameters
    ----------
    device:
        Device identifier string (lowercase, underscores).  Use ``"default"``
        for an unknown device.

    Returns
    -------
    int
        Memory budget in mebibytes.  Returns 50% of total device RAM as the
        safe budget for tile loading.
    """
    total = _DEVICE_MEMORY_MB.get(device.lower(), _DEVICE_MEMORY_MB["default"])
    return total // 2


def for_device(model: str) -> dict:
    """Return a profile dict configured for the given iOS device model.

    Parameters
    ----------
    model:
        Device model string, e.g. ``"iphone_14"`` or ``"ipad_pro"``.

    Returns
    -------
    dict
        Profile dict (from :func:`detect_profile`) augmented with
        ``device_model``, ``memory_budget_mb``, and ``tile_cache_limit``.
    """
    profile = detect_profile()
    budget = memory_budget_mb(model)
    profile["device_model"] = model
    profile["memory_budget_mb"] = budget
    profile["tile_cache_limit"] = max(1, budget // 4)
    return profile


def print_profile() -> None:
    p = detect_profile()
    log(f"Platform : {p['platform']}")
    log(f"Python   : {p['python_version'].split()[0]}")
    log(f"iOS mode : {p['ios_mode']}")
    log(f"Pillow   : {p['has_pillow']}")
    log(f"numpy    : {p['has_numpy']}")
    log(f"folium   : {p['has_folium']}")
