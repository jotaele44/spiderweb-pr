#!/usr/bin/env python3
"""Freeze current-service Census TIGERweb Puerto Rico admin manifestations.

Read-only acquisition. The script records exact response bytes, SHA-256,
query parameters, feature counts, GEOID uniqueness, geometry types, and bbox.
It does not update the canonical registry or certify identity/geometry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "PRII-federation-spatial-reference-freeze/1.1"
PAGE_SIZE = 1_000
SOURCES = {
    "municipios": {
        "endpoint": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/82/query",
        "where": "STATE='72'",
        "expected_min": 78,
        "stable_id": "GEOID",
        "authority": "U.S. Census Bureau",
        "declared_vintage": "2026-01-01",
    },
    "barrios": {
        "endpoint": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/1/query",
        "where": "STATE='72'",
        "expected_min": 900,
        "stable_id": "GEOID",
        "authority": "U.S. Census Bureau",
        "declared_vintage": "2026-01-01",
    },
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def iter_positions(value: Any) -> Iterable[tuple[float, float]]:
    if not isinstance(value, list) or not value:
        raise RuntimeError("geometry coordinates must be a non-empty array")
    if isinstance(value[0], (int, float)) and not isinstance(value[0], bool):
        if len(value) < 2:
            raise RuntimeError(
                "coordinate position must contain longitude and latitude"
            )
        coordinates = value[:2]
        if any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
            for item in coordinates
        ):
            raise RuntimeError(
                "coordinate position contains a non-finite or non-numeric value"
            )
        yield float(coordinates[0]), float(coordinates[1])
        return
    for child in value:
        yield from iter_positions(child)


def bbox(features: list[dict[str, Any]]) -> list[float] | None:
    points: list[tuple[float, float]] = []
    for index, feature in enumerate(features):
        geometry = feature.get("geometry")
        if not isinstance(geometry, Mapping):
            raise RuntimeError(f"feature[{index}] geometry must be an object")
        points.extend(iter_positions(geometry.get("coordinates")))
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def fetch(url: str, name: str) -> tuple[bytes, int, str | None]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/geo+json,application/json",
        },
    )
    with urlopen(request, timeout=120) as response:
        payload = response.read()
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type")
    if status != 200:
        raise RuntimeError(f"{name}: HTTP {status}")
    return payload, status, content_type


def json_object(payload: bytes, name: str) -> Mapping[str, Any]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{name}: response is not valid UTF-8 JSON") from exc
    if not isinstance(data, Mapping):
        raise RuntimeError(f"{name}: response root must be an object")
    if "error" in data:
        raise RuntimeError(f"{name}: ArcGIS error response: {data['error']!r}")
    return data


def write_raw_member(
    output_dir: Path, file_name: str, payload: bytes, *, url: str, offset: int | None
) -> dict[str, Any]:
    artifact = output_dir / file_name
    artifact.write_bytes(payload)
    return {
        "path": artifact.name,
        "offset": offset,
        "url": url,
        "uncompressed_size": len(payload),
        "sha256": sha256_bytes(payload),
    }


def freeze_layer_metadata(
    name: str, spec: dict[str, Any], output_dir: Path, requested_page_size: int
) -> tuple[dict[str, Any], int]:
    layer_url = spec["endpoint"].removesuffix("/query")
    metadata_url = f"{layer_url}?f=pjson"
    payload, status, content_type = fetch(metadata_url, f"{name} layer metadata")
    metadata = json_object(payload, f"{name} layer metadata")
    fields = metadata.get("fields")
    if not isinstance(fields, list):
        raise RuntimeError(f"{name}: layer metadata fields must be an array")
    stable_id = spec["stable_id"]
    matches = [
        field
        for field in fields
        if isinstance(field, Mapping) and field.get("name") == stable_id
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"{name}: layer metadata must declare exactly one {stable_id} field"
        )
    stable_id_type = matches[0].get("type")
    if stable_id_type != "esriFieldTypeString":
        raise RuntimeError(
            f"{name}: {stable_id} must be esriFieldTypeString, got {stable_id_type!r}"
        )

    max_record_count = metadata.get("maxRecordCount")
    if (
        not isinstance(max_record_count, int)
        or isinstance(max_record_count, bool)
        or max_record_count <= 0
    ):
        raise RuntimeError(f"{name}: invalid maxRecordCount {max_record_count!r}")
    effective_page_size = min(requested_page_size, max_record_count)
    advanced = metadata.get("advancedQueryCapabilities")
    supports_pagination = (
        advanced.get("supportsPagination") if isinstance(advanced, Mapping) else None
    )

    receipt = write_raw_member(
        output_dir,
        f"census_tigerweb_current_pr_{name}-layer-metadata.json",
        payload,
        url=metadata_url,
        offset=None,
    )
    receipt.update(
        {
            "http_status": status,
            "content_type": content_type,
            "layer_name": metadata.get("name"),
            "layer_type": metadata.get("type"),
            "current_version": metadata.get("currentVersion"),
            "max_record_count": max_record_count,
            "supports_pagination": supports_pagination,
            "stable_id_field": stable_id,
            "stable_id_field_type": stable_id_type,
            "editing_info": metadata.get("editingInfo"),
        }
    )
    return receipt, effective_page_size


def freeze_one(
    name: str,
    spec: dict[str, Any],
    output_dir: Path,
    *,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    metadata_receipt, effective_page_size = freeze_layer_metadata(
        name, spec, output_dir, page_size
    )
    count_params = {
        "where": spec["where"],
        "returnCountOnly": "true",
        "f": "json",
    }
    count_url = f"{spec['endpoint']}?{urlencode(count_params)}"
    count_payload, count_status, count_content_type = fetch(count_url, f"{name} count")
    count_data = json_object(count_payload, f"{name} count")
    expected_count = count_data.get("count")
    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count < int(spec["expected_min"])
    ):
        raise RuntimeError(
            f"{name}: suspicious count {expected_count!r} < {spec['expected_min']}"
        )
    count_receipt = write_raw_member(
        output_dir,
        f"census_tigerweb_current_pr_{name}-count.json",
        count_payload,
        url=count_url,
        offset=None,
    )
    count_receipt.update(
        {
            "http_status": count_status,
            "content_type": count_content_type,
            "count": expected_count,
        }
    )

    base_params = {
        "where": spec["where"],
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "orderByFields": f"{spec['stable_id']} ASC",
        "f": "geojson",
    }
    features: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    offset = 0
    while offset < expected_count:
        params = {
            **base_params,
            "resultOffset": str(offset),
            "resultRecordCount": str(effective_page_size),
        }
        page_url = f"{spec['endpoint']}?{urlencode(params)}"
        payload, status, content_type = fetch(page_url, f"{name} page offset={offset}")
        data = json_object(payload, f"{name} page offset={offset}")
        if data.get("type") != "FeatureCollection":
            raise RuntimeError(
                f"{name}: expected GeoJSON FeatureCollection at offset {offset}"
            )
        page_features = data.get("features")
        if not isinstance(page_features, list):
            raise RuntimeError(f"{name}: features must be an array at offset {offset}")
        if not page_features:
            raise RuntimeError(
                f"{name}: pagination incomplete at offset {offset}; "
                f"expected {expected_count}"
            )
        for index, feature in enumerate(page_features):
            if not isinstance(feature, dict):
                raise RuntimeError(
                    f"{name}: feature[{offset + index}] must be an object"
                )
        member = write_raw_member(
            output_dir,
            f"census_tigerweb_current_pr_{name}-offset-{offset:06d}.geojson",
            payload,
            url=page_url,
            offset=offset,
        )
        member.update(
            {
                "http_status": status,
                "content_type": content_type,
                "feature_count": len(page_features),
                "exceeded_transfer_limit": data.get("exceededTransferLimit"),
            }
        )
        pages.append(member)
        features.extend(page_features)
        offset += len(page_features)
        if offset > expected_count:
            raise RuntimeError(
                f"{name}: paginated features exceed count receipt "
                f"{offset} > {expected_count}"
            )

    if len(features) != expected_count:
        raise RuntimeError(
            f"{name}: pagination count mismatch {len(features)} != {expected_count}"
        )

    stable_id = str(spec["stable_id"])
    ids: list[str] = []
    missing_ids: list[int] = []
    for index, feature in enumerate(features):
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise RuntimeError(f"{name}: feature[{index}] properties must be an object")
        value = properties.get(stable_id)
        if not isinstance(value, str) or not value or value != value.strip():
            missing_ids.append(index)
        else:
            ids.append(value)
    duplicate_ids = sorted(value for value, count in Counter(ids).items() if count > 1)
    if missing_ids:
        raise RuntimeError(f"{name}: {len(missing_ids)} features missing {stable_id}")
    if duplicate_ids:
        raise RuntimeError(f"{name}: duplicate {stable_id}: {duplicate_ids[:10]}")

    geometry_types: set[str] = set()
    for index, feature in enumerate(features):
        geometry = feature.get("geometry")
        if not isinstance(geometry, Mapping):
            raise RuntimeError(f"{name}: feature[{index}] geometry must be an object")
        geometry_type = geometry.get("type")
        if not isinstance(geometry_type, str) or not geometry_type.strip():
            raise RuntimeError(f"{name}: feature[{index}] geometry type is missing")
        geometry_types.add(geometry_type)

    artifact = output_dir / f"census_tigerweb_current_pr_{name}.geojson"
    logical_payload = (
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    artifact.write_bytes(logical_payload)
    payload_multiset = sorted(
        [
            {"uncompressed_size": page["uncompressed_size"], "sha256": page["sha256"]}
            for page in pages
        ],
        key=lambda member: (member["uncompressed_size"], member["sha256"]),
    )
    payload_multiset_bytes = json.dumps(
        payload_multiset, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    return {
        "scope": name,
        "authority": spec["authority"],
        "declared_vintage": spec["declared_vintage"],
        "declared_vintage_evidence_state": "ASSUMPTION",
        "endpoint": spec["endpoint"],
        "query": base_params,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact": artifact.name,
        "artifact_identity": "LOGICAL_COMPOSITE",
        "logical_sha256": sha256_bytes(logical_payload),
        "logical_byte_count": len(logical_payload),
        "service_metadata_receipt": metadata_receipt,
        "count_receipt": count_receipt,
        "raw_pages": pages,
        "payload_multiset": payload_multiset,
        "payload_multiset_sha256": sha256_bytes(payload_multiset_bytes),
        "feature_count": len(features),
        "stable_id": stable_id,
        "stable_id_unique_count": len(set(ids)),
        "geometry_types": sorted(geometry_types),
        "crs": "EPSG:4326",
        "bbox": bbox(features),
        "identity_state": "SOURCE_MANIFESTATION_ONLY",
        "geometry_state": "UNADJUDICATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(
            "output directory already exists; choose a new immutable snapshot path: "
            f"{args.output_dir}"
        )
    args.output_dir.mkdir(parents=True)

    try:
        results = [
            freeze_one(name, spec, args.output_dir) for name, spec in SOURCES.items()
        ]
    except Exception as exc:
        failure = {
            "contract_version": "federation-spatial-reference-freeze/1.1",
            "generated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "state": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        (args.output_dir / "failure_receipt.json").write_text(
            json.dumps(failure, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, sort_keys=True, ensure_ascii=False), file=sys.stderr)
        return 1
    manifest = {
        "contract_version": "federation-spatial-reference-freeze/1.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "canonical_promotion": False,
        "results": results,
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    (args.output_dir / "manifest.json").write_bytes(manifest_bytes)
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
