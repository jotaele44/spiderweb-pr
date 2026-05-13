"""Tests for earthgpt.seam_graph and earthgpt.seam_chain."""


def test_build_seam_graph_empty():
    from earthgpt.seam_graph import build_seam_graph
    result = build_seam_graph([], zoom=15)
    assert result == []


def test_build_seam_graph_adjacent_anomalies():
    from earthgpt.seam_graph import build_seam_graph
    nodes = [
        {"x": 10, "y": 10, "zoom": 15, "score": 0.8, "tile_type": "land"},
        {"x": 10, "y": 11, "zoom": 15, "score": 0.75, "tile_type": "land"},
    ]
    seams = build_seam_graph(nodes, zoom=15, threshold=0.4)
    assert len(seams) >= 1
    s = seams[0]
    assert "seam_score" in s
    assert "seam_id" in s
    assert "angle_deg" in s
    assert 0.0 <= s["seam_score"] <= 1.0


def test_build_seam_graph_no_seam_below_threshold():
    from earthgpt.seam_graph import build_seam_graph
    nodes = [
        {"x": 10, "y": 10, "zoom": 15, "score": 0.1, "tile_type": "land"},
        {"x": 10, "y": 11, "zoom": 15, "score": 0.2, "tile_type": "land"},
    ]
    seams = build_seam_graph(nodes, zoom=15, threshold=0.5)
    assert seams == []


def test_build_seam_graph_water_penalty():
    from earthgpt.seam_graph import build_seam_graph
    nodes = [
        {"x": 5, "y": 5, "zoom": 15, "score": 0.9, "tile_type": "water"},
        {"x": 5, "y": 6, "zoom": 15, "score": 0.9, "tile_type": "water"},
    ]
    seams = build_seam_graph(nodes, zoom=15, threshold=0.4)
    assert len(seams) >= 1
    # Water tiles get penalized — seam_score should be < raw 0.9
    assert seams[0]["seam_score"] < 0.9


def test_build_seam_chains_empty():
    from earthgpt.seam_chain import build_seam_chains
    result = build_seam_chains([])
    assert result == []


def test_build_seam_chains_single():
    from earthgpt.seam_chain import build_seam_chains
    seams = [
        {"seam_id": "1_1_1_2", "x1": 1, "y1": 1, "x2": 1, "y2": 2, "seam_score": 0.7}
    ]
    chains = build_seam_chains(seams)
    assert len(chains) == 1
    assert chains[0]["seam_count"] == 1
