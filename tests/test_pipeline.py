"""Tests for earthgpt.pipeline and io_utils."""

import os
import tempfile


def test_analyze_node_always_returns_valid_dict():
    from earthgpt.pipeline import analyze_node
    result = analyze_node(x=99999, y=99999, zoom=15)
    assert isinstance(result, dict)
    assert "score" in result
    assert "decision" in result
    assert "risk_final_v2_0_100" in result
    assert "status" in result
    assert "node_id" in result
    assert "lat" in result
    assert "lon" in result


def test_analyze_node_required_fields():
    from earthgpt.pipeline import analyze_node
    result = analyze_node(x=1, y=1, zoom=15, lat=18.0, lon=-66.0)
    assert result["x"] == 1
    assert result["y"] == 1
    assert result["zoom"] == 15
    assert abs(result["lat"] - 18.0) < 0.001 or result["lat"] == 18.0


def test_io_utils_write_read_roundtrip():
    from earthgpt.io_utils import write_jsonl, read_jsonl
    rows = [{"a": 1, "b": "hello"}, {"a": 2, "b": "world"}]
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = f.name
    try:
        write_jsonl(tmp, rows)
        loaded = read_jsonl(tmp)
        assert loaded == rows
    finally:
        os.unlink(tmp)


def test_io_utils_tolerates_empty_file():
    from earthgpt.io_utils import read_jsonl
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = f.name
    try:
        result = read_jsonl(tmp)
        assert result == []
    finally:
        os.unlink(tmp)


def test_io_utils_tolerates_malformed_lines():
    from earthgpt.io_utils import read_jsonl, count_jsonl
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        f.write('{"a": 1}\n')
        f.write("not json\n")
        f.write('{"b": 2}\n')
        tmp = f.name
    try:
        rows = read_jsonl(tmp)
        assert len(rows) == 2  # only valid rows
        valid, invalid = count_jsonl(tmp)
        assert valid == 2
        assert invalid == 1
    finally:
        os.unlink(tmp)


def test_corridor_candidates_empty():
    from earthgpt.corridor_graph import build_corridor_candidates
    result = build_corridor_candidates([], seams=[])
    assert result == []


def test_target_ranker_empty():
    from earthgpt.target_ranker import run_target_ranker
    result = run_target_ranker([])
    assert result == []
