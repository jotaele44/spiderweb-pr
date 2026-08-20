"""Network adapters with explicit completeness receipts and raw-page hashing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import shape

from .aoi import FrozenAOI
from .evidence import EvidenceTier, adjudicate_feature
from .sources import SourceKind, SourceSpec, SourceStatus


@dataclass(frozen=True)
class PageReceipt:
    page_index: int
    request_url: str
    byte_count: int
    byte_sha256: str
    logical_sha256: str
    row_count: int
    next_url: str | None


@dataclass(frozen=True)
class SourceRunReceipt:
    source_id: str
    family: str
    state: str
    started_utc: str
    completed_utc: str
    expected_count: int | None
    retained_count: int
    page_count: int
    complete: bool
    pages: tuple[PageReceipt, ...]
    reason: str


Fetch = Callable[[str], bytes]


def _default_fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "spiderweb-pr/0.1 subsurface-adapter"})
    with urlopen(req, timeout=60) as response:  # noqa: S310 - endpoints are registry-controlled HTTPS
        return response.read()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _logical_sha(obj: object) -> str:
    return _sha(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())


def _tier(role: str) -> EvidenceTier:
    try:
        return EvidenceTier[role]
    except KeyError as exc:
        raise ValueError(f"unknown evidence role: {role}") from exc


def _snapshot(snapshot_dir: Path | None, source_id: str, index: int, raw: bytes) -> None:
    if snapshot_dir is None:
        return
    target = snapshot_dir / source_id
    target.mkdir(parents=True, exist_ok=True)
    (target / f"page_{index:05d}.json").write_bytes(raw)


def _arcgis_query_url(spec: SourceSpec, aoi: FrozenAOI, *, count_only: bool, offset: int = 0, page_size: int = 2000) -> str:
    minx, miny, maxx, maxy = aoi.geometry.bounds
    params = {
        "where": "1=1",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outSR": "4326",
        "f": "json" if count_only else "geojson",
        "returnCountOnly": "true" if count_only else "false",
        "returnGeometry": "false" if count_only else "true",
    }
    if not count_only:
        params.update({
            "outFields": "*",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
            "orderByFields": "OBJECTID ASC",
        })
    params.update(spec.query_dict)
    return f"{spec.endpoint.rstrip('/')}/{spec.layer_id}/query?{urlencode(params)}"


def run_arcgis_source(
    spec: SourceSpec,
    aoi: FrozenAOI,
    *,
    fetch: Fetch = _default_fetch,
    snapshot_dir: str | Path | None = None,
    page_size: int = 2000,
) -> tuple[list[object], SourceRunReceipt]:
    if spec.kind != SourceKind.ARCGIS_LAYER:
        raise ValueError("run_arcgis_source requires ARCGIS_LAYER")
    if spec.status not in {SourceStatus.VERIFIED_QUERYABLE, SourceStatus.DISCOVERY_ONLY}:
        raise ValueError("source is not queryable")
    started = datetime.now(timezone.utc).isoformat()
    snapshot = None if snapshot_dir is None else Path(snapshot_dir)

    count_url = _arcgis_query_url(spec, aoi, count_only=True)
    count_raw = fetch(count_url)
    count_obj = json.loads(count_raw)
    if "error" in count_obj:
        raise RuntimeError(f"ArcGIS count query failed for {spec.source_id}: {count_obj['error']}")
    expected = int(count_obj.get("count", 0))

    records: list[object] = []
    receipts: list[PageReceipt] = []
    offset = 0
    page_index = 0
    while offset < expected:
        url = _arcgis_query_url(spec, aoi, count_only=False, offset=offset, page_size=page_size)
        raw = fetch(url)
        obj = json.loads(raw)
        if "error" in obj:
            raise RuntimeError(f"ArcGIS page query failed for {spec.source_id}: {obj['error']}")
        features = list(obj.get("features", []))
        if not features and offset < expected:
            raise RuntimeError(f"premature empty ArcGIS page for {spec.source_id} at offset {offset}")
        _snapshot(snapshot, spec.source_id, page_index, raw)
        receipts.append(PageReceipt(
            page_index, url, len(raw), _sha(raw), _logical_sha(obj), len(features),
            None if offset + len(features) >= expected else "OFFSET_NEXT",
        ))
        for idx, feature in enumerate(features):
            props = dict(feature.get("properties") or {})
            geom_obj = feature.get("geometry")
            geom = None if geom_obj is None else shape(geom_obj)
            stable = next((props.get(field) for field in spec.stable_id_fields if props.get(field) not in {None, ""}), None)
            record_id = f"{spec.source_id}:{stable if stable is not None else offset + idx}"
            basis = ["certified_geometry"]
            if stable is not None:
                basis.append("authoritative_id")
            if spec.status == SourceStatus.DISCOVERY_ONLY:
                basis.append("same_category")
            records.append(adjudicate_feature(
                aoi=aoi.geometry,
                record_id=record_id,
                source_id=spec.source_id,
                layer_family=spec.family,
                source_uri=url,
                feature=geom,
                asserted_tier=_tier(spec.evidence_role),
                basis=basis,
                attributes=props,
                source_sha256=_sha(raw),
                retrieved_utc=datetime.now(timezone.utc).isoformat(),
            ))
        offset += len(features)
        page_index += 1

    complete = len(records) == expected and sum(p.row_count for p in receipts) == expected
    state = "ZERO" if expected == 0 else "PASS" if complete else "FAIL"
    return records, SourceRunReceipt(
        spec.source_id, spec.family, state, started, datetime.now(timezone.utc).isoformat(),
        expected, len(records), len(receipts), complete, tuple(receipts),
        "count/page arithmetic closed" if complete else "count/page arithmetic mismatch",
    )


def _ogc_url(spec: SourceSpec, aoi: FrozenAOI) -> str:
    minx, miny, maxx, maxy = aoi.geometry.bounds
    params = {"f": "json", "bbox": f"{minx},{miny},{maxx},{maxy}", "limit": "10000"}
    params.update(spec.query_dict)
    return f"{spec.endpoint}?{urlencode(params)}"


def run_ogc_source(
    spec: SourceSpec,
    aoi: FrozenAOI,
    *,
    fetch: Fetch = _default_fetch,
    snapshot_dir: str | Path | None = None,
) -> tuple[list[object], SourceRunReceipt]:
    if spec.kind != SourceKind.OGC_FEATURES or spec.status != SourceStatus.VERIFIED_QUERYABLE:
        raise ValueError("run_ogc_source requires a verified OGC_FEATURES source")
    started = datetime.now(timezone.utc).isoformat()
    snapshot = None if snapshot_dir is None else Path(snapshot_dir)
    url: str | None = _ogc_url(spec, aoi)
    records: list[object] = []
    receipts: list[PageReceipt] = []
    seen_urls: set[str] = set()
    number_matched: int | None = None

    while url is not None:
        if url in seen_urls:
            raise RuntimeError(f"OGC pagination cycle for {spec.source_id}")
        seen_urls.add(url)
        raw = fetch(url)
        obj = json.loads(raw)
        if number_matched is None and obj.get("numberMatched") is not None:
            number_matched = int(obj["numberMatched"])
        features = list(obj.get("features", []))
        next_url = None
        for link in obj.get("links", []):
            if link.get("rel") == "next" and link.get("href"):
                next_url = str(link["href"])
                break
        _snapshot(snapshot, spec.source_id, len(receipts), raw)
        receipts.append(PageReceipt(len(receipts), url, len(raw), _sha(raw), _logical_sha(obj), len(features), next_url))
        for idx, feature in enumerate(features):
            props = dict(feature.get("properties") or {})
            geom_obj = feature.get("geometry")
            geom = None if geom_obj is None else shape(geom_obj)
            stable = feature.get("id") or next((props.get(f) for f in spec.stable_id_fields if props.get(f)), None)
            records.append(adjudicate_feature(
                aoi=aoi.geometry,
                record_id=f"{spec.source_id}:{stable if stable is not None else len(records) + idx}",
                source_id=spec.source_id,
                layer_family=spec.family,
                source_uri=url,
                feature=geom,
                asserted_tier=_tier(spec.evidence_role),
                basis=["authoritative_id" if stable is not None else "certified_geometry", "certified_geometry"],
                attributes=props,
                source_sha256=_sha(raw),
                retrieved_utc=datetime.now(timezone.utc).isoformat(),
            ))
        url = next_url

    expected = number_matched if number_matched is not None else len(records)
    complete = len(records) == expected and receipts and receipts[-1].next_url is None
    if expected == 0 and not receipts:
        complete = False
    state = "ZERO" if complete and expected == 0 else "PASS" if complete else "FAIL"
    return records, SourceRunReceipt(
        spec.source_id, spec.family, state, started, datetime.now(timezone.utc).isoformat(),
        expected, len(records), len(receipts), complete, tuple(receipts),
        "OGC pagination exhausted and arithmetic closed" if complete else "OGC completeness unresolved",
    )


def write_run_receipt(path: str | Path, receipt: SourceRunReceipt) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True), encoding="utf-8")
    return out
