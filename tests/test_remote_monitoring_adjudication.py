"""Candidate → confirmed adjudication and detection-state interpretation tests."""

import pytest

from spiderweb.remote_monitoring import (
    AdjudicationError,
    RemoteObservation,
    adjudicate,
    interpret_signals,
    schemas,
)
from spiderweb.remote_monitoring.crosswalk import (
    NO_SIGNAL_DISCLAIMER,
    PhysicalContractCrosswalk,
    reconcile,
)


def _obs(signals, status=schemas.CANDIDATE):
    return RemoteObservation(
        aoi_uid="rm_aoi_carraizo_reservoir",
        scene_uids=["s1"],
        detector_name="test",
        detector_version="0.1",
        signals=list(signals),
        geometry={"type": "Point", "coordinates": [-66.0, 18.32]},
        change_start="2024-01-01",
        candidate_status=status,
    )


# ── detection-state interpretation ──────────────────────────────────────────


def test_sar_amplitude_alone_is_only_a_candidate():
    assert (
        interpret_signals([schemas.SIGNAL_SAR_AMPLITUDE]) == schemas.TIER_RADAR_CHANGE
    )


def test_coherence_loss_alone_is_only_a_candidate():
    # Correction #2: coherence loss is not a disturbance classification.
    tier = interpret_signals([schemas.SIGNAL_COHERENCE_LOSS])
    assert tier == schemas.TIER_SURFACE_DECORRELATION
    assert tier != schemas.TIER_CONFIRMED


def test_sar_plus_optical_is_corroborated_candidate():
    tier = interpret_signals(
        [schemas.SIGNAL_SAR_AMPLITUDE, schemas.SIGNAL_OPTICAL_CHANGE]
    )
    assert tier == schemas.TIER_CORROBORATED_SURFACE


def test_full_stack_reaches_high_confidence_disturbance_only():
    tier = interpret_signals(
        [
            schemas.SIGNAL_SAR_AMPLITUDE,
            schemas.SIGNAL_OPTICAL_CHANGE,
            schemas.SIGNAL_TERRAIN_MORPHOLOGY,
        ]
    )
    # High-confidence *disturbance* — still not a confirmed classified event.
    assert tier == schemas.TIER_HIGH_CONFIDENCE
    assert tier != schemas.TIER_CONFIRMED


# ── adjudication state machine ──────────────────────────────────────────────


def test_promote_then_confirm_requires_field_signal():
    obs = _obs([schemas.SIGNAL_SAR_AMPLITUDE, schemas.SIGNAL_OPTICAL_CHANGE])
    ev = adjudicate(obs, schemas.DECISION_PROMOTE, analyst_or_rule="rule:corroboration")
    assert obs.candidate_status == schemas.SUPPORTED_CANDIDATE
    assert ev.previous_status == schemas.CANDIDATE
    assert ev.new_status == schemas.SUPPORTED_CANDIDATE


def test_confirm_without_field_signal_is_blocked():
    # Remote sensing alone can never CONFIRM.
    obs = _obs(
        [
            schemas.SIGNAL_SAR_AMPLITUDE,
            schemas.SIGNAL_OPTICAL_CHANGE,
            schemas.SIGNAL_TERRAIN_MORPHOLOGY,
        ]
    )
    with pytest.raises(AdjudicationError):
        adjudicate(obs, schemas.DECISION_CONFIRM, analyst_or_rule="analyst:jl")
    assert obs.candidate_status == schemas.CANDIDATE  # unchanged


def test_confirm_with_field_signal_succeeds():
    obs = _obs([schemas.SIGNAL_OPTICAL_CHANGE, schemas.SIGNAL_FIELD_CONFIRMATION])
    ev = adjudicate(
        obs,
        schemas.DECISION_CONFIRM,
        analyst_or_rule="analyst:jl",
        decision_reason="field visit",
    )
    assert obs.candidate_status == schemas.CONFIRMED
    assert ev.new_status == schemas.CONFIRMED
    assert len(ev.adjudication_uid) == 32


def test_terminal_status_cannot_be_re_adjudicated():
    obs = _obs([schemas.SIGNAL_FIELD_CONFIRMATION])
    adjudicate(obs, schemas.DECISION_CONFIRM, analyst_or_rule="analyst:jl")
    with pytest.raises(AdjudicationError):
        adjudicate(obs, schemas.DECISION_PROMOTE, analyst_or_rule="analyst:jl")


def test_reject_is_terminal():
    obs = _obs([schemas.SIGNAL_SAR_AMPLITUDE])
    ev = adjudicate(obs, schemas.DECISION_REJECT, analyst_or_rule="rule:cloud_artifact")
    assert obs.candidate_status == schemas.REJECTED
    assert ev.decision == schemas.DECISION_REJECT


# ── the NO_SIGNAL_DETECTED guardrail ────────────────────────────────────────


def test_no_signal_detected_never_means_work_did_not_occur():
    cw = PhysicalContractCrosswalk(
        observation_uid="a" * 32,
        contract_node_uid="ms:node:1",
        activity_period_start="2024-01-01",
        activity_period_end="2024-03-01",
        contract_period_start="2024-01-15",
        contract_period_end="2024-02-15",
        observed_signal=None,
    )
    reconcile(cw, observable=True)
    assert cw.reconciliation_status == schemas.NO_SIGNAL_DETECTED
    # The disclaimer travels with the record.
    assert NO_SIGNAL_DISCLAIMER in cw.notes
    # There is no reconciliation state that asserts non-performance.
    assert "NON_PERFORMANCE" not in schemas.RECONCILIATION_STATES
    assert "WORK_DID_NOT_OCCUR" not in schemas.RECONCILIATION_STATES


def test_inadequate_observability_is_not_no_signal():
    cw = PhysicalContractCrosswalk(
        observation_uid="a" * 32,
        contract_node_uid="ms:node:1",
        observed_signal=None,
    )
    reconcile(cw, observable=False)
    assert cw.reconciliation_status == schemas.INSUFFICIENT_OBSERVABILITY
    assert cw.reconciliation_status != schemas.NO_SIGNAL_DETECTED


def test_signal_outside_contract_window():
    cw = PhysicalContractCrosswalk(
        observation_uid="a" * 32,
        contract_node_uid="ms:node:1",
        activity_period_start="2024-06-01",
        activity_period_end="2024-07-01",
        contract_period_start="2024-01-01",
        contract_period_end="2024-02-01",
        observed_signal="turbidity_plume",
    )
    reconcile(cw, observable=True)
    assert cw.reconciliation_status == schemas.SIGNAL_OUTSIDE_CONTRACT_PERIOD


def test_consistent_when_expected_signal_matches_in_window():
    cw = PhysicalContractCrosswalk(
        observation_uid="a" * 32,
        contract_node_uid="ms:node:1",
        activity_period_start="2024-01-10",
        activity_period_end="2024-02-10",
        contract_period_start="2024-01-01",
        contract_period_end="2024-03-01",
        expected_physical_signal="dredging_plume",
        observed_signal="dredging_plume",
    )
    reconcile(cw, observable=True)
    assert cw.reconciliation_status == schemas.CONSISTENT


def test_contradictory_records_short_circuit():
    cw = PhysicalContractCrosswalk(
        observation_uid="a" * 32,
        contract_node_uid="ms:node:1",
        observed_signal="plume",
    )
    reconcile(cw, observable=True, contradictory_records=True)
    assert cw.reconciliation_status == schemas.CONTRADICTORY_RECORDS
