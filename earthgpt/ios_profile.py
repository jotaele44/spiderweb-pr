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
