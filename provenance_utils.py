"""
PROVENANCE UTILS
Reproducibility metadata helpers shared across release_check, pr_intel_adapter,
aasb_airspace_bridge, spiderweb_intake, and prii_readiness_engine.

The reproducibility block is the single canonical lineage record that ties
an output artifact to the exact run that produced it (commit, command,
platform, input file hashes, mode). The field-by-field contract is the
REPRO_KEYS tuple defined below.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPRO_KEYS = (
    "timestamp_utc",
    "repo_commit",
    "python_version",
    "platform",
    "command",
    "input_paths",
    "input_sha256s",
    "mode",
)

CHUNK = 65536
SMALL_FILE_MAX_BYTES = 32 * 1024 * 1024  # don't hash anything >32MB by default


def reproducibility_metadata(
    command: Optional[str] = None,
    input_paths: Optional[Iterable[str]] = None,
    *,
    mode: str = "normal",
    hash_inputs: bool = True,
    hash_max_bytes: int = SMALL_FILE_MAX_BYTES,
) -> Dict[str, object]:
    """Build the canonical reproducibility block.

    *command* is the operator-visible invocation that triggered the export
    (e.g. ``python run_all.py --release-check``).  When None, derived from
    ``sys.argv``.  *input_paths* are absolute or relative paths the operator
    wants tied to this output.  Files larger than *hash_max_bytes* are listed
    with sha256 ``"skipped_large_file"`` to keep the manifest cheap.
    """
    inputs = list(input_paths or [])
    hashed: Dict[str, str] = {}
    if hash_inputs:
        for p in inputs:
            try:
                hashed[p] = compute_sha256(p, max_bytes=hash_max_bytes)
            except Exception:
                hashed[p] = "unknown"

    return {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "repo_commit": git_head_or_unknown(),
        "python_version": platform.python_version(),
        "platform": _platform_label(),
        "command": command or " ".join(sys.argv),
        "input_paths": inputs,
        "input_sha256s": hashed,
        "mode": mode,
    }


def compute_sha256(path: str, *, max_bytes: int = SMALL_FILE_MAX_BYTES) -> str:
    """Stream a file's SHA-256.  Returns ``"unknown"`` if unreadable and
    ``"skipped_large_file"`` if it would exceed *max_bytes*."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return "unknown"
    try:
        size = p.stat().st_size
    except OSError:
        return "unknown"
    if size > max_bytes:
        return "skipped_large_file"
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return "unknown"
    return h.hexdigest()


def git_head_or_unknown() -> str:
    """Return short git commit (HEAD) or ``"unknown"`` if not a git repo or
    git isn't installed.  Never raises."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return "unknown"


def attach_to_manifest(manifest: dict, **kwargs) -> dict:
    """Insert (or replace) a top-level ``"reproducibility"`` key.  Returns the
    same manifest dict for chaining."""
    manifest["reproducibility"] = reproducibility_metadata(**kwargs)
    return manifest


def feature_collection_summary(features: List[dict]) -> Dict[str, object]:
    """Return a GeoJSON summary block: bbox, centroid, feature_count, and the
    set of geometry types observed.  Coordinates are EPSG:4326 (lon, lat).

    Returns sentinels (None for bbox, 0 for count) when no valid geometry is
    available — never raises.
    """
    lats: List[float] = []
    lons: List[float] = []
    gtypes: set = set()
    count = 0
    for feat in features or []:
        geom = (feat or {}).get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not gtype or coords is None:
            continue
        count += 1
        gtypes.add(gtype)
        for lon, lat in _iter_coords(coords):
            lons.append(lon)
            lats.append(lat)

    if not lons or not lats:
        return {
            "feature_count": count,
            "bbox": None,
            "centroid": None,
            "geometry_types": sorted(gtypes),
            "crs": "EPSG:4326",
        }
    return {
        "feature_count": count,
        "bbox": [
            round(min(lons), 6),
            round(min(lats), 6),
            round(max(lons), 6),
            round(max(lats), 6),
        ],
        "centroid": [
            round(sum(lons) / len(lons), 6),
            round(sum(lats) / len(lats), 6),
        ],
        "geometry_types": sorted(gtypes),
        "crs": "EPSG:4326",
    }


def geojson_feature_meta(
    *,
    producer_module: str,
    source_artifact: str,
    produced_at: Optional[str] = None,
) -> Dict[str, str]:
    """Return the standardized GeoJSON Feature `_meta` block (T5-41).

    Every Feature emitted by a producer should carry this block under
    ``properties._meta`` so a downstream tool can answer three questions
    by reading a single Feature in isolation:

      - "which module wrote this?"          → ``producer_module``
      - "what file does it live in?"        → ``source_artifact``
      - "when was it written?"              → ``produced_at`` (ISO 8601 UTC)

    ``produced_at`` defaults to the current UTC timestamp so all features
    written in a single run share the same value — this lets consumers
    cluster a Feature by its emission run without needing the parent
    manifest's reproducibility block. Pass an explicit timestamp when
    matching the manifest exactly.
    """
    if produced_at is None:
        produced_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "producer_module": producer_module,
        "source_artifact": source_artifact,
        "produced_at": produced_at,
    }


def _platform_label() -> str:
    try:
        return f"{platform.system()}-{platform.release()}-{platform.machine()}"
    except Exception:
        return "unknown"


def _iter_coords(coords):
    """Yield (lon, lat) tuples from any GeoJSON coordinate nesting."""
    if (
        isinstance(coords, (list, tuple))
        and len(coords) >= 2
        and isinstance(coords[0], (int, float))
        and isinstance(coords[1], (int, float))
    ):
        yield float(coords[0]), float(coords[1])
        return
    if isinstance(coords, (list, tuple)):
        for sub in coords:
            yield from _iter_coords(sub)
