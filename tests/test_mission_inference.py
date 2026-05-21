"""Tests for MultiFactorMissionScorer probabilities."""

import sqlite3

import pytest

from mission_inference import MultiFactorMissionScorer


def test_scorer_initializes(populated_db):
    scorer = MultiFactorMissionScorer(populated_db)
    assert scorer is not None


def test_score_flight_returns_list(populated_db):
    conn = sqlite3.connect(populated_db)
    conn.row_factory = sqlite3.Row
    flight = dict(conn.execute(
        "SELECT * FROM flights WHERE flight_id = 'FLT_N5854Z_001'"
    ).fetchone())
    track = [dict(r) for r in conn.execute(
        "SELECT * FROM track_points WHERE flight_id = 'FLT_N5854Z_001'"
    )]
    conn.close()

    scorer = MultiFactorMissionScorer(populated_db)
    results = scorer.score_flight(flight, track, [], [])
    assert isinstance(results, list)


def test_score_values_in_range(populated_db):
    conn = sqlite3.connect(populated_db)
    conn.row_factory = sqlite3.Row
    flight = dict(conn.execute(
        "SELECT * FROM flights WHERE flight_id = 'FLT_C6062_001'"
    ).fetchone())
    track = [dict(r) for r in conn.execute(
        "SELECT * FROM track_points WHERE flight_id = 'FLT_C6062_001'"
    )]
    conn.close()

    scorer = MultiFactorMissionScorer(populated_db)
    results = scorer.score_flight(flight, track, [], [])
    for ms in results:
        score = ms.total_score if hasattr(ms, "total_score") else ms.get("total_score", 0)
        assert 0.0 <= float(score) <= 1.0, f"Score {score} out of range"


def test_score_flight_no_track(populated_db):
    conn = sqlite3.connect(populated_db)
    conn.row_factory = sqlite3.Row
    flight = dict(conn.execute(
        "SELECT * FROM flights WHERE flight_id = 'FLT_N767PD_001'"
    ).fetchone())
    conn.close()

    scorer = MultiFactorMissionScorer(populated_db)
    results = scorer.score_flight(flight, [], [], [])
    assert isinstance(results, list)


def test_score_boundary_zero_and_one(populated_db):
    import sqlite3
    conn = sqlite3.connect(populated_db)
    conn.row_factory = sqlite3.Row
    flight = dict(conn.execute(
        "SELECT * FROM flights WHERE flight_id = 'FLT_N5854Z_001'"
    ).fetchone())
    conn.close()

    scorer = MultiFactorMissionScorer(populated_db)
    results = scorer.score_flight(flight, [], [], [])
    for ms in results:
        score = ms.total_score if hasattr(ms, "total_score") else ms.get("total_score", 0)
        assert 0.0 <= float(score) <= 1.0, f"Score {score} outside [0, 1]"


# ── Task 26: all MissionType enum values produce non-zero score ───────────────

import pytest as _pytest

def test_all_mission_types_have_profile():
    """All MissionType values should have a MISSION_PROFILES entry (Task 26)."""
    from mission_inference import MissionType, MISSION_PROFILES
    for mt in MissionType:
        if mt == MissionType.UNKNOWN:
            continue  # UNKNOWN has no profile by design
        assert mt in MISSION_PROFILES, f"MissionType.{mt.name} has no profile"


# ── Task 27: BehavioralClusterer with k=3 and ≥10 points ─────────────────────

def test_behavioral_clusterer_fit_k3():
    """BehavioralClusterer must run fit() with k=3 and ≥10 data points (Task 27)."""
    from mission_inference import BehavioralClusterer, FlightFeatureVector
    clusterer = BehavioralClusterer(n_clusters=3)
    vectors = [
        FlightFeatureVector(
            flight_id=f"FLT-{i:03d}",
            callsign=f"N{1000+i}",
            altitude_norm=float(i % 5) / 5.0,
            speed_norm=float(i % 4) / 4.0,
            duration_norm=0.3,
            altitude_variance_norm=0.1,
            hover_proportion=0.0,
            path_linearity=0.8,
            coverage_area_norm=0.2,
            coastal_proportion=0.1,
            infrastructure_score=0.2,
        )
        for i in range(12)  # 12 >= 10
    ]
    clusterer.fit(vectors)
    assert len(clusterer.centroids) == 3


# ── Task 28: MarkovChainPredictor train + predict round-trip ─────────────────

def test_markov_chain_train_predict():
    """MarkovChainPredictor train() + predict() round-trip with deterministic seq (Task 28)."""
    from mission_inference import MarkovChainPredictor, MissionType
    predictor = MarkovChainPredictor.__new__(MarkovChainPredictor)
    from collections import defaultdict
    predictor.transition_counts = defaultdict(lambda: defaultdict(int))
    predictor.transition_probs = {}
    predictor.db_path = ":memory:"

    # Build a deterministic sequence: N5854Z always goes POWER_INSPECTION → LAW_ENFORCEMENT
    from pathlib import Path
    from datetime import datetime, timedelta
    base = datetime(2024, 3, 14, 8, 0)
    flights = []
    for i in range(6):
        mission = MissionType.POWER_INSPECTION.value if i % 2 == 0 else MissionType.LAW_ENFORCEMENT.value
        flights.append({
            "callsign": "N5854Z",
            "takeoff_time": (base + timedelta(hours=i * 2)).isoformat(),
            "mission_type": mission,
        })
    predictor.train(flights)
    result = predictor.predict(
        callsign="N5854Z",
        hour=8,
        day_of_week=3,
        last_mission=MissionType.POWER_INSPECTION.value,
    )
    assert isinstance(result, dict)
    assert len(result) > 0
    # Top predicted mission should be LAW_ENFORCEMENT
    top = max(result, key=result.get)
    assert top == MissionType.LAW_ENFORCEMENT.value
