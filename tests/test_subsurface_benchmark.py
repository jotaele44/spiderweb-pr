import copy
import json
from pathlib import Path

import pytest

from spiderweb.subsurface.benchmark import (
    Anchor,
    CandidateObject,
    ObjectState,
    acquisition_bbox,
    certification_state,
    load_benchmark,
    source_arithmetic,
    validate_benchmark,
)


BENCHMARK = Path("configs/subsurface_benchmarks/aguadilla_maleza_alta_001.json")


def test_aguadilla_benchmark_contract_is_valid():
    payload = load_benchmark(BENCHMARK)
    assert payload["benchmark_id"] == "AGUADILLA_MALEZA_ALTA_SUBSURFACE_001"
    assert payload["anchor"]["lat"] == pytest.approx(18.5091743)
    assert payload["anchor"]["lon"] == pytest.approx(-67.1140566)
    assert [w["radius_m"] for w in payload["metric_windows"]] == [5000, 1000, 250, 50]


def test_metric_windows_fail_closed_if_not_nested():
    payload = json.loads(BENCHMARK.read_text())
    payload = copy.deepcopy(payload)
    payload["metric_windows"][2]["radius_m"] = 2000
    with pytest.raises(ValueError, match="strictly nested"):
        validate_benchmark(payload)


def test_acquisition_bbox_contains_anchor_and_is_not_certified_geometry():
    anchor = Anchor(18.5091743, -67.1140566)
    west, south, east, north = acquisition_bbox(anchor, 1000)
    assert west < anchor.lon < east
    assert south < anchor.lat < north
    assert east - west < 0.03
    assert north - south < 0.03


def test_identity_promotion_requires_independent_evidence():
    candidate = CandidateObject(
        candidate_id="MA-001",
        object_class="SUBSURFACE_CONDUIT",
        state=ObjectState.VERIFIED,
        evidence_ids=("surface-lineament", "terrain-depression"),
    )
    with pytest.raises(ValueError, match="independent identity evidence"):
        candidate.validate()


def test_identity_promotion_passes_with_independent_evidence():
    candidate = CandidateObject(
        candidate_id="MA-001",
        object_class="SUBSURFACE_CONDUIT",
        state=ObjectState.VERIFIED,
        evidence_ids=("surface-lineament",),
        independent_identity_evidence_ids=("field-tracer-study-001",),
    )
    candidate.validate()


def test_source_arithmetic_exposes_missing_and_unexpected_rows():
    result = source_arithmetic(
        ("geology", "lidar", "bathymetry"),
        (
            {"family": "geology"},
            {"family": "lidar"},
            {"family": "unexpected"},
        ),
    )
    assert result == {
        "required_families": 3,
        "covered_families": 2,
        "missing_families": 1,
        "unexpected_rows": 1,
        "rows": 3,
    }


def test_current_benchmark_cannot_self_certify():
    payload = load_benchmark(BENCHMARK)
    assert certification_state(payload) == "PROVISIONAL"
