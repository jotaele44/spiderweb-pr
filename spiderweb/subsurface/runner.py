"""Source-backed dispatcher registration and family completeness accounting."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable
from .adapters import SourceRunReceipt, run_ogc_source, write_run_receipt
from .arcgis_adapter_v2 import run_arcgis_source_v2
from .dispatcher import LAYER_FAMILIES, SubsurfaceDispatcher
from .preflight import freeze_arcgis_layer_manifest
from .reference_adapter import run_reference_source
from .sources import SourceKind, SourceSpec, SourceStatus, denominator_sha256
from .sources_exhaustion_v04 import SOURCE_DENOMINATOR_V04

TERMINAL_PASS_STATES = frozenset({"PASS", "ZERO"})

@dataclass(frozen=True)
class SourceLedgerRow:
    source_id: str
    family: str
    required: bool
    registry_status: str
    run_state: str
    terminal: bool
    reason: str

@dataclass(frozen=True)
class FamilyCertification:
    family: str
    state: str
    required_sources: int
    terminal_sources: int
    pass_sources: int
    open_sources: tuple[str, ...]

def source_ledger(sources: Iterable[SourceSpec], receipts: Iterable[SourceRunReceipt]) -> list[SourceLedgerRow]:
    receipt_map = {receipt.source_id: receipt for receipt in receipts}
    rows: list[SourceLedgerRow] = []
    for source in sources:
        receipt = receipt_map.get(source.source_id)
        if receipt is not None:
            run_state = receipt.state
            terminal = receipt.state in TERMINAL_PASS_STATES
            reason = receipt.reason
        elif source.status == SourceStatus.OPEN:
            run_state, terminal, reason = "OPEN", False, "source denominator intentionally unresolved"
        elif source.status == SourceStatus.VERIFIED_REFERENCE:
            run_state, terminal, reason = "NOT_RUN", False, "verified reference has not yet been byte-frozen"
        elif source.status == SourceStatus.DISCOVERY_ONLY:
            run_state, terminal, reason = "OPEN", False, "discovery-only manifestation cannot close authoritative denominator"
        else:
            run_state, terminal, reason = "NOT_RUN", False, "queryable source has not been executed for this AOI"
        rows.append(SourceLedgerRow(source.source_id, source.family, source.required, source.status.value, run_state, terminal, reason))
    return rows

def certify_families(rows: Iterable[SourceLedgerRow]) -> list[FamilyCertification]:
    ledger = list(rows)
    output: list[FamilyCertification] = []
    for family in LAYER_FAMILIES:
        required = [row for row in ledger if row.family == family and row.required]
        terminal = [row for row in required if row.terminal]
        passed = [row for row in required if row.run_state in TERMINAL_PASS_STATES]
        open_ids = tuple(row.source_id for row in required if not row.terminal)
        state = "PASS" if required and len(passed) == len(required) else "OPEN"
        output.append(FamilyCertification(family, state, len(required), len(terminal), len(passed), open_ids))
    return output

class AuthoritativeSourceRunner:
    """Runs executable public sources while preserving unresolved denominator rows."""
    def __init__(self, sources: Iterable[SourceSpec] = SOURCE_DENOMINATOR_V04, *, snapshot_root: str | Path | None = None, fetch=None) -> None:
        self.sources = tuple(sources)
        self.snapshot_root = None if snapshot_root is None else Path(snapshot_root)
        self.fetch = fetch
        self.receipts: list[SourceRunReceipt] = []

    def _fetcher(self):
        if self.fetch is not None:
            return self.fetch
        from .adapters import _default_fetch
        return _default_fetch

    def _run_source(self, source: SourceSpec, aoi):
        kwargs = {"snapshot_dir": self.snapshot_root}
        if self.fetch is not None:
            kwargs["fetch"] = self.fetch
        if source.kind == SourceKind.ARCGIS_LAYER:
            manifest = freeze_arcgis_layer_manifest(source, fetch=self._fetcher(), snapshot_dir=self.snapshot_root)
            if not manifest.object_id_field:
                raise RuntimeError(f"{source.source_id} has no OID field")
            return run_arcgis_source_v2(source, aoi, manifest, **kwargs)
        if source.kind == SourceKind.OGC_FEATURES:
            return run_ogc_source(source, aoi, **kwargs)
        if source.kind in {SourceKind.REFERENCE_PAGE, SourceKind.REFERENCE_DOWNLOAD}:
            return run_reference_source(source, **kwargs)
        return [], None

    def _failure_receipt(self, source: SourceSpec, exc: Exception) -> SourceRunReceipt:
        now = datetime.now(timezone.utc).isoformat()
        return SourceRunReceipt(
            source.source_id,
            source.family,
            "FAIL",
            now,
            now,
            None,
            0,
            0,
            False,
            (),
            f"{type(exc).__name__}: {exc}",
        )

    def run_family(self, family: str, aoi) -> list[object]:
        if family not in LAYER_FAMILIES:
            raise ValueError(f"unknown layer family: {family}")
        output: list[object] = []
        executable = {
            SourceStatus.VERIFIED_QUERYABLE,
            SourceStatus.VERIFIED_REFERENCE,
            SourceStatus.DISCOVERY_ONLY,
        }
        for source in self.sources:
            if source.family != family or source.status not in executable:
                continue
            try:
                records, receipt = self._run_source(source, aoi)
            except Exception as exc:  # noqa: BLE001 - receipt must preserve external-source failure
                records, receipt = [], self._failure_receipt(source, exc)
            output.extend(records)
            if receipt is not None:
                self.receipts.append(receipt)
                if self.snapshot_root is not None:
                    write_run_receipt(self.snapshot_root / source.source_id / "receipt.json", receipt)
        return output

    def dispatcher(self) -> SubsurfaceDispatcher:
        dispatcher = SubsurfaceDispatcher()
        for family in LAYER_FAMILIES:
            def handler(aoi, _family=family):
                return self.run_family(_family, aoi)
            dispatcher.register(family, handler, name=f"authoritative:{family}")
        return dispatcher

    def ledger(self) -> list[SourceLedgerRow]:
        return source_ledger(self.sources, self.receipts)

    def certification(self) -> list[FamilyCertification]:
        return certify_families(self.ledger())

    def write_control_manifest(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "spiderweb.subsurface.source_control.v4",
            "source_denominator_sha256": denominator_sha256(self.sources),
            "sources": [asdict(source) for source in self.sources],
            "ledger": [asdict(row) for row in self.ledger()],
            "family_certification": [asdict(row) for row in self.certification()],
            "certification_rule": "PASS only when every required source in the family has a terminal PASS|ZERO receipt",
        }
        out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return out
