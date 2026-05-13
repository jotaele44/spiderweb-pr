"""
EarthGPT iOS — Configuration module.

Loads .env if present, defines all iOS-safe defaults for paths,
tile provider settings, thresholds, and logging intervals.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Base directories ─────────────────────────────────────────────────────────
BASE_DIR = Path(os.getenv("EARTHGPT_BASE_DIR", Path(__file__).parent.parent))
OUTPUT_DIR = Path(os.getenv("EARTHGPT_OUTPUT_DIR", BASE_DIR / "outputs"))
CACHE_DIR = Path(os.getenv("EARTHGPT_CACHE_DIR", BASE_DIR / "cache"))
TILE_CACHE_DIR = Path(os.getenv("EARTHGPT_TILE_CACHE_DIR", BASE_DIR / "tile_cache"))

# Create directories automatically
for _d in [OUTPUT_DIR, CACHE_DIR, TILE_CACHE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Tile provider ────────────────────────────────────────────────────────────
TILE_URL_TEMPLATE = os.getenv(
    "EARTHGPT_TILE_URL",
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
)
TILE_USER_AGENT = os.getenv(
    "EARTHGPT_USER_AGENT",
    "EarthGPT-iOS/0.1 (anomaly-detection)",
)

# ── Fetch settings ───────────────────────────────────────────────────────────
FETCH_TIMEOUT_S = int(os.getenv("EARTHGPT_FETCH_TIMEOUT", "15"))
FETCH_RETRIES = int(os.getenv("EARTHGPT_FETCH_RETRIES", "3"))

# ── Zoom levels ──────────────────────────────────────────────────────────────
DEFAULT_ZOOM = int(os.getenv("EARTHGPT_DEFAULT_ZOOM", "15"))
DEFAULT_ZOOMS = [int(z) for z in os.getenv("EARTHGPT_DEFAULT_ZOOMS", "14,15,16").split(",")]
MULTISCALE_ZOOMS = [int(z) for z in os.getenv("EARTHGPT_MULTISCALE_ZOOMS", "15,16,17").split(",")]

# ── Anomaly thresholds ───────────────────────────────────────────────────────
ANOMALY_THRESHOLD = float(os.getenv("EARTHGPT_ANOMALY_THRESHOLD", "0.5"))
RISK_THRESHOLD = float(os.getenv("EARTHGPT_RISK_THRESHOLD", "40.0"))

# ── Print intervals (for iOS terminal readability) ───────────────────────────
PHASE1_PRINT_INTERVAL = int(os.getenv("EARTHGPT_PHASE1_INTERVAL", "10"))
PHASE2_PRINT_INTERVAL = int(os.getenv("EARTHGPT_PHASE2_INTERVAL", "5"))
SEAM_PRINT_INTERVAL = int(os.getenv("EARTHGPT_SEAM_INTERVAL", "10"))
SWEEP_PRINT_INTERVAL = int(os.getenv("EARTHGPT_SWEEP_INTERVAL", "10"))

# ── iOS mode flag ────────────────────────────────────────────────────────────
IOS_MODE = os.getenv("EARTHGPT_IOS_MODE", "1").strip() not in ("0", "false", "no")
