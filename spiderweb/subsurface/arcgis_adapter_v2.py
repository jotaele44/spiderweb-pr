"""ArcGIS adapter v2: dynamic OID paging and ESRI JSON geometry decoding.

Some authoritative services in the public denominator advertise JSON but not
GeoJSON and some use an OID field whose spelling/case differs from OBJECTID.
This adapter uses layer preflight output to avoid assumptions about either.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode

from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon

from .adapters import Fetch, PageReceipt, SourceRunReceipt, _default_fetch, _logical_sha, _sha
from .aoi import FrozenAOI
from .evidence import EvidenceTier, adjudicate_feature
from .preflight import ArcGISLayerManifest
from .sources import SourceKind, SourceSpec, SourceStatus


def _tier(role: str) -> EvidenceTier:
    try:
        return EvidenceTier[role]
    except KeyError as exc:
        raise ValueError(f"unknown evidence role: {role}") from exc


def _source_dir(snapshot_dir: Path | None, source_id: str) -> Path | None:
    if snapshot_dir is None:
        return None
    target = snapshot_dir / source_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _signed_area(ring: list[list[float]]) -> float:
    if len(ring) < 3:
        return 0.0
    total = 0.0
    for i, a in enumerate(ring):
        b = ring[(i + 1) % len(ring)]
        total += a[0] * b[1] - b[0] * a[1]
    return total / 2.0


def _polygon_from_rings(rings: list[list[list[float]]]):
    """Decode ArcGIS rings using clockwise exterior / CCW hole convention."""
    if not rings:
        return None
    exteriors = [ring for ring in rings if _signed_area(ring) < 0]
    holes = [ring for ring in rings if _signed_area(ring) >= 0]
    # Some producers violate orientation. Fail to a conservative polygon only when
    # there is a single ring; otherwise reject rather than invent topology.
    if not exteriors:
        if len(rings) == 1:
            return Polygon(rings[0])
        raise ValueError("ArcGIS polygon rings have no identifiable exterior")

    shells = [Polygon(ring) for ring in exteriors]
    assigned: list[list[list[list[float]]]] = [[] for _ in shells]
    for hole in holes:
        hp = Polygon(hole).representative_point()
        candidates = [(idx, shell.area) for idx, shell in enumerate(shells) if shell.contains(hp)]
        if not candidates:
            raise ValueError("ArcGIS polygon hole is not contained by any exterior")
        idx = min(candidates, key=lambda item: item[1])[0]
        assigned[idx].append(hole)
    polygons = [Polygon(exteriors[i], assigned[i]) for i in range(len(exteriors))]
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def esri_geometry_to_shapely(obj: dict | None):
    if obj is None:
        return None
    if "x" in obj and "y" in obj:
        return Point(float(obj["x"]), float(obj["y"]))
    if "points" in obj:
        return MultiPoint(obj["points"])
    if "paths" in obj:
        paths = obj["paths"]
        if len(paths) == 1:
            return LineString(paths[0])
        return MultiLineString(paths)
    if "rings" in obj:
        return _polygon_from_rings(obj["rings"])
    raise ValueError(f"unsupported ArcGIS geometry keys: {sorted(obj)}")


def _query_url(
    spec: SourceSpec,
    aoi: FrozenAOI,
    *,
    count_only: bool,
    oid_field: str,
    offset: int = 0,
    page_size: int = 2000,
) -> str:
    minx, miny, maxx, maxy = aoi.geometry.bounds
    params = {
        "where": "1=1",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outSR": "4326",
        "f": "json",
        "returnCountOnly": "true" if count_only else "false",
        "returnGeometry": "false" if count_only else "true",
    }
    if not count_only:
        params.update(
            {
                "outFields": "*",
                "resultOffset": str(offset),
                "resultRecordCount": str(page_size),
                "orderByFields": f"{oid_field} ASC",
            }
        )
    params.update(spec.query_dict)
    return f"{spec.endpoint.rstrip('/')}/{spec.layer_id}/query?{urlencode(params)}"


def run_arcgis_source_v2(
    spec: SourceSpec,
    aoi: FrozenAOI,
    manifest: ArcGISLayerManifest,
    *,
    fetch: Fetch = _default_fetch,
    snapshot_dir: str | Path | None = None,
    page_size: int | None = None,
) -> tuple[list[object], SourceRunReceipt]:
    if spec.kind != SourceKind.ARCGIS_LAYER:
        raise ValueError("run_arcgis_source_v2 requires ARCGIS_LAYER")
    if spec.status not in {SourceStatus.VERIFIED_QUERYABLE, SourceStatus.DISCOVERY_ONLY}:
        raise ValueError("source is not queryable")
    if not manifest.object_id_field:
        raise RuntimeError(f"{spec.source_id} has no OID field")

    oid_field = manifest.object_id_field
    effective_page_size = min(page_size or manifest.max_record_count or 2000, manifest.max_record_count or 2000)
    started = datetime.now(timezone.utc).isoformat()
    snapshot = None if snapshot_dir is None else Path(snapshot_dir)
    source_dir = _source_dir(snapshot, spec.source_id)

    count_url = _query_url(spec, aoi, count_only=True, oid_field=oid_field)
    count_raw = fetch(count_url)
    count_obj = json.loads(count_raw)
    if "error" in count_obj:
        raise RuntimeError(f"ArcGIS count query failed for {spec.source_id}: {count_obj['error']}")
    if "count" not in count_obj:
        raise RuntimeError(f"ArcGIS count response missing count for {spec.source_id}")
    expected = int(count_obj["count"])
    if source_dir is not None:
        (source_dir / "count.raw.json").write_bytes(count_raw)
        (source_dir / "count_manifest.json").write_text(
            json.dumps(
                {
                    "request_url": count_url,
                    "byte_count": len(count_raw),
                    "byte_sha256": _sha(count_raw),
                    "logical_sha256": _logical_sha(count_obj),
                    "count": expected,
                    "oid_field": oid_field,
                    "page_size": effective_page_size,
                    "response_format": "esri-json",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    records: list[object] = []
    pages: list[PageReceipt] = []
    offset = 0
    page_index = 0
    while offset < expected:
        url = _query_url(
            spec,
            aoi,
            count_only=False,
            oid_field=oid_field,
            offset=offset,
            page_size=effective_page_size,
        )
        raw = fetch(url)
        obj = json.loads(raw)
        if "error" in obj:
            raise RuntimeError(f"ArcGIS page query failed for {spec.source_id}: {obj['error']}")
        features = list(obj.get("features", []))
        if not features and offset < expected:
            raise RuntimeError(f"premature empty ArcGIS page for {spec.source_id} at offset {offset}")
        if source_dir is not None:
            (source_dir / f"page_{page_index:05d}.json").write_bytes(raw)
        pages.append(
            PageReceipt(
                page_index,
                url,
                len(raw),
                _sha(raw),
                _logical_sha(obj),
                len(features),
                None if offset + len(features) >= expected else "OFFSET_NEXT",
            )
        )
        for idx, feature in enumerate(features):
            attrs = dict(feature.get("attributes") or {})
            geom = esri_geometry_to_shapely(feature.get("geometry"))
            stable = next(
                (
                    attrs.get(field)
                    for field in (oid_field, *spec.stable_id_fields)
                    if attrs.get(field) not in {None, ""}
                ),
                None,
            )
            record_id = f"{spec.source_id}:{stable if stable is not None else offset + idx}"
            basis = ["certified_geometry"]
            if stable is not None:
                basis.append("authoritative_id")
            if spec.status == SourceStatus.DISCOVERY_ONLY:
                basis.append("same_category")
            records.append(
                adjudicate_feature(
                    aoi=aoi.geometry,
                    record_id=record_id,
                    source_id=spec.source_id,
                    layer_family=spec.family,
                    source_uri=url,
                    feature=geom,
                    asserted_tier=_tier(spec.evidence_role),
                    basis=basis,
                    attributes=attrs,
                    source_sha256=_sha(raw),
                    retrieved_utc=datetime.now(timezone.utc).isoformat(),
                )
            )
        offset += len(features)
        page_index += 1

    complete = len(records) == expected and sum(page.row_count for page in pages) == expected
    state = "ZERO" if expected == 0 else "PASS" if complete else "FAIL"
    return records, SourceRunReceipt(
        spec.source_id,
        spec.family,
        state,
        started,
        datetime.now(timezone.utc).isoformat(),
        expected,
        len(records),
        len(pages),
        complete,
        tuple(pages),
        "count/page arithmetic closed with dynamic OID + ESRI JSON"
        if complete
        else "count/page arithmetic mismatch",
    )
