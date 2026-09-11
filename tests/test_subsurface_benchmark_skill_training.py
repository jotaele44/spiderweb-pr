import copy
import pytest

from spiderweb.subsurface.benchmark import CandidateObject, ObjectState
from spiderweb.subsurface.benchmark_skill_training import build_skill_receipt


BASE = {
    "schema": "spiderweb.subsurface.benchmark.v1",
    "benchmark_id": "TEST",
    "anchor": {"lat": 18.5, "lon": -67.1, "crs": "EPSG:4326"},
    "metric_windows": [
        {"id": "Z1", "radius_m": 5000, "purpose": "a"},
        {"id": "Z2", "radius_m": 1000, "purpose": "b"},
        {"id": "Z3", "radius_m": 250, "purpose": "c"},
        {"id": "Z4", "radius_m": 50, "purpose": "d"},
    ],
    "classification_states": ["OBSERVED", "CANDIDATE", "UNRESOLVED", "VERIFIED"],
    "required_source_families": ["exact_geology"],
    "certification_gates": {
        "exact_geology_bound": False,
        "zero_unresolved_inside_certified_scope": False,
        "skill_training_allowed": False,
    },
}


def test_training_fails_closed_for_provisional_benchmark():
    with pytest.raises(ValueError, match="certification PASS"):
        build_skill_receipt(
            benchmark_payload=BASE,
            benchmark_config_bytes=b"{}",
            evidence_manifest_sha256="a" * 64,
            candidates=(),
        )


def test_training_fails_for_verified_identity_without_independent_evidence():
    payload = copy.deepcopy(BASE)
    payload["certification_gates"] = {key: True for key in payload["certification_gates"]}
    candidate = CandidateObject(
        candidate_id="C-1",
        object_class="SUBSURFACE_CONDUIT",
        state=ObjectState.VERIFIED,
    )
    with pytest.raises(ValueError, match="independent identity evidence"):
        build_skill_receipt(
            benchmark_payload=payload,
            benchmark_config_bytes=b"{}",
            evidence_manifest_sha256="a" * 64,
            candidates=(candidate,),
        )


def test_certified_training_receipt_is_deterministically_hash_bound():
    payload = copy.deepcopy(BASE)
    payload["certification_gates"] = {key: True for key in payload["certification_gates"]}
    candidate = CandidateObject(
        candidate_id="OBS-1",
        object_class="SURFACE_DEPRESSION",
        state=ObjectState.OBSERVED,
        evidence_ids=("DEM-1",),
    )
    first = build_skill_receipt(
        benchmark_payload=payload,
        benchmark_config_bytes=b"benchmark",
        evidence_manifest_sha256="b" * 64,
        candidates=(candidate,),
    )
    second = build_skill_receipt(
        benchmark_payload=payload,
        benchmark_config_bytes=b"benchmark",
        evidence_manifest_sha256="b" * 64,
        candidates=(candidate,),
    )
    assert first == second
    assert len(first.descriptor_sha256) == 64
    assert first.training_rows == 1
