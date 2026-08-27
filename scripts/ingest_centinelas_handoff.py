#!/usr/bin/env python3
"""Durably ingest one idempotent Centinelas handoff envelope.

Project-lead receipts are immutable. An exact replay is idempotent; reuse of the
same idempotency key with different protected payload bytes is a collision/fork
and fails closed. Correlation handles never acquire identity semantics here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _receipt(payload: dict[str, Any]) -> dict[str, Any]:
    signal = payload.get("signal")
    project_lead = signal.get("project_lead") if isinstance(signal, dict) else None
    lead_id = str(payload.get("lead_id") or "")
    if isinstance(project_lead, dict):
        embedded = str(project_lead.get("lead_id") or "")
        if not embedded or not lead_id or embedded != lead_id:
            raise SystemExit("project lead_id mismatch")
    return {
        "receipt_schema": "centinelas_handoff_receipt/v2",
        "target": payload.get("target"),
        "item_id": payload.get("item_id"),
        "idempotency_key": payload.get("idempotency_key"),
        "lead_id": lead_id or None,
        "identity_effect": "NONE",
        "payload_sha256": _sha256(payload),
        "payload": payload,
    }


def main() -> int:
    payload = json.loads(os.environ["CENTINELAS_CLIENT_PAYLOAD"])
    key = str(payload["idempotency_key"])
    if payload["target"] != os.environ["EXPECTED_TARGET"]:
        raise SystemExit("handoff target mismatch")

    out = (
        Path("data/centinelas_handoffs")
        / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    )
    candidate = _receipt(payload)
    duplicate = False
    collision = False
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists():
        duplicate = True
        existing = json.loads(out.read_text(encoding="utf-8"))
        # Backward-compatible generic receipts may predate receipt_schema/v2. They
        # are compared against the original envelope. Never rewrite them silently.
        if existing.get("receipt_schema") == "centinelas_handoff_receipt/v2":
            same = existing.get("payload_sha256") == candidate["payload_sha256"]
        else:
            same = _sha256(existing) == candidate["payload_sha256"]
        if not same:
            collision = True
            evidence = out.with_suffix(".collision.json")
            evidence.write_text(
                json.dumps(
                    {
                        "collision_schema": "centinelas_handoff_collision/v1",
                        "identity_effect": "NONE",
                        "existing_receipt": str(out),
                        "incoming_payload_sha256": candidate["payload_sha256"],
                        "incoming_payload": payload,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            raise SystemExit(f"handoff collision/fork rejected; evidence={evidence}")
    else:
        out.write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(
                f"duplicate={str(duplicate).lower()}\n"
                f"collision={str(collision).lower()}\n"
                f"receipt_path={out}\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
