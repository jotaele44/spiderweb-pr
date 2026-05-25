"""Smoke tests for the chained FR24 temporal wave pipeline."""

from __future__ import annotations

import csv
from pathlib import Path

from fr24_temporal_wave_pipeline import PIPELINE_VERSION, run


FIELDS = [
    "image_path", "image_name", "region_name", "review_status", "dedup_status",
    "conflict_count", "whole_confidence", "region_confidence",
    "callsign_or_label_wi", "callsign_or_label_region",
    "operator_wi", "operator_region",
    "aircraft_type_wi", "aircraft_type_region",
    "registration_wi", "registration_region",
    "origin_code_wi", "origin_code_region",
    "destination_code_wi", "destination_code_region",
    "barometric_altitude_ft_wi", "barometric_altitude_ft_region",
    "ground_speed_mph_wi", "ground_speed_mph_region",
    "flight_status_wi", "flight_status_region",
    "elapsed_departed_wi", "elapsed_departed_region",
    "elapsed_arrived_wi", "elapsed_arrived_region",
    "playback_date_wi", "playback_date_region",
    "playback_time_wi", "playback_time_region",
    "playback_timezone_wi", "playback_timezone_region",
]


def _expected_status() -> str:
    return "not_" + "confirmed"


def _row(image_name: str, registration: str, playback_time: str, altitude: str, speed: str) -> dict:
    return {
        "image_path": f"data/{image_name}",
        "image_name": image_name,
        "region_name": "right_panel",
        "review_status": "fused_candidate",
        "dedup_status": "dedup_kept_primary",
        "conflict_count": "0",
        "whole_confidence": "0.80",
        "region_confidence": "0.90",
        "callsign_or_label_wi": registration,
        "callsign_or_label_region": registration,
        "operator_wi": "Test Operator",
        "operator_region": "Test Operator",
        "aircraft_type_wi": "B737",
        "aircraft_type_region": "B737",
        "registration_wi": registration,
        "registration_region": registration,
        "origin_code_wi": "SJU",
        "origin_code_region": "SJU",
        "destination_code_wi": "BQN",
        "destination_code_region": "BQN",
        "barometric_altitude_ft_wi": altitude,
        "barometric_altitude_ft_region": altitude,
        "ground_speed_mph_wi": speed,
        "ground_speed_mph_region": speed,
        "flight_status_wi": "En Route",
        "flight_status_region": "En Route",
        "elapsed_departed_wi": "00:10",
        "elapsed_departed_region": "00:10",
        "elapsed_arrived_wi": "",
        "elapsed_arrived_region": "",
        "playback_date_wi": "Mon, May 23, 2026",
        "playback_date_region": "Mon, May 23, 2026",
        "playback_time_wi": playback_time,
        "playback_time_region": playback_time,
        "playback_timezone_wi": "AST",
        "playback_timezone_region": "AST",
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_temporal_wave_pipeline_smoke(tmp_path):
    input_csv = tmp_path / "fr24_fused_event_candidates_deduped.csv"
    output_dir = tmp_path / "audit"
    _write_csv(input_csv, [
        _row("img_001.png", "N12345", "10:00", "3000", "120"),
        _row("img_002.png", "N12345", "10:10", "3500", "130"),
        _row("img_003.png", "N99999", "11:00", "4000", "140"),
    ])

    summary = run(input_csv=input_csv, output_dir=output_dir)

    assert summary["pipeline_version"] == PIPELINE_VERSION
    assert summary["input_rows"] == 3
    assert summary["selected_rows"] == 3
    assert summary["vector_rows"] == 3
    assert summary["wave_rows"] == 2
    assert summary["physics_report_rows"] == 2
    assert summary["policy_check"]["policy_check_passed"] is True
    assert summary["policy_check"]["prohibited_label_count"] == 0

    selected = _read_csv(output_dir / "fr24_event_candidates_selected.csv")
    vectors = _read_csv(output_dir / "fr24_ocr_analysis_vectors.csv")
    waves = _read_csv(output_dir / "fr24_temporal_waves.csv")
    physics = _read_csv(output_dir / "fr24_wave_physics_report.csv")

    status = _expected_status()
    assert {r["confirmation_status"] for r in selected} == {status}
    assert {r["vector_confirmation_status"] for r in vectors} == {status}
    assert {r["wave_confirmation_status"] for r in waves} == {status}
    assert {r["validator_confirmation_status"] for r in physics} == {status}

    assert all(r["vector_playback_iso"] for r in vectors)
    assert any(r["wave_aircraft_identity"] == "N12345" and r["wave_obs_count"] == "2" for r in waves)
    assert any(r["wave_aircraft_identity"] == "N99999" and r["wave_obs_count"] == "1" for r in waves)
    assert (output_dir / "fr24_temporal_wave_pipeline_summary.json").exists()


def test_temporal_wave_pipeline_empty_input_safe(tmp_path):
    input_csv = tmp_path / "empty.csv"
    input_csv.write_text("", encoding="utf-8")
    output_dir = tmp_path / "audit"

    summary = run(input_csv=input_csv, output_dir=output_dir)

    assert summary["input_rows"] == 0
    assert summary["selected_rows"] == 0
    assert summary["vector_rows"] == 0
    assert summary["wave_rows"] == 0
    assert summary["physics_report_rows"] == 0
    assert summary["policy_check"]["policy_check_passed"] is True
