#!/usr/bin/env python3
"""Rebuild the frozen TIGER 2025 municipios GeoJSON for Martin CI.

This intentionally builds only the municipios artifact and verifies both the
upstream TIGER zip and the generated GeoJSON against the committed provenance
manifest. It never writes the application database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

from server.ingestion.ingest_tiger_pr import LAYER_SPECS, _build_layer_gdf, _serialize_with_size_check

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "tiger" / "2025" / "manifest.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/spiderweb-data/municipios.geojson")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    row = next(item for item in manifest["layers"] if item["layer"] == "municipios")
    src = row["source"]
    expected = row["output"]

    with tempfile.TemporaryDirectory(prefix="spiderweb-martin-") as td:
        zip_path = Path(td) / src["filename"]
        req = urllib.request.Request(src["url"], headers={"User-Agent": "spiderweb-pr-martin-canary/1.0"})
        with urllib.request.urlopen(req, timeout=180) as response:
            payload = response.read()
        if len(payload) != src["bytes"]:
            raise RuntimeError(f"source byte mismatch: {len(payload)} != {src['bytes']}")
        if sha256_bytes(payload) != src["sha256"]:
            raise RuntimeError("source TIGER SHA256 mismatch")
        zip_path.write_bytes(payload)

        gdf = _build_layer_gdf(zip_path, LAYER_SPECS["municipios"])
        geojson, tolerance, oversized = _serialize_with_size_check(gdf, "municipios")

    if int(len(gdf)) != expected["feature_count"]:
        raise RuntimeError(f"feature-count mismatch: {len(gdf)} != {expected['feature_count']}")
    if tolerance != expected["simplify_tolerance"]:
        raise RuntimeError(f"simplification mismatch: {tolerance} != {expected['simplify_tolerance']}")
    if bool(oversized) != bool(expected["oversized_warning"]):
        raise RuntimeError("oversized flag mismatch")
    if len(geojson) != expected["bytes"]:
        raise RuntimeError(f"GeoJSON byte mismatch: {len(geojson)} != {expected['bytes']}")
    actual_sha = sha256_bytes(geojson)
    if actual_sha != expected["sha256"]:
        raise RuntimeError(f"GeoJSON SHA256 mismatch: {actual_sha} != {expected['sha256']}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(geojson)
    print(f"PASS: municipios fixture features={len(gdf)} sha256={actual_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
