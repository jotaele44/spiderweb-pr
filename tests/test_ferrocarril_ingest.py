from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.ferrocarril_ingest import load_features


COLUMNS = [
    "Row_No",
    "ID",
    "POI_Name",
    "Municipio",
    "Subtype",
    "Status",
    "Notes",
    "Segment",
    "Corridor",
    "Subtype_Description",
    "Latitude",
    "Longitude",
    "Coordinate_Status",
]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Row_No": 1,
        "ID": 1,
        "POI_Name": "Estación Test",
        "Municipio": "San Juan",
        "Subtype": "F1",
        "Status": "E1",
        "Notes": "source note",
        "Segment": 1,
        "Corridor": "Metro Core",
        "Subtype_Description": "Mainline / station",
        "Latitude": "",
        "Longitude": "",
        "Coordinate_Status": "Pending exact georeference",
    }
    row.update(overrides)
    return row


def test_ingest_preserves_null_geometry_and_provisional_state(tmp_path: Path) -> None:
    src = tmp_path / "ferrocarril.csv"
    write_csv(src, [base_row()])

    features, summary = load_features(src)

    assert summary["source_row_count"] == 1
    assert summary["coordinate_counts"] == {"without_coordinates": 1}
    assert features[0]["geometry"] is None
    props = features[0]["properties"]
    assert props["feature_id"] == "FERRO-0001"
    assert props["source_evidence_level"] == "E1"
    assert props["certification_state"] == "PROVISIONAL"
    assert props["coordinate_status"] == "Pending exact georeference"


def test_ingest_accepts_valid_source_coordinates_without_modification(tmp_path: Path) -> None:
    src = tmp_path / "ferrocarril.csv"
    write_csv(src, [base_row(Latitude="18.4655", Longitude="-66.1057", Coordinate_Status="source_provided")])

    features, summary = load_features(src)

    assert summary["coordinate_counts"] == {"with_coordinates": 1}
    assert features[0]["geometry"] == {"type": "Point", "coordinates": [-66.1057, 18.4655]}


def test_ingest_rejects_invalid_subtype(tmp_path: Path) -> None:
    src = tmp_path / "ferrocarril.csv"
    write_csv(src, [base_row(Subtype="F9")])

    with pytest.raises(ValueError, match="unsupported Ferrocarril subtype"):
        load_features(src)


def test_ingest_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    src = tmp_path / "ferrocarril.csv"
    write_csv(src, [base_row(), base_row(Row_No=2)])

    with pytest.raises(ValueError, match="source ID is not unique"):
        load_features(src)


def test_ingest_rejects_partial_coordinates(tmp_path: Path) -> None:
    src = tmp_path / "ferrocarril.csv"
    write_csv(src, [base_row(Latitude="18.4", Longitude="")])

    with pytest.raises(ValueError, match="both present or both absent"):
        load_features(src)
