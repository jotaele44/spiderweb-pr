#!/usr/bin/env python3
"""Enumerate file-level NCEI products for the frozen Guayama survey denominator."""

from __future__ import annotations

import argparse
import json
import re
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


def _geometry_envelope(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    numbers = [float(v) for v in re.findall(r"[-+]?\d+(?:\.\d+)?", value)]
    if len(numbers) < 4 or len(numbers) % 2:
        return None
    lons = numbers[0::2]
    lats = numbers[1::2]
    if not lons or not lats:
        return None
    return min(lons), min(lats), max(lons), max(lats)


def _intersects(a: tuple[float, float, float, float], bbox: BoundingBox) -> bool:
    min_lon, min_lat, max_lon, max_lat = a
    return not (
        max_lon < bbox.min_lon
        or min_lon > bbox.max_lon
        or max_lat < bbox.min_lat
        or min_lat > bbox.max_lat
    )


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
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # The live NCEI service currently returns HTTP 500 for the documented
    # multibeam file geometry query in this AOI. Reuse the already-passed survey
    # denominator and query each survey separately, then intersect file geometry
    # locally. The raw service responses are still frozen before filtering.
    multibeam_pages_by_survey: dict[str, tuple[object, ...]] = {}
    multibeam_selected: list[dict[str, object]] = []
    multibeam_unresolved_geometry: list[dict[str, object]] = []
    for survey_id in multibeam_ids:
        pages = fetch_all_ncei_file_pages(
            CatalogFamily.MULTIBEAM,
            surveys=(survey_id,),
            page_size=200,
        )
        multibeam_pages_by_survey[survey_id] = pages
        for page in pages:
            for item in page.items:
                envelope = _geometry_envelope(item.get("geometry"))
                row = dict(item)
                if envelope is None:
                    multibeam_unresolved_geometry.append(row)
                elif _intersects(envelope, bbox):
                    multibeam_selected.append(row)

    # Sounding file rows have no file-specific geometry. Query each frozen survey
    # separately and preserve all rows; the selected point-data rows remain
    # SURVEY_BOUND_ONLY rather than file-level AOI-certified.
    sounding_pages_by_survey: dict[str, tuple[object, ...]] = {}
    sounding_selected: list[dict[str, object]] = []
    for survey_id in sounding_ids:
        pages = fetch_all_ncei_file_pages(
            CatalogFamily.SOUNDING,
            surveys=(survey_id,),
            page_size=200,
        )
        sounding_pages_by_survey[survey_id] = pages
        for page in pages:
            for item in page.items:
                if item.get("category") == "Point Data":
                    sounding_selected.append(dict(item))

    frozen_multibeam: dict[str, list[dict[str, object]]] = {}
    for survey_id, pages in multibeam_pages_by_survey.items():
        frozen_multibeam[survey_id] = _freeze_pages(
            pages, out, f"ncei_multibeam_{survey_id}_all"
        )

    frozen_sounding: dict[str, list[dict[str, object]]] = {}
    for survey_id, pages in sounding_pages_by_survey.items():
        frozen_sounding[survey_id] = _freeze_pages(
            pages, out, f"ncei_sounding_{survey_id}_all"
        )

    manifest = {
        "receipt_version": "0.2",
        "source_denominator_artifact_sha256": receipt["source"]["artifact_sha256"],
        "bounded_aoi_wgs84": receipt["source"]["bounded_aoi_wgs84"],
        "file_pages": {
            "ncei_multibeam_all_categories_by_survey": frozen_multibeam,
            "ncei_sounding_all_categories_by_survey": frozen_sounding,
        },
        "counts": {
            "ncei_multibeam_surveys_queried": len(multibeam_ids),
            "ncei_multibeam_files_intersecting_bbox": len(multibeam_selected),
            "ncei_multibeam_files_unresolved_geometry": len(multibeam_unresolved_geometry),
            "ncei_sounding_surveys_queried": len(sounding_ids),
            "ncei_sounding_point_data_files": len(sounding_selected),
        },
        "selected": {
            "ncei_multibeam_bbox_intersections": multibeam_selected,
            "ncei_multibeam_unresolved_geometry": multibeam_unresolved_geometry,
            "ncei_sounding_point_data": sounding_selected,
        },
        "coverage_semantics": {
            "ncei_multibeam": "LOCAL_FILE_GEOMETRY_BBOX_FILTERED",
            "ncei_sounding": "SURVEY_BOUND_ONLY",
        },
        "transport_note": (
            "The documented multibeam file geometry endpoint returned HTTP 500 in this bounded run; "
            "the pipeline reused the frozen survey denominator, queried files per survey, preserved raw responses, "
            "and applied the AOI envelope intersection locally."
        ),
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
