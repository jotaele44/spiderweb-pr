"""Operator entrypoint for the reusable subsurface AOI skill."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .aoi import freeze_aoi
from .artifacts import export_csv, export_geojson, export_kml, export_kmz, write_manifest
from .dispatcher import SubsurfaceDispatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spiderweb-subsurface",
        description="Freeze a KML/KMZ/GeoJSON AOI and build a subsurface dispatch receipt.",
    )
    parser.add_argument("aoi", help="AOI path (.kml, .kmz, .geojson, .json)")
    parser.add_argument("--out", default="subsurface_run", help="Output directory")
    parser.add_argument(
        "--family",
        action="append",
        dest="families",
        help="Restrict dispatch to one layer family; repeatable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    aoi = freeze_aoi(args.aoi)
    dispatcher = SubsurfaceDispatcher()
    plan = dispatcher.plan(args.families)
    records = []

    (out / "aoi_frozen.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "geometry": aoi.canonical_geojson,
                "properties": {
                    "canonical_sha256": aoi.canonical_sha256,
                    "source_sha256": aoi.source_sha256,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    write_manifest(
        out / "manifest.json",
        aoi=aoi,
        records=records,
        dispatch_plan=[asdict(task) for task in plan],
    )
    export_csv(out / "evidence.csv", records)
    export_geojson(out / "evidence.geojson", records)
    export_kml(out / "evidence.kml", records)
    export_kmz(out / "evidence.kmz", records)

    print(json.dumps({"aoi": aoi.canonical_sha256, "dispatch": [asdict(t) for t in plan]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
