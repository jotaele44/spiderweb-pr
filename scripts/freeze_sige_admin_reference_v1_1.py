#!/usr/bin/env python3
"""Freeze Puerto Rico Planning Board/SIGE municipio and barrio boundary manifestations.

For each layer this preserves source-native Esri JSON requested in EPSG:32161 and
an explicitly transformed EPSG:4326 GeoJSON comparison manifestation. SIGE name
fields remain candidate keys only; this script never creates canonical identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "PRII-federation-sige-admin-freeze/1.1"
SOURCES = {
    "municipios": {
        "endpoint": "https://sigejp.pr.gov/server/rest/services/Advisory_Maps/Datos_Generales/MapServer/2/query",
        "expected_min": 78,
        "candidate_fields": ["Nombre"],
    },
    "barrios": {
        "endpoint": "https://sigejp.pr.gov/server/rest/services/Advisory_Maps/Datos_Generales/MapServer/3/query",
        "expected_min": 900,
        "candidate_fields": ["MUNICIPIO", "BARRIO"],
    },
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def fetch(url: str, name: str) -> tuple[bytes, int, str | None]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,application/geo+json"})
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
        raise RuntimeError(f"{name}: invalid UTF-8 JSON") from exc
    if not isinstance(data, Mapping):
        raise RuntimeError(f"{name}: response root must be an object")
    if "error" in data:
        raise RuntimeError(f"{name}: ArcGIS error response: {data['error']!r}")
    return data


def write_member(output_dir: Path, filename: str, payload: bytes, url: str, **extra):
    path = output_dir / filename
    path.write_bytes(payload)
    return {
        "path": path.name,
        "url": url,
        "byte_count": len(payload),
        "sha256": sha256_bytes(payload),
        **extra,
    }


def metadata(name: str, spec: Mapping[str, Any], output_dir: Path):
    layer_url = str(spec["endpoint"]).removesuffix("/query")
    url = f"{layer_url}?f=pjson"
    payload, status, content_type = fetch(url, f"{name} metadata")
    data = json_object(payload, f"{name} metadata")
    if data.get("geometryType") != "esriGeometryPolygon":
        raise RuntimeError(f"{name}: expected polygon layer")
    source_sr = data.get("sourceSpatialReference")
    if not isinstance(source_sr, Mapping) or source_sr.get("latestWkid", source_sr.get("wkid")) != 32161:
        raise RuntimeError(f"{name}: expected source EPSG:32161")
    max_count = data.get("maxRecordCount")
    if not isinstance(max_count, int) or isinstance(max_count, bool) or max_count <= 0:
        raise RuntimeError(f"{name}: invalid maxRecordCount")
    fields = {row.get("name") for row in data.get("fields", []) if isinstance(row, Mapping)}
    missing = [field for field in spec["candidate_fields"] if field not in fields]
    if missing:
        raise RuntimeError(f"{name}: missing candidate fields {missing}")
    receipt = write_member(
        output_dir,
        f"sige_{name}-layer-metadata.json",
        payload,
        url,
        http_status=status,
        content_type=content_type,
    )
    receipt.update(
        {
            "layer_id": data.get("id"),
            "layer_name": data.get("name"),
            "description": data.get("description"),
            "source_spatial_reference": source_sr,
            "max_record_count": max_count,
            "candidate_fields": spec["candidate_fields"],
            "stable_identifier": None,
        }
    )
    return receipt, max_count


def freeze_one(name: str, spec: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    metadata_receipt, page_size = metadata(name, spec, output_dir)
    count_params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
    count_url = f"{spec['endpoint']}?{urlencode(count_params)}"
    count_payload, count_status, count_content_type = fetch(count_url, f"{name} count")
    count_data = json_object(count_payload, f"{name} count")
    expected_count = count_data.get("count")
    if not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count < int(spec["expected_min"]):
        raise RuntimeError(f"{name}: suspicious count {expected_count!r}")
    count_receipt = write_member(
        output_dir,
        f"sige_{name}-count.json",
        count_payload,
        count_url,
        http_status=count_status,
        content_type=count_content_type,
        count=expected_count,
    )

    native_pages = []
    canonical_pages = []
    canonical_features: list[dict[str, Any]] = []
    offset = 0
    while offset < expected_count:
        common = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "orderByFields": "OBJECTID ASC",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }
        native_params = {**common, "outSR": "32161", "f": "json"}
        native_url = f"{spec['endpoint']}?{urlencode(native_params)}"
        native_payload, native_status, native_type = fetch(native_url, f"{name} native offset={offset}")
        native_data = json_object(native_payload, f"{name} native offset={offset}")
        native_features = native_data.get("features")
        if not isinstance(native_features, list) or not native_features:
            raise RuntimeError(f"{name}: incomplete native pagination at {offset}")
        native_pages.append(
            write_member(
                output_dir,
                f"sige_{name}-epsg32161-offset-{offset:06d}.json",
                native_payload,
                native_url,
                offset=offset,
                feature_count=len(native_features),
                http_status=native_status,
                content_type=native_type,
            )
        )

        canonical_params = {**common, "outSR": "4326", "f": "geojson"}
        canonical_url = f"{spec['endpoint']}?{urlencode(canonical_params)}"
        canonical_payload, canonical_status, canonical_type = fetch(
            canonical_url, f"{name} canonical offset={offset}"
        )
        canonical_data = json_object(canonical_payload, f"{name} canonical offset={offset}")
        if canonical_data.get("type") != "FeatureCollection":
            raise RuntimeError(f"{name}: expected canonical GeoJSON FeatureCollection")
        page_features = canonical_data.get("features")
        if not isinstance(page_features, list) or len(page_features) != len(native_features):
            raise RuntimeError(f"{name}: native/canonical page count mismatch at {offset}")
        canonical_pages.append(
            write_member(
                output_dir,
                f"sige_{name}-epsg4326-offset-{offset:06d}.geojson",
                canonical_payload,
                canonical_url,
                offset=offset,
                feature_count=len(page_features),
                http_status=canonical_status,
                content_type=canonical_type,
            )
        )
        canonical_features.extend(page_features)
        offset += len(page_features)

    if len(canonical_features) != expected_count:
        raise RuntimeError(f"{name}: count closure failed {len(canonical_features)} != {expected_count}")

    keys = []
    missing_keys = []
    for index, feature in enumerate(canonical_features):
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            missing_keys.append(index)
            continue
        parts = [normalize(properties.get(field)) for field in spec["candidate_fields"]]
        if any(not part for part in parts):
            missing_keys.append(index)
        else:
            keys.append("|".join(parts))
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)

    logical_payload = (
        json.dumps(
            {"type": "FeatureCollection", "features": canonical_features},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    logical_path = output_dir / f"sige_{name}-epsg4326-logical.geojson"
    logical_path.write_bytes(logical_payload)

    return {
        "scope": name,
        "authority": "Puerto Rico Planning Board / SIGE",
        "service_metadata_receipt": metadata_receipt,
        "count_receipt": count_receipt,
        "source_native_crs": "EPSG:32161",
        "canonical_comparison_crs": "EPSG:4326",
        "source_native_pages": native_pages,
        "canonical_pages": canonical_pages,
        "logical_artifact": logical_path.name,
        "logical_sha256": sha256_bytes(logical_payload),
        "feature_count": len(canonical_features),
        "candidate_fields": spec["candidate_fields"],
        "candidate_unique_count": len(set(keys)),
        "missing_candidate_key_count": len(missing_keys),
        "duplicate_candidate_keys": duplicates,
        "stable_identifier": None,
        "identity_state": "CANDIDATE_NOT_IDENTITY",
        "geometry_state": "SOURCE_MANIFESTATION_UNADJUDICATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("output directory already exists; use a new immutable snapshot path")
    args.output_dir.mkdir(parents=True)
    try:
        results = [freeze_one(name, spec, args.output_dir) for name, spec in SOURCES.items()]
    except Exception as exc:
        failure = {
            "contract_version": "federation-spatial-sige-admin-freeze/1.1",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "state": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        (args.output_dir / "failure_receipt.json").write_text(
            json.dumps(failure, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1
    manifest = {
        "contract_version": "federation-spatial-sige-admin-freeze/1.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "canonical_promotion": False,
        "results": results,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({row["scope"]: row["feature_count"] for row in results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
