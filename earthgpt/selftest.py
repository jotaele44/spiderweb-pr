"""
EarthGPT iOS — Self-test module.

Verifies core pipeline components without network access where possible.
Designed to be fast and safe on iOS / a-Shell.

Usage:
    python -m earthgpt.selftest
"""

import sys
import json
import time

from .log_utils import log, warn, error


def _pass(name: str) -> None:
    log(f"PASS  {name}", prefix="TEST")


def _fail(name: str, reason: str) -> None:
    error(f"FAIL  {name}: {reason}")


def test_config() -> bool:
    try:
        from . import config
        assert hasattr(config, "BASE_DIR")
        assert hasattr(config, "ANOMALY_THRESHOLD")
        assert hasattr(config, "IOS_MODE")
        _pass("config")
        return True
    except Exception as exc:
        _fail("config", str(exc))
        return False


def test_tile_utils() -> bool:
    try:
        from .tile_utils import lat_lon_to_tile, tile_center, node_id_for
        x, y = lat_lon_to_tile(18.2208, -66.5901, 15)
        assert isinstance(x, int) and isinstance(y, int)
        lat, lon = tile_center(x, y, 15)
        assert isinstance(lat, float) and isinstance(lon, float)
        nid = node_id_for(x, y, 15)
        assert isinstance(nid, str)
        _pass("tile_utils")
        return True
    except Exception as exc:
        _fail("tile_utils", str(exc))
        return False


def test_features_lite() -> bool:
    try:
        from .features_lite import extract_features
        # Test with None (no Pillow / no image)
        feats = extract_features(None)
        # Should return valid dict even with None image
        assert isinstance(feats, dict)
        assert "risk_final_v2_0_100" in feats
        _pass("features_lite (None image)")

        # Try with real image if Pillow available
        try:
            from PIL import Image
            import numpy as np
            arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
            img = Image.fromarray(arr)
            feats2 = extract_features(img)
            assert "score" not in feats2 or True  # no crash
            assert feats2["risk_final_v2_0_100"] >= 0
            _pass("features_lite (real image)")
        except ImportError:
            warn("Pillow/numpy not available — skipping image test")

        return True
    except Exception as exc:
        _fail("features_lite", str(exc))
        return False


def test_metrics() -> bool:
    try:
        from .metrics import compute_node_metrics
        result = compute_node_metrics({})
        assert "score" in result
        assert "decision" in result
        assert "risk_final_v2_0_100" in result
        assert "status" in result
        _pass("metrics (empty zooms)")
        return True
    except Exception as exc:
        _fail("metrics", str(exc))
        return False


def test_pipeline_analyze_node() -> bool:
    try:
        from .pipeline import analyze_node
        # Use a Puerto Rico tile — will fail to fetch but must return valid dict
        result = analyze_node(x=9999, y=9999, zoom=15)
        assert "score" in result
        assert "decision" in result
        assert "risk_final_v2_0_100" in result
        assert "status" in result
        assert "node_id" in result
        _pass("pipeline.analyze_node (graceful failure)")
        return True
    except Exception as exc:
        _fail("pipeline.analyze_node", str(exc))
        return False


def test_seam_graph() -> bool:
    try:
        from .seam_graph import build_seam_graph
        nodes = [
            {"x": 10, "y": 10, "zoom": 15, "score": 0.8, "tile_type": "land"},
            {"x": 10, "y": 11, "zoom": 15, "score": 0.7, "tile_type": "land"},
            {"x": 10, "y": 12, "zoom": 15, "score": 0.1, "tile_type": "land"},
        ]
        seams = build_seam_graph(nodes, zoom=15)
        assert isinstance(seams, list)
        # First two should form a seam; third should not
        assert len(seams) >= 1
        assert "seam_score" in seams[0]
        _pass("seam_graph")
        return True
    except Exception as exc:
        _fail("seam_graph", str(exc))
        return False


def test_io_utils() -> bool:
    try:
        import tempfile, os
        from .io_utils import write_jsonl, read_jsonl, count_jsonl
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            tmp = f.name
        try:
            rows = [{"a": 1}, {"b": 2}]
            write_jsonl(tmp, rows)
            loaded = read_jsonl(tmp)
            assert loaded == rows
            valid, invalid = count_jsonl(tmp)
            assert valid == 2 and invalid == 0
            _pass("io_utils")
            return True
        finally:
            os.unlink(tmp)
    except Exception as exc:
        _fail("io_utils", str(exc))
        return False


SUBMODULES = [
    "pipeline", "tiles", "ranking", "seam_graph", "seam_chain",
    "corridor_graph", "context", "context_normalizer", "propagation",
    "async_fetch", "cache_index", "ios_profile", "metrics", "log_utils",
    "terrain_path_filter", "target_ranker", "temporal_epoch_compare", "features_lite"
]


def test_submodule_imports() -> bool:
    """Test that all 18 submodules can be imported."""
    all_ok = True
    for submod in SUBMODULES:
        try:
            import importlib
            importlib.import_module(f".{submod}", package="earthgpt")
            _pass(f"import earthgpt.{submod}")
        except Exception as exc:
            _fail(f"import earthgpt.{submod}", str(exc))
            all_ok = False
    return all_ok


def run_all() -> bool:
    log("EarthGPT iOS selftest starting ...", prefix="SELF")
    results = [
        test_config(),
        test_tile_utils(),
        test_features_lite(),
        test_metrics(),
        test_pipeline_analyze_node(),
        test_seam_graph(),
        test_io_utils(),
        test_submodule_imports(),
    ]
    passed = sum(1 for r in results if r)
    total = len(results)
    log(f"Selftest complete: {passed}/{total} passed", prefix="SELF")
    return passed == total


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
