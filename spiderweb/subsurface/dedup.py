"""Conservative cross-source identity resolution for subsurface evidence exports.

The resolver is intentionally not a nearest-neighbour merger. Geometry proximity,
shared system IDs, and category similarity may create candidate edges, but canonical
asset components are formed only from hard or high-confidence identity bindings.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Iterable


WITHIN_STATES = frozenset({"FULLY_WITHIN", "PARTIAL"})
WELL_SOURCES = frozenset({"PRPB_WELLS_JCA_20", "PRPB_WELLS_AAA_21", "USGS_MONITORING_LOCATIONS_PR"})
SPRING_SOURCE = "PRPB_SPRINGS_19"
QUARRY_SOURCES = frozenset({"PRPB_QUARRIES_10", "USGS_USMIN_CONSOLIDATED_POINTS_17", "USGS_MRDS_HOSTED_0_PR_AOI"})
TARGET_SOURCES = WELL_SOURCES | {SPRING_SOURCE} | QUARRY_SOURCES


@dataclass(frozen=True)
class IdentityEdge:
    left_record_id: str
    right_record_id: str
    relation: str
    binding: bool
    confidence: str
    distance_m: float | None
    name_similarity: float | None
    basis: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalAsset:
    canonical_id: str
    asset_class: str
    relation: str
    member_record_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    confidence: str


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(well|pozo|spring|quarry|cantera|pr|puerto rico)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _name_similarity(a: object, b: object) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _coords(feature: dict) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    return float(coords[0]), float(coords[1])


def _distance_m(a: dict, b: dict) -> float | None:
    ca, cb = _coords(a), _coords(b)
    if ca is None or cb is None:
        return None
    lon1, lat1 = map(math.radians, ca)
    lon2, lat2 = map(math.radians, cb)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371008.8 * math.asin(min(1.0, math.sqrt(h)))


def _prop(feature: dict, key: str, default=None):
    return (feature.get("properties") or {}).get(key, default)


def _attrs(feature: dict) -> dict:
    return dict(_prop(feature, "attributes", {}) or {})


def _record_id(feature: dict) -> str:
    return str(_prop(feature, "record_id"))


def _source_id(feature: dict) -> str:
    return str(_prop(feature, "source_id"))


def _display_name(feature: dict) -> str:
    a = _attrs(feature)
    source = _source_id(feature)
    if source == "PRPB_WELLS_JCA_20":
        return str(a.get("Nombre") or "")
    if source == "PRPB_WELLS_AAA_21":
        return str(a.get("Name") or "")
    if source == "USGS_MONITORING_LOCATIONS_PR":
        return str(a.get("monitoring_location_name") or "")
    if source == SPRING_SOURCE:
        return str(a.get("STATION_NA") or a.get("C900") or "")
    if source == "PRPB_QUARRIES_10":
        return str(a.get("Comment") or "")
    if source == "USGS_USMIN_CONSOLIDATED_POINTS_17":
        return str(a.get("ftr_name") or a.get("remarks") or "")
    if source == "USGS_MRDS_HOSTED_0_PR_AOI":
        return str(a.get("site_name") or "")
    return ""


def _is_target(feature: dict) -> bool:
    source = _source_id(feature)
    if source not in TARGET_SOURCES:
        return False
    if source == "USGS_MONITORING_LOCATIONS_PR":
        site_type = str(_attrs(feature).get("site_type") or "").lower()
        return site_type in {"well", "spring", "multiple wells"}
    return True


def _within(features: Iterable[dict]) -> list[dict]:
    return [
        f for f in features
        if _prop(f, "spatial_state") in WITHIN_STATES and _is_target(f)
    ]


def build_identity_edges(features: Iterable[dict]) -> list[IdentityEdge]:
    rows = _within(features)
    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(_source_id(row), []).append(row)
    edges: list[IdentityEdge] = []

    usgs_by_number = {
        str(_attrs(row).get("monitoring_location_number") or "").strip(): row
        for row in by_source.get("USGS_MONITORING_LOCATIONS_PR", [])
        if _attrs(row).get("monitoring_location_number")
    }
    spring_by_id: dict[str, list[dict]] = {}
    for spring in by_source.get(SPRING_SOURCE, []):
        site_id = str(_attrs(spring).get("SITE_ID") or "").strip()
        if not site_id:
            continue
        spring_by_id.setdefault(site_id, []).append(spring)
        usgs = usgs_by_number.get(site_id)
        if usgs is not None:
            edges.append(IdentityEdge(
                _record_id(spring), _record_id(usgs), "AUTHORITATIVE_ID", True, "DIRECT",
                _distance_m(spring, usgs), _name_similarity(_display_name(spring), _display_name(usgs)),
                ("PRPB.SITE_ID=USGS.monitoring_location_number",),
            ))
    for site_id, duplicate_rows in spring_by_id.items():
        if len(duplicate_rows) > 1:
            first = duplicate_rows[0]
            for other in duplicate_rows[1:]:
                edges.append(IdentityEdge(
                    _record_id(first), _record_id(other), "DUPLICATE_SOURCE_ROW", True, "DIRECT",
                    _distance_m(first, other), 1.0, (f"same PRPB SITE_ID {site_id}",),
                ))

    for jca in by_source.get("PRPB_WELLS_JCA_20", []):
        for aaa in by_source.get("PRPB_WELLS_AAA_21", []):
            distance = _distance_m(jca, aaa)
            if distance is None or distance > 25.0:
                continue
            similarity = _name_similarity(_display_name(jca), _display_name(aaa))
            exact_name = similarity == 1.0
            strong = similarity >= 0.82
            very_tight = distance <= 5.0 and similarity >= 0.60
            binding = exact_name or strong or very_tight
            edges.append(IdentityEdge(
                _record_id(jca), _record_id(aaa), "GEOMETRY_NAME" if binding else "PROXIMITY_CANDIDATE",
                binding, "SUPPORTING" if binding else "CANDIDATE", distance, similarity,
                ("point_distance<=25m", "normalized_name_similarity", "system IDs not used as asset identity"),
            ))

    for jca in by_source.get("PRPB_WELLS_JCA_20", []):
        for usgs in by_source.get("USGS_MONITORING_LOCATIONS_PR", []):
            if str(_attrs(usgs).get("site_type") or "").lower() != "well":
                continue
            distance = _distance_m(jca, usgs)
            if distance is None or distance > 30.0:
                continue
            similarity = _name_similarity(_display_name(jca), _display_name(usgs))
            if similarity >= 0.80:
                edges.append(IdentityEdge(
                    _record_id(jca), _record_id(usgs), "GEOMETRY_NAME", True, "SUPPORTING",
                    distance, similarity, ("point_distance<=30m", "strong normalized name similarity"),
                ))
            elif distance <= 10.0:
                edges.append(IdentityEdge(
                    _record_id(jca), _record_id(usgs), "PROXIMITY_CANDIDATE", False, "CANDIDATE",
                    distance, similarity, ("point_distance<=10m", "name binding insufficient"),
                ))

    prpb_quarries = by_source.get("PRPB_QUARRIES_10", [])
    other_quarries = by_source.get("USGS_USMIN_CONSOLIDATED_POINTS_17", []) + by_source.get("USGS_MRDS_HOSTED_0_PR_AOI", [])
    for left in prpb_quarries:
        for right in other_quarries:
            distance = _distance_m(left, right)
            if distance is None or distance > 150.0:
                continue
            similarity = _name_similarity(_display_name(left), _display_name(right))
            binding = similarity >= 0.86 and distance <= 75.0
            edges.append(IdentityEdge(
                _record_id(left), _record_id(right), "GEOMETRY_NAME" if binding else "PROXIMITY_CANDIDATE",
                binding, "SUPPORTING" if binding else "CANDIDATE", distance, similarity,
                ("quarry/mineral context", "proximity alone cannot establish identity"),
            ))
    return edges


def _relation_for_members(members: list[dict]) -> str:
    counts: dict[str, int] = {}
    for row in members:
        counts[_source_id(row)] = counts.get(_source_id(row), 0) + 1
    if len(counts) == 1:
        return "1:1" if len(members) == 1 else "N:1_SOURCE_DUPLICATE"
    multiplicities = list(counts.values())
    if all(v == 1 for v in multiplicities):
        return "1:1"
    if sum(v > 1 for v in multiplicities) == 1:
        return "N:1"
    return "N:N"


def canonicalize(features: Iterable[dict]) -> tuple[list[CanonicalAsset], list[IdentityEdge]]:
    rows = _within(features)
    by_id = {_record_id(row): row for row in rows}
    edges = build_identity_edges(rows)
    parent = {rid: rid for rid in by_id}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for edge in edges:
        if edge.binding and edge.left_record_id in parent and edge.right_record_id in parent:
            union(edge.left_record_id, edge.right_record_id)

    groups: dict[str, list[dict]] = {}
    for rid, row in by_id.items():
        groups.setdefault(find(rid), []).append(row)

    assets: list[CanonicalAsset] = []
    for index, members in enumerate(sorted(groups.values(), key=lambda g: sorted(_record_id(r) for r in g)[0]), start=1):
        sources = tuple(sorted({_source_id(row) for row in members}))
        source_set = set(sources)
        if source_set & (WELL_SOURCES | {SPRING_SOURCE}):
            asset_class = "GROUNDWATER_POINT"
        elif source_set & QUARRY_SOURCES:
            asset_class = "MINE_QUARRY_FEATURE"
        else:
            asset_class = "UNRESOLVED_TARGET"
        relation = _relation_for_members(members)
        member_ids = {_record_id(m) for m in members}
        confidence = "DIRECT" if any(
            edge.binding and edge.confidence == "DIRECT" and edge.left_record_id in member_ids
            for edge in edges
        ) else "SUPPORTING" if len(members) > 1 else "SOURCE_ONLY"
        assets.append(CanonicalAsset(
            canonical_id=f"SANTIAGO-ASSET-{index:06d}",
            asset_class=asset_class,
            relation=relation,
            member_record_ids=tuple(sorted(_record_id(row) for row in members)),
            source_ids=sources,
            confidence=confidence,
        ))
    return assets, edges


def write_dedup_outputs(evidence_geojson: str | Path, out_dir: str | Path) -> tuple[Path, Path]:
    src = Path(evidence_geojson)
    obj = json.loads(src.read_text(encoding="utf-8"))
    assets, edges = canonicalize(obj.get("features", []))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    asset_path = out / "canonical_assets.json"
    edge_path = out / "identity_edges.json"
    asset_path.write_text(json.dumps({"schema": "spiderweb.subsurface.canonical_assets.v1", "assets": [asdict(a) for a in assets]}, indent=2, sort_keys=True), encoding="utf-8")
    edge_path.write_text(json.dumps({"schema": "spiderweb.subsurface.identity_edges.v1", "edges": [asdict(e) for e in edges]}, indent=2, sort_keys=True), encoding="utf-8")
    return asset_path, edge_path
