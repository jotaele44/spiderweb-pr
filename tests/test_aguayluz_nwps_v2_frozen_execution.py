"""Frozen execution evidence for the AguaYLuz NWPS -> PR Grid V2 L1 slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry/spatial/v2"
CERT_PATH = REGISTRY / "aguayluz_nwps_l1_migration.certification.json"
REQUEST_PATH = REGISTRY / "aguayluz_nwps_l1_migration.request.json"
DENOMINATOR_PATH = REGISTRY / "record_binding_migration_denominator.json"

CERT_SHA256 = "9f6b31369b8372e64f697079b5335c769573cb0dfd1f98147af8649e13eeb5b0"
SOURCE_COMMIT = "459c0777365786419da5c62db20abfdec21aa092"
SOURCE_BLOB = "e79f4526c8f6128f6e312ce3592f5518332ecd2f"
SOURCE_SHA256 = "232569ad1465a6b89e3e3625fe237dc8a18fa5547cf81bc3dd3e7f5f5d8c2363"
ARTIFACT_SHA256 = "432df011b706eacd6a1462201c6747d403934317ef02c9d4f3cbc8feb88c9449"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _slice(denominator: dict) -> dict:
    producer = next(
        row for row in denominator["Producers"]
        if row["Repository"] == "aguayluz-pr"
    )
    assert producer["Migration_State"] == "FIRST_SLICE_EXECUTION_FROZEN"
    return next(
        row for row in producer["Slices"]
        if row["Slice_ID"] == "NWPS_GAUGE_STATE"
    )


def test_certification_bytes_and_frozen_source_identity_close():
    cert_bytes = CERT_PATH.read_bytes()
    cert = json.loads(cert_bytes)
    request = _load(REQUEST_PATH)

    assert hashlib.sha256(cert_bytes).hexdigest() == CERT_SHA256
    assert cert["State"] == "PASS"
    assert cert["Repository"] == "aguayluz-pr"
    assert cert["Grid_Level"] == "L1"
    assert cert["Source_Commit"] == request["source_commit"] == SOURCE_COMMIT
    assert cert["Source_Git_Blob_SHA1"] == request["source_git_blob_sha1"] == SOURCE_BLOB
    assert cert["Source_SHA256"] == SOURCE_SHA256
    assert cert["Geometry_Copied"] is False


def test_record_and_profile_denominators_close_without_promotion():
    cert = _load(CERT_PATH)
    denominator = _load(DENOMINATOR_PATH)
    slice_row = _slice(denominator)

    assert cert["Input_Record_Count"] == 118
    assert cert["Binding_Row_Count"] == 118
    assert cert["Profile_Count"] == 111
    assert cert["State_Counts"] == {"INTERIOR": 118}

    assert slice_row["Execution_Evidence_State"] == "FROZEN_CI_ARTIFACT_PASS"
    assert slice_row["Certification_Receipt_Path"] == str(CERT_PATH.relative_to(ROOT))
    assert slice_row["Certification_SHA256"] == CERT_SHA256
    assert slice_row["Source_SHA256"] == SOURCE_SHA256
    assert slice_row["Input_Record_Count"] == cert["Input_Record_Count"]
    assert slice_row["Binding_Row_Count"] == cert["Binding_Row_Count"]
    assert slice_row["Profile_Count"] == cert["Profile_Count"]
    assert slice_row["Workflow_Run_ID"] == 41530288733
    assert slice_row["Workflow_Job_ID"] == 125568406973
    assert slice_row["Workflow_Artifact_ID"] == 13181641984
    assert slice_row["Workflow_Artifact_Bytes"] == 33989
    assert slice_row["Workflow_Artifact_SHA256"] == ARTIFACT_SHA256
    assert slice_row["Promotion_State"] == "CANDIDATE_NOT_CANONICAL"


def test_internal_artifact_hashes_are_frozen_and_geometry_is_not_copied():
    cert = _load(CERT_PATH)
    artifacts = cert["Artifacts"]

    assert artifacts == {
        "binding_input.jsonl": {
            "bytes": 54001,
            "sha256": "a9ddd63ab37253c48150775315577e9dc1d421fc87e7b41e36718565874bbdf8",
        },
        "binding_receipt.json": {
            "bytes": 1208,
            "sha256": "22c7d80de63d683e5cfe42095c9de9a9ceadc8a22f2c6c6cba17a5c9fbd9789b",
        },
        "bindings.jsonl": {
            "bytes": 57702,
            "sha256": "b7ae12e2d70145c945ef838998f39f3179ff67294875f7382b066e4696abba56",
        },
        "export_receipt.json": {
            "bytes": 899,
            "sha256": "ebc022859cc1c56b4b329684b7513d09ae06ef8486fd01a35873e6c90ec7ee70",
        },
        "profile_receipt.json": {
            "bytes": 1303,
            "sha256": "f6c38ce92194b61feca14142b698ff15e0a29c716b9e8c9d90a62d4fecaa6233",
        },
        "profile_records.jsonl": {
            "bytes": 44827,
            "sha256": "74dbc6426f3c8c5337dcdad33eb36a11002fc24417d9d4e75edff01df6b81ea5",
        },
        "profiles.jsonl": {
            "bytes": 114305,
            "sha256": "6bfd1fe2ac7025dcf1fe6969f31d0a827240400176db7ec1ba7852778fd3745f",
        },
        "projection_audit.jsonl": {
            "bytes": 107597,
            "sha256": "81b6377d767f78bd9816ba294652a0f783ea76f56ce8c8d865b0bd980cb67176",
        },
    }
    assert cert["Geometry_Copied"] is False
