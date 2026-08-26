"""Monitoring AOIs — versioned polygons, not informal map bookmarks.

Each monitored location is an explicit ``MonitoringAOI`` loaded from
``configs/remote_monitoring/aois.yaml`` through the shared fail-closed loader
(``pipeline.config_loader.load_yaml_config``). Only AOIs marked active are
returned by ``active_aois``; the rest stay seeded but dormant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AOI_CONFIG = _REPO_ROOT / "configs" / "remote_monitoring" / "aois.yaml"


@dataclass
class MonitoringAOI:
    """A versioned area of interest with its monitoring objective."""

    aoi_uid: str
    name: str
    geometry: Dict[str, Any]
    aoi_class: str
    monitoring_objective: str
    municipio: Optional[str] = None
    allowed_detectors: List[str] = field(default_factory=list)
    baseline_start: Optional[str] = None
    monitoring_start: Optional[str] = None
    priority: int = 3
    active: bool = True
    source_ref: Optional[str] = None
    review_status: str = "seed"

    def centroid(self) -> Optional[List[float]]:
        """Rough centroid of the exterior ring; None if geometry is unusable."""
        try:
            ring = self.geometry["coordinates"][0]
        except (KeyError, IndexError, TypeError):
            return None
        if not ring:
            return None
        lons = [pt[0] for pt in ring]
        lats = [pt[1] for pt in ring]
        return [round(sum(lons) / len(lons), 6), round(sum(lats) / len(lats), 6)]

    def in_pr_bounds(self) -> bool:
        c = self.centroid()
        if c is None:
            return False
        lon, lat = c
        b = schemas.PR_BOUNDS
        return (
            b["min_lon"] <= lon <= b["max_lon"] and b["min_lat"] <= lat <= b["max_lat"]
        )


def _coerce_aoi(raw: Dict[str, Any]) -> MonitoringAOI:
    return MonitoringAOI(
        aoi_uid=str(raw["aoi_uid"]),
        name=str(raw.get("name", raw["aoi_uid"])),
        geometry=raw.get("geometry", {}),
        aoi_class=str(raw.get("aoi_class", "unknown")),
        monitoring_objective=str(raw.get("monitoring_objective", "")),
        municipio=raw.get("municipio"),
        allowed_detectors=list(raw.get("allowed_detectors", [])),
        baseline_start=raw.get("baseline_start"),
        monitoring_start=raw.get("monitoring_start"),
        priority=int(raw.get("priority", 3)),
        active=bool(raw.get("active", True)),
        source_ref=raw.get("source_ref"),
        review_status=str(raw.get("review_status", "seed")),
    )


def load_aois(path: Optional[str] = None) -> List[MonitoringAOI]:
    """Load all AOIs from the registry via the shared config loader."""
    from pipeline.config_loader import load_yaml_config

    config_path = path or str(DEFAULT_AOI_CONFIG)
    data = load_yaml_config(config_path, required_keys=["aois"])
    return [_coerce_aoi(entry) for entry in data.get("aois", [])]


def active_aois(path: Optional[str] = None) -> List[MonitoringAOI]:
    """Load only the AOIs currently flagged active, highest priority first."""
    aois = [a for a in load_aois(path) if a.active]
    return sorted(aois, key=lambda a: a.priority)
