"""Operator entrypoint for the reusable subsurface AOI skill."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from .aoi import freeze_aoi
from .artifacts import export_csv, export_geojson, export_kml, export_kmz, write_manifest
from .dispatcher import SubsurfaceDispatcher
from .runner import AuthoritativeSourceRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spiderweb-subsurface",
        description="Freeze a KML/KMZ/GeoJSON AOI and optionally run the authoritative public-source denominator.",
    )
    parser.add_argument("aoi", help="AOI path (.kml, .kmz, .geojson, .json)")
    parser.add_argument("--out", default="subsurface_run", help="Output directory")
    parser.add_argument("--family", action="append", dest="families", help="Restrict dispatch to one layer family; repeatable")
    parser.add_argument(
        "--run-sources", action="store_true",
        help="Execute registered public-source adapters. Without this flag, only freeze/plan artifacts are produced.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    aoi = freeze_aoi(args.aoi)

    source_runner = None
    if args.run_sources:
        source_runner = AuthoritativeSourceRunner(snapshot_root=out / "sources")
        dispatcher = source_runner.dispatcher()
        outputs = dispatcher.run(aoi, args.families)
        records = [record for family_records in outputs.values() for record in family_records]
    else:
        dispatcher = SubsurfaceDispatcher()
        records = []
    plan = dispatcher.plan(args.families)

    (out / "aoi_frozen.geojson").write_text(
        json.dumps({
            "type": "Feature",
            "geometry": aoi.canonical_geojson,
            "properties": {
                "canonical_sha256": aoi.canonical_sha256,
                "source_sha256": aoi.source_sha256,
                "source_crs": aoi.source_crs,
            },
        }, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_manifest(
        out / "manifest.json", aoi=aoi, records=records,
        dispatch_plan=[asdict(task) for task in plan],
        source_manifest=[] if source_runner is None else [asdict(row) for row in source_runner.ledger()],
    )
    if source_runner is not None:
        source_runner.write_control_manifest(out / "source_control.json")
    export_csv(out / "evidence.csv", records)
    export_geojson(out / "evidence.geojson", records)
    export_kml(out / "evidence.kml", records)
    export_kmz(out / "evidence.kmz", records)

    result = {"aoi": aoi.canonical_sha256, "dispatch": [asdict(t) for t in plan]}
    if source_runner is not None:
        result["family_certification"] = [asdict(row) for row in source_runner.certification()]
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
