#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from integration.crim_lookup import CrimClient, canonical_json, utc_now, validate_layer_metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/crim/source_contract"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metadata, provenance = CrimClient().metadata()
    validate_layer_metadata(metadata)
    raw = canonical_json(metadata)
    metadata_sha256 = hashlib.sha256(raw).hexdigest()

    (args.output_dir / "layer_metadata.json").write_bytes(raw + b"\n")
    manifest = {
        "manifest_id": "crim_sige_parcelario_v0_1",
        "retrieval_utc": utc_now(),
        "metadata_sha256": metadata_sha256,
        "provenance": provenance.__dict__,
        "field_count": len(metadata.get("fields", [])),
        "geometry_type": metadata.get("geometryType"),
        "native_wkid": (metadata.get("sourceSpatialReference") or {}).get("wkid"),
    }
    (args.output_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
