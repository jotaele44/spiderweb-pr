from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "data" / "jp_flood_documents" / "producer_contract_v1.json"
EXPECTED_CONTRACT_SHA256 = "f665aba3176f9defbdce322b1e480c8db596df666ea130ccb435bf46a66a2e78"


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode() + data
    return hashlib.sha1(payload).hexdigest()


def test_jp_flood_producer_contract_bytes_and_bindings() -> None:
    raw = CONTRACT_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_CONTRACT_SHA256

    contract = json.loads(raw)
    assert contract["schema_version"] == "jp-flood-producer-contract/1.0"
    assert contract["producer"] == "spiderweb-pr"
    assert contract["producer_merge_sha"] == "d6326c04e8ecc585b4068f8252a903246498dbb3"

    script = contract["acquisition_script"]
    assert _git_blob_sha(ROOT / script["path"]) == script["git_blob_sha"]

    q = contract["quebradillas_receipt"]
    assert _git_blob_sha(ROOT / q["path"]) == q["git_blob_sha"]
    assert q["pdf_sha256"] == "a1a2ccbfe0097da6f531e78f834d01be5a1555700b809d8f68b162db83d23e7a"
    assert q["pdf_byte_size"] == 51_199_142

    source = contract["source_contract"]
    assert source["municipalities"] == 78
    assert source["series_listed"] == 77
    assert source["series_available"] == 76
    assert source["listed_but_missing"] == 1
    assert source["not_listed"] == 1
    assert source["operational_coverage"] == 78
    assert source["series_available"] + source["listed_but_missing"] + source["not_listed"] == 78

    rules = contract["identity_rules"]
    assert rules["quebradillas_source_state"] == "LISTED_BUT_MISSING"
    assert rules["florida_source_state"] == "NOT_LISTED"
    assert rules["fallback_is_not_equivalent_series_member"] is True
