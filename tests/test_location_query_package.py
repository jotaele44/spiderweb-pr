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



def _spec(role: str = "source") -> dict:
    return {
        "method": "GET",
        "provider_id": "X",
        "request_role": role,
        "identity_state": "SOURCE_MANIFESTATION",
        "url": f"https://example.invalid/{role}",
        "media_type": "application/octet-stream",
    }


def _receipt_request(spec: dict, **extra) -> dict:
    row = {
        "provider_id": spec["provider_id"],
        "request_role": spec["request_role"],
        "request_spec_sha256": mod.canonical_json_sha256(spec),
    }
    row.update(extra)
    return row

def test_package_rehashes_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "source.raw"
    raw.write_bytes(b"abc")
    digest = mod.sha256_file(raw)

    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "provider_denominator_count": 1,
        "requests": [_spec()],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "fetch_gate": "READY",
        "request_count": 1,
        "pass_count": 1,
        "no_coverage_count": 0,
        "failure_count": 0,
        "state": "PASS",
        "requests": [_receipt_request(_spec(), raw_path=str(raw), sha256=digest)],
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
    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "provider_denominator_count": 2,
        "requests": [],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
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
    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "requests": [_spec()],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "fetch_gate": "READY",
        "request_count": 1,
        "failure_count": 0,
        "state": "PASS",
        "requests": [_receipt_request(_spec(), raw_path=str(raw), sha256="0" * 64)],
    })

    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit, match="raw artifact verification failed"):
        mod.main()


def test_package_binds_executor_plan_hash_and_parent_denominator(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "source.raw"
    raw.write_bytes(b"abc")
    digest = mod.sha256_file(raw)

    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "provider_denominator_count": 1,
        "requests": [_spec()],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "fetch_gate": "READY",
        "request_count": 1,
        "pass_count": 1,
        "no_coverage_count": 0,
        "failure_count": 0,
        "state": "PASS",
        "requests": [_receipt_request(
            _spec(),
            raw_path=str(raw),
            sha256=digest,
            parent_denominator_sha256="a" * 64,
        )],
    })

    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    assert mod.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["plan"]["canonical_hash_matches_executor"] is True
    assert result["parent_denominator_hash_count"] == 1
    assert result["parent_denominator_sha256"] == ["a" * 64]


def test_package_rejects_executor_plan_hash_drift(tmp_path: Path, monkeypatch) -> None:
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, {
        "query": {"query_id": "q", "mode": "fetch"},
        "requests": [],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    })
    _write(receipt_path, {
        "plan_sha256": "0" * 64,
        "fetch_gate": "READY",
        "request_count": 0,
        "failure_count": 0,
        "state": "PASS",
        "requests": [],
    })
    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit, match="plan SHA drift"):
        mod.main()


def test_package_supports_discovery_stage_receipt(tmp_path: Path, monkeypatch) -> None:
    plan = {
        "query": {"query_id": "q", "mode": "plan"},
        "provider_denominator_count": 1,
        "requests": [],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "execution_scope": "DISCOVERY_OR_RESOLVER_STAGE",
        "fetch_gate": "DISCOVERY_ONLY",
        "request_count": 0,
        "pass_count": 0,
        "no_coverage_count": 0,
        "failure_count": 0,
        "state": "DISCOVERY_PASS",
        "requests": [],
    })
    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    assert mod.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["state"] == "DISCOVERY_PASS"


def test_package_rejects_missing_executor_plan_hash(tmp_path: Path, monkeypatch) -> None:
    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, plan)
    _write(receipt_path, {
        "fetch_gate": "READY",
        "request_count": 0,
        "failure_count": 0,
        "state": "PASS",
        "requests": [],
    })
    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit, match="lacks a valid executor plan SHA256"):
        mod.main()


def test_package_rejects_duplicate_raw_artifact_path(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "source.raw"
    raw.write_bytes(b"abc")
    digest = mod.sha256_file(raw)
    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "requests": [],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "fetch_gate": "READY",
        "request_count": 2,
        "pass_count": 2,
        "failure_count": 0,
        "state": "PASS",
        "requests": [
            _receipt_request(spec_a, raw_path=str(raw), sha256=digest),
            _receipt_request(spec_b, raw_path=str(raw), sha256=digest),
        ],
    })
    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit, match="duplicate raw artifact path"):
        mod.main()


def test_package_refuses_manifest_overwrite(tmp_path: Path, monkeypatch) -> None:
    spec_a = _spec("a")
    spec_b = _spec("b")
    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "requests": [spec_a, spec_b],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "fetch_gate": "READY",
        "request_count": 0,
        "pass_count": 0,
        "failure_count": 0,
        "state": "PASS",
        "requests": [],
    })
    output.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit, match="package manifest already exists"):
        mod.main()


def test_package_rejects_missing_executed_request(tmp_path: Path, monkeypatch) -> None:
    spec_a = _spec("a")
    spec_b = _spec("b")
    plan = {
        "query": {"query_id": "q", "mode": "fetch"},
        "requests": [spec_a, spec_b],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "fetch_gate": "READY",
        "request_count": 1,
        "pass_count": 1,
        "failure_count": 0,
        "state": "PASS",
        "requests": [_receipt_request(spec_a)],
    })
    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit, match="request-spec vector mismatch"):
        mod.main()


def test_package_discovery_scope_matches_only_discovery_subset(tmp_path: Path, monkeypatch) -> None:
    discovery = {
        "method": "GET",
        "provider_id": "X",
        "request_role": "metadata",
        "identity_state": "DISCOVERY_FOR_LAYER_DENOMINATOR",
        "url": "https://example.invalid/metadata",
        "media_type": "application/json",
    }
    production = _spec("production")
    plan = {
        "query": {"query_id": "q", "mode": "plan"},
        "requests": [discovery, production],
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True},
    }
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "fetch_receipt.json"
    output = tmp_path / "package.json"
    _write(plan_path, plan)
    _write(receipt_path, {
        "plan_sha256": mod.canonical_json_sha256(plan),
        "execution_scope": "DISCOVERY_OR_RESOLVER_STAGE",
        "fetch_gate": "DISCOVERY_ONLY",
        "request_count": 1,
        "pass_count": 1,
        "no_coverage_count": 0,
        "failure_count": 0,
        "state": "DISCOVERY_PASS",
        "requests": [_receipt_request(discovery)],
    })
    monkeypatch.setattr(
        "sys.argv",
        ["location_query_package.py", str(plan_path), str(receipt_path), "--output", str(output)],
    )
    assert mod.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["invariants"]["request_spec_vector_equal"] is True
    assert result["planned_request_count_for_execution_scope"] == 1
