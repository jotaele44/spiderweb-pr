from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.source_adapters.pr_hydrography.core import (
    BASELINE_EXPECTATIONS,
    CandidateRelationship,
    ImmutableSnapshotStore,
    SOURCE_SPECS,
    SnapshotRecord,
    certify_baselines,
    decide_refresh,
    matching_text,
    rank_candidates,
    request_signature,
    schema_fingerprint,
    select_candidates,
    strict_bool,
)
from scripts.source_adapters.pr_hydrography.validation import (
    audit_geojson_geometry,
    csv_dict_rows,
)


def _nhd_rows():
    rows = []
    for index in range(2560):
        rows.append({
            "PERMANENT_IDENTIFIER": str(100000000 + index),
            "FTYPE": 390,
            "FCODE": 39009,
            "GNIS_NAME": None,
        })
    for index in range(653):
        rows.append({
            "PERMANENT_IDENTIFIER": str(200000000 + index),
            "FTYPE": 436,
            "FCODE": 43617,
            "GNIS_NAME": None,
        })
    return rows


def _nid_rows():
    return [
        {
            "NID ID": f"PR{i:05d}",
            "State": "PR",
            "Dam Name": f"Dam {i}",
        }
        for i in range(1, 37)
    ]


def _v4_rows():
    return [
        {"Feature": "Lago Carite, PR"},
        {"Feature": "Lago Patillas, PR"},
        {"Feature": "Lago Caonillas, PR"},
        {"Feature": "Levittown Lake, PR"},
        {"Feature": "Lago Guayabal, PR"},
        {"Feature": "Lago Lucchetti, PR"},
    ]


def test_frozen_baseline_contract_closes_without_using_counts_as_selection_logic():
    result = certify_baselines(
        nhd_rows=_nhd_rows(),
        nid_rows=_nid_rows(),
        v4_rows=_v4_rows(),
    )
    assert result["pass"] is True
    assert result["observed"] == BASELINE_EXPECTATIONS
    assert result["nhd"]["arithmetic_closure"] is True
    assert result["nid"]["prefix_state_set_equal"] is True


def test_schema_fingerprint_is_order_independent_for_rows():
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": None}]
    assert schema_fingerprint(rows) == schema_fingerprint(list(reversed(rows)))


def test_request_signature_preserves_semantics():
    a = request_signature("X", "GET", {"b": 2, "a": 1})
    b = request_signature("X", "GET", {"a": 1, "b": 2})
    c = request_signature("X", "GET", {"a": 1, "b": 3})
    assert a == b
    assert a != c


def test_strict_boolean_parser_rejects_python_string_truthiness():
    assert strict_bool("False") is False
    assert strict_bool("true") is True
    with pytest.raises(ValueError):
        strict_bool("maybe")


def test_mojibake_matching_normalization_preserves_intended_name():
    assert matching_text("Ana Mariaâ\u00a0Ii Dam") == "ana maria ii dam"
    assert matching_text("Rio Â\u00a0Blanco Dam") == "rio blanco dam"


def test_csv_header_detection_accepts_nid_style_preamble():
    payload = (
        b"Data Last Updated:,2026-8-10\n"
        b"Dam Name,NID ID,State\n"
        b"Caonillas Dam,PR00011,PR\n"
    )
    rows, metadata = csv_dict_rows(payload, ["Dam Name", "NID ID", "State"])
    assert metadata["header_line_index"] == 1
    assert metadata["preamble_lines"] == ["Data Last Updated:,2026-8-10"]
    assert rows[0]["NID ID"] == "PR00011"


def test_snapshot_store_is_immutable_and_content_addressed(tmp_path: Path):
    spec = SOURCE_SPECS["USACE_NID_DAMS"]
    store = ImmutableSnapshotStore(tmp_path)
    record = store.write(
        spec,
        b"abc",
        request_sig="r" * 64,
        schema_fp="s" * 64,
        source_update_date="2026-08-10",
        extension=".bin",
    )
    payload = Path(record.payload_path)
    assert payload.read_bytes() == b"abc"
    assert record.sha256.startswith("ba7816bf")
    assert json.loads((payload.parent / "snapshot.json").read_text())["snapshot_id"] == record.snapshot_id


def test_refresh_states_include_no_change_and_schema_drift():
    previous = SnapshotRecord(
        snapshot_id="x",
        source_id="USACE_NID_DAMS",
        adapter_version="v",
        request_signature="r",
        source_update_date="2026-08-10",
        sha256="abc",
        bytes=1,
        schema_fingerprint="schema-a",
        acquired_utc="2026-08-11T00:00:00Z",
        parent_snapshot="",
        payload_path="x",
        state="SNAPSHOT_CREATED",
    )
    assert decide_refresh(previous, remote_sha256="abc", remote_schema_fingerprint="schema-a") == "NO_CHANGE"
    assert decide_refresh(previous, remote_sha256="def", remote_schema_fingerprint="schema-b") == "BLOCKED_SCHEMA_DRIFT"
    assert decide_refresh(previous, remote_sha256="def", remote_schema_fingerprint="schema-a") == "ACQUIRE_NEW_SNAPSHOT"


def test_discovery_boundary_cannot_exclude_caonillas_hard_binding():
    discovery = [
        CandidateRelationship(
            source_a_id="PR00011",
            source_b_id="26378301",
            evidence_class="DISTANCE_ONLY_WITHIN_500M",
            evidence_rank=10,
            distance_m=314.521943,
        )
    ]
    explicit = [
        CandidateRelationship(
            source_a_id="PR00011",
            source_b_id="120013183",
            evidence_class="HARD_V4_POLYGON_BINDING",
            evidence_rank=0,
            distance_m=7933.52259,
            explicit_hard_binding=True,
        )
    ]
    candidates = select_candidates(discovery, explicit)
    assert {row.source_b_id for row in candidates} == {"26378301", "120013183"}
    ranked = rank_candidates(candidates)
    assert ranked["state"] == "PREFERRED_RELATIONSHIP_CANDIDATE"
    assert ranked["winner"].source_b_id == "120013183"


def test_distance_only_never_auto_promotes():
    ranked = rank_candidates([
        CandidateRelationship(
            source_a_id="PR00079",
            source_b_id="26382039",
            evidence_class="DISTANCE_ONLY_WITHIN_2_5KM",
            evidence_rank=12,
            distance_m=1941.537764,
            source_taxonomy="FTYPE436",
        )
    ])
    assert ranked["state"] == "UNRESOLVED_PROXIMITY_ONLY"
    assert ranked["winner"] is None


def test_source_taxonomy_never_breaks_equal_evidence_tie():
    candidates = [
        CandidateRelationship("PRX", "A", "DISTANCE_ONLY_WITHIN_100M", 8, 10.0, False, "FTYPE390"),
        CandidateRelationship("PRX", "B", "DISTANCE_ONLY_WITHIN_100M", 8, 11.0, False, "FTYPE436"),
    ]
    ranked = rank_candidates(candidates)
    assert ranked["state"] == "TOP_EVIDENCE_TIE_REVIEW"
    assert ranked["winner"] is None
    assert len(ranked["top"]) == 2


def test_invalid_geometry_is_repaired_only_for_analysis():
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]],
    }
    audit = audit_geojson_geometry(bowtie)
    assert audit.source_valid is False
    assert audit.analysis_valid is True
    assert audit.repair_applied is True
    assert audit.source_mutated is False
