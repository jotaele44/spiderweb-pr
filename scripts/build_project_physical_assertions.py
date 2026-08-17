#!/usr/bin/env python3
"""Build and federate SpiderWeb project physical/spatial assertion packets.

The Centinelas lead opens discovery only. Municipality candidates, names, and
proximity remain non-identity evidence; without independently sourced geometry or
stable asset/project IDs the packet is explicitly UNRESOLVED.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / "data" / "centinelas_handoffs"
PKG = ROOT / "exports" / "federation"
OUT = PKG / "project_physical_assertions.jsonl"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sid(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not RECEIPTS.exists():
        return rows
    for path in sorted(RECEIPTS.glob("*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload = receipt.get("payload") if receipt.get("receipt_schema") else receipt
        if not isinstance(payload, dict):
            continue
        signal = payload.get("signal")
        lead = signal.get("project_lead") if isinstance(signal, dict) else None
        if not isinstance(lead, dict) or not lead.get("lead_id"):
            continue
        lead_id = str(lead["lead_id"])
        candidates = [
            {
                "candidate_type": "municipality",
                "raw": raw,
                "spatial_state": "UNRESOLVED",
                "identity_effect": "NONE",
            }
            for raw in (lead.get("municipality_candidates") or [])
        ]
        rows.append(
            {
                "assertion_schema": "project_physical_assertion/v1",
                "assertion_id": _sid("prjphy_", lead_id, "spiderweb-pr"),
                "lead_id": lead_id,
                "producer": "spiderweb-pr",
                "identity_effect": "NONE",
                "binding_state": "UNRESOLVED",
                "candidate_count": len(candidates),
                "candidates": candidates,
                "unresolved_cardinality": len(candidates),
                "geometry": None,
                "geometry_crs": None,
                "independent_binding_evidence": [],
                "lead_snapshot": lead,
                "provenance": {
                    "receipt_path": str(path.relative_to(ROOT)),
                    "receipt_sha256": _sha(path),
                    "method": "centinelas_project_lead_spatial_discovery",
                },
            }
        )
    return sorted(rows, key=lambda r: r["assertion_id"])


def main() -> int:
    rows = _rows()
    if not rows:
        return 0
    PKG.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    manifest_path = PKG / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("canonical federation manifest missing; refusing orphan assertion stream")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = [f for f in manifest.get("files", []) if f.get("stream") != "project_physical_assertions"]
    files.append(
        {
            "filename": OUT.name,
            "stream": "project_physical_assertions",
            "record_count": len(rows),
            "sha256": _sha(OUT),
            "schema_id": "project_physical_assertion/v1",
        }
    )
    manifest["files"] = files
    mode = str(manifest.get("mode") or "test")
    digest = hashlib.sha256(
        ("|".join(f"{f['filename']}:{f['sha256']}" for f in files) + f"|{mode}").encode("utf-8")
    ).hexdigest()[:32]
    manifest["package_id"] = f"pkg_{digest}"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
