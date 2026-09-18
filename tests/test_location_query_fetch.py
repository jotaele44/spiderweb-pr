from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "location_query_fetch.py"
spec = importlib.util.spec_from_file_location("location_query_fetch", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_executor_rejects_plan_mode_before_network(tmp_path: Path) -> None:
    plan = {
        "query": {"mode": "plan"},
        "requests": [{
            "method": "GET",
            "provider_id": "X",
            "request_role": "should_not_execute",
            "url": "https://example.invalid/",
        }],
    }
    with pytest.raises(SystemExit, match="requires query.mode=fetch"):
        mod.execute(plan, tmp_path)


def test_executor_accepts_empty_fetch_plan_without_network(tmp_path: Path) -> None:
    plan = {"query": {"mode": "fetch"}, "requests": []}
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PASS"
    assert result["query_mode"] == "fetch"
    assert result["request_count"] == 0
    assert result["raw_bytes_preserved_before_derivation"] is True


def test_safe_name_is_deterministic() -> None:
    assert mod.safe_name("USFWS_NWI", "wetlands", 1) == "001_USFWS_NWI_wetlands"
