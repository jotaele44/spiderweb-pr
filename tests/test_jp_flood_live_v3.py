from __future__ import annotations

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_jp_flood_live_v3.py"
spec = importlib.util.spec_from_file_location("jp_flood_live_v3", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _replica(path: Path, *, sha: str = "a" * 64, filename: str = "A.pdf") -> None:
    path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "documents": [
                    {
                        "municipality": "A",
                        "source_state": "AVAILABLE",
                        "operational_document_class": "flood_risk_zone_map",
                        "filename": filename,
                        "byte_size": 123,
                        "sha256": sha,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _baseline(path: Path, *, sha: str = "a" * 64, filename: str = "A.pdf") -> None:
    path.write_text(
        "municipality,source_state,series_document_class,operational_document_class,"
        "fallback_relationship,filename,byte_size,sha256,acquisition_status\n"
        f"A,AVAILABLE,flood_risk_zone_map,flood_risk_zone_map,,{filename},123,{sha},downloaded\n",
        encoding="utf-8",
    )


def test_compare_identical_replica_and_baseline_passes(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    baseline = tmp_path / "baseline.csv"
    report = tmp_path / "report.json"
    _replica(a)
    _replica(b)
    _baseline(baseline)

    assert mod.compare(a, b, baseline, report) == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["blocking_count"] == 0
    assert payload["identical_count"] == 1


def test_compare_remote_byte_change_requires_readjudication(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    baseline = tmp_path / "baseline.csv"
    report = tmp_path / "report.json"
    _replica(a, sha="b" * 64)
    _replica(b, sha="b" * 64)
    _baseline(baseline, sha="a" * 64)

    assert mod.compare(a, b, baseline, report) == 2
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "REQUIRES_READJUDICATION"
    assert payload["classifications"][0]["kind"] == "REMOTE_BYTES_CHANGED"


def test_compare_replica_divergence_requires_readjudication(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    baseline = tmp_path / "baseline.csv"
    report = tmp_path / "report.json"
    _replica(a, sha="a" * 64)
    _replica(b, sha="b" * 64)
    _baseline(baseline, sha="a" * 64)

    assert mod.compare(a, b, baseline, report) == 2
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "REQUIRES_READJUDICATION"
    assert payload["classifications"][0]["kind"] == "REPLICA_DIVERGENCE"


def test_metadata_only_change_is_nonblocking_but_explicit(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    baseline = tmp_path / "baseline.csv"
    report = tmp_path / "report.json"
    _replica(a, filename="renamed.pdf")
    _replica(b, filename="renamed.pdf")
    _baseline(baseline, filename="A.pdf")

    assert mod.compare(a, b, baseline, report) == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["metadata_only_count"] == 1
    assert payload["classifications"][0]["kind"] == "REMOTE_METADATA_CHANGED_ONLY"


def test_transport_blocked_replica_is_not_negative_evidence(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    baseline = tmp_path / "baseline.csv"
    report = tmp_path / "report.json"
    a.write_text(json.dumps({"status": "TRANSPORT_BLOCKED", "documents": []}), encoding="utf-8")
    _replica(b)
    _baseline(baseline)

    assert mod.compare(a, b, baseline, report) == 3
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "TRANSPORT_BLOCKED"
