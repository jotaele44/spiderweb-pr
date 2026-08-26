"""Cadence-from-catalog and InSAR-pair compatibility tests.

Guards the brief's correction #1: revisit cadence is derived from actual
acquisitions, never a hard-coded 12-day assumption.
"""

from spiderweb.remote_monitoring import (
    compatible_pairs,
    insar_pair_compatibility,
    observed_revisit_days,
)


def test_cadence_computed_from_actual_scenes():
    scenes = [
        {"acquired_at": "2024-01-01"},
        {"acquired_at": "2024-01-13"},  # 12-day gap
        {"acquired_at": "2024-01-19"},  # 6-day gap
    ]
    r = observed_revisit_days(scenes)
    assert r["intervals_days"] == [12.0, 6.0]
    assert r["min_days"] == 6.0
    assert r["max_days"] == 12.0
    assert r["median_days"] == 9.0


def test_irregular_cadence_is_not_forced_to_12():
    # A 6-day constellation cadence must surface as 6, not a hard-coded 12.
    scenes = [{"acquisition_start": f"2024-02-{d:02d}T10:00:00Z"} for d in (1, 7, 13)]
    r = observed_revisit_days(scenes)
    assert r["intervals_days"] == [6.0, 6.0]
    assert r["median_days"] == 6.0


def test_single_scene_yields_no_cadence():
    r = observed_revisit_days([{"acquired_at": "2024-01-01"}])
    assert r["intervals_days"] == []
    assert r["min_days"] is None and r["median_days"] is None


def test_empty_input_is_safe():
    r = observed_revisit_days([])
    assert r["scene_count"] == 0
    assert r["intervals_days"] == []


def test_varying_cadence_reflects_inputs_not_a_default():
    """Two different scene sets must yield two different observed cadences —
    proving the cadence tracks the catalog rather than a fixed assumption."""
    six_day = observed_revisit_days(
        [{"acquired_at": f"2024-03-{d:02d}"} for d in (1, 7, 13)]
    )
    twelve_day = observed_revisit_days(
        [{"acquired_at": f"2024-03-{d:02d}"} for d in (1, 13, 25)]
    )
    assert six_day["median_days"] == 6.0
    assert twelve_day["median_days"] == 12.0
    assert six_day["median_days"] != twelve_day["median_days"]


def _scene(**kw):
    base = {
        "acquired_at": "2024-01-01T10:00:00Z",
        "relative_orbit": 25,
        "acquisition_mode": "IW",
        "polarization": "VV",
        "processing_baseline": "003.61",
        "bbox": [-66.1, 18.2, -65.9, 18.4],
    }
    base.update(kw)
    return base


def test_compatible_pair_accepted():
    ref = _scene(acquired_at="2024-01-01T10:00:00Z")
    sec = _scene(acquired_at="2024-01-13T10:00:00Z")
    r = insar_pair_compatibility(ref, sec)
    assert r["compatible"] is True
    assert r["reasons"] == []
    assert r["temporal_baseline_days"] == 12.0


def test_orbit_and_polarization_mismatch_rejected_with_reasons():
    ref = _scene()
    sec = _scene(
        acquired_at="2024-01-13T10:00:00Z", relative_orbit=99, polarization="HH"
    )
    r = insar_pair_compatibility(ref, sec)
    assert r["compatible"] is False
    assert any("relative_orbit" in x for x in r["reasons"])
    assert any("polarization" in x for x in r["reasons"])


def test_baseline_too_large_rejected():
    ref = _scene()
    sec = _scene(acquired_at="2024-01-13T10:00:00Z", perpendicular_baseline_m=500)
    r = insar_pair_compatibility(ref, sec, max_perp_baseline_m=300)
    assert r["compatible"] is False
    assert any("perpendicular baseline" in x for x in r["reasons"])


def test_compatible_pairs_enumerates_only_valid():
    scenes = [
        _scene(acquired_at="2024-01-01T10:00:00Z"),
        _scene(acquired_at="2024-01-13T10:00:00Z"),
        _scene(acquired_at="2024-01-25T10:00:00Z", relative_orbit=99),  # incompatible
    ]
    pairs = compatible_pairs(scenes)
    # Only the first two are mutually compatible.
    assert len(pairs) == 1
    assert pairs[0]["temporal_baseline_days"] == 12.0
