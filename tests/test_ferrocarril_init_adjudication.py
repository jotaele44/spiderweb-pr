import csv
import json
from pathlib import Path

import pytest

from scripts.ferrocarril_init_adjudication import init_rows, write_template


def _write_source(path: Path, ids):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": None, "properties": {"feature_id": fid}}
            for fid in ids
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_init_rows_is_fail_closed(tmp_path):
    source = tmp_path / "source.geojson"
    _write_source(source, ["FERRO-0001", "FERRO-0002"])
    rows = init_rows(source)
    assert len(rows) == 2
    assert {r["feature_id"] for r in rows} == {"FERRO-0001", "FERRO-0002"}
    assert all(r["certification_state"] == "UNRESOLVED" for r in rows)
    assert all(r["coordinate_status"] == "UNRESOLVED" for r in rows)
    assert all(r["identity_relation"] == "UNRESOLVED" for r in rows)
    assert all(r["canonical_id"] == "" for r in rows)
    assert all(r["latitude"] == r["longitude"] == "" for r in rows)


def test_write_template_conserves_rows(tmp_path):
    source = tmp_path / "source.geojson"
    output = tmp_path / "adj.csv"
    _write_source(source, ["FERRO-0001", "FERRO-0002", "FERRO-0003"])
    assert write_template(source, output) == 3
    with output.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 3


def test_duplicate_source_id_fails(tmp_path):
    source = tmp_path / "source.geojson"
    _write_source(source, ["FERRO-0001", "FERRO-0001"])
    with pytest.raises(ValueError, match="duplicate source feature_id"):
        init_rows(source)


def test_empty_source_fails(tmp_path):
    source = tmp_path / "source.geojson"
    _write_source(source, [])
    with pytest.raises(ValueError, match="no features"):
        init_rows(source)
