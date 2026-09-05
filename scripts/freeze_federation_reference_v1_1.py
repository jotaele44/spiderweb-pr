#!/usr/bin/env python3
"""Freeze current Census TIGERweb Puerto Rico admin-boundary manifestations.

Read-only acquisition. The script records exact response bytes, SHA-256,
query parameters, feature counts, GEOID uniqueness, geometry types, and bbox.
It does not update the canonical registry or certify identity/geometry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "PRII-federation-spatial-reference-freeze/1.1"
SOURCES = {
    "municipios": {
        "endpoint": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/82/query",
        "where": "STATE='72'",
        "expected_min": 78,
        "stable_id": "GEOID",
        "authority": "U.S. Census Bureau",
        "vintage": "2026-01-01",
    },
    "barrios": {
        "endpoint": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/1/query",
        "where": "STATE='72'",
        "expected_min": 900,
        "stable_id": "GEOID",
        "authority": "U.S. Census Bureau",
        "vintage": "2026-01-01",
    },
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def iter_positions(value: Any) -> Iterable[tuple[float, float]]:
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for child in value:
                yield from iter_positions(child)


def bbox(features: list[dict[str, Any]]) -> list[float] | None:
    points: list[tuple[float, float]] = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        points.extend(iter_positions(geometry.get("coordinates")))
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def freeze_one(name: str, spec: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    params = {
        "where": spec["where"],
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    url = f"{spec['endpoint']}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json,application/json"})
    with urlopen(request, timeout=120) as response:
        payload = response.read()
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type")
    if status != 200:
        raise RuntimeError(f"{name}: HTTP {status}")

    data = json.loads(payload.decode("utf-8"))
    if data.get("type") != "FeatureCollection":
        raise RuntimeError(f"{name}: expected GeoJSON FeatureCollection")
    features = data.get("features") or []
    if len(features) < int(spec["expected_min"]):
        raise RuntimeError(f"{name}: suspicious feature count {len(features)} < {spec['expected_min']}")

    stable_id = str(spec["stable_id"])
    ids = [str((feature.get("properties") or {}).get(stable_id, "")).strip() for feature in features]
    missing_ids = [index for index, value in enumerate(ids) if not value]
    duplicates = sorted({value for value in ids if value and ids.count(value) > 1})
    if missing_ids:
        raise RuntimeError(f"{name}: {len(missing_ids)} features missing {stable_id}")
    if duplicates:
        raise RuntimeError(f"{name}: duplicate {stable_id}: {duplicates[:10]}")

    geometry_types = sorted({str((feature.get("geometry") or {}).get("type")) for feature in features})
    artifact = output_dir / f"census_tigerweb_2026_pr_{name}.geojson"
    artifact.write_bytes(payload)

    return {
        "scope": name,
        "authority": spec["authority"],
        "vintage": spec["vintage"],
        "endpoint": spec["endpoint"],
        "query_url": url,
        "query": params,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "http_status": status,
        "content_type": content_type,
        "artifact": artifact.name,
        "byte_sha256": sha256_bytes(payload),
        "byte_count": len(payload),
        "feature_count": len(features),
        "stable_id": stable_id,
        "stable_id_unique_count": len(set(ids)),
        "geometry_types": geometry_types,
        "crs": "EPSG:4326",
        "bbox": bbox(features),
        "identity_state": "SOURCE_MANIFESTATION_ONLY",
        "geometry_state": "UNADJUDICATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = [freeze_one(name, spec, args.output_dir) for name, spec in SOURCES.items()]
    manifest = {
        "contract_version": "federation-spatial-reference-freeze/1.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "canonical_promotion": False,
        "results": results,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (args.output_dir / "manifest.json").write_bytes(manifest_bytes)
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
