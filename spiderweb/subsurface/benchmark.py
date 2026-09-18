"""Evidence-bounded benchmark controls for subsurface/karst/ocean-outlet analysis.

The module deliberately separates acquisition geometry from semantic identity. Metric
windows are used to discover/source records; they never establish a cave, void,
conduit, spring, or outlet by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable


class ObjectState(StrEnum):
    OBSERVED = "OBSERVED"
    CANDIDATE = "CANDIDATE"
    UNRESOLVED = "UNRESOLVED"
    VERIFIED = "VERIFIED"


FORBIDDEN_IDENTITY_CLASSES = frozenset(
    {"CAVE", "VOID", "SUBSURFACE_CONDUIT", "SUBMARINE_SPRING", "OCEAN_OUTLET"}
)


@dataclass(frozen=True)
class Anchor:
    lat: float
    lon: float
    crs: str = "EPSG:4326"

    def __post_init__(self) -> None:
        if not -90 <= self.lat <= 90:
            raise ValueError("latitude outside WGS84 bounds")
        if not -180 <= self.lon <= 180:
            raise ValueError("longitude outside WGS84 bounds")
        if self.crs != "EPSG:4326":
            raise ValueError("benchmark anchor must be frozen in EPSG:4326")


@dataclass(frozen=True)
class MetricWindow:
    window_id: str
    radius_m: float
    purpose: str

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ValueError("window_id is required")
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")


@dataclass(frozen=True)
class CandidateObject:
    candidate_id: str
    object_class: str
    state: ObjectState
    evidence_ids: tuple[str, ...] = ()
    independent_identity_evidence_ids: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id is required")
        if self.state == ObjectState.VERIFIED and self.object_class in FORBIDDEN_IDENTITY_CLASSES:
            if not self.independent_identity_evidence_ids:
                raise ValueError(
                    f"{self.object_class} cannot be VERIFIED without independent identity evidence"
                )


def load_benchmark(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_benchmark(payload)
    return payload


def validate_benchmark(payload: dict) -> None:
    if payload.get("schema") != "spiderweb.subsurface.benchmark.v1":
        raise ValueError("unexpected benchmark schema")
    if not payload.get("benchmark_id"):
        raise ValueError("benchmark_id is required")
    anchor = payload.get("anchor") or {}
    Anchor(float(anchor["lat"]), float(anchor["lon"]), str(anchor.get("crs", "")))

    windows = [
        MetricWindow(str(row["id"]), float(row["radius_m"]), str(row["purpose"]))
        for row in payload.get("metric_windows", [])
    ]
    if len(windows) != 4:
        raise ValueError("benchmark requires exactly four metric windows")
    ids = [row.window_id for row in windows]
    if ids != ["Z1", "Z2", "Z3", "Z4"]:
        raise ValueError("metric windows must be ordered Z1, Z2, Z3, Z4")
    radii = [row.radius_m for row in windows]
    if any(a <= b for a, b in zip(radii, radii[1:])):
        raise ValueError("metric windows must be strictly nested from largest to smallest")

    states = payload.get("classification_states", [])
    expected_states = [state.value for state in ObjectState]
    if states != expected_states:
        raise ValueError(f"classification_states must equal {expected_states}")

    families = payload.get("required_source_families", [])
    if len(families) != len(set(families)):
        raise ValueError("duplicate required source family")


def acquisition_bbox(anchor: Anchor, radius_m: float) -> tuple[float, float, float, float]:
    """Return a conservative WGS84 bbox for source discovery only.

    This uses local metres-per-degree approximations. It is intentionally labelled an
    acquisition bbox, not certified metric geometry. Exact distance/topology gates must
    run in a suitable projected CRS or geodesic engine after source acquisition.
    """
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    lat_rad = math.radians(anchor.lat)
    meters_per_lat_degree = 111_132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
    meters_per_lon_degree = 111_412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)
    dlat = radius_m / meters_per_lat_degree
    dlon = radius_m / meters_per_lon_degree
    return (anchor.lon - dlon, anchor.lat - dlat, anchor.lon + dlon, anchor.lat + dlat)


def source_arithmetic(required_source_families: Iterable[str], source_rows: Iterable[dict]) -> dict[str, int]:
    families = tuple(required_source_families)
    counts = {family: 0 for family in families}
    unexpected = 0
    for row in source_rows:
        family = row.get("family")
        if family in counts:
            counts[family] += 1
        else:
            unexpected += 1
    missing = sum(1 for count in counts.values() if count == 0)
    return {
        "required_families": len(families),
        "covered_families": len(families) - missing,
        "missing_families": missing,
        "unexpected_rows": unexpected,
        "rows": sum(counts.values()) + unexpected,
    }


def freeze_bytes(path: str | Path) -> dict[str, str | int]:
    raw = Path(path).read_bytes()
    return {
        "path": str(path),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def certification_state(payload: dict, candidates: Iterable[CandidateObject] = ()) -> str:
    validate_benchmark(payload)
    candidate_rows = tuple(candidates)
    for candidate in candidate_rows:
        candidate.validate()
    gates = payload.get("certification_gates") or {}
    if not gates:
        return "OPEN"
    if not all(bool(value) for value in gates.values()):
        return "PROVISIONAL"
    if any(candidate.state == ObjectState.UNRESOLVED for candidate in candidate_rows):
        return "OPEN"
    return "PASS"
