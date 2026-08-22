import hashlib
import json

import pytest

from spiderweb.spatial.archipelago_provider import (
    ArchipelagoSnapshotError,
    load_certified_snapshot,
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_snapshot(
    tmp_path,
    *,
    state="PASS",
    identity_residue=0,
    geometry_residue=0,
    candidate_geometry_residue=0,
    closed=True,
    durable=True,
    preservation_state="PASS",
    bad_hash=False,
):
    features = tmp_path / "features.json"
    geometry = tmp_path / "geometry.geojson"
    features.write_text('[{"canonical_feature_id":"PR-1"}]', encoding="utf-8")
    geometry.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "certification": {
            "CURRENT_PR_ARCHIPELAGO": state,
            "SOURCE_EVIDENCE_PRESERVATION": preservation_state,
        },
        "source_evidence_durable": durable,
        "unresolved_current_identity_residue": identity_residue,
        "unresolved_current_geometry_residue": geometry_residue,
        "candidate_only_current_geometry_residue": candidate_geometry_residue,
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
    _write_snapshot(tmp_path, identity_residue=1)
    with pytest.raises(ArchipelagoSnapshotError, match="identity residue"):
        load_certified_snapshot(tmp_path)


def test_nonzero_geometry_residue_is_rejected(tmp_path):
    _write_snapshot(tmp_path, geometry_residue=1)
    with pytest.raises(ArchipelagoSnapshotError, match="geometry residue"):
        load_certified_snapshot(tmp_path)


def test_candidate_only_geometry_residue_is_rejected(tmp_path):
    _write_snapshot(tmp_path, candidate_geometry_residue=1)
    with pytest.raises(ArchipelagoSnapshotError, match="candidate-only current geometry residue"):
        load_certified_snapshot(tmp_path)


def test_ephemeral_only_source_evidence_is_rejected(tmp_path):
    _write_snapshot(tmp_path, durable=False)
    with pytest.raises(ArchipelagoSnapshotError, match="durably preserved"):
        load_certified_snapshot(tmp_path)


def test_open_evidence_preservation_is_rejected(tmp_path):
    _write_snapshot(tmp_path, preservation_state="OPEN")
    with pytest.raises(ArchipelagoSnapshotError, match="SOURCE_EVIDENCE_PRESERVATION"):
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
