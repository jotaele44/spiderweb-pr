import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from federation.usgs_native_reference import build_native_streams

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests/fixtures/usgs_native/input.json"


def test_real_frozen_features_crs_keys_counts_and_order_preserved():
    streams, audit = build_native_streams(INPUT, ROOT)
    assert len(streams["sources"]) == 3 and len(streams["observations"]) == 92
    assert audit["activation_state"] == audit["production_export_state"] == "BLOCKED"
    assert len({r["observation_id"] for r in streams["observations"]}) == 92
    for asset in json.loads(INPUT.read_text())["assets"]:
        native = json.loads(gzip.decompress((ROOT / asset["raw_file"]).read_bytes()))
        rows = [
            r
            for r in streams["observations"]
            if r["attributes"]["asset_id"] == asset["asset_id"]
        ]
        assert [r["attributes"]["native_feature"] for r in rows] == native["features"]
        assert all(
            r["attributes"]["native_collection_metadata"]["crs"] == native["crs"]
            for r in rows
        )
        assert all(
            "location" not in r and r["observed_at"] == asset["retrieval_utc"]
            for r in rows
        )
        assert all(r["confidence"] == 0.0 and r["synthetic"] is False for r in rows)
    assert build_native_streams(INPUT, ROOT) == (streams, audit)


@pytest.mark.parametrize("mode", ["production", "PRODUCTION", "", None])
def test_production_and_unknown_modes_refused_before_export(mode):
    with pytest.raises(ValueError, match="Production export BLOCKED"):
        build_native_streams(INPUT, ROOT, mode=mode)


def _fixture(tmp_path, features=None, raw=None):
    sid = "a" * 24
    if raw is None:
        raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": features
                or [
                    {"type": "Feature", "properties": {"ID": 1}, "geometry": None},
                    {"type": "Feature", "properties": {"ID": "1"}, "geometry": None},
                ],
            }
        ).encode()
    packed = gzip.compress(raw, mtime=0)
    (tmp_path / "source.gz").write_bytes(packed)
    d = copy.deepcopy(json.loads(INPUT.read_text()))
    a = d["assets"][0]
    a.update(
        asset_id=sid + ":0",
        source_item_id=sid,
        source_key="ID",
        raw_file="source.gz",
        packed_sha256=hashlib.sha256(packed).hexdigest(),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        expected_features=2,
    )
    a["source_descriptor_raw"] = {
        "name": "source.geojson",
        "size": len(raw),
        "downloadUri": "https://www.sciencebase.gov/catalog/file/get/" + sid,
        "checksum": {"type": "MD5", "value": hashlib.md5(raw).hexdigest()},
    }
    d["assets"] = [a]
    p = tmp_path / "input.json"
    p.write_text(json.dumps(d))
    return p, d


def test_typed_source_keys_distinct_and_no_native_null_geometry_invention(tmp_path):
    path, _ = _fixture(tmp_path)
    streams, _ = build_native_streams(path, tmp_path)
    rows = streams["observations"]
    assert len({r["observation_id"] for r in rows}) == 2
    assert [r["attributes"]["source_key_raw"] for r in rows] == [1, "1"]
    assert all(r["attributes"]["native_feature"]["geometry"] is None for r in rows)


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("duplicate_asset", "Duplicate asset"),
        ("wrong_item", "identity mismatch"),
        ("wrong_producer", "Expected blocked"),
        ("promoted_input", "Expected blocked"),
        ("count", "denominator"),
        ("packed_hash", "Packed input checksum"),
        ("raw_hash", "Raw/source checksum"),
        ("source_hash", "Raw/source checksum"),
        ("url", "URL/source-item"),
        ("timezone", "timezone"),
        ("traversal", "not in the subpath"),
    ],
)
def test_negative_identity_integrity_and_refusal_gates(tmp_path, mutation, match):
    path, d = _fixture(tmp_path)
    a = d["assets"][0]
    if mutation == "duplicate_asset":
        d["assets"].append(copy.deepcopy(a))
    elif mutation == "wrong_item":
        a["source_item_id"] = "b" * 24
    elif mutation == "wrong_producer":
        d["producer"] = "ovnis-pr"
    elif mutation == "promoted_input":
        d["activation_state"] = "PASS"
    elif mutation == "count":
        a["expected_features"] = 3
    elif mutation == "packed_hash":
        a["packed_sha256"] = "0" * 64
    elif mutation == "raw_hash":
        a["raw_sha256"] = "0" * 64
    elif mutation == "source_hash":
        a["source_descriptor_raw"]["checksum"]["value"] = "0" * 32
    elif mutation == "url":
        a["source_descriptor_raw"]["downloadUri"] = "https://example.com/file"
    elif mutation == "timezone":
        a["retrieval_utc"] = "2026-10-16T06:00:00"
    elif mutation == "traversal":
        a["raw_file"] = "../outside.gz"
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match=match):
        build_native_streams(path, tmp_path)


@pytest.mark.parametrize(
    "raw,match",
    [
        (
            b'{"type":"FeatureCollection","type":"FeatureCollection","features":[]}',
            "Duplicate JSON",
        ),
        (b'{"features":[1e999]}', "Non-finite"),
        (b'{"features":[NaN]}', "Non-finite"),
        (b" " * (5 * 1024 * 1024 + 1), "capacity"),
    ],
)
def test_malformed_json_and_expansion_are_blocked(tmp_path, raw, match):
    path, _ = _fixture(tmp_path, raw=raw)
    with pytest.raises(ValueError, match=match):
        build_native_streams(path, tmp_path)


def test_duplicate_primary_key_rejected(tmp_path):
    path, _ = _fixture(
        tmp_path, features=[{"type": "Feature", "properties": {"ID": 1}}] * 2
    )
    with pytest.raises(ValueError, match="Duplicate source primary key"):
        build_native_streams(path, tmp_path)


def test_cli_production_refusal_and_nonempty_output_are_non_destructive(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "package"
    command = [
        sys.executable,
        str(ROOT / "scripts/export_usgs_native.py"),
        "--input-manifest",
        str(INPUT),
        "--source-root",
        str(ROOT),
        "--out",
        str(out),
    ]
    result = subprocess.run(
        command + ["--mode", "production"], capture_output=True, text=True
    )
    assert result.returncode != 0 and not out.exists()
    assert "Production export BLOCKED" in result.stderr
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0 and "Output must be empty" in result.stderr
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
    assert "TERMINAL_READY.txt" in before
