"""Bounded federation spatial-service adapter over proven Spiderweb primitives.

This module exposes domain-neutral spatial operations only. It does not assign
canonical identity or producer-domain meaning. Predicate results are evidence.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from spiderweb.spatial.duckdb_engine import municipio_from_point, spatial_join
from .spatial_core import geodesic_distance_m, validate_lon_lat

PREDICATES = {
    "INTERSECTS": "ST_Intersects",
    "CONTAINS": "ST_Contains",
    "WITHIN": "ST_Within",
    "TOUCHES": "ST_Touches",
    "CROSSES": "ST_Crosses",
    "OVERLAPS": "ST_Overlaps",
}


def validate_point(lon: float, lat: float) -> dict[str, Any]:
    lon, lat = validate_lon_lat(lon, lat)
    return {"geometry_type": "Point", "coordinates": [lon, lat], "crs": "OGC:CRS84", "state": "PASS"}


def distance_evidence(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> dict[str, Any]:
    return {
        "relation": "DISTANCE",
        "distance_m": geodesic_distance_m(a_lon, a_lat, b_lon, b_lat),
        "identity_semantics": "CANDIDATE_NOT_IDENTITY",
        "evidence_state": "COMPUTED",
    }


def boundary_candidate(lat: float, lon: float, *, municipios_path: Path) -> dict[str, Any]:
    name = municipio_from_point(lat, lon, municipios_path=municipios_path)
    return {
        "relation": "POINT_IN_POLYGON",
        "candidate_name_raw": name or None,
        "spatial_state": "FULLY_WITHIN" if name else "OUTSIDE",
        "identity_semantics": "CANDIDATE_NOT_IDENTITY",
        "evidence_state": "COMPUTED",
    }


def join_evidence(left_path: Path, right_path: Path, relation: str) -> list[dict[str, Any]]:
    key = relation.upper()
    if key not in PREDICATES:
        raise ValueError(f"unsupported relation {relation!r}")
    rows = spatial_join(left_path, right_path, predicate=PREDICATES[key])
    return [
        {
            "left": row["left"],
            "right": row["right"],
            "relation": key,
            "identity_semantics": "CANDIDATE_NOT_IDENTITY",
            "evidence_state": "COMPUTED",
        }
        for row in rows
    ]
