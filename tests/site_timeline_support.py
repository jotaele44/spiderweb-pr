"""Shared builders for the site timeline tests. Synthetic data only."""

from __future__ import annotations

from typing import Any

from spiderweb.site_timeline.adapters import SyntheticAdapter, synthetic_scene
from spiderweb.site_timeline.metrics import FixtureMetric
from spiderweb.site_timeline.models import (
    EpochRecord,
    SceneRecord,
    Site,
    TemporalObservation,
)
from spiderweb.site_timeline.timeline import build_document, build_site_timeline

NOW = "2026-11-07T00:00:00Z"
START, END = "2015-06-23", "2026-11-07"

# The id aguayluz-pr mints for the Arroyo landfill; here it is only input data.
ARROYO_ENT = "ent_6db14f6d105b4cfa826d6c71f657f761"
PIN_ENT = "ent_00000000000000000000000000000001"


def precise_site() -> Site:
    return Site(
        external_site_id="LMOP-ARROYO-TEST",
        producer_entity_id=ARROYO_ENT,
        name="Arroyo Landfill (fixture)",
        lat=18.004595,
        lon=-66.04773,
        geometry_precision_decimals=6,
    )


def coarse_site() -> Site:
    return Site(
        external_site_id="PIN-TOABAJA-TEST",
        producer_entity_id=PIN_ENT,
        name="Toa Baja pin (fixture)",
        lat=18.444,
        lon=-66.262,
        geometry_precision_decimals=3,
    )


def scene(
    site: Site,
    scene_id: str,
    acquired_at: str | None,
    cloud: float | None,
    **kwargs: Any,
) -> SceneRecord:
    return synthetic_scene(site, scene_id, acquired_at, cloud, **kwargs)


def observation_for_score(signals: dict[str, float]) -> TemporalObservation:
    epoch = EpochRecord(
        "r", "e", "2020-01-01T00:00:00Z", "p", 10.0, "g", {"scene_id": "s"}
    )
    return TemporalObservation("c", epoch, epoch, signals)


def timeline_for(
    site: Site,
    scenes: list[SceneRecord],
    signals: dict[tuple[str, str], dict[str, float]],
    **kwargs: Any,
) -> dict[str, Any]:
    adapter = SyntheticAdapter({site.external_site_id: scenes})
    return build_site_timeline(
        site, adapter, FixtureMetric(signals), start=START, end=END, now=NOW, **kwargs
    )


def document_for(*timelines: dict[str, Any]) -> dict[str, Any]:
    return build_document(
        list(timelines), now=NOW, adapter_name="synthetic", start=START, end=END
    )


def standard_document() -> dict[str, Any]:
    """Arroyo (precise) with an undated screenshot plus a coarse Toa Baja pin."""
    arroyo = precise_site()
    toa = coarse_site()
    a = timeline_for(
        arroyo,
        [
            scene(arroyo, "S2-2017", "2017-03-02T14:50:00Z", 4.0),
            scene(arroyo, "S2-2021", "2021-03-05T14:50:00Z", 6.0),
            scene(
                arroyo,
                "SHOT",
                None,
                None,
                capture_kind="UNDATED_BASEMAP_CAPTURE",
                provider="unknown",
            ),
        ],
        {("S2-2017", "S2-2021"): {"SURFACE_COVER_CHANGE": 0.85, "NEW_FEATURE": 0.9}},
    )
    t = timeline_for(
        toa,
        [
            scene(toa, "T-2018", "2018-01-10T14:50:00Z", 2.0),
            scene(toa, "T-2022", "2022-01-12T14:50:00Z", 2.0),
        ],
        {("T-2018", "T-2022"): {"EXPANSION": 0.9, "ACCESS_CHANGE": 0.9}},
    )
    return document_for(a, t)


def make_live(doc: dict[str, Any]) -> dict[str, Any]:
    """Re-flag a synthetic document as live, consistently, on every record type."""
    doc["synthetic"] = False
    for entry in doc["sites"]:
        for art in entry["artifacts"]:
            art["synthetic"] = False
        for acq in entry["acquisitions"]:
            acq["synthetic"] = False
            acq["classification"] = "INTERNAL"
        for cmp in entry["comparisons"]:
            cmp["signal"]["result"]["synthetic"] = False
    return doc


def set_after_date(doc: dict[str, Any], new_date: str) -> dict[str, Any]:
    """Edit the first comparison's after date everywhere it appears, consistently.

    The epoch label is left alone, which is the tampering a stale label allows.
    """
    entry = doc["sites"][0]
    entry["artifacts"][1]["acquired_at"] = new_date
    entry["epochs"][1]["capture_time"] = new_date
    entry["epochs"][1]["provenance"]["acquired_at"] = new_date
    entry["comparisons"][0]["signal"]["result"]["after"]["acquired_at"] = new_date
    return doc
