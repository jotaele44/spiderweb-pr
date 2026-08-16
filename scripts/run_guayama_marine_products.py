#!/usr/bin/env python3
"""Probe file-level NCEI products for the frozen Guayama survey denominator.

A source/API failure is preserved as BLOCKED residue rather than converted to a
zero-result response.  The script finishes the entire bounded denominator so a
single legacy survey cannot suppress later probes.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError

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


def _failure(exc: Exception) -> dict[str, object]:
    record: dict[str, object] = {
        "exception_type": type(exc).__name__,
        "message": str(exc),
    }
    if isinstance(exc, HTTPError):
        record["http_status"] = exc.code
        record["request_url"] = exc.geturl()
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - diagnostic only
            body = b""
        record["response_body_preview"] = body[:1000].decode("utf-8", "replace")
    elif isinstance(exc, URLError):
        record["reason"] = str(exc.reason)
    return record


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

    multibeam_pages_by_survey: dict[str, tuple[object, ...]] = {}
    sounding_pages_by_survey: dict[str, tuple[object, ...]] = {}
    multibeam_failures: dict[str, dict[str, object]] = {}
    sounding_failures: dict[str, dict[str, object]] = {}
    multibeam_selected: list[dict[str, object]] = []
    multibeam_unresolved_geometry: list[dict[str, object]] = []
    sounding_selected: list[dict[str, object]] = []

    # NCEI's documented file endpoint has returned HTTP 500 in preceding live
    # attempts. Probe all 13 frozen multibeam surveys independently and preserve
    # every successful response or exact failure. No failed probe becomes zero.
    for survey_id in multibeam_ids:
        try:
            pages = fetch_all_ncei_file_pages(
                CatalogFamily.MULTIBEAM,
                surveys=(survey_id,),
                page_size=200,
            )
        except Exception as exc:  # bounded source transport/schema residue
            multibeam_failures[survey_id] = _failure(exc)
            continue
        multibeam_pages_by_survey[survey_id] = pages
        for page in pages:
            for item in page.items:
                envelope = _geometry_envelope(item.get("geometry"))
                row = dict(item)
                if envelope is None:
                    multibeam_unresolved_geometry.append(row)
                elif _intersects(envelope, bbox):
                    multibeam_selected.append(row)

    # Sounding file rows have no file-specific geometry. Probe all 29 frozen
    # surveys separately and select Point Data only from successful responses.
    for survey_id in sounding_ids:
        try:
            pages = fetch_all_ncei_file_pages(
                CatalogFamily.SOUNDING,
                surveys=(survey_id,),
                page_size=200,
            )
        except Exception as exc:
            sounding_failures[survey_id] = _failure(exc)
            continue
        sounding_pages_by_survey[survey_id] = pages
        for page in pages:
            for item in page.items:
                if item.get("category") == "Point Data":
                    sounding_selected.append(dict(item))

    frozen_multibeam = {
        survey_id: _freeze_pages(pages, out, f"ncei_multibeam_{survey_id}_all")
        for survey_id, pages in multibeam_pages_by_survey.items()
    }
    frozen_sounding = {
        survey_id: _freeze_pages(pages, out, f"ncei_sounding_{survey_id}_all")
        for survey_id, pages in sounding_pages_by_survey.items()
    }

    unresolved = bool(
        multibeam_failures
        or sounding_failures
        or multibeam_unresolved_geometry
    )
    state = "BLOCKED" if unresolved else "PASS"
    manifest = {
        "receipt_version": "0.2",
        "state": state,
        "source_denominator_artifact_sha256": receipt["source"]["artifact_sha256"],
        "bounded_aoi_wgs84": receipt["source"]["bounded_aoi_wgs84"],
        "file_pages": {
            "ncei_multibeam_all_categories_by_survey": frozen_multibeam,
            "ncei_sounding_all_categories_by_survey": frozen_sounding,
        },
        "failures": {
            "ncei_multibeam_by_survey": multibeam_failures,
            "ncei_sounding_by_survey": sounding_failures,
        },
        "counts": {
            "ncei_multibeam_surveys_in_denominator": len(multibeam_ids),
            "ncei_multibeam_surveys_successful": len(multibeam_pages_by_survey),
            "ncei_multibeam_surveys_failed": len(multibeam_failures),
            "ncei_multibeam_files_intersecting_bbox": len(multibeam_selected),
            "ncei_multibeam_files_unresolved_geometry": len(multibeam_unresolved_geometry),
            "ncei_sounding_surveys_in_denominator": len(sounding_ids),
            "ncei_sounding_surveys_successful": len(sounding_pages_by_survey),
            "ncei_sounding_surveys_failed": len(sounding_failures),
            "ncei_sounding_point_data_files": len(sounding_selected),
        },
        "selected": {
            "ncei_multibeam_bbox_intersections": multibeam_selected,
            "ncei_multibeam_unresolved_geometry": multibeam_unresolved_geometry,
            "ncei_sounding_point_data": sounding_selected,
        },
        "coverage_semantics": {
            "ncei_multibeam": "LOCAL_FILE_GEOMETRY_BBOX_FILTERED_WHEN_RESPONSE_AVAILABLE",
            "ncei_sounding": "SURVEY_BOUND_ONLY_WHEN_RESPONSE_AVAILABLE",
        },
        "transport_note": (
            "Documented NCEI file endpoints are probed across the complete frozen survey denominator. "
            "HTTP/schema failures are retained as unresolved residue and never interpreted as zero files."
        ),
        "certification_boundary": (
            "A PASS means the bounded file-metadata probe closed without source/API or geometry residue. "
            "A BLOCKED state is an execution receipt, not product-coverage certification. No file is promoted "
            "to a direct observation until bytes, format, datum and lineage are frozen."
        ),
    }
    (out / "product_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    # Exit success because the bounded probe itself completed and explicitly
    # reports domain state. Downstream certification must require state == PASS.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
