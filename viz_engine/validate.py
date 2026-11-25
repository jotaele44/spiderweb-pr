"""Validation gates.  Any ``error`` issue makes the run ``FAIL``.

Codes: CRS_MISMATCH, DATUM_MISMATCH, UNIT_MISMATCH, DUPLICATE_FEATURE_ID,
MERGED_ID_WITHOUT_ADJUDICATION, REVERSED_FLOW, DISCONNECTED_SEGMENT,
MISSING_RASTER_COVERAGE, NO_RASTER, UNSUPPORTED_CONNECTION,
CONNECTION_ENDPOINT_MISSING, UNKNOWN_EVIDENCE_CLASS, DEPTH_REFERENCE_UNSUPPORTED.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from . import EVIDENCE_CLASSES
from . import dem as demlib
from .snapshot import Snapshot

Issue = dict[str, Any]
FLOW_TOLERANCE_M = 1.0
SUPPORTED_DEPTH_REFERENCE = "below_land_surface"


def issue(
    code: str, message: str, ids: Iterable[str] = (), severity: str = "error"
) -> Issue:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "feature_ids": sorted(set(ids)),
    }


def evidence_of(feature: dict[str, Any]) -> str:
    """Declared evidence class; anything absent or unrecognised is ``unknown``."""
    ev = (feature.get("properties") or {}).get("evidence")
    return ev if ev in EVIDENCE_CLASSES else "unknown"


def check_reference_frames(snap: Snapshot) -> list[Issue]:
    out: list[Issue] = []
    m = snap.manifest
    for layer_id, data in sorted(snap.layers.items()):
        if data.get("crs") != m["crs"]:
            out.append(
                issue(
                    "CRS_MISMATCH",
                    f"layer {layer_id} crs {data.get('crs')!r} != snapshot {m['crs']!r}",
                    [layer_id],
                )
            )
        vd = data.get("vertical_datum")
        if vd is not None and vd != m["vertical_datum"]:
            out.append(
                issue(
                    "DATUM_MISMATCH",
                    f"layer {layer_id} vertical datum {vd!r} != snapshot {m['vertical_datum']!r}",
                    [layer_id],
                )
            )
        unit = data.get("unit")
        if data.get("kind") == "raster_dem" and unit != m["units"]["vertical"]:
            out.append(
                issue(
                    "UNIT_MISMATCH",
                    f"layer {layer_id} unit {unit!r} != snapshot {m['units']['vertical']!r}",
                    [layer_id],
                )
            )
    return out


def check_identities(snap: Snapshot) -> list[Issue]:
    out: list[Issue] = []
    seen: dict[str, list[str]] = defaultdict(list)
    for layer in snap.feature_layers():
        for f in layer["features"]:
            seen[f["id"]].append(layer["layer_id"])
            props = f.get("properties") or {}
            if props.get("merged_from") and not props.get("identity_adjudication"):
                out.append(
                    issue(
                        "MERGED_ID_WITHOUT_ADJUDICATION",
                        f"feature {f['id']} merges {props['merged_from']} without an identity adjudication",
                        [f["id"], *props["merged_from"]],
                    )
                )
    for fid, where in sorted(seen.items()):
        if len(where) > 1:
            out.append(
                issue(
                    "DUPLICATE_FEATURE_ID",
                    f"feature id {fid} appears {len(where)} times ({', '.join(where)})",
                    [fid],
                )
            )
    return out


def _components(edges: list[tuple[str, str, str]]) -> list[set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for _, a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    comps, seen = [], set()
    for start in sorted(adj):
        if start in seen:
            continue
        comp, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node in comp:
                continue
            comp.add(node)
            stack.extend(adj[node] - comp)
        seen |= comp
        comps.append(comp)
    return comps


def check_network(snap: Snapshot) -> list[Issue]:
    """Flow direction against the DEM, and connectivity of the digitised network."""
    out: list[Issue] = []
    net = snap.layer("hydro_network")
    if net is None:
        return out
    dem = snap.layer("raster_dem")
    segs = net["features"]
    for f in segs:
        props = f.get("properties") or {}
        if dem is None or props.get("flow_direction") != "digitized_downstream":
            continue
        coords = f["geometry"]["coordinates"]
        up, down = demlib.sample(dem, *coords[0]), demlib.sample(dem, *coords[-1])
        if up is None or down is None:
            continue  # reported as MISSING_RASTER_COVERAGE by the view checks
        if up < down - FLOW_TOLERANCE_M:
            out.append(
                issue(
                    "REVERSED_FLOW",
                    f"segment {f['id']} is digitised downstream but rises {down - up:.1f} m",
                    [f["id"]],
                )
            )
    edges = [
        (f["id"], f["properties"]["from_node"], f["properties"]["to_node"])
        for f in segs
    ]
    comps = _components(edges)
    if len(comps) > 1:
        main = max(comps, key=lambda c: (len(c), sorted(c)))
        for f in segs:
            props = f["properties"]
            if (
                props["from_node"] not in main
                and props.get("network_role") != "isolated_declared"
            ):
                out.append(
                    issue(
                        "DISCONNECTED_SEGMENT",
                        f"segment {f['id']} is not connected to the main network",
                        [f["id"]],
                    )
                )
    return out


def check_connections(snap: Snapshot) -> list[Issue]:
    """A connection must carry the evidence its class claims, and real endpoints."""
    out: list[Issue] = []
    layer = snap.layer("connections")
    if layer is None:
        return out
    known = {
        f["id"]
        for lyr in snap.feature_layers()
        for f in lyr["features"]
        if lyr is not layer
    }
    for f in layer["features"]:
        props = f.get("properties") or {}
        ev = evidence_of(f)
        if props.get("evidence") not in EVIDENCE_CLASSES:
            out.append(
                issue(
                    "UNKNOWN_EVIDENCE_CLASS",
                    f"connection {f['id']} has evidence {props.get('evidence')!r}",
                    [f["id"]],
                    "warning",
                )
            )
        if ev == "observed" and not props.get("observation_ref"):
            out.append(
                issue(
                    "UNSUPPORTED_CONNECTION",
                    f"connection {f['id']} claims observed without an observation_ref",
                    [f["id"]],
                )
            )
        if ev == "modeled" and not props.get("model_id"):
            out.append(
                issue(
                    "UNSUPPORTED_CONNECTION",
                    f"connection {f['id']} claims modeled without a model_id",
                    [f["id"]],
                )
            )
        for end in (props.get("from_id"), props.get("to_id")):
            if end not in known:
                out.append(
                    issue(
                        "CONNECTION_ENDPOINT_MISSING",
                        f"connection {f['id']} endpoint {end!r} is not a snapshot feature",
                        [f["id"]],
                    )
                )
    return out


def check_wells(snap: Snapshot) -> list[Issue]:
    out: list[Issue] = []
    layer = snap.layer("wells")
    for f in (layer or {}).get("features", []):
        ref = (f.get("properties") or {}).get("depth_reference")
        if ref != SUPPORTED_DEPTH_REFERENCE:
            out.append(
                issue(
                    "DEPTH_REFERENCE_UNSUPPORTED",
                    f"well {f['id']} depth reference {ref!r}; only {SUPPORTED_DEPTH_REFERENCE!r} is supported",
                    [f["id"]],
                )
            )
    return out


def check_extent_coverage(
    snap: Snapshot, points: Iterable[tuple[float, float]], label: str
) -> list[Issue]:
    dem = snap.layer("raster_dem")
    if dem is None:
        return [issue("NO_RASTER", f"{label} needs a raster_dem layer")]
    missing = [(lon, lat) for lon, lat in points if not demlib.covers(dem, lon, lat)]
    if missing:
        return [
            issue(
                "MISSING_RASTER_COVERAGE",
                f"{len(missing)} {label} sample point(s) fall outside raster coverage or on nodata",
                [],
            )
        ]
    return []


def validate_snapshot(snap: Snapshot) -> list[Issue]:
    return [
        *check_reference_frames(snap),
        *check_identities(snap),
        *check_network(snap),
        *check_connections(snap),
        *check_wells(snap),
    ]


def status_of(issues: list[Issue]) -> str:
    return "FAIL" if any(i["severity"] == "error" for i in issues) else "PASS"
