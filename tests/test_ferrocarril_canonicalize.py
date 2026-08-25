import csv
import json
from pathlib import Path

import pytest

from scripts.ferrocarril_canonicalize import canonicalize


def write_source(path: Path, ids=(1, 2)):
    features = []
    for i in ids:
        features.append({
            "type": "Feature",
            "geometry": None,
            "properties": {
                "feature_id": f"FERRO-{i:04d}",
                "source_record_id": i,
                "name_raw": f"POI {i}",
                "municipio_raw": "Test",
                "ferrocarril_subtype": "F3",
                "source_evidence_level": "E1",
                "certification_state": "PROVISIONAL",
                "coordinate_status": "not_extracted",
                "source_sha256": "0" * 64,
            },
        })
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def write_adjudication(path: Path, rows):
    fields = [
        "feature_id", "certification_state", "coordinate_status", "provenance_locator",
        "provenance_type", "identity_relation", "canonical_id", "latitude", "longitude",
        "adjudication_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def provisional(fid):
    return {
        "feature_id": fid,
        "certification_state": "PROVISIONAL",
        "coordinate_status": "UNRESOLVED",
        "provenance_locator": "",
        "provenance_type": "",
        "identity_relation": "UNRESOLVED",
        "canonical_id": "",
        "latitude": "",
        "longitude": "",
        "adjudication_notes": "pending",
    }


def test_requires_full_source_coverage(tmp_path):
    source = tmp_path / "source.geojson"
    adj = tmp_path / "adj.csv"
    write_source(source)
    write_adjudication(adj, [provisional("FERRO-0001")])
    with pytest.raises(ValueError, match="does not cover all source features"):
        canonicalize(source, adj)


def test_certified_requires_provenance_and_geometry(tmp_path):
    source = tmp_path / "source.geojson"
    adj = tmp_path / "adj.csv"
    write_source(source, ids=(1,))
    row = provisional("FERRO-0001")
    row.update({"certification_state": "CERTIFIED", "coordinate_status": "EXACT", "identity_relation": "1:1", "canonical_id": "FERROCARRIL-CAN-0001"})
    write_adjudication(adj, [row])
    with pytest.raises(ValueError, match="lacks provenance_locator"):
        canonicalize(source, adj)


def test_unresolved_coordinates_cannot_assert_geometry(tmp_path):
    source = tmp_path / "source.geojson"
    adj = tmp_path / "adj.csv"
    write_source(source, ids=(1,))
    row = provisional("FERRO-0001")
    row.update({"latitude": "18.2", "longitude": "-66.1"})
    write_adjudication(adj, [row])
    with pytest.raises(ValueError, match="must not assert point geometry"):
        canonicalize(source, adj)


def test_n1_collision_requires_explicit_relation(tmp_path):
    source = tmp_path / "source.geojson"
    adj = tmp_path / "adj.csv"
    write_source(source)
    rows = []
    for fid in ("FERRO-0001", "FERRO-0002"):
        row = provisional(fid)
        row.update({
            "certification_state": "CERTIFIED",
            "coordinate_status": "EXACT",
            "provenance_locator": "archive:sheet-1",
            "provenance_type": "map",
            "identity_relation": "1:1",
            "canonical_id": "FERROCARRIL-CAN-0001",
            "latitude": "18.2",
            "longitude": "-66.1",
        })
        rows.append(row)
    write_adjudication(adj, rows)
    with pytest.raises(ValueError, match="collision"):
        canonicalize(source, adj)


def test_row_conservation_and_separation(tmp_path):
    source = tmp_path / "source.geojson"
    adj = tmp_path / "adj.csv"
    write_source(source)
    a = provisional("FERRO-0001")
    a.update({
        "certification_state": "CERTIFIED",
        "coordinate_status": "EXACT",
        "provenance_locator": "archive:sheet-1",
        "provenance_type": "map",
        "identity_relation": "1:1",
        "canonical_id": "FERROCARRIL-CAN-0001",
        "latitude": "18.2",
        "longitude": "-66.1",
    })
    b = provisional("FERRO-0002")
    b.update({"certification_state": "NONCANONICAL"})
    write_adjudication(adj, [a, b])
    source_out, canonical, analytical, crosswalk, summary = canonicalize(source, adj)
    assert len(source_out) == 2
    assert len(canonical) == 1
    assert len(analytical) == 1
    assert len(crosswalk) == 2
    assert summary["row_conservation_pass"] is True
