#!/usr/bin/env python3
"""
SPIDERWEB
Complete Unified Pipeline — All Phases

Usage:
  python run_all.py                    # Run all phases
  python run_all.py --phase 1          # Run specific phase only
  python run_all.py --images 100       # Test with 100 images
  python run_all.py --report daily     # Generate daily report only
  python run_all.py --aircraft N5854Z  # Profile single aircraft
  python run_all.py --status           # Show database status
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


BANNER = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║          SPIDERWEB                                                            ║
║          Unified Pipeline v1.0                                                ║
║                                                                               ║
║  Phase 0: Image Extraction                                                    ║
║  Phase 1: Telemetry Hardening     (Confidence + Validation)                  ║
║  Phase 2: GIS Intelligence        (Infrastructure + Corridors)               ║
║  Phase 3: Mission Inference       (Scoring + Clustering + Prediction)        ║
║  Phase 4: Operational Platform    (Alerts + Reports)                         ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""


def run_phase_0(args):
    from pipeline.flight_analyzer import FlightAnalyzer
    print("\n  PHASE 0: IMAGE EXTRACTION")
    print("  " + "─" * 50)
    analyzer = FlightAnalyzer(args.image_dir, args.db)
    analyzer.process_all_images(max_images=args.images)
    analyzer.link_screenshots_to_flights()
    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM flights")
    count = cursor.fetchone()[0]
    conn.close()
    print(f"\n  ✓ Phase 0 complete — {count} flights in database")


def run_phase_1(args):
    from pipeline.hardened_pipeline import HardenedFlightAnalyzer
    print("\n  PHASE 1: TELEMETRY HARDENING")
    print("  " + "─" * 50)
    analyzer = HardenedFlightAnalyzer(args.image_dir, args.db)
    analyzer.process_with_hardening(
        batch_id=f"run_{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d_%H%M')}",
        max_images=args.images,
        checkpoint_interval=50,
    )
    print(f"\n  ✓ Phase 1 complete")


def run_phase_2(args):
    from pipeline.gis_intelligence import (
        PuertoRicoInfrastructure, CorridorAnalyzer,
        AnomalyDetector, HeatmapGenerator, Phase2Database,
    )
    import json

    print("\n  PHASE 2: GIS INTELLIGENCE")
    print("  " + "─" * 50)

    infrastructure = PuertoRicoInfrastructure()
    corridor_analyzer = CorridorAnalyzer(infrastructure)
    anomaly_detector = AnomalyDetector(infrastructure)
    heatmap = HeatmapGenerator()
    db = Phase2Database(args.db)

    for feature in infrastructure.features.values():
        db.store_infrastructure(feature)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flights")
    flights = [dict(r) for r in cursor.fetchall()]
    conn.close()

    processed = 0
    for flight in flights:
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM track_points WHERE flight_id = ? ORDER BY timestamp",
            (flight["flight_id"],)
        )
        track = [dict(r) for r in cursor.fetchall()]
        conn.close()

        if not track:
            continue

        corridors = corridor_analyzer.find_corridors_for_flight(track)
        infra_anomalies = anomaly_detector.detect_infrastructure_proximity(track)
        restricted = anomaly_detector.detect_restricted_airspace_entry(track)
        behavioral = anomaly_detector.detect_unusual_patterns(flight)

        all_anomalies = infra_anomalies + restricted + behavioral
        if all_anomalies:
            db.store_anomalies(flight["flight_id"], [
                {"type": a.get("type", "unknown"),
                 "severity": "medium",
                 "description": str(a)}
                for a in all_anomalies
            ])

        heatmap.add_track(track)
        processed += 1

    geojson = heatmap.get_geojson()
    heatmap_path = Path(args.db).parent / "heatmap.geojson"
    with open(heatmap_path, "w") as f:
        json.dump(geojson, f)

    stats = heatmap.get_density_stats()
    print(f"  Infrastructure features loaded: {len(infrastructure.features)}")
    print(f"  Flights processed: {processed}")
    print(f"  Heatmap cells: {stats.get('total_cells', 0)}")
    print(f"  Heatmap exported: {heatmap_path}")
    print(f"\n  ✓ Phase 2 complete")


def run_phase_3(args):
    from pipeline.mission_inference import Phase3Pipeline
    print("\n  PHASE 3: MISSION INFERENCE")
    print("  " + "─" * 50)
    pipeline = Phase3Pipeline(args.db)
    pipeline.run()


def run_phase_4(args):
    from pipeline.operational_intelligence import Phase4Pipeline
    print("\n  PHASE 4: OPERATIONAL INTELLIGENCE")
    print("  " + "─" * 50)
    pipeline = Phase4Pipeline(args.db)
    pipeline.run()


def run_aircraft_profile(args):
    from pipeline.operational_intelligence import ReportGenerator
    from pipeline.aircraft_intelligence import AircraftIntelligence
    print(f"\n  AIRCRAFT PROFILE: {args.aircraft}\n")
    intel = AircraftIntelligence(args.db)
    reporter = ReportGenerator(args.db)
    print(intel.compile_intelligence_report(args.aircraft))
    print(reporter.aircraft_profile_report(args.aircraft))


def run_home_base(args):
    from pipeline.home_base_correlation import HomeBaseDeducer
    print(f"\n  HOME-BASE INTELLIGENCE: {args.home_base}\n")
    print(HomeBaseDeducer(args.db).intelligence_report(args.home_base))


def run_fleet_correlation(args):
    from pipeline.home_base_correlation import FleetColocationAnalyzer
    print("\n  FLEET HOME-BASE CORRELATION\n")
    print(FleetColocationAnalyzer(args.db).correlation_report())


def _run_export_home_base(db_path: str, output_dir: str):
    """Write home_base_report.md, home_base_assignments.csv, shared_space_leads.json."""
    import csv
    import json

    from pipeline.home_base_correlation import (
        FleetColocationAnalyzer,
        HomeBaseDeducer,
        OPERATOR_MISSION,
        OPERATOR_OWNER,
        GENERIC_OPERATORS,
    )

    print("\n  HOME-BASE EXPORT")
    print("  " + "─" * 50)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fleet = FleetColocationAnalyzer(db_path)
    deducer = HomeBaseDeducer(db_path)
    hb = fleet.home_base_map()

    (out / "home_base_report.md").write_text(fleet.correlation_report())

    with open(out / "home_base_assignments.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["callsign", "lat", "lon", "feature_id", "feature_name",
                    "operator", "owner", "mission", "confidence"])
        for cs in sorted(hb):
            spot = hb[cs]
            profile = deducer.deduce_profile(cs)
            op = spot.nearest_operator
            owner = OPERATOR_OWNER.get(op, "" if op in GENERIC_OPERATORS else op)
            w.writerow([cs, spot.lat, spot.lon, spot.nearest_feature_id,
                        spot.nearest_feature_name, op, owner,
                        OPERATOR_MISSION.get(op, ""), profile.confidence_level])

    leads = {fid: cs for fid, cs in fleet.shared_bases().items() if len(cs) >= 2}
    (out / "shared_space_leads.json").write_text(json.dumps(leads, indent=2))

    print(f"  ✓ Home-base outputs written to: {output_dir}")


def run_daily_report(args):
    from pipeline.operational_intelligence import ReportGenerator
    reporter = ReportGenerator(args.db)
    report = reporter.daily_report()
    print(report)
    report_path = Path(args.db).parent / f"daily_report_{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d')}.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\n  Report saved: {report_path}")


def export_json(db_path: str, output_path: str):
    """Dump a DB snapshot to JSON for the dashboard.html viewer."""
    import json

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    def rows(table, order=""):
        try:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} {order} LIMIT 5000")]
        except Exception:
            return []

    try:
        aircraft_profiles_raw = rows("aircraft_profiles")
        if not aircraft_profiles_raw:
            try:
                cur = conn.execute(
                    "SELECT callsign, aircraft_type, operator, mission_type FROM flights GROUP BY callsign"
                )
                aircraft_profiles_raw = [
                    {"callsign": r[0], "aircraft_type": r[1], "operator": r[2],
                     "primary_mission": r[3], "confidence_level": None}
                    for r in cur.fetchall()
                ]
            except Exception:
                aircraft_profiles_raw = []

        data = {
            "exported_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "db_path": db_path,
            "flights": rows("flights", "ORDER BY takeoff_time DESC"),
            "aircraft_profiles": aircraft_profiles_raw,
            "alerts": rows("alerts", "ORDER BY triggered_at DESC"),
            "anomalies": rows("gis_anomalies", "ORDER BY detected_at DESC"),
        }
    finally:
        conn.close()

    with open(output_path, "w") as f:
        json.dump(data, f, default=str)

    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    print(f"\n  Dashboard JSON exported: {output_path}")
    for k, v in counts.items():
        print(f"    {k:<22} {v:>6,} records")


def print_status(db_path: str):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        tables = {
            "flights": "Total flight records",
            "track_points": "Track points",
            "screenshots": "Processed screenshots",
            "alerts": "Total alerts",
            "mission_scores": "Mission scores",
            "cluster_assignments": "Cluster assignments",
        }

        print("\n  DATABASE STATUS")
        print("  " + "─" * 45)

        for table, label in tables.items():
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {label:<30} {count:>8,}")
            except Exception:
                print(f"  {label:<30} {'N/A':>8}")

        try:
            cursor.execute("SELECT AVG(combined_confidence) FROM extraction_confidence")
            avg_conf = cursor.fetchone()[0]
            if avg_conf:
                print(f"  {'Avg extraction confidence':<30} {avg_conf:>8.1%}")
        except Exception:
            pass

        try:
            cursor.execute("SELECT severity, COUNT(*) FROM alerts GROUP BY severity")
            alert_counts = cursor.fetchall()
            if alert_counts:
                print("\n  ALERT BREAKDOWN")
                print("  " + "─" * 45)
                for severity, count in sorted(alert_counts):
                    print(f"  {severity:<30} {count:>8,}")
        except Exception:
            pass

        conn.close()
    except Exception as e:
        print(f"  Database not found or uninitialized: {e}")


def print_rlsm_status(db_path: str):
    """RLSM screenshot-processing status: coverage + low-confidence backlog."""
    try:
        conn = sqlite3.connect(db_path)

        print("\n  RLSM STATUS")
        print("  " + "─" * 45)

        def _count(sql: str):
            try:
                return conn.execute(sql).fetchone()[0]
            except Exception:
                return None

        rows = [
            ("Screenshots processed", _count("SELECT COUNT(*) FROM screenshots")),
            ("Low-confidence (<0.5)",
             _count("SELECT COUNT(*) FROM screenshots WHERE ocr_confidence < 0.5")),
            ("No OCR text",
             _count("SELECT COUNT(*) FROM screenshots WHERE raw_text IS NULL OR raw_text = ''")),
        ]
        for label, val in rows:
            shown = f"{val:,}" if isinstance(val, int) else "N/A"
            print(f"  {label:<30} {shown:>8}")

        conn.close()
    except Exception as e:
        print(f"  Database not found or uninitialized: {e}")


def _run_schema_validation(db_path: str):
    print("\n  SCHEMA VALIDATION")
    print("  " + "─" * 50)
    if not Path(db_path).exists():
        print(f"  Error: database not found: {db_path}")
        print(f"  Hint: run the pipeline first to populate the database")
        sys.exit(1)
    try:
        from integration.schema_validation import SchemaValidator
        validator = SchemaValidator()
        review_path = str(Path(db_path).parent / "review_queue.csv")
        results = validator.run_db_validation(db_path, review_path)
        for schema_name, summary in results.items():
            if schema_name == "_error":
                print(f"  Error: {summary.get('error')}")
                continue
            table = summary.get("table", schema_name)
            total = summary.get("total", 0)
            invalid = summary.get("invalid", 0)
            print(f"  {table:<25} {total:>6} rows  {invalid:>4} invalid")
        if any(s.get("invalid", 0) for k, s in results.items() if k != "_error"):
            print(f"  Invalid records routed to: {review_path}")
        print(f"\n  ✓ Validation complete")
    except Exception as e:
        print(f"  Validation error: {e}")


def _run_export_pr_intel(db_path: str, output_dir: str):
    print("\n  PR INTEL EXPORT")
    print("  " + "─" * 50)
    if not Path(db_path).exists():
        print(f"  Error: database not found: {db_path}")
        print(f"  Hint: run the full pipeline first, then re-run --export-pr-intel")
        sys.exit(1)
    try:
        from integration.pr_intel_adapter import PRIntelAdapter
        adapter = PRIntelAdapter(db_path, output_dir)
        report = adapter.export_all()
        status = report.get("overall_status", "UNKNOWN")
        print(f"  Status: {status}")
        for gate_name, gate in report.get("gates", {}).items():
            marker = {"PASS": "✓", "FAIL": "✗"}.get(gate["status"], "~")
            print(f"  {marker} {gate_name}")
        print(f"\n  ✓ PR Intel exported to: {output_dir}")
    except Exception as e:
        print(f"  Export error: {e}")
        raise


def _run_export_spiderweb(db_path: str, output_dir: str):
    print("\n  SPIDERWEB BRIDGE EXPORT")
    print("  " + "─" * 50)
    try:
        from integration.ilap_airspace_bridge import ILAPAirspaceBridge
        from integration.aasb_airspace_bridge import AASBAirspaceBridge
        ILAPAirspaceBridge(db_path, output_dir).export_all()
        AASBAirspaceBridge(db_path, output_dir).export_all()
        print(f"\n  ✓ Spiderweb exported to: {output_dir}")
    except Exception as e:
        print(f"  Export error: {e}")
        raise


def _run_headstart_export(csv_path: str, output_dir: str, grid_only: bool = False):
    print("\n  HEAD START CIVIC LAYER EXPORT")
    print("  " + "─" * 50)
    if not Path(csv_path).exists():
        print(f"  Error: Head Start CSV not found: {csv_path}")
        sys.exit(1)
    try:
        from spiderweb.exports.headstart_context_grid import export_context_grid
        from spiderweb.ingestors.ingest_headstart import export_headstart

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        grid_summary = export_context_grid(csv_path, out / "headstart_context_grid.geojson")
        if grid_only:
            print(f"  Public grid cells: {grid_summary['grid_cells']}")
            print(f"\n  ✓ Public grid export written to: {grid_summary['output_path']}")
            return
        summary = export_headstart(csv_path, out)
        print(f"  Records:          {summary['records']}")
        print(f"  Operators:        {summary['operators']}")
        print(f"  Edges:            {summary['edges']}")
        print(f"  Public grid cells: {grid_summary['grid_cells']}")
        print("  Policy: precise points restricted; public output is grid-only")
        print(f"\n  ✓ Head Start civic layer exported to: {output_dir}")
    except Exception as e:
        print(f"  Head Start export error: {e}")
        raise


def _run_spiderweb_intake(intake_dir: str):
    print("\n  SPIDERWEB INTAKE — OVERLAY + GAP AUDIT")
    print("  " + "─" * 50)
    if not Path(intake_dir).exists():
        print(f"  Error: directory not found: {intake_dir}")
        sys.exit(1)
    try:
        from readiness.spiderweb_intake import SpiderwebIntake
        result = SpiderwebIntake(intake_dir, intake_dir).run()
        audit = result["gap_audit"]["gaps"]
        print(f"  Candidates normalized: {result['total_candidates']}")
        print(f"  Duplicates removed:    {audit['dedup_gap']['duplicates_removed']}")
        print(f"  Missing bridge files:  {audit['export_gap']['missing_files'] or 'none'}")
        print(f"  Evidence gaps:         {audit['evidence_gap']['no_hydro_or_utility']}")
        print(f"\n  ✓ Overlay written to: {intake_dir}/spiderweb_overlay_candidates.geojson")
        print(f"  ✓ Gap audit written to: {intake_dir}/spiderweb_gap_audit.json")
    except Exception as e:
        print(f"  Intake error: {e}")
        raise


def _run_calibrate_scoring(calibrate_dir: str):
    print("\n  SPIDERWEB SCORING CALIBRATION")
    print("  " + "─" * 50)
    d = Path(calibrate_dir)
    if not d.exists():
        print(f"  Error: directory not found: {calibrate_dir}")
        sys.exit(1)
    overlay = d / "spiderweb_overlay_candidates.geojson"
    if not overlay.exists():
        print(f"  Error: overlay not found in {calibrate_dir}")
        print(f"  Hint: run --spiderweb-intake {calibrate_dir} first")
        sys.exit(1)
    try:
        from readiness.calibrate_scoring import CalibrationDriver
        report = CalibrationDriver(calibrate_dir).run()
        flags = report.get("calibration_flags", [])
        print(f"  Mode:                  {report.get('baseline_mode', '?')}")
        print(f"  Status:                {report.get('status', '?')}")
        print(f"  Candidates audited:    {report['candidate_count']}")
        print(f"  Calibration flags:     {len(flags)}")
        for f in flags:
            bound = f.get("expected_max") or f.get("expected_min")
            label = "max" if "expected_max" in f else "min"
            print(f"    [{f['metric']}] value={f['value']} (expected_{label}={bound}) → {f['action']}")
        print(f"\n  ✓ Calibration report written to: {calibrate_dir}/calibration_report.json")
    except Exception as e:
        print(f"  Calibration error: {e}")
        raise


def _run_assess_readiness(export_dir: str):
    print("\n  PRII READINESS ASSESSMENT")
    print("  " + "─" * 50)
    d = Path(export_dir)
    if not d.exists():
        print(f"  Error: directory not found: {export_dir}")
        print(f"  Hint: run --export-pr-intel and --calibrate-scoring first")
        sys.exit(1)
    try:
        from readiness.prii_readiness_engine import PRIIReadinessEngine
        report = PRIIReadinessEngine(export_dir).assess()
        status = report.get("readiness_status", "UNKNOWN")
        marker = "✓" if status == "READY" else ("~" if status == "DEGRADED" else "✗")
        print(f"  {marker} Status: {status}")
        for b in report.get("blockers", []):
            src = b.get("source", "")
            key = b.get("gate") or b.get("flag") or ""
            print(f"  ✗ BLOCKER [{src}:{key}] {b.get('detail', '')}")
        for w in report.get("warnings", []):
            print(f"  ~ WARNING [{w.get('source')}] {w.get('detail')}")
        if report.get("missing_inputs"):
            print(f"  Missing inputs: {', '.join(report['missing_inputs'])}")
        print(f"\n  ✓ Readiness report written to: {export_dir}/prii_readiness_report.json")
        if status == "NOT_READY":
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"  Assessment error: {e}")
        raise


def _run_ingest_satellite(manifest_path: str, dry_run: bool = False):
    print("\n  SATELLITE MANIFEST INGEST")
    print("  " + "─" * 50)
    from readiness.satellite_ingest import ingest_from_cli
    rc = ingest_from_cli(manifest_path, dry_run=dry_run)
    if rc != 0:
        sys.exit(rc)


def _run_release_check(args):
    print("\n  RELEASE GATE")
    print("  " + "─" * 50)
    from release_check import ReleaseCheck
    from run_modes import resolve_mode
    mode = resolve_mode(args).mode
    out_dir = args.release_output_dir or str(Path(args.db).parent / "release")
    command = " ".join(["python", "run_all.py"] + sys.argv[1:])
    report = ReleaseCheck(args.db, out_dir, mode, command=command).run()
    markers = {"PASS": "✓", "FAIL": "✗", "WARNING": "~", "SKIPPED": "·"}
    for stage in ("syntax_check", "core_tests", "validate",
                  "export_pr_intel", "export_spiderweb", "earthgpt_selftest"):
        st = report.get(stage, {}).get("status", "?")
        print(f"  {markers.get(st, '?')} {stage:<20} {st}")
    overall = report["overall_status"]
    print(f"\n  {markers.get(overall, '?')} Overall: {overall}")
    if report.get("failure_reasons"):
        print(f"  Failures: {', '.join(report['failure_reasons'])}")
    print(f"  ✓ Release report: {report['_report_path']}")
    if overall != "PASS":
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Spiderweb — Unified Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all.py                              Run complete pipeline
  python run_all.py --phase 1                    Hardening only
  python run_all.py --phase 3                    Mission inference only
  python run_all.py --images 50                  Test with 50 images
  python run_all.py --report daily               Daily operational report
  python run_all.py --aircraft N5854Z            Aircraft intelligence profile
  python run_all.py --status                     Show database status
  python run_all.py --export-json data.json      Export DB snapshot for dashboard
        """
    )
    parser.add_argument("--phase", type=int, choices=[0, 1, 2, 3, 4],
                        help="Run only specified phase (0-4)")
    parser.add_argument("--images", type=int, default=None,
                        help="Max images to process (default: all)")
    parser.add_argument("--image-dir", dest="image_dir",
                        default="/mnt/user-data/uploads",
                        help="Directory containing screenshots")
    parser.add_argument("--db", default=str(Path.home() / "flight_database.db"),
                        help="Database path")
    parser.add_argument("--report", choices=["daily", "infrastructure", "all"],
                        help="Generate report only")
    parser.add_argument("--aircraft", type=str,
                        help="Generate intelligence profile for callsign")
    parser.add_argument("--home-base", dest="home_base", metavar="CALLSIGN",
                        help="Deduce operator/owner/mission from a craft's home base")
    parser.add_argument("--fleet-correlation", action="store_true",
                        help="Cross-craft home-base correlation and shared-space leads")
    parser.add_argument("--export-home-base", metavar="DIR",
                        help="Export home-base report + assignments CSV + shared-space leads JSON")
    parser.add_argument("--status", action="store_true",
                        help="Show database status and exit")
    parser.add_argument("--rlsm-status", dest="rlsm_status", action="store_true",
                        help="Show RLSM screenshot processing status and exit")
    parser.add_argument("--export-json", metavar="PATH",
                        help="Export DB snapshot to JSON for dashboard.html")
    parser.add_argument("--validate", action="store_true",
                        help="Run schema validation after pipeline")
    parser.add_argument("--export-pr-intel", metavar="DIR",
                        help="Export PR Intel parquet/GeoJSON to DIR")
    parser.add_argument("--export-spiderweb", metavar="DIR",
                        help="Export Spiderweb bridge outputs to DIR")
    parser.add_argument("--headstart-csv", metavar="PATH",
                        help="Ingest Head Start PR CSV and export civic layer artifacts")
    parser.add_argument("--export-headstart", metavar="DIR",
                        help="Directory for Head Start civic layer exports")
    parser.add_argument("--headstart-grid-only", action="store_true",
                        help="With --headstart-csv/--export-headstart: write public grid only")
    parser.add_argument("--spiderweb-intake", metavar="DIR",
                        help="Normalize --export-spiderweb output into Spiderweb overlay candidates")
    parser.add_argument("--calibrate-scoring", metavar="DIR",
                        help="Audit spiderweb overlay candidates against operational baseline ranges")
    parser.add_argument("--assess-readiness", metavar="DIR",
                        help="Assess PRII readiness from integration_report + calibration_report in DIR")
    parser.add_argument("--ingest-satellite", metavar="MANIFEST",
                        help="Validate and ingest a satellite source manifest JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --ingest-satellite: validate only, do not write to disk")
    parser.add_argument("--release-check", action="store_true",
                        help="Run the full release gate and write release_report.json")
    parser.add_argument("--release-output-dir", metavar="DIR", default=None,
                        help="Where to write release_report.json (default: <db_dir>/release)")
    parser.add_argument("--strict-production", action="store_true",
                        help="Strict mode: missing/empty production inputs fail hard (exit 2)")
    parser.add_argument("--demo", action="store_true",
                        help="Demo mode: stamp outputs with mode=demo and [DEMO] banners")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose logging (DEBUG level)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Quiet logging (WARNING level and above)")
    parser.add_argument("--log-json", action="store_true",
                        help="Emit structured JSON log lines")

    args = parser.parse_args()

    # Central logging setup (T10-80/82): --verbose/-quiet pick the level.
    import logging as _logging
    from pipeline.logging_config import configure_logging
    from pipeline.verbosity import resolve_log_level

    configure_logging(
        level=resolve_log_level(verbose=args.verbose, quiet=args.quiet,
                                default=_logging.INFO),
        json_format=args.log_json,
    )

    print(BANNER)
    print(f"  Database:   {args.db}")
    print(f"  Image dir:  {args.image_dir}")
    print(f"  Max images: {args.images or 'All'}")
    print(f"  Started:    {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}\n")

    if args.status:
        print_status(args.db)
        return

    if args.rlsm_status:
        print_rlsm_status(args.db)
        return

    if args.export_json:
        export_json(args.db, args.export_json)
        return

    if args.report:
        if args.report in ("daily", "all"):
            run_daily_report(args)
        return

    if args.aircraft:
        run_aircraft_profile(args)
        return

    if args.home_base:
        run_home_base(args)
        return

    if args.fleet_correlation:
        run_fleet_correlation(args)
        return

    if args.export_home_base:
        _run_export_home_base(args.db, args.export_home_base)
        return

    if args.headstart_csv or args.export_headstart:
        if not (args.headstart_csv and args.export_headstart):
            print("  Error: --headstart-csv and --export-headstart must be supplied together")
            sys.exit(1)
        _run_headstart_export(args.headstart_csv, args.export_headstart, args.headstart_grid_only)
        return

    # Determine whether to run the main pipeline phases.
    # Skip phases when the user only supplied integration-export flags
    # (standalone export mode against an existing DB).
    new_flags_only = (
        not args.images
        and args.phase is None
        and (args.validate or args.export_pr_intel or args.export_spiderweb
             or args.spiderweb_intake or args.calibrate_scoring
             or args.assess_readiness or args.ingest_satellite
             or args.release_check)
    )

    if not new_flags_only:
        start = datetime.now(timezone.utc).replace(tzinfo=None)

        if args.phase is None or args.phase == 0:
            run_phase_0(args)

        if args.phase is None or args.phase == 1:
            run_phase_1(args)

        if args.phase is None or args.phase == 2:
            run_phase_2(args)

        if args.phase is None or args.phase == 3:
            run_phase_3(args)

        if args.phase is None or args.phase == 4:
            run_phase_4(args)

        elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - start).total_seconds()
        print("\n" + "═" * 70)
        print(f"  PIPELINE COMPLETE")
        print(f"  Elapsed: {elapsed:.0f}s ({elapsed/3600:.2f}h)")
        print(f"  Database: {args.db}")
        print("═" * 70)
        print_status(args.db)

    # Integration hardening exports — run after pipeline (or standalone).
    if args.validate:
        _run_schema_validation(args.db)

    if args.export_pr_intel:
        _run_export_pr_intel(args.db, args.export_pr_intel)

    if args.export_spiderweb:
        _run_export_spiderweb(args.db, args.export_spiderweb)

    if args.spiderweb_intake:
        _run_spiderweb_intake(args.spiderweb_intake)

    if args.calibrate_scoring:
        _run_calibrate_scoring(args.calibrate_scoring)

    if args.assess_readiness:
        _run_assess_readiness(args.assess_readiness)

    if args.ingest_satellite:
        _run_ingest_satellite(args.ingest_satellite, getattr(args, "dry_run", False))

    if args.release_check:
        _run_release_check(args)


if __name__ == "__main__":
    main()
