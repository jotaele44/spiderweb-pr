"""Restartable, fail-closed acquisition helpers for subsurface benchmarks.

This module freezes source manifestations before interpretation. Discovery query
construction is deterministic, raw bytes are retained, and mutable responses are
versioned by content hash rather than silently overwritten.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class FrozenManifestation:
    source_id: str
    request_url: str
    retrieval_utc: str
    http_status: int
    content_type: str
    size_bytes: int
    sha256: str
    raw_path: str
    reused_existing_bytes: bool


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_url(base_url: str, params: Mapping[str, str | int | float | bool]) -> str:
    """Build a deterministic query URL with stable key ordering."""
    if not base_url.startswith("https://"):
        raise ValueError("authoritative acquisition URLs must use https")
    query = urlencode(sorted((str(k), str(v).lower() if isinstance(v, bool) else str(v)) for k, v in params.items()))
    return f"{base_url}?{query}"


def arcgis_point_query(
    layer_url: str,
    *,
    lon: float,
    lat: float,
    out_sr: int = 4326,
) -> str:
    """Return an ArcGIS REST point-intersection query URL.

    This performs discovery/binding against the source layer; the returned record
    still needs stable-ID and geometry validation before identity promotion.
    """
    return canonical_url(
        f"{layer_url.rstrip('/')}/query",
        {
            "f": "json",
            "where": "1=1",
            "geometry": f"{lon:.7f},{lat:.7f}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": True,
            "outSR": out_sr,
        },
    )


def arcgis_bbox_query(
    layer_url: str,
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    out_sr: int = 4326,
) -> str:
    if not (west < east and south < north):
        raise ValueError("invalid bbox ordering")
    return canonical_url(
        f"{layer_url.rstrip('/')}/query",
        {
            "f": "json",
            "where": "1=1",
            "geometry": f"{west:.7f},{south:.7f},{east:.7f},{north:.7f}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": True,
            "outSR": out_sr,
        },
    )


def ogc_bbox_query(
    collection_items_url: str,
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    extra: Mapping[str, str | int | float | bool] | None = None,
) -> str:
    if not (west < east and south < north):
        raise ValueError("invalid bbox ordering")
    params: dict[str, str | int | float | bool] = {
        "bbox": f"{west:.7f},{south:.7f},{east:.7f},{north:.7f}",
        "limit": 10000,
        "f": "json",
    }
    if extra:
        params.update(extra)
    return canonical_url(collection_items_url, params)


def freeze_http_response(
    *,
    source_id: str,
    request_url: str,
    raw: bytes,
    http_status: int,
    content_type: str,
    output_dir: str | Path,
    retrieval_utc: str | None = None,
) -> FrozenManifestation:
    """Freeze exact response bytes under a hash-qualified immutable filename."""
    if not source_id:
        raise ValueError("source_id is required")
    if http_status < 200 or http_status >= 300:
        raise ValueError(f"refusing to freeze non-success HTTP status {http_status}")
    if not raw:
        raise ValueError("refusing to freeze empty response")

    digest = _sha256(raw)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / f"{source_id}.{digest}.raw"
    reused = raw_path.exists()
    if reused:
        if _sha256(raw_path.read_bytes()) != digest:
            raise ValueError("existing frozen manifestation hash mismatch")
    else:
        tmp = raw_path.with_suffix(raw_path.suffix + ".tmp")
        tmp.write_bytes(raw)
        if _sha256(tmp.read_bytes()) != digest:
            tmp.unlink(missing_ok=True)
            raise ValueError("post-write hash verification failed")
        tmp.replace(raw_path)

    timestamp = retrieval_utc or datetime.now(timezone.utc).isoformat()
    return FrozenManifestation(
        source_id=source_id,
        request_url=request_url,
        retrieval_utc=timestamp,
        http_status=http_status,
        content_type=content_type,
        size_bytes=len(raw),
        sha256=digest,
        raw_path=str(raw_path),
        reused_existing_bytes=reused,
    )


def acquire_url(
    *,
    source_id: str,
    request_url: str,
    output_dir: str | Path,
    timeout_seconds: float = 60.0,
) -> FrozenManifestation:
    """Fetch and freeze one source response. Network errors fail closed."""
    req = Request(request_url, headers={"User-Agent": "spiderweb-pr/0.1 subsurface-benchmark"})
    with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310 - URLs are predeclared authoritative HTTPS sources
        raw = response.read()
        status = int(getattr(response, "status", 200))
        content_type = str(response.headers.get("Content-Type", ""))
    return freeze_http_response(
        source_id=source_id,
        request_url=request_url,
        raw=raw,
        http_status=status,
        content_type=content_type,
        output_dir=output_dir,
    )


def write_manifest(path: str | Path, rows: list[FrozenManifestation]) -> dict[str, object]:
    """Write a canonical logical manifest and return its closure metadata."""
    ids = [row.source_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source_id in manifestation manifest")
    serialized_rows = [asdict(row) for row in sorted(rows, key=lambda r: r.source_id)]
    logical = {"schema": "spiderweb.subsurface.benchmark_manifest.v1", "sources": serialized_rows}
    canonical = json.dumps(logical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    logical_sha256 = _sha256(canonical)
    payload = {**logical, "logical_sha256": logical_sha256, "source_count": len(rows)}
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
