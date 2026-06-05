"""Static dashboard tests for retiring the bottom temporal-wave overlay."""

from __future__ import annotations

from pathlib import Path


def test_dashboard_html_no_longer_loads_temporal_wave_overlay():
    html = Path("dashboard/dashboard.html").read_text(encoding="utf-8")

    assert "fr24_temporal_wave_dashboard.json" not in html
    assert "window.fr24TemporalWaveData" not in html
    assert "dashboard_temporal_waves.jsx" not in html


def test_temporal_wave_panel_source_remains_reference_only():
    """The old component can remain in-tree as a reference file, but static
    dashboard wiring must not load or bundle it."""
    exporter = Path("scripts/export_static_dashboard.py").read_text(encoding="utf-8")
    html = Path("dashboard/dashboard.html").read_text(encoding="utf-8")

    assert "dashboard_temporal_waves.jsx" not in exporter
    assert "fr24_temporal_wave_dashboard.json" not in exporter
    assert "dashboard_temporal_waves.jsx" not in html
    assert "fr24_temporal_wave_dashboard.json" not in html


def test_temporal_wave_exporter_can_still_generate_reference_artifact():
    exporter = Path("fr24/temporal_wave_dashboard_data.py").read_text(encoding="utf-8")

    assert "fr24_temporal_wave_dashboard.json" in exporter
    assert "TEMPORAL_DASHBOARD_DATA_VERSION" in exporter
    assert "candidate_only_no_auto_confirmation" in exporter
    assert "temporal_wave_candidate" in exporter
