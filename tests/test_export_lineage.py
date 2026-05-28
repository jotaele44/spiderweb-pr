"""
Federation export contract — lineage, confidence, ID determinism, and timestamp tests.

For every row in every fixture stream:
  - source_id is present and non-empty
  - lineage is a non-empty list of well-formed {step, actor, ts} steps
  - confidence.score is in [0, 1] and method is non-empty
  - the required timestamp is ISO-8601 with a timezone offset
  - the stored id matches compute_row_id (deterministic-id contract)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "valid_airspace_export"

sys.path.insert(0, str(REPO_ROOT))
from scripts.validate_export import compute_row_id  # noqa: E402

STREAMS = {
    "airspace_events.jsonl": "event_time",
    "observations.jsonl":    "observed_at",
    "tracks.jsonl":          "observed_at",
    "sources.jsonl":         "first_seen_at",
}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _all_rows() -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    for fname in STREAMS:
        for row in _read_jsonl(FIXTURE_DIR / fname):
            rows.append((fname, row))
    return rows


@pytest.mark.parametrize("fname,row", _all_rows())
def test_source_id_present(fname, row):
    assert isinstance(row.get("source_id"), str) and row["source_id"], f"{fname}: missing source_id"


@pytest.mark.parametrize("fname,row", _all_rows())
def test_lineage_chain_well_formed(fname, row):
    lineage = row.get("lineage")
    assert isinstance(lineage, list) and len(lineage) >= 1, f"{fname}: lineage missing/empty"
    for i, step in enumerate(lineage):
        assert isinstance(step, dict), f"{fname}: lineage[{i}] not an object"
        assert step.get("step"), f"{fname}: lineage[{i}].step missing"
        assert step.get("actor"), f"{fname}: lineage[{i}].actor missing"
        assert step.get("ts"), f"{fname}: lineage[{i}].ts missing"


@pytest.mark.parametrize("fname,row", _all_rows())
def test_confidence_well_formed(fname, row):
    conf = row.get("confidence")
    assert isinstance(conf, dict), f"{fname}: confidence missing"
    score = conf.get("score")
    assert isinstance(score, (int, float)) and 0.0 <= score <= 1.0, f"{fname}: confidence.score out of range"
    assert isinstance(conf.get("method"), str) and conf["method"], f"{fname}: confidence.method missing"


@pytest.mark.parametrize("fname,row", _all_rows())
def test_required_timestamp_is_tz_aware_iso8601(fname, row):
    field = STREAMS[fname]
    ts = row.get(field)
    assert isinstance(ts, str), f"{fname}: {field} missing"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo is not None, f"{fname}: {field} must be timezone-aware"


@pytest.mark.parametrize("fname,row", _all_rows())
def test_id_is_deterministic(fname, row):
    stored = row.get("id")
    recomputed = compute_row_id(row)
    assert stored == recomputed, f"{fname}: stored id {stored!r} != recomputed {recomputed!r}"
