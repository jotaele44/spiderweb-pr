from __future__ import annotations

import json
from pathlib import Path

import spiderweb.execution_orchestrator as mod


def _plan():
    return {
        "schema_version": "spiderweb.location_query_plan.v1.1",
        "provider_registry_sha256": "a" * 64,
        "query": {"query_id": "x", "mode": "fetch"},
        "fetch_gate": "READY",
        "request_count": 1,
        "requests": [{"provider_id": "GENERIC", "request_role": "x"}],
        "specialized_call_count": 1,
        "specialized_calls": [{"provider_id": "NASA_GIBS_IMAGERY", "execution_kind": "IMAGERY_PROVIDER_CALL"}],
        "specialized_executor_provider_ids": ["NASA_GIBS_IMAGERY"],
    }


def test_unified_runner_composes_separate_receipts(monkeypatch, tmp_path: Path) -> None:
    seen = {}

    def fake_generic(plan, output_dir, timeout=0):
        seen["generic_plan"] = plan
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {"state": "PASS", "request_count": 1}
        (output_dir / "fetch_receipt.json").write_text(json.dumps(result), encoding="utf-8")
        return result

    def fake_specialized(plan, output_dir):
        seen["specialized_plan"] = plan
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {"state": "PASS", "call_count": 1}
        (output_dir / "specialized_receipt.json").write_text(json.dumps(result), encoding="utf-8")
        return result

    monkeypatch.setattr(mod, "execute_generic", fake_generic)
    monkeypatch.setattr(mod, "execute_specialized_calls", fake_specialized)

    plan = _plan()
    result = mod.execute_location_query(plan, tmp_path)
    assert result["state"] == "PASS"
    assert seen["generic_plan"]["specialized_calls"] == []
    assert seen["specialized_plan"] == plan
    assert result["arithmetic"]["generic_request_count_closed"] is True
    assert result["arithmetic"]["specialized_call_count_closed"] is True
    assert (tmp_path / "run_receipt.json").is_file()


def test_unified_runner_preserves_partial_top_level_gate(monkeypatch, tmp_path: Path) -> None:
    def fake_generic(plan, output_dir, timeout=0):
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {"state": "PARTIAL", "request_count": 1}
        (output_dir / "fetch_receipt.json").write_text(json.dumps(result), encoding="utf-8")
        return result

    def fake_specialized(plan, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {"state": "PASS", "call_count": 1}
        (output_dir / "specialized_receipt.json").write_text(json.dumps(result), encoding="utf-8")
        return result

    monkeypatch.setattr(mod, "execute_generic", fake_generic)
    monkeypatch.setattr(mod, "execute_specialized_calls", fake_specialized)
    plan = _plan()
    plan["fetch_gate"] = "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS"
    assert mod.execute_location_query(plan, tmp_path)["state"] == "PARTIAL"


def test_specialized_only_plan_skips_generic_network_executor(monkeypatch, tmp_path: Path) -> None:
    calls = {"generic": 0, "specialized": 0}

    def fail_generic(plan, output_dir, timeout=0):
        calls["generic"] += 1
        raise AssertionError("generic executor must not run for zero-request plan")

    def fake_specialized(plan, output_dir):
        calls["specialized"] += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        result = {"state": "PASS", "call_count": 1}
        (output_dir / "specialized_receipt.json").write_text(json.dumps(result), encoding="utf-8")
        return result

    monkeypatch.setattr(mod, "execute_generic", fail_generic)
    monkeypatch.setattr(mod, "execute_specialized_calls", fake_specialized)

    plan = _plan()
    plan["request_count"] = 0
    plan["requests"] = []
    result = mod.execute_location_query(plan, tmp_path)

    assert result["state"] == "PASS"
    assert calls["generic"] == 0
    assert calls["specialized"] == 1
    assert result["arithmetic"]["planned_generic_requests"] == 0
    assert result["arithmetic"]["executed_generic_requests"] == 0

    generic = json.loads(
        (tmp_path / "generic" / "fetch_receipt.json").read_text(encoding="utf-8")
    )
    assert generic["execution_scope"] == "NO_GENERIC_REQUESTS"
    assert generic["request_count"] == 0
    assert generic["state"] == "PASS"
