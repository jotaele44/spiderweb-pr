from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "location_query_package.py"
spec = importlib.util.spec_from_file_location("location_query_package", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def test_package_rehashes_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "source.raw"
    raw.write_bytes(b"abc")
    digest = mod.sha256_file(raw)

    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, {
        "query": {"query_id": "q", "mode": "fetch"},
        "provider_denominator_count": 1,
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    })
    _write(receipt_path, {
        "fetch_gate": "READY",
        "request_count": 1,
        "pass_count": 1,
        "no_coverage_count": 0,
        "failure_count": 0,
        "state": "PASS",
        "requests": [{"raw_path": str(raw), "sha256": digest}],
    })

    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    assert mod.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["state"] == "PASS"
    assert result["raw_artifact_count"] == 1
    assert result["total_raw_bytes"] == 3


def test_package_preserves_partial_execution_state(tmp_path: Path, monkeypatch) -> None:
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, {
        "query": {"query_id": "q", "mode": "fetch"},
        "provider_denominator_count": 2,
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    })
    _write(receipt_path, {
        "fetch_gate": "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS",
        "fetch_blocker_provider_ids": ["X"],
        "request_count": 0,
        "pass_count": 0,
        "no_coverage_count": 0,
        "failure_count": 0,
        "state": "PARTIAL",
        "requests": [],
    })

    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    assert mod.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["state"] == "PARTIAL"
    assert result["fetch_blocker_provider_ids"] == ["X"]


def test_package_fails_when_raw_hash_drifted(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "source.raw"
    raw.write_bytes(b"changed")
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, {
        "query": {"query_id": "q", "mode": "fetch"},
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    })
    _write(receipt_path, {
        "fetch_gate": "READY",
        "request_count": 1,
        "failure_count": 0,
        "state": "PASS",
        "requests": [{"raw_path": str(raw), "sha256": "0" * 64}],
    })

    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit, match="raw artifact verification failed"):
        mod.main()
