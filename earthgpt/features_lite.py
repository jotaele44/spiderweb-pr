"""
EarthGPT iOS — Lightweight feature extraction from tile images.

Computes anomaly-relevant signals using only numpy and Pillow.
No GDAL, rasterio, or heavy GIS dependencies.
"""

from typing import Any, Optional
import math

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

try:
    from PIL import Image
    _PIL = True
except ImportError:
    _PIL = False


def _img_to_array(img: Any) -> Optional[Any]:
    """Convert a PIL Image to a numpy float32 array [H, W, 3], range 0-1."""
    if not _NP or not _PIL:
        return None
    if img is None:
        return None
    import numpy as np
    arr = np.array(img, dtype=np.float32) / 255.0
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    return arr


def compute_entropy(arr: Any) -> float:
    """Approximate pixel entropy as variance proxy."""
    if arr is None or not _NP:
        return 0.0
    import numpy as np
    gray = arr.mean(axis=-1) if arr.ndim == 3 else arr
    flat = gray.flatten()
    hist, _ = np.histogram(flat, bins=32, range=(0.0, 1.0))
    hist = hist.astype(np.float32)
    total = hist.sum()
    if total == 0:
        return 0.0
    p = hist / total
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


def compute_edge_density(arr: Any) -> float:
    """
    Compute edge density via simple gradient magnitude.
    Higher values indicate more structural complexity.
    """
    if arr is None or not _NP:
        return 0.0
    import numpy as np
    gray = arr.mean(axis=-1) if arr.ndim == 3 else arr
    gy = np.diff(gray, axis=0)
    gx = np.diff(gray, axis=1)
    gy_sq = (gy[:, :-1] ** 2)
    gx_sq = (gx[:-1, :] ** 2)
    mag = np.sqrt(gy_sq + gx_sq)
    return float(mag.mean())


def compute_banding(arr: Any) -> float:
    """
    Detect horizontal banding / striping by measuring row-mean variance.
    """
    if arr is None or not _NP:
        return 0.0
    import numpy as np
    gray = arr.mean(axis=-1) if arr.ndim == 3 else arr
    row_means = gray.mean(axis=1)
    return float(row_means.std())


def compute_axis_coherence(arr: Any) -> float:
    """
    Measure directional coherence using column-mean vs row-mean variance ratio.
    Elevated values suggest linear or structured anomalies.
    """
    if arr is None or not _NP:
        return 0.0
    import numpy as np
    gray = arr.mean(axis=-1) if arr.ndim == 3 else arr
    col_var = gray.mean(axis=0).std()
    row_var = gray.mean(axis=1).std()
    denom = row_var + 1e-9
    return float(col_var / denom)


def compute_risk_score(entropy: float, edge: float, banding: float, coherence: float) -> float:
    """
    Combine feature signals into a 0-100 risk score.
    Weights are intentionally simple for iOS determinism.
    """
    raw = (
        0.30 * min(entropy / 5.0, 1.0)
        + 0.30 * min(edge * 20.0, 1.0)
        + 0.20 * min(banding * 15.0, 1.0)
        + 0.20 * min(coherence, 1.0)
    )
    return float(round(raw * 100.0, 2))


def extract_features(img: Any) -> dict:
    """
    Extract all lightweight features from a PIL Image.
    Returns a dict with all metric fields.
    """
    arr = _img_to_array(img)
    entropy = compute_entropy(arr)
    edge = compute_edge_density(arr)
    banding = compute_banding(arr)
    coherence = compute_axis_coherence(arr)
    risk = compute_risk_score(entropy, edge, banding, coherence)
    return {
        "entropy": round(entropy, 4),
        "edge_density": round(edge, 4),
        "banding": round(banding, 4),
        "axis_coherence": round(coherence, 4),
        "risk_final_v2_0_100": risk,
    }
