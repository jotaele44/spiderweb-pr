"""Operator entrypoint for the reusable subsurface AOI skill."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from .aoi import freeze_aoi
from .artifacts import export_csv, export_geojson, export_kml, export_kmz, write_manifest
from .dedup import write_dedup_outputs
from .dispatcher import SubsurfaceDispatcher
from .public_exhaustion import current_public_exhaustion_certificate, write_public_exhaustion_certificate
from .relevance import write_relevance_geojson
from .residuals import write_residual_assessment
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
    parser.add_argument("--dedup", action="store_true", help="Build conservative cross-source canonical-asset and identity-edge outputs.")
    parser.add_argument("--relevance", action="store_true", help="Build coarse public-evidence relevance zones; military-family evidence is excluded.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    aoi = freeze_aoi(args.aoi)

    source_runner = None
    exhaustion = None
    if args.run_sources:
        source_runner = AuthoritativeSourceRunner(snapshot_root=out / "sources")
        dispatcher = source_runner.dispatcher()
        outputs = dispatcher.run(aoi, args.families)
        records = [record for family_records in outputs.values() for record in family_records]
        exhaustion = current_public_exhaustion_certificate(
            source_runner.receipts,
            sources=source_runner.sources,
        )
    else:
        dispatcher = SubsurfaceDispatcher()
        records = []
    plan = dispatcher.plan(args.families)

    aoi_path = out / "aoi_frozen.geojson"
    aoi_path.write_text(
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
        write_residual_assessment(out / "public_residual_assessment.json")
    if exhaustion is not None:
        write_public_exhaustion_certificate(out / "public_exhaustion.json", exhaustion)
    evidence_path = export_geojson(out / "evidence.geojson", records)
    export_csv(out / "evidence.csv", records)
    export_kml(out / "evidence.kml", records)
    export_kmz(out / "evidence.kmz", records)

    derived = {}
    if args.dedup:
        asset_path, edge_path = write_dedup_outputs(evidence_path, out / "derived")
        derived["canonical_assets"] = str(asset_path)
        derived["identity_edges"] = str(edge_path)
    if args.relevance:
        relevance_path = write_relevance_geojson(aoi_path, evidence_path, out / "derived" / "relevance_zones.geojson")
        derived["relevance_zones"] = str(relevance_path)

    result = {"aoi": aoi.canonical_sha256, "dispatch": [asdict(t) for t in plan]}
    if source_runner is not None:
        result["family_certification"] = [asdict(row) for row in source_runner.certification()]
    if exhaustion is not None:
        result["public_exhaustion"] = asdict(exhaustion)
    if derived:
        result["derived_outputs"] = derived
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
