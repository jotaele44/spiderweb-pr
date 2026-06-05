import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.export_static_dashboard import (
    StaticDashboardExportError,
    bundle_static_dashboard,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_static_dashboard_bundle_copies_assets_and_rewrites_output_paths(tmp_path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "dashboard_data.json").write_text(
        json.dumps({"flights": [], "aircraft_profiles": [], "alerts": [], "anomalies": []}),
        encoding="utf-8",
    )
    (outputs / "fr24_dashboard_review_queue.json").write_text(
        json.dumps({"items": []}),
        encoding="utf-8",
    )

    dist = tmp_path / "dist" / "static-dashboard"
    manifest = bundle_static_dashboard(
        repo_root=_repo_root(),
        dist_dir=dist,
        source_outputs=outputs,
        clean=True,
    )

    assert (dist / "index.html").exists()
    assert (dist / "dashboard.jsx").exists()
    assert (dist / "dashboard_temporal_waves.jsx").exists()
    assert (dist / "dashboard_contract_finance.jsx").exists()
    assert (dist / "outputs" / "dashboard_data.json").exists()
    assert (dist / "outputs" / "fr24_dashboard_review_queue.json").exists()

    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'fetchJson("./outputs/dashboard_data.json")' in html
    assert 'fetchJson("../outputs/dashboard_data.json")' not in html

    manifest_path = dist / "static_dashboard_manifest.json"
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["server_required"] is False
    assert persisted["server_required"] is False
    assert persisted["entrypoint"] == "index.html"
    assert persisted["required_outputs"]["dashboard_data.json"].endswith("dashboard_data.json")
    assert persisted["optional_outputs"]["contract_finance_scored_overlay.geojson"] == "missing"


def test_static_dashboard_bundle_requires_dashboard_data_json(tmp_path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    with pytest.raises(StaticDashboardExportError, match="missing required dashboard output"):
        bundle_static_dashboard(
            repo_root=_repo_root(),
            dist_dir=tmp_path / "dist",
            source_outputs=outputs,
            clean=True,
        )


def test_cli_db_mode_generates_dashboard_json_via_run_all(tmp_path):
    """Regression: running the script directly with --db must put the repo root
    on sys.path so `from run_all import export_json` resolves. Previously this
    raised `ModuleNotFoundError: No module named 'run_all'`."""
    db_path = tmp_path / "priis.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE flights (flight_id TEXT, callsign TEXT, aircraft_type TEXT, "
        "operator TEXT, mission_type TEXT, takeoff_time TEXT)"
    )
    conn.commit()
    conn.close()

    outputs = tmp_path / "outputs"  # no dashboard_data.json -> must be generated from --db
    dist = tmp_path / "dist" / "static-dashboard"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/export_static_dashboard.py",
            "--db", str(db_path),
            "--outputs", str(outputs),
            "--dist", str(dist),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
    )

    assert "ModuleNotFoundError" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stderr
    assert (outputs / "dashboard_data.json").exists()
    assert (dist / "outputs" / "dashboard_data.json").exists()
