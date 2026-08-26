"""Schema constants for the ``spiderweb.remote_monitoring`` subsystem.

This module holds the vocabulary of the remote-sensing monitoring backbone as
plain Python constants (mirroring ``spiderweb/schemas/headstart_schema.py``).
Keeping the vocabulary here — rather than only in the JSON Schemas — lets the
pure-Python core reason about detection states, adjudication decisions and
reconciliation outcomes without a jsonschema dependency, so the base test suite
runs offline.

The central design rule from the architecture brief is encoded here: a
remote-sensing *detection* is a candidate, never a conclusion. What a sensor can
establish is bounded by ``EVIDENCE_TIERS`` and the
``DETECTION_STATE_INTERPRETATION`` table; promotion to a confirmed classified
event is a separate, explicit adjudication decision.
"""

from __future__ import annotations

LAYER_ID = "rm_monitoring_pr"
SUBSYSTEM = "spiderweb.remote_monitoring"

# Node / edge types emitted into the Spiderweb graph.
AOI_NODE_TYPE = "rm_monitoring_aoi"
OBSERVATION_NODE_TYPE = "rm_remote_observation"
SCENE_NODE_TYPE = "rm_source_scene"
EDGE_OBSERVED_IN = "OBSERVED_IN"  # observation -> aoi
EDGE_DERIVED_FROM_SCENE = "DERIVED_FROM"  # observation -> scene
EDGE_ADJUDICATES = "ADJUDICATES"  # adjudication -> observation
EDGE_CROSSWALKS = "CROSSWALKS"  # crosswalk -> (observation, contract)

# ── Candidate lifecycle ──────────────────────────────────────────────────────
# Every remote observation begins as a candidate. Only human/authoritative
# adjudication may move it to CONFIRMED; nothing auto-confirms.
CANDIDATE = "candidate"
SUPPORTED_CANDIDATE = "supported_candidate"
CONFIRMED = "confirmed"
REJECTED = "rejected"
CANDIDATE_STATUSES = (CANDIDATE, SUPPORTED_CANDIDATE, CONFIRMED, REJECTED)

# ── Evidence tiers ───────────────────────────────────────────────────────────
# What the combined evidence can *establish*, from the brief's detection-state
# table. Ordered weakest -> strongest. These are observability tiers, NOT event
# classifications: "high_confidence_disturbance" is still not, by itself, a
# confirmed dredging / landslide / earthwork.
TIER_RADAR_CHANGE = "radar_change_candidate"
TIER_SURFACE_DECORRELATION = "surface_decorrelation_candidate"
TIER_CORROBORATED_SURFACE = "corroborated_surface_change_candidate"
TIER_HIGH_CONFIDENCE = "high_confidence_disturbance"
TIER_MEASURED_ELEVATION = "measured_elevation_or_volume_change"
TIER_CONFIRMED = "confirmed_classified_event"
EVIDENCE_TIERS = (
    TIER_RADAR_CHANGE,
    TIER_SURFACE_DECORRELATION,
    TIER_CORROBORATED_SURFACE,
    TIER_HIGH_CONFIDENCE,
    TIER_MEASURED_ELEVATION,
    TIER_CONFIRMED,
)

# ── Detection signals ────────────────────────────────────────────────────────
# Atomic signals a detector may raise. They combine into an evidence tier via
# DETECTION_STATE_INTERPRETATION.
SIGNAL_SAR_AMPLITUDE = "sar_amplitude_change"
SIGNAL_COHERENCE_LOSS = "coherence_loss"
SIGNAL_OPTICAL_CHANGE = "optical_change"
SIGNAL_TERRAIN_MORPHOLOGY = "terrain_morphology"
SIGNAL_MULTI_EPOCH_LIDAR = "multi_epoch_lidar_elevation"
SIGNAL_FIELD_CONFIRMATION = "field_or_authoritative_record"

