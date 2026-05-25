"""Static wiring tests for FR24 temporal-wave dashboard visibility."""

from __future__ import annotations

from pathlib import Path


def test_dashboard_html_loads_temporal_wave_json_and_module():
    html = Path("dashboard.html").read_text(encoding="utf-8")

    assert "fr24_temporal_wave_dashboard.json" in html
    assert "window.fr24TemporalWaveData" in html
    assert "dashboard_temporal_waves.jsx" in html


def test_temporal_wave_panel_is_read_only_candidate_visibility():
    jsx = Path("dashboard_temporal_waves.jsx").read_text(encoding="utf-8")

    assert "TemporalWavePanel" in jsx
    assert "window.fr24TemporalWaveData" in jsx
    assert "Read-only candidate visibility" in jsx
    assert "localStorage" not in jsx
    assert "fetch(" not in jsx
    assert "confirmed_aircraft_event" not in jsx
    assert "validated_aircraft_event" not in jsx


def test_temporal_wave_exporter_default_output_name():
    exporter = Path("fr24_temporal_wave_dashboard_data.py").read_text(encoding="utf-8")

    assert "fr24_temporal_wave_dashboard.json" in exporter
    assert "TEMPORAL_DASHBOARD_DATA_VERSION" in exporter
    assert "candidate_only_no_auto_confirmation" in exporter
    assert "temporal_wave_candidate" in exporter
