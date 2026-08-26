"""Optional STAC discovery seam (Phase 1 forward hook).

This is a thin, metadata-only wrapper over the existing ``imagery/`` provider
registry. It performs a catalog ``search()`` (no pixel fetch) and normalizes the
returned ``SceneMetadata`` into the lightweight scene dicts that ``catalog.py``
consumes for cadence and InSAR-pair reasoning.

The ``imagery`` import is deferred and guarded so the rest of the
``remote_monitoring`` core imports — and its tests run — with neither the
``imagery`` extra nor network access installed. Calling ``discover_scenes``
without ``imagery`` raises ``DiscoveryUnavailable`` with a clear remediation.
"""

from __future__ import annotations

from typing import Any, Dict, List


class DiscoveryUnavailable(RuntimeError):
    """Raised when the optional imagery/STAC dependency is not installed."""


def _scene_from_metadata(meta: Any) -> Dict[str, Any]:
    """Normalize an imagery ``SceneMetadata`` (or dict) to a catalog scene dict."""
    get = (
        (lambda k, d=None: meta.get(k, d))
        if isinstance(meta, dict)
        else (lambda k, d=None: getattr(meta, k, d))
    )
    extra = get("extra", {}) or {}
    return {
        "scene_uid": get("scene_id"),
        "provider": get("provider"),
        "collection": get("collection"),
        "acquisition_start": get("datetime"),
        "cloud_cover": get("cloud_cover_pct"),
        "bbox": get("bbox"),
        # Orbit/mode/polarization ride along in `extra` when the provider
        # supplies them; catalog.insar_pair_compatibility tolerates their absence.
        "relative_orbit": extra.get("relative_orbit"),
        "acquisition_mode": extra.get("acquisition_mode") or extra.get("sensor_mode"),
        "polarization": extra.get("polarization"),
        "processing_baseline": extra.get("processing_baseline"),
    }


def discover_scenes(
    bbox: List[float],
    date_range: str,
    *,
    provider: str = "copernicus",
    max_items: int = 50,
) -> List[Dict[str, Any]]:
    """Search a STAC catalog and return normalized scene dicts (metadata only).

    Raises ``DiscoveryUnavailable`` if the ``imagery`` package is not importable.
    """
    try:
        from imagery.providers import get_provider
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise DiscoveryUnavailable(
            "STAC discovery needs the imagery extra: pip install '.[imagery]'"
        ) from exc

    prov = get_provider(provider)
    scenes = prov.search(bbox, date_range, max_items=max_items)
    return [_scene_from_metadata(s) for s in scenes]
