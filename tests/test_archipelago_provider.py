import hashlib
import json

import pytest

from spiderweb.spatial.archipelago_provider import (
    ArchipelagoSnapshotError,
    load_certified_snapshot,
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_snapshot(tmp_path, *, state="PASS", residue=0, closed=True, bad_hash=False):
    features = tmp_path / "features.json"
    geometry = tmp_path / "geometry.geojson"
    features.write_text('[{"canonical_feature_id":"PR-1"}]', encoding="utf-8")
    geometry.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "certification": {"CURRENT_PR_ARCHIPELAGO": state},
        "unresolved_current_identity_residue": residue,
        "arithmetic_closed": closed,
        "canonical_feature_count": 1,
        "features_file": "features.json",
        "geometry_file": "geometry.geojson",
        "sha256": {
            "features_file": "0" * 64 if bad_hash else _sha(features),
            "geometry_file": _sha(geometry),
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_open_snapshot_is_rejected(tmp_path):
    _write_snapshot(tmp_path, state="OPEN")
    with pytest.raises(ArchipelagoSnapshotError, match="not PASS"):
        load_certified_snapshot(tmp_path)


def test_nonzero_identity_residue_is_rejected(tmp_path):
    _write_snapshot(tmp_path, residue=1)
    with pytest.raises(ArchipelagoSnapshotError, match="identity residue"):
        load_certified_snapshot(tmp_path)


def test_open_arithmetic_is_rejected(tmp_path):
    _write_snapshot(tmp_path, closed=False)
    with pytest.raises(ArchipelagoSnapshotError, match="arithmetic"):
        load_certified_snapshot(tmp_path)


def test_hash_mismatch_is_rejected(tmp_path):
    _write_snapshot(tmp_path, bad_hash=True)
    with pytest.raises(ArchipelagoSnapshotError, match="SHA256 mismatch"):
        load_certified_snapshot(tmp_path)


def test_pass_snapshot_loads(tmp_path):
    _write_snapshot(tmp_path)
    snapshot = load_certified_snapshot(tmp_path)
    assert snapshot.feature_count == 1
    assert snapshot.manifest["certification"]["CURRENT_PR_ARCHIPELAGO"] == "PASS"
