"""Bounded public-source exhaustion certification for subsurface classes.

This module is deliberately stricter than adapter success. It answers whether the
frozen public-source denominator is terminal enough to permit consideration of a
records-request vector. It never interprets an OPEN source, missing index, or
reference-only manifestation as a negative finding.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from .dispatcher import LAYER_FAMILIES
from .runner import SourceLedgerRow, source_ledger
from .sources import SourceSpec
from .sources_exhaustion_v04 import SOURCE_DENOMINATOR_V04


@dataclass(frozen=True)
class PublicExhaustionClass:
    family: str
    state: str
    required_sources: int
    terminal_sources: int
    unresolved_sources: tuple[str, ...]


@dataclass(frozen=True)
class PublicExhaustionCertificate:
    scope: str
    state: str
    families: tuple[PublicExhaustionClass, ...]
    required_sources: int
    terminal_sources: int
    unresolved_sources: tuple[str, ...]
    records_request_eligible: bool
    reason: str


def certify_public_exhaustion(
    rows: Iterable[SourceLedgerRow],
    *,
    families: Iterable[str] = LAYER_FAMILIES,
    scope: str = "PUERTO_RICO_PUBLIC_SUBSURFACE_SOURCE_DENOMINATOR_V04",
) -> PublicExhaustionCertificate:
    """Certify bounded exhaustion only when every required row is terminal.

    Terminal means the source manifestation itself has a PASS or ZERO receipt from
    an executed, completeness-checked adapter. VERIFIED_REFERENCE, DISCOVERY_ONLY,
    NOT_RUN, OPEN, BLOCKED, or failed rows are non-terminal for this gate.
    """
    requested = tuple(families)
    unknown = set(requested) - set(LAYER_FAMILIES)
    if unknown:
        raise ValueError(f"unknown layer families: {sorted(unknown)}")

    ledger = [row for row in rows if row.family in requested and row.required]
    by_family: list[PublicExhaustionClass] = []
    all_open: list[str] = []
    terminal_total = 0
    for family in requested:
        family_rows = [row for row in ledger if row.family == family]
        terminal = [row for row in family_rows if row.terminal]
        unresolved = tuple(row.source_id for row in family_rows if not row.terminal)
        state = "PASS" if family_rows and not unresolved else "OPEN"
        by_family.append(
            PublicExhaustionClass(
                family=family,
                state=state,
                required_sources=len(family_rows),
                terminal_sources=len(terminal),
                unresolved_sources=unresolved,
            )
        )
        terminal_total += len(terminal)
        all_open.extend(unresolved)

    passed = bool(ledger) and not all_open and terminal_total == len(ledger)
    state = "PASS" if passed else "OPEN"
    return PublicExhaustionCertificate(
        scope=scope,
        state=state,
        families=tuple(by_family),
        required_sources=len(ledger),
        terminal_sources=terminal_total,
        unresolved_sources=tuple(all_open),
        records_request_eligible=passed,
        reason=(
            "bounded public-source denominator terminal; records-request vector may be considered"
            if passed
            else "public-source residue remains; records-request vector is forbidden"
        ),
    )


def current_public_exhaustion_certificate(
    receipts=(),
    *,
    sources: Iterable[SourceSpec] = SOURCE_DENOMINATOR_V04,
) -> PublicExhaustionCertificate:
    return certify_public_exhaustion(source_ledger(sources, receipts))


def write_public_exhaustion_certificate(
    path: str | Path,
    certificate: PublicExhaustionCertificate,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(asdict(certificate), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return out
