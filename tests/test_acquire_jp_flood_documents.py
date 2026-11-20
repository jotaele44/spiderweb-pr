from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "acquire_jp_flood_documents.py"
spec = importlib.util.spec_from_file_location("jp_flood_docs", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

def _series_html() -> str:
    links = []
    for municipality in mod.CANONICAL_MUNICIPALITIES:
        if municipality == "Florida":
            continue
        filename = municipality.replace(" ", "_") + "_sectores_inundables.pdf"
        links.append(f'<a href="/uploads/Mapas Inundacion/{filename}">{municipality}</a>')
    return "\n".join(links)

def test_source_state_contract_closes_78() -> None:
    rows = mod.apply_source_states(mod.discover_series(_series_html()))
    mod.validate(rows)
    assert len(rows) == 78
    assert sum(r["source_state"] == "AVAILABLE" for r in rows) == 76
    assert sum(r["source_state"] == "LISTED_BUT_MISSING" for r in rows) == 1
    assert sum(r["source_state"] == "NOT_LISTED" for r in rows) == 1

def test_quebradillas_is_listed_but_missing_and_frozen() -> None:
    rows = mod.apply_source_states(mod.discover_series(_series_html()))
    q = next(r for r in rows if r["municipality"] == "Quebradillas")
    assert q["source_state"] == "LISTED_BUT_MISSING"
    assert q["source_url"]
    assert q["fallback_document_class"] == "hazard_mitigation_plan"
    assert q["fallback_relationship"] == "authoritative_fallback_not_equivalent"
    assert q["fallback_operational_mode"] == "frozen_local_manifestation"
    assert q["fallback_source_url"] == mod.QUEBRADILLAS_HMP_PROVENANCE_URL
    assert q["frozen_manifestation"] == {
        "filename": "Quebradillas.pdf",
        "byte_size": 51_199_142,
        "sha256": "a1a2ccbfe0097da6f531e78f834d01be5a1555700b809d8f68b162db83d23e7a",
        "identity_scope": "byte_manifestation",
    }

def test_florida_is_not_listed() -> None:
    rows = mod.apply_source_states(mod.discover_series(_series_html()))
    f = next(r for r in rows if r["municipality"] == "Florida")
    assert f["source_state"] == "NOT_LISTED"
    assert f["source_url"] is None
    assert f["fallback_document_class"] == "hazard_mitigation_plan"
    assert f["fallback_operational_mode"] == "remote_fetch"

def test_verify_frozen_quebradillas_passes_without_remote_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"offline-frozen-quebradillas-fixture"
    p = tmp_path / "Quebradillas.pdf"
    p.write_bytes(payload)
    monkeypatch.setattr(mod, "QUEBRADILLAS_FROZEN_BYTE_SIZE", len(payload))
    monkeypatch.setattr(mod, "QUEBRADILLAS_FROZEN_SHA256", hashlib.sha256(payload).hexdigest())
    result = mod.verify_frozen_quebradillas(p)
    assert result["acquisition_status"] == "frozen_local_verified"
    assert result["verification"] == "BYTE_SIZE_AND_SHA256_PASS"

def test_verify_frozen_quebradillas_rejects_wrong_size(tmp_path: Path) -> None:
    p = tmp_path / "Quebradillas.pdf"
    p.write_bytes(b"not-the-frozen-file")
    with pytest.raises(RuntimeError, match="QUEBRADILLAS_SIZE_MISMATCH"):
        mod.verify_frozen_quebradillas(p)

def test_verify_frozen_quebradillas_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="QUEBRADILLAS_FROZEN_MISSING"):
        mod.verify_frozen_quebradillas(tmp_path / "Quebradillas.pdf")

def test_missing_municipality_fails_closed() -> None:
    rows = mod.apply_source_states(mod.discover_series(_series_html()))
    with pytest.raises(AssertionError):
        mod.validate([r for r in rows if r["municipality"] != "Yauco"])
