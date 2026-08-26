"""CLI for the NCEI Coastal DEM adapter.

`discover` is metadata-only by default. `fetch` requires an explicit dataset id and
an acknowledgment that raw DEM files must remain local/uncommitted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .coverage import build_coverage_report
from .fetch_plan import DEFAULT_CACHE_DIR, build_fetch_plan, cache_name_for
from .provenance import acquisition_context_leads, build_source_manifest
from .registry import (
    DEFAULT_REGISTRY_PATH,
    load_registry,
    require_single_dataset,
    select_datasets,
)

USER_AGENT = "spiderweb-pr-ncei-coastal-dem-adapter/1.0"
DEFAULT_LIVE_CATALOG_URL = (
    "https://www.ngdc.noaa.gov/thredds/catalog/regional/catalog.html"
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(body, encoding="utf-8")


def _fetch_live_catalog_metadata(
    urls: list[str], timeout: int
) -> list[dict[str, object]]:
    catalogs: list[dict[str, object]] = []
    for url in urls:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=timeout) as response:  # noqa: S310
                text = response.read().decode("utf-8", errors="replace")
                catalogs.append(
                    {
                        "url": url,
                        "http_status": getattr(response, "status", ""),
                        "content_type": response.headers.get("Content-Type", ""),
                        "bytes": len(text.encode("utf-8")),
                        "dataset_id_hits": [],
                        "review_status": "metadata_catalog_fetched",
                    }
                )
        except (HTTPError, URLError, TimeoutError) as exc:
            catalogs.append(
                {
                    "url": url,
                    "http_status": getattr(exc, "code", ""),
                    "content_type": "",
                    "bytes": 0,
                    "dataset_id_hits": [],
                    "review_status": "metadata_catalog_failed",
                    "error": str(exc),
                }
            )
    return catalogs


def discover(args: argparse.Namespace) -> int:
    records = load_registry(Path(args.registry))
    selected = select_datasets(records, aoi=args.aoi, priority=args.priority)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    fetch_plan = build_fetch_plan(
        selected,
        aoi=args.aoi,
        priority=args.priority,
        metadata_only=True,
        cache_dir=args.cache_dir,
    )
    coverage_report = build_coverage_report(selected, aoi=args.aoi)
    source_manifest = build_source_manifest(selected)
    review_summary = {
        "adapter": "ncei_coastal_dem",
        "metadata_only": True,
        "live_catalogs_requested": bool(args.include_live_catalogs),
        "static_registry_included": bool(args.include_static_registry),
        "acquisition_context_included": bool(args.include_acquisition_context_leads),
        "selected_count": len(selected),
        "guardrails": [
            "discover never downloads raw DEM rasters",
            "fetch requires an explicit dataset id",
            "fetch requires --acknowledge-no-commit",
            "procurement award references are non-authoritative context leads",
        ],
    }

    write_json(out / "fetch_plan.json", fetch_plan)
    write_json(out / "coverage_report.json", coverage_report)
    write_json(out / "source_manifest.json", source_manifest)
    if args.include_live_catalogs:
        catalog_rows = _fetch_live_catalog_metadata(
            args.live_catalog_url, args.timeout
        )
        dataset_ids = [record.dataset_id for record in selected]
        for row in catalog_rows:
            url = str(row.get("url", ""))
            row["dataset_id_hits"] = [
                dataset_id for dataset_id in dataset_ids if dataset_id in url
            ]
        write_json(out / "ncei_catalog_inventory.json", catalog_rows)
    write_json(out / "source_review_summary.json", review_summary)
    if args.include_acquisition_context_leads:
        write_json(out / "acquisition_context_leads.json", acquisition_context_leads())
    print(json.dumps(review_summary, indent=2, sort_keys=True))
    return 0


def fetch(args: argparse.Namespace) -> int:
    if not args.dataset:
        raise SystemExit("fetch requires --dataset")
    if not args.acknowledge_no_commit:
        raise SystemExit("fetch requires --acknowledge-no-commit")

    records = load_registry(Path(args.registry))
    record = require_single_dataset(records, args.dataset)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / cache_name_for(record)

    req = Request(record.source_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=args.timeout) as response:  # noqa: S310
            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
            status = getattr(response, "status", "")
    except (HTTPError, URLError, TimeoutError) as exc:
        write_json(
            Path(args.out),
            {
                "dataset_id": record.dataset_id,
                "source_url": record.source_url,
                "local_cache_path": str(target),
                "status": "failed",
                "error": str(exc),
            },
        )
        return 1

    target.write_bytes(payload)
    manifest = build_source_manifest((record,), local_cache_root=cache_dir)
    manifest["fetch_result"] = {
        "dataset_id": record.dataset_id,
        "source_url": record.source_url,
        "local_cache_path": str(target),
        "http_status": status,
        "content_type": content_type,
        "bytes": len(payload),
        "raw_commit_allowed": False,
        "review_status": "downloaded_local",
    }
    write_json(Path(args.out), manifest)
    print(json.dumps(manifest["fetch_result"], indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NCEI Coastal DEM metadata adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser(
        "discover",
        help="Review all known metadata without raw DEM downloads",
    )
    discover_parser.add_argument("--aoi", default="puerto_rico")
    discover_parser.add_argument("--priority", default=None)
    discover_parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    discover_parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    discover_parser.add_argument(
        "--out",
        default="outputs/ncei_coastal_dem/review_bundle",
    )
    discover_parser.add_argument(
        "--include-static-registry",
        action="store_true",
        default=True,
    )
    discover_parser.add_argument("--include-live-catalogs", action="store_true")
    discover_parser.add_argument(
        "--live-catalog-url",
        action="append",
        default=[DEFAULT_LIVE_CATALOG_URL],
    )
    discover_parser.add_argument("--timeout", type=int, default=60)
    discover_parser.add_argument(
        "--include-acquisition-context-leads",
        action="store_true",
    )
    discover_parser.add_argument("--metadata-only", action="store_true", default=True)
    discover_parser.set_defaults(func=discover)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch one explicit DEM source into local ignored cache",
    )
    fetch_parser.add_argument("--dataset", required=True)
    fetch_parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    fetch_parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    fetch_parser.add_argument(
        "--out",
        default="outputs/ncei_coastal_dem/fetch_result.json",
    )
    fetch_parser.add_argument("--timeout", type=int, default=120)
    fetch_parser.add_argument(
        "--acknowledge-no-commit",
        action="store_true",
        required=True,
    )
    fetch_parser.set_defaults(func=fetch)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
