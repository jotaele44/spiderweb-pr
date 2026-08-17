import json
from pathlib import Path

import pytest

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


def test_exact_replay_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _run(monkeypatch, _payload()) == 0
    files = list((tmp_path / "data" / "centinelas_handoffs").glob("*.json"))
    assert len(files) == 1
    before = files[0].read_bytes()
    assert _run(monkeypatch, _payload()) == 0
    assert files[0].read_bytes() == before


def test_same_lead_changed_payload_is_rejected_and_preserved(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _run(monkeypatch, _payload()) == 0
    with pytest.raises(SystemExit, match="collision/fork rejected"):
        _run(monkeypatch, _payload("CHANGED TITLE"))
    collisions = list((tmp_path / "data" / "centinelas_handoffs").glob("*.collision.json"))
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
