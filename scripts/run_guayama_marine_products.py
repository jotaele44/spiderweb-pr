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
    multibeam_ids = set(receipt["ncei_multibeam_survey_ids"])
    sounding_ids = tuple(receipt["ncei_sounding_survey_ids"])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # NCEI supports file-specific geometry for multibeam. Query the AOI directly
    # without combining it with a long survey/category filter (the service may 500
    # on that combination), then fail closed if a returned survey was not present
    # in the frozen survey denominator.
    multibeam = fetch_all_ncei_file_pages(
        CatalogFamily.MULTIBEAM,
        bbox=bbox,
        page_size=200,
    )
    returned_multibeam_ids = {
        str(item.get("surveyId"))
        for page in multibeam
        for item in page.items
        if item.get("surveyId") is not None
    }
    residue = sorted(returned_multibeam_ids - multibeam_ids)
    if residue:
        raise ValueError(f"multibeam file survey ids escaped frozen denominator: {residue}")

    # Sounding files do not have file-specific geometry. Query one frozen survey
    # at a time so one malformed/legacy survey cannot silently collapse the whole
    # denominator, and preserve each survey's response separately.
    sounding_pages_by_survey: dict[str, tuple[object, ...]] = {}
    for survey_id in sounding_ids:
        sounding_pages_by_survey[survey_id] = fetch_all_ncei_file_pages(
            CatalogFamily.SOUNDING,
            surveys=(survey_id,),
            categories=("Point Data",),
            page_size=200,
        )

    frozen_sounding: dict[str, list[dict[str, object]]] = {}
    sounding_count = 0
    for survey_id, pages in sounding_pages_by_survey.items():
        frozen_sounding[survey_id] = _freeze_pages(
            pages, out, f"ncei_sounding_{survey_id}_point_data"
        )
        sounding_count += sum(len(page.items) for page in pages)

    manifest = {
        "receipt_version": "0.2",
        "source_denominator_artifact_sha256": receipt["source"]["artifact_sha256"],
        "bounded_aoi_wgs84": receipt["source"]["bounded_aoi_wgs84"],
        "file_pages": {
            "ncei_multibeam_all_categories_bbox": _freeze_pages(
                multibeam, out, "ncei_multibeam_bbox"
            ),
            "ncei_sounding_point_data_by_survey": frozen_sounding,
        },
        "counts": {
            "ncei_multibeam_files_all_categories_bbox": sum(
                len(page.items) for page in multibeam
            ),
            "ncei_multibeam_survey_ids_returned": len(returned_multibeam_ids),
            "ncei_sounding_point_data_files": sounding_count,
            "ncei_sounding_surveys_queried": len(sounding_ids),
        },
        "coverage_semantics": {
            "ncei_multibeam": "FILE_LEVEL_BBOX_FILTERED",
            "ncei_sounding": "SURVEY_BOUND_ONLY",
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
