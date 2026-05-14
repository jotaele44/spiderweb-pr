#!/usr/bin/env python3
"""
PUERTO RICO AIRSPACE INTELLIGENCE SYSTEM
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
from datetime import datetime
from pathlib import Path


BANNER = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║          PUERTO RICO AIRSPACE INTELLIGENCE SYSTEM                             ║
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
    from flight_analyzer import FlightAnalyzer
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
    from hardened_pipeline import HardenedFlightAnalyzer
    print("\n  PHASE 1: TELEMETRY HARDENING")
    print("  " + "─" * 50)
    analyzer = HardenedFlightAnalyzer(args.image_dir, args.db)
    analyzer.process_with_hardening(
        batch_id=f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M')}",
        max_images=args.images,
        checkpoint_interval=50,
    )
    print(f"\n  ✓ Phase 1 complete")


def run_phase_2(args):
    from gis_intelligence import (
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
    from mission_inference import Phase3Pipeline
    print("\n  PHASE 3: MISSION INFERENCE")
    print("  " + "─" * 50)
    pipeline = Phase3Pipeline(args.db)
    pipeline.run()


def run_phase_4(args):
    from operational_intelligence import Phase4Pipeline
    print("\n  PHASE 4: OPERATIONAL INTELLIGENCE")
    print("  " + "─" * 50)
    pipeline = Phase4Pipeline(args.db)
    pipeline.run()


def run_aircraft_profile(args):
    from operational_intelligence import ReportGenerator
    from aircraft_intelligence import AircraftIntelligence
    print(f"\n  AIRCRAFT PROFILE: {args.aircraft}\n")
    intel = AircraftIntelligence(args.db)
    reporter = ReportGenerator(args.db)
    print(intel.compile_intelligence_report(args.aircraft))
    print(reporter.aircraft_profile_report(args.aircraft))


def run_daily_report(args):
    from operational_intelligence import ReportGenerator
    reporter = ReportGenerator(args.db)
    report = reporter.daily_report()
    print(report)
    report_path = Path(args.db).parent / f"daily_report_{datetime.utcnow().strftime('%Y%m%d')}.txt"
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
            "exported_at": datetime.utcnow().isoformat() + "Z",
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


def _run_schema_validation(db_path: str):
    print("\n  SCHEMA VALIDATION")
    print("  " + "─" * 50)
    try:
        from schema_validation import SchemaValidator
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
    try:
        from pr_intel_adapter import PRIntelAdapter
        adapter = PRIntelAdapter(db_path, output_dir)
        report = adapter.export_all()
        status = report.get("overall_status", "UNKNOWN")
        print(f"  Status: {status}")
        for gate_name, gate in report.get("gates", {}).items():
            marker = "✓" if gate["status"] == "PASS" else "✗"
            print(f"  {marker} {gate_name}")
        print(f"\n  ✓ PR Intel exported to: {output_dir}")
    except Exception as e:
        print(f"  Export error: {e}")
        raise


def _run_export_spiderweb(db_path: str, output_dir: str):
    print("\n  SPIDERWEB BRIDGE EXPORT")
    print("  " + "─" * 50)
    try:
        from ilap_airspace_bridge import ILAPAirspaceBridge
        from aasb_airspace_bridge import AASBAirspaceBridge
        ILAPAirspaceBridge(db_path, output_dir).export_all()
        AASBAirspaceBridge(db_path, output_dir).export_all()
        print(f"\n  ✓ Spiderweb exported to: {output_dir}")
    except Exception as e:
        print(f"  Export error: {e}")
        raise


def _run_spiderweb_intake(intake_dir: str):
    print("\n  SPIDERWEB INTAKE — OVERLAY + GAP AUDIT")
    print("  " + "─" * 50)
    try:
        from spiderweb_intake import SpiderwebIntake
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


def _run_scan_inventory(images_dir: str, db_path: str):
    print("\n  SCREENSHOT INVENTORY SCAN")
    print("  " + "─" * 50)
    from screenshot_inventory import ScreenshotInventory
    from pathlib import Path as _Path
    inv = ScreenshotInventory(images_dir, db_path=db_path)
    manifest = inv.scan()
    out = str(_Path(db_path).parent / "screenshot_inventory.csv")
    summary = inv.build_report(out)
    for k, v in summary.items():
        if k != "output_path":
            print(f"  {k:<20} {v:>8}")
    print(f"\n  ✓ Inventory written to: {out}")


def _run_export_fr24_events(images_dir: str, db_path: str):
    print("\n  FR24 EVENT EXPORT")
    print("  " + "─" * 50)
    from fr24_event_export import FR24EventExporter
    exp = FR24EventExporter(db_path)
    report = exp.export_batch(images_dir)
    print(f"  Screenshots upserted:  {report['screenshots_upserted']}")
    print(f"  Track points inserted: {report['track_points_inserted']}")
    print(f"  Review items added:    {report['review_items_added']}")
    print(f"\n  ✓ FR24 events exported to DB: {db_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Puerto Rico Airspace Intelligence System — Unified Pipeline",
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
  python run_all.py --scan-inventory /img/dir    Scan & inventory screenshots
  python run_all.py --export-fr24-events /img    Export FR24 events to DB
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
    parser.add_argument("--status", action="store_true",
                        help="Show database status and exit")
    parser.add_argument("--export-json", metavar="PATH",
                        help="Export DB snapshot to JSON for dashboard.html")
    parser.add_argument("--validate", action="store_true",
                        help="Run schema validation after pipeline")
    parser.add_argument("--export-pr-intel", metavar="DIR",
                        help="Export PR Intel parquet/GeoJSON to DIR")
    parser.add_argument("--export-spiderweb", metavar="DIR",
                        help="Export Spiderweb bridge outputs to DIR")
    parser.add_argument("--scan-inventory", metavar="DIR",
                        help="Scan screenshot directory and build inventory CSV")
    parser.add_argument("--export-fr24-events", metavar="DIR",
                        help="Export FR24 screenshot events from DIR into DB")
    parser.add_argument("--spiderweb-intake", metavar="DIR",
                        help="Normalize --export-spiderweb output into Spiderweb overlay candidates")

    args = parser.parse_args()

    print(BANNER)
    print(f"  Database:   {args.db}")
    print(f"  Image dir:  {args.image_dir}")
    print(f"  Max images: {args.images or 'All'}")
    print(f"  Started:    {datetime.utcnow().isoformat()}\n")

    if args.status:
        print_status(args.db)
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

    # Determine whether to run the main pipeline phases.
    # Skip phases when the user only supplied integration-export flags
    # (standalone export mode against an existing DB).
    new_flags_only = (
        not args.images
        and args.phase is None
        and (args.validate or args.export_pr_intel or args.export_spiderweb
             or args.scan_inventory or args.export_fr24_events
             or args.spiderweb_intake)
    )

    if not new_flags_only:
        start = datetime.utcnow()

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

        elapsed = (datetime.utcnow() - start).total_seconds()
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

    if args.scan_inventory:
        _run_scan_inventory(args.scan_inventory, args.db)

    if args.export_fr24_events:
        _run_export_fr24_events(args.export_fr24_events, args.db)

    if args.spiderweb_intake:
        _run_spiderweb_intake(args.spiderweb_intake)


if __name__ == "__main__":
    main()
