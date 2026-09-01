#!/usr/bin/env python3
"""Execute or dry-run the bounded Guayama–Punta Tuna source denominator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.marine_lidar_sources import (
    LidarInventoryLayer,
    fetch_all_usiei_pages,
)
from pipeline.marine_reference_run import (
    GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1,
    build_reference_queries,
)
from pipeline.marine_sources import (
    CatalogFamily,
    fetch_all_ncei_catalog_pages,
    fetch_all_nos_bag_pages,
    freeze_http_response,
)


def _freeze_pages(pages: tuple[object, ...], root: Path, prefix: str) -> list[dict[str, object]]:
    manifests: list[dict[str, object]] = []
    for idx, page in enumerate(pages):
        frozen = getattr(page, "frozen")
        stem = f"{prefix}_page_{idx:04d}"
        body_path, manifest_path = freeze_http_response(frozen, root, stem=stem)
        manifests.append(
            {
                "page": idx,
                "body_path": str(body_path),
                "manifest_path": str(manifest_path),
                **frozen.manifest(),
            }
        )
    return manifests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="perform live NOAA/NCEI requests")
    parser.add_argument("--out", default="evidence/marine/guayama_punta_tuna_v0_1")
    args = parser.parse_args()

    aoi = GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1
    plan = {
        "aoi_id": aoi.aoi_id,
        "role": aoi.role.value,
        "certified": aoi.certified,
        "bbox": [aoi.bbox.min_lon, aoi.bbox.min_lat, aoi.bbox.max_lon, aoi.bbox.max_lat],
        "provenance": aoi.provenance,
        "queries": dict(build_reference_queries(aoi)),
    }

    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    multibeam = fetch_all_ncei_catalog_pages(CatalogFamily.MULTIBEAM, aoi.bbox)
    sounding = fetch_all_ncei_catalog_pages(CatalogFamily.SOUNDING, aoi.bbox)
    bags = fetch_all_nos_bag_pages(aoi.bbox, page_size=2000)
    topobathy = fetch_all_usiei_pages(LidarInventoryLayer.TOPOBATHY_SHORELINE, aoi.bbox)
    bathy_lidar = fetch_all_usiei_pages(LidarInventoryLayer.BATHYMETRIC, aoi.bbox)
    other_bathy = fetch_all_usiei_pages(LidarInventoryLayer.OTHER_BATHYMETRIC_SURVEYS, aoi.bbox)

    run_manifest = {
        **plan,
        "source_pages": {
            "ncei_multibeam": _freeze_pages(multibeam, out, "ncei_multibeam"),
            "ncei_sounding": _freeze_pages(sounding, out, "ncei_sounding"),
            "nos_bag": _freeze_pages(bags, out, "nos_bag"),
            "usiei_topobathy": _freeze_pages(topobathy, out, "usiei_topobathy"),
            "usiei_bathymetric": _freeze_pages(bathy_lidar, out, "usiei_bathymetric"),
            "usiei_other_bathymetric": _freeze_pages(other_bathy, out, "usiei_other_bathymetric"),
        },
        "certification_boundary": (
            "Source-denominator acquisition only; exact screenshot footprint and seafloor "
            "feature certification remain unresolved."
        ),
    }
    (out / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(run_manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
