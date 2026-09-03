import json
from pathlib import Path

import pytest

from scripts import build_project_physical_assertions as assertions
from scripts import ingest_centinelas_handoff as ingest


def _payload(title="RESIDENCIAL LOS ROSALES"):
    return {
        "item_id": "los-rosales-observed-banner",
        "target": "spiderweb-pr",
        "idempotency_key": "project-lead:prjlead_fixture",
        "lead_id": "prjlead_fixture",
        "signal": {
            "title": title,
            "project_lead": {
                "lead_id": "prjlead_fixture",
                "municipality_candidates": ["Yabucoa"],
                "identity_effect": "NONE",
            },
        },
    }


def _run(monkeypatch, payload):
    monkeypatch.setenv("CENTINELAS_CLIENT_PAYLOAD", json.dumps(payload))
    monkeypatch.setenv("EXPECTED_TARGET", "spiderweb-pr")
    return ingest.main()


def _configure_assertion_paths(monkeypatch, tmp_path):
    receipts = tmp_path / "data" / "centinelas_handoffs"
    package = tmp_path / "exports" / "federation"
    monkeypatch.setattr(assertions, "ROOT", tmp_path)
    monkeypatch.setattr(assertions, "RECEIPTS", receipts)
    monkeypatch.setattr(assertions, "PKG", package)
    monkeypatch.setattr(
        assertions, "OUT", package / "project_physical_assertions.jsonl"
    )
    return receipts, package


def _write_receipt(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_exact_replay_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _run(monkeypatch, _payload()) == 0
    files = list((tmp_path / "data" / "centinelas_handoffs").glob("*.json"))
    assert len(files) == 1
    before = files[0].read_bytes()
    assert _run(monkeypatch, _payload()) == 0
    assert files[0].read_bytes() == before


def test_success_outputs_report_duplicate_and_receipt_path(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert _run(monkeypatch, _payload()) == 0
    assert _run(monkeypatch, _payload()) == 0

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "duplicate=false"
    assert lines[1].startswith("receipt_path=data/centinelas_handoffs/")
    assert lines[2] == "duplicate=true"
    assert lines[3] == lines[1]


def test_same_lead_changed_payload_is_rejected_and_preserved(
    tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert _run(monkeypatch, _payload()) == 0
    with pytest.raises(SystemExit, match="collision/fork rejected"):
        _run(monkeypatch, _payload("CHANGED TITLE"))
    collisions = list(
        (tmp_path / "data" / "centinelas_handoffs").glob("*.collision.json")
    )
    assert len(collisions) == 1
    evidence = json.loads(collisions[0].read_text(encoding="utf-8"))
    assert evidence["collision_schema"] == "centinelas_handoff_collision/v1"
    assert evidence["identity_effect"] == "NONE"


def test_embedded_lead_id_mismatch_fails_closed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = _payload()
    payload["signal"]["project_lead"]["lead_id"] = "prjlead_other"
    with pytest.raises(SystemExit, match="project lead_id mismatch"):
        _run(monkeypatch, payload)


def test_assertion_builder_preserves_full_candidate_set_and_manifest(
    tmp_path: Path, monkeypatch
):
    receipts, package = _configure_assertion_paths(monkeypatch, tmp_path)
    payload = _payload()
    payload["signal"]["project_lead"]["municipality_candidates"] = [
        "Yabucoa",
        "Maunabo",
    ]
    _write_receipt(receipts / "receipt.json", payload)
    package.mkdir(parents=True)
    manifest_path = package / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "mode": "test",
                "files": [
                    {
                        "filename": "entities.jsonl",
                        "stream": "entities",
                        "sha256": "a" * 64,
                    },
                    {
                        "filename": "stale.jsonl",
                        "stream": "project_physical_assertions",
                        "sha256": "b" * 64,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert assertions.main() == 0

    rows = [json.loads(line) for line in assertions.OUT.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["candidate_count"] == 2
    assert rows[0]["unresolved_cardinality"] == 2
    assert [candidate["raw"] for candidate in rows[0]["candidates"]] == [
        "Yabucoa",
        "Maunabo",
    ]
    assert all(
        candidate["spatial_state"] == "UNRESOLVED"
        for candidate in rows[0]["candidates"]
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assertion_files = [
        entry
        for entry in manifest["files"]
        if entry["stream"] == "project_physical_assertions"
    ]
    assert len(assertion_files) == 1
    assert assertion_files[0]["record_count"] == 1
    assert assertion_files[0]["sha256"] == assertions._sha(assertions.OUT)


def test_assertion_builder_refuses_orphan_output(tmp_path: Path, monkeypatch):
    receipts, _ = _configure_assertion_paths(monkeypatch, tmp_path)
    _write_receipt(receipts / "receipt.json", _payload())

    with pytest.raises(SystemExit, match="canonical federation manifest missing"):
        assertions.main()

    assert not assertions.OUT.exists()


def test_assertion_builder_rejects_non_list_candidates(tmp_path: Path, monkeypatch):
    receipts, package = _configure_assertion_paths(monkeypatch, tmp_path)
    payload = _payload()
    payload["signal"]["project_lead"]["municipality_candidates"] = "Yabucoa"
    _write_receipt(receipts / "receipt.json", payload)
    package.mkdir(parents=True)
    (package / "manifest.json").write_text('{"files": []}', encoding="utf-8")

    with pytest.raises(SystemExit, match="municipality_candidates must be a list"):
        assertions.main()

    assert not assertions.OUT.exists()


def test_assertion_builder_rejects_duplicate_lead_ids(tmp_path: Path, monkeypatch):
    receipts, package = _configure_assertion_paths(monkeypatch, tmp_path)
    _write_receipt(receipts / "first.json", _payload())
    _write_receipt(receipts / "second.json", _payload("SECOND OBSERVATION"))
    package.mkdir(parents=True)
    (package / "manifest.json").write_text('{"files": []}', encoding="utf-8")

    with pytest.raises(SystemExit, match="duplicate project lead_id"):
        assertions.main()

    assert not assertions.OUT.exists()
