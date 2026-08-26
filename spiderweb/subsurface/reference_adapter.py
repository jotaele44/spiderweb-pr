"""Byte-freezing adapter for exact authoritative public reference manifestations."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable

from .adapters import PageReceipt, SourceRunReceipt, _default_fetch
from .sources import SourceKind, SourceSpec, SourceStatus

Fetch = Callable[[str], bytes]


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def run_reference_source(
    spec: SourceSpec,
    *,
    fetch: Fetch = _default_fetch,
    snapshot_dir: str | Path | None = None,
) -> tuple[list[object], SourceRunReceipt]:
    """Freeze one exact public page/download as a terminal source manifestation.

    A DISCOVERY_ONLY reference may be byte-frozen to prove that its registered
    manifestation was searched/retrieved; its evidence role remains candidate-level
    and cannot prove buried infrastructure or identity. Terminality here is source
    execution, not evidentiary promotion.
    """
    if spec.kind not in {SourceKind.REFERENCE_PAGE, SourceKind.REFERENCE_DOWNLOAD}:
        raise ValueError("reference adapter requires REFERENCE_PAGE or REFERENCE_DOWNLOAD")
    if spec.status not in {SourceStatus.VERIFIED_REFERENCE, SourceStatus.DISCOVERY_ONLY}:
        raise ValueError("reference adapter requires VERIFIED_REFERENCE or DISCOVERY_ONLY")
    if not spec.endpoint.startswith("https://"):
        raise ValueError("reference endpoint must be HTTPS")

    started = datetime.now(timezone.utc).isoformat()
    raw = fetch(spec.endpoint)
    if not raw:
        raise RuntimeError(f"empty reference payload for {spec.source_id}")
    digest = _sha(raw)
    completed = datetime.now(timezone.utc).isoformat()
    page = PageReceipt(
        page_index=0,
        request_url=spec.endpoint,
        byte_count=len(raw),
        byte_sha256=digest,
        logical_sha256=digest,
        row_count=1,
        next_url=None,
    )

    if snapshot_dir is not None:
        target = Path(snapshot_dir) / spec.source_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "reference.raw").write_bytes(raw)
        (target / "reference_manifest.json").write_text(
            json.dumps(
                {
                    "source_id": spec.source_id,
                    "url": spec.endpoint,
                    "retrieved_utc": completed,
                    "byte_count": len(raw),
                    "sha256": digest,
                    "kind": spec.kind.value,
                    "registry_status": spec.status.value,
                    "evidence_role": spec.evidence_role,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    receipt = SourceRunReceipt(
        source_id=spec.source_id,
        family=spec.family,
        state="PASS",
        started_utc=started,
        completed_utc=completed,
        expected_count=1,
        retained_count=1,
        page_count=1,
        complete=True,
        pages=(page,),
        reason="exact registered public reference manifestation retrieved and byte-frozen",
    )
    return [], receipt
