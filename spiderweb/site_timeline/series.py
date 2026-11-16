"""Series admission: which scenes may enter a site's timeline, and why others do not.

Only provider-dated scenes are admitted. An undated capture (a consumer-map
screenshot, say) is class ``UNDATED_BASEMAP_CAPTURE``: its epoch is unknown, so it
is excluded from the series and from every change claim. Every considered scene is
either admitted or excluded with a reason, and the counts must close.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .epoch import parse_acquired_at
from .models import PROVIDER_SCENE, SceneRecord, Site

# UNCALIBRATED HEURISTIC: a scene with more cloud than this is excluded. Sentinel-2
# over Puerto Rico is often cloudy, so this trades series length for clean epochs.
DEFAULT_CLOUD_CUTOFF_PCT = 20.0

_UNKNOWN_PROVIDERS = frozenset({"", "unknown"})


@dataclass(frozen=True)
class Exclusion:
    scene_id: str
    reason: str


@dataclass(frozen=True)
class Series:
    site: Site
    admitted: tuple[SceneRecord, ...]
    exclusions: tuple[Exclusion, ...]
    considered: int

    def ledger(self) -> dict[str, Any]:
        by_reason = Counter(e.reason for e in self.exclusions)
        return {
            "considered": self.considered,
            "admitted": len(self.admitted),
            "excluded": len(self.exclusions),
            "by_reason": dict(sorted(by_reason.items())),
        }


def _contains(bbox: tuple[float, float, float, float], lat: float, lon: float) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


def _exclusion_reason(
    scene: SceneRecord, site: Site, seen: set[str], cloud_cutoff_pct: float
) -> str | None:
    if scene.capture_kind != PROVIDER_SCENE:
        return scene.capture_kind
    if parse_acquired_at(scene.acquired_at) is None:
        return "UNDATED"
    if scene.provider.strip().lower() in _UNKNOWN_PROVIDERS:
        return "UNKNOWN_PROVIDER"
    if scene.scene_id in seen:
        return "DUPLICATE_SCENE_ID"
    if not _contains(scene.bbox, site.lat, site.lon):
        return "SITE_OUTSIDE_SCENE_BBOX"
    if scene.cloud_cover_pct is None:
        return "CLOUD_COVER_UNKNOWN"
    if scene.cloud_cover_pct > cloud_cutoff_pct:
        return "CLOUD_COVER_ABOVE_CUTOFF"
    return None


def build_series(
    site: Site,
    scenes: Iterable[SceneRecord],
    cloud_cutoff_pct: float = DEFAULT_CLOUD_CUTOFF_PCT,
) -> Series:
    admitted: list[SceneRecord] = []
    exclusions: list[Exclusion] = []
    seen: set[str] = set()
    considered = 0
    for scene in scenes:
        considered += 1
        reason = _exclusion_reason(scene, site, seen, cloud_cutoff_pct)
        if reason:
            exclusions.append(Exclusion(scene.scene_id, reason))
            continue
        seen.add(scene.scene_id)
        admitted.append(scene)

    def order(scene: SceneRecord) -> tuple[Any, str]:
        return (parse_acquired_at(scene.acquired_at), scene.scene_id)

    admitted.sort(key=order)
    series = Series(site, tuple(admitted), tuple(exclusions), considered)
    ledger = series.ledger()
    if ledger["considered"] != ledger["admitted"] + ledger["excluded"]:
        raise ValueError("series ledger does not close")
    return series


def comparison_pairs(
    series: Series,
) -> list[tuple[SceneRecord, SceneRecord, str]]:
    """Consecutive pairs, plus baseline-to-latest when the series has three or more."""
    scenes = series.admitted
    pairs = [(a, b, "consecutive") for a, b in zip(scenes, scenes[1:], strict=False)]
    if len(scenes) >= 3:
        pairs.append((scenes[0], scenes[-1], "baseline_latest"))
    return pairs