# Map a frozenset of raised signals -> the tier they are permitted to establish.
# Coherence loss or SAR amplitude *alone* is only ever a candidate — this is the
# brief's correction #2 encoded as data.
DETECTION_STATE_INTERPRETATION = {
    frozenset({SIGNAL_SAR_AMPLITUDE}): TIER_RADAR_CHANGE,
    frozenset({SIGNAL_COHERENCE_LOSS}): TIER_SURFACE_DECORRELATION,
    frozenset({SIGNAL_SAR_AMPLITUDE, SIGNAL_OPTICAL_CHANGE}): TIER_CORROBORATED_SURFACE,
    frozenset(
        {SIGNAL_COHERENCE_LOSS, SIGNAL_OPTICAL_CHANGE}
    ): TIER_CORROBORATED_SURFACE,
    frozenset(
        {SIGNAL_SAR_AMPLITUDE, SIGNAL_OPTICAL_CHANGE, SIGNAL_TERRAIN_MORPHOLOGY}
    ): TIER_HIGH_CONFIDENCE,
    frozenset(
        {SIGNAL_COHERENCE_LOSS, SIGNAL_OPTICAL_CHANGE, SIGNAL_TERRAIN_MORPHOLOGY}
    ): TIER_HIGH_CONFIDENCE,
    frozenset({SIGNAL_MULTI_EPOCH_LIDAR}): TIER_MEASURED_ELEVATION,
    frozenset({SIGNAL_FIELD_CONFIRMATION}): TIER_CONFIRMED,
}

# ── Reconciliation states (physical observation <-> contract record) ─────────
# Deliberately does NOT include a state meaning "work did not occur". The
# absence of a detected signal is NO_SIGNAL_DETECTED, which the brief is emphatic
# must never be read as proof of non-performance.
CONSISTENT = "CONSISTENT"
PARTIALLY_CONSISTENT = "PARTIALLY_CONSISTENT"
NO_SIGNAL_DETECTED = "NO_SIGNAL_DETECTED"
SIGNAL_OUTSIDE_CONTRACT_PERIOD = "SIGNAL_OUTSIDE_CONTRACT_PERIOD"
INSUFFICIENT_OBSERVABILITY = "INSUFFICIENT_OBSERVABILITY"
CONTRADICTORY_RECORDS = "CONTRADICTORY_RECORDS"
NOT_ASSESSABLE = "NOT_ASSESSABLE"
RECONCILIATION_STATES = (
    CONSISTENT,
    PARTIALLY_CONSISTENT,
    NO_SIGNAL_DETECTED,
    SIGNAL_OUTSIDE_CONTRACT_PERIOD,
    INSUFFICIENT_OBSERVABILITY,
    CONTRADICTORY_RECORDS,
    NOT_ASSESSABLE,
)

# ── Adjudication decisions ───────────────────────────────────────────────────
DECISION_PROMOTE = "promote"
DECISION_DOWNGRADE = "downgrade"
DECISION_CONFIRM = "confirm"
DECISION_REJECT = "reject"
DECISION_HOLD = "hold"
ADJUDICATION_DECISIONS = (
    DECISION_PROMOTE,
    DECISION_DOWNGRADE,
    DECISION_CONFIRM,
    DECISION_REJECT,
    DECISION_HOLD,
)

# ── Confidence model (brief's scoring table) ─────────────────────────────────
# Component -> maximum contribution. Sums to 100.
CONFIDENCE_COMPONENTS = {
    "sensor_quality": 15,
    "registration_reliability": 15,
    "temporal_persistence": 15,
    "independent_corroboration": 20,
    "terrain_hydro_consistency": 10,
    "authoritative_correlation": 15,
    "human_adjudication": 10,
}

# Classification bands: (min_score_inclusive, label). Highest first.
CONFIDENCE_BANDS = (
    (85, "high_confidence_change"),
    (70, "corroborated_change"),
    (50, "supported_candidate"),
    (30, "candidate"),
    (0, "weak_signal"),
)

# Puerto Rico envelope (loose), matching schemas/satellite_source_manifest defs.
PR_BOUNDS = {
    "min_lat": 17.8,
    "max_lat": 18.7,
    "min_lon": -68.2,
    "max_lon": -65.1,
}
