#!/usr/bin/env python3
"""Enumerate file-level NCEI products for the frozen Guayama survey denominator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.marine_product_sources import fetch_all_ncei_file_pages
from pipeline.marine_sources import BoundingBox, CatalogFamily, freeze_http_response


def _freeze_pages(pages: tuple[object, ...], root: Path, prefix: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for idx, page in enumerate(pages):
        frozen = getattr(page, "frozen")
        body_path, manifest_path = freeze_http_response(frozen, root, stem=f"{prefix}_page_{idx:04d}")
        out.append({
            "page": idx,
            "body_path": str(body_path),
            "manifest_path": str(manifest_path),
            "row_count": len(getattr(page, "items")),
            "total_count": getattr(page, "total_count"),
            **frozen.manifest(),
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--receipt",
        default="evidence/marine/guayama_punta_tuna_v0_1/source_denominator_receipt.json",
    )
    parser.add_argument(
        "--out",
        default="evidence/marine/guayama_punta_tuna_products_v0_2",
    )
    args = parser.parse_args()

    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    bbox = BoundingBox(*receipt["source"]["bounded_aoi_wgs84"])
    multibeam_ids = tuple(receipt["ncei_multibeam_survey_ids"])
    sounding_ids = tuple(receipt["ncei_sounding_survey_ids"])

    # Multibeam supports file-level geometry; preserve it to reduce false-positive files.
    multibeam = fetch_all_ncei_file_pages(
        CatalogFamily.MULTIBEAM,
        surveys=multibeam_ids,
        categories=("Point Data",),
        bbox=bbox,
        page_size=200,
    )
    # NCEI documents that sounding file rows do not expose file-specific geometry.
    # Therefore this inventory is survey-bound, not file-level AOI certified.
    sounding = fetch_all_ncei_file_pages(
        CatalogFamily.SOUNDING,
        surveys=sounding_ids,
        categories=("Point Data",),
        page_size=200,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "receipt_version": "0.2",
        "source_denominator_artifact_sha256": receipt["source"]["artifact_sha256"],
        "bounded_aoi_wgs84": receipt["source"]["bounded_aoi_wgs84"],
        "file_pages": {
            "ncei_multibeam_point_data": _freeze_pages(multibeam, out, "ncei_multibeam_point_data"),
            "ncei_sounding_point_data": _freeze_pages(sounding, out, "ncei_sounding_point_data"),
        },
        "counts": {
            "ncei_multibeam_point_data_files": sum(len(page.items) for page in multibeam),
            "ncei_sounding_point_data_files": sum(len(page.items) for page in sounding),
        },
        "coverage_semantics": {
            "ncei_multibeam_point_data": "FILE_LEVEL_BBOX_FILTERED",
            "ncei_sounding_point_data": "SURVEY_BOUND_ONLY",
        },
        "certification_boundary": (
            "File metadata enumeration only. Sounding files are not file-level spatially filtered; "
            "no file is promoted to a direct observation until bytes, format, datum and lineage are frozen."
        ),
    }
    (out / "product_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
