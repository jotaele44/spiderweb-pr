import json
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
