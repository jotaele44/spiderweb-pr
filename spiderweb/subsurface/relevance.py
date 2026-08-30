"""Coarse evidence-bounded subsurface relevance zoning.

This model scores public geological, hydrogeological, historical-mining, cave,
industrial, utility, and historical-map evidence. It does not infer connectivity,
access, intent, hidden facilities, or current protected military assets. Military
family records are deliberately excluded from the score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Iterable

from shapely.geometry import box, mapping, shape


@dataclass(frozen=True)
class RelevanceZone:
    zone_id: str
    score: float
    relevance: str
    evidence_tier: str
    independent_sources: int
    cave_features: int
    groundwater_points: int
    mine_quarry_features: int
    industrial_features: int
    utility_features: int
    historical_map_features: int
    notes: tuple[str, ...]


SCORING_FAMILIES = frozenset({
    "GEOLOGY_KARST_CAVES",
    "AQUIFERS_WELLS_SPRINGS",
    "MINES_QUARRIES_SHAFTS",
    "INDUSTRIAL_REMEDIATION",
    "UTILITIES_UNDERGROUND",
    "HISTORICAL_CORROBORATION",
})


def _props(feature: dict) -> dict:
    return dict(feature.get("properties") or {})


def _attrs(feature: dict) -> dict:
    return dict(_props(feature).get("attributes") or {})


def _is_cave(feature: dict) -> bool:
    return _props(feature).get("source_id") == "PRPB_CAVES_31"


def _is_groundwater_point(feature: dict) -> bool:
    source = _props(feature).get("source_id")
    if source in {"PRPB_WELLS_JCA_20", "PRPB_WELLS_AAA_21", "PRPB_SPRINGS_19"}:
        return True
    if source == "USGS_MONITORING_LOCATIONS_PR":
        return str(_attrs(feature).get("site_type") or "").lower() in {"well", "spring"}
    return False


def _is_mine_quarry(feature: dict) -> bool:
    return _props(feature).get("source_id") in {
        "PRPB_QUARRIES_10",
        "USGS_USMIN_CONSOLIDATED_POINTS_17",
        "USGS_USMIN_EXPLICIT_OPENINGS_17",
        "USGS_USMIN_CONSOLIDATED_POLYGONS_18",
        "USGS_MRDS_HOSTED_0_PR_AOI",
    }


def _is_industrial(feature: dict) -> bool:
    return _props(feature).get("layer_family") == "INDUSTRIAL_REMEDIATION"


def _is_utility(feature: dict) -> bool:
    return _props(feature).get("layer_family") == "UTILITIES_UNDERGROUND"


def _is_historical_map(feature: dict) -> bool:
    return _props(feature).get("source_id") == "USGS_TOPOVIEW_OVERLAY_0"


def _classification(score: float) -> str:
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MODERATE"
    if score >= 1.5:
        return "LOW"
    return "VERY_LOW"


def _tier(caves: int, direct_openings: int, score: float, source_count: int) -> str:
    if caves > 0 or direct_openings > 0:
        return "DIRECT"
    if score >= 4.0 and source_count >= 3:
        return "SUPPORTING"
    if score > 0:
        return "CANDIDATE"
    return "UNRESOLVED"


def build_relevance_zones(
    aoi_geojson: dict,
    evidence_features: Iterable[dict],
    *,
    cell_degrees: float = 0.02,
) -> list[tuple[RelevanceZone, dict]]:
    """Build coarse cells intersecting the AOI from exact evidence predicates.

    No nearest-feature or distance-buffer promotion is used.  Geometry objects are
    parsed once before cell iteration so live acceptance remains deterministic and
    fast even when segmented utility layers contain thousands of rows.
    """
    aoi = shape(aoi_geojson)
    minx, miny, maxx, maxy = aoi.bounds
    indexed: list[tuple[dict, object]] = []
    for feature in evidence_features:
        props = _props(feature)
        if props.get("layer_family") not in SCORING_FAMILIES:
            continue
        if props.get("spatial_state") not in {"FULLY_WITHIN", "PARTIAL"}:
            continue
        geom = feature.get("geometry")
        if not geom:
            continue
        try:
            indexed.append((feature, shape(geom)))
        except Exception:
            continue

    output: list[tuple[RelevanceZone, dict]] = []
    ix = 0
    x = math.floor(minx / cell_degrees) * cell_degrees
    while x < maxx:
        y = math.floor(miny / cell_degrees) * cell_degrees
        while y < maxy:
            cell = box(x, y, x + cell_degrees, y + cell_degrees)
            if not cell.intersects(aoi):
                y += cell_degrees
                continue
            hits = [feature for feature, geom in indexed if geom.intersects(cell)]
            sources = {_props(f).get("source_id") for f in hits if _props(f).get("source_id")}
            caves = sum(_is_cave(f) for f in hits)
            groundwater = sum(_is_groundwater_point(f) for f in hits)
            mines = sum(_is_mine_quarry(f) for f in hits)
            industrial = sum(_is_industrial(f) for f in hits)
            utilities = sum(_is_utility(f) for f in hits)
            history = sum(_is_historical_map(f) for f in hits)
            direct_openings = sum(_props(f).get("source_id") == "USGS_USMIN_EXPLICIT_OPENINGS_17" for f in hits)

            score = 0.0
            score += min(3.0, caves * 3.0)
            score += min(2.5, math.log1p(groundwater) * 0.75)
            score += min(2.0, math.log1p(mines) * 0.9)
            score += min(0.75, math.log1p(industrial) * 0.25)
            score += min(0.50, math.log1p(utilities) * 0.08)
            score += min(0.25, math.log1p(history) * 0.05)
            if len(sources) >= 3:
                score += min(1.0, (len(sources) - 2) * 0.15)
            score = round(min(10.0, score), 3)

            notes = ["exact cell intersection only", "military family excluded", "no proximity-only connectivity inference"]
            if caves:
                notes.append("mapped cave evidence present")
            if direct_openings:
                notes.append("explicit historical opening symbol present")
            zone = RelevanceZone(
                zone_id=f"SZ-{ix:04d}",
                score=score,
                relevance=_classification(score),
                evidence_tier=_tier(caves, direct_openings, score, len(sources)),
                independent_sources=len(sources),
                cave_features=caves,
                groundwater_points=groundwater,
                mine_quarry_features=mines,
                industrial_features=industrial,
                utility_features=utilities,
                historical_map_features=history,
                notes=tuple(notes),
            )
            output.append((zone, mapping(cell.intersection(aoi))))
            ix += 1
            y += cell_degrees
        x += cell_degrees
    return output


def write_relevance_geojson(aoi_file: str | Path, evidence_file: str | Path, output: str | Path, *, cell_degrees: float = 0.02) -> Path:
    aoi_obj = json.loads(Path(aoi_file).read_text(encoding="utf-8"))
    evidence_obj = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
    zones = build_relevance_zones(aoi_obj["geometry"], evidence_obj.get("features", []), cell_degrees=cell_degrees)
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": geom, "properties": asdict(zone)}
            for zone, geom in zones
        ],
        "metadata": {
            "model": "SANTIAGO_SUBSURFACE_RELEVANCE_MODEL_v1",
            "military_family_excluded": True,
            "connectivity_inference": "PROHIBITED",
            "cell_degrees": cell_degrees,
        },
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, indent=2, sort_keys=True), encoding="utf-8")
    return out
