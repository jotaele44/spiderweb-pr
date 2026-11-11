"""Fixture loading for offline runs: synthetic sites, scenes and change signals.

Fixtures describe *metadata only*. Content hashes are computed here from the
synthetic payload, never trusted from the file, and every scene built this way is
marked ``synthetic``. Nothing here reads a network or an image.
"""

from __future__ import annotations

from typing import Any

from .adapters import synthetic_scene
from .metrics import FixtureMetric
from .models import PROVIDER_SCENE, SceneRecord, Site

_SITE_KEYS = frozenset(
    {
        "external_site_id",
        "producer_entity_id",
        "name",
        "lat",
        "lon",
        "geometry_precision_decimals",
        "authority",
    }
)
_REQUIRED_SITE_KEYS = frozenset(
    {"external_site_id", "producer_entity_id", "name", "lat", "lon"}
)
_SCENE_KEYS = frozenset(
    {
        "scene_id",
        "acquired_at",
        "cloud_cover_pct",
        "provider",
        "resolution_m",
        "capture_kind",
        "geometric_confidence",
        "platform",
        "instrument",
        "collection",
    }
)


class FixtureError(ValueError):
    """The fixture is malformed. Raised instead of guessing."""


def load_sites(rows: Any) -> list[Site]:
    """Build sites from a frozen list. Unknown keys and duplicate ids are errors."""
    if not isinstance(rows, list) or not rows:
        raise FixtureError("site list must be a non-empty list")
    sites: list[Site] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise FixtureError("each site must be an object")
        unknown = set(row) - _SITE_KEYS
        missing = _REQUIRED_SITE_KEYS - set(row)
        if unknown or missing:
            raise FixtureError(
                f"site keys: unknown={sorted(unknown)} missing={sorted(missing)}"
            )
        if row["external_site_id"] in seen:
            raise FixtureError(f"duplicate site {row['external_site_id']}")
        seen.add(row["external_site_id"])
        try:
            sites.append(Site(**row))
        except (TypeError, ValueError) as exc:
            raise FixtureError(f"site {row.get('external_site_id')}: {exc}") from exc
    return sites


def load_scenes(
    sites: list[Site], fixture: Any
) -> tuple[dict[str, list[SceneRecord]], FixtureMetric]:
    """Build synthetic scenes and a signal table from a fixture document."""
    if not isinstance(fixture, dict):
        raise FixtureError("scenes fixture must be an object")
    known = {s.external_site_id: s for s in sites}
    extra = set(fixture.get("scenes", {})) - set(known)
    if extra:
        raise FixtureError(f"scenes name unknown sites: {sorted(extra)}")

    scenes: dict[str, list[SceneRecord]] = {}
    for site_id, rows in fixture.get("scenes", {}).items():
        built: list[SceneRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                raise FixtureError("each scene must be an object")
            unknown = set(row) - _SCENE_KEYS
            if unknown or "scene_id" not in row:
                raise FixtureError(f"scene keys invalid: {sorted(unknown)}")
            kwargs = {k: v for k, v in row.items() if k in _SCENE_KEYS}
            built.append(
                synthetic_scene(
                    known[site_id],
                    kwargs.pop("scene_id"),
                    kwargs.pop("acquired_at", None),
                    kwargs.pop("cloud_cover_pct", None),
                    **kwargs,
                )
            )
        scenes[site_id] = built

    table: dict[tuple[str, str], dict[str, float]] = {}
    for row in fixture.get("change_signals", []):
        if not isinstance(row, dict) or not {"before", "after", "signals"} <= set(row):
            raise FixtureError("change_signals rows need before, after and signals")
        table[(row["before"], row["after"])] = dict(row["signals"])
    return scenes, FixtureMetric(table)


__all__ = ["FixtureError", "PROVIDER_SCENE", "load_scenes", "load_sites"]
