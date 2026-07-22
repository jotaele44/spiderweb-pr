"""Physical observation ↔ contract-record crosswalk.

Connects a remote observation to a MoneySweep contract node *without asserting
causation*. ``reconcile`` classifies the relationship into one of
``schemas.RECONCILIATION_STATES`` using only temporal overlap and observability.

The load-bearing guardrail (brief's correction #5 and its closing warning):
``NO_SIGNAL_DETECTED`` is returned when observability was adequate but no signal
was found — and it explicitly does **not** mean the contracted work did not
occur. When observability itself is inadequate, the state is
``INSUFFICIENT_OBSERVABILITY``, never ``NO_SIGNAL_DETECTED``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from . import schemas

# Human-readable note attached to every NO_SIGNAL_DETECTED reconciliation so the
# guardrail travels with the record and cannot be lost downstream.
NO_SIGNAL_DISCLAIMER = (
    "No remote signal detected within adequate observability. This is NOT "
    "evidence that the contracted work did not occur; absence of a detectable "
    "signal has many causes (sub-detection scale, timing, sensor limits)."
)


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19].replace("Z", ""))
    except ValueError:
        try:
            return datetime.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _overlap_days(a_start, a_end, b_start, b_end) -> Optional[float]:
    """Days overlap between [a_start,a_end] and [b_start,b_end]; None if unknowable."""
    s1, e1 = _parse_date(a_start), _parse_date(a_end)
    s2, e2 = _parse_date(b_start), _parse_date(b_end)
    if None in (s1, e1, s2, e2):
        return None
    latest_start = max(s1, s2)
    earliest_end = min(e1, e2)
    delta = (earliest_end - latest_start).total_seconds() / 86400.0
    return round(delta, 4) if delta > 0 else 0.0


@dataclass
class PhysicalContractCrosswalk:
    """One assessed relationship between an observation and a contract node."""

    observation_uid: str
    contract_node_uid: str
    asset_uid: Optional[str] = None
    activity_period_start: Optional[str] = None
    activity_period_end: Optional[str] = None
    contract_period_start: Optional[str] = None
    contract_period_end: Optional[str] = None
    spatial_relationship: str = "within"
    expected_physical_signal: Optional[str] = None
    observed_signal: Optional[str] = None
    reconciliation_status: str = schemas.NOT_ASSESSABLE
    temporal_overlap_days: Optional[float] = None
    confidence: float = 0.0
    notes: str = ""
    crosswalk_uid: str = ""

    def __post_init__(self) -> None:
        if not self.crosswalk_uid:
            basis = f"{self.observation_uid}|{self.contract_node_uid}"
            self.crosswalk_uid = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]

    def to_record(self) -> Dict[str, Any]:
        return {
            "crosswalk_uid": self.crosswalk_uid,
            "asset_uid": self.asset_uid,
            "contract_node_uid": self.contract_node_uid,
            "observation_uid": self.observation_uid,
            "activity_period_start": self.activity_period_start,
            "activity_period_end": self.activity_period_end,
            "contract_period_start": self.contract_period_start,
            "contract_period_end": self.contract_period_end,
            "temporal_overlap_days": self.temporal_overlap_days,
            "spatial_relationship": self.spatial_relationship,
            "expected_physical_signal": self.expected_physical_signal,
            "observed_signal": self.observed_signal,
            "reconciliation_status": self.reconciliation_status,
            "confidence": self.confidence,
            "notes": self.notes,
        }


def reconcile(
    crosswalk: PhysicalContractCrosswalk,
    *,
    observable: bool = True,
    contradictory_records: bool = False,
) -> PhysicalContractCrosswalk:
    """Classify the crosswalk into a reconciliation state (in place).

    Args:
        observable: whether the AOI/period had adequate remote observability
            (usable, cloud-free-enough, in-cadence coverage). When False the
            result is ``INSUFFICIENT_OBSERVABILITY`` — never ``NO_SIGNAL_DETECTED``.
        contradictory_records: set when independent records conflict, yielding
            ``CONTRADICTORY_RECORDS``.
    """
    if contradictory_records:
        crosswalk.reconciliation_status = schemas.CONTRADICTORY_RECORDS
        return crosswalk

    if not observable:
        crosswalk.reconciliation_status = schemas.INSUFFICIENT_OBSERVABILITY
        return crosswalk

    overlap = _overlap_days(
        crosswalk.activity_period_start,
        crosswalk.activity_period_end,
        crosswalk.contract_period_start,
        crosswalk.contract_period_end,
    )
    crosswalk.temporal_overlap_days = overlap

    has_signal = bool(crosswalk.observed_signal)

    if not has_signal:
        # Observability was adequate but nothing was detected. This is an
        # observability statement, NOT a performance judgement.
        crosswalk.reconciliation_status = schemas.NO_SIGNAL_DETECTED
        crosswalk.notes = (crosswalk.notes + " " + NO_SIGNAL_DISCLAIMER).strip()
        return crosswalk

    if overlap is None:
        crosswalk.reconciliation_status = schemas.NOT_ASSESSABLE
        return crosswalk

    if overlap <= 0:
        crosswalk.reconciliation_status = schemas.SIGNAL_OUTSIDE_CONTRACT_PERIOD
        return crosswalk

    # A signal exists and overlaps the contract window. Whether it fully or
    # partially matches the expected signal decides consistent vs partial.
    if (
        crosswalk.expected_physical_signal
        and crosswalk.observed_signal == crosswalk.expected_physical_signal
    ):
        crosswalk.reconciliation_status = schemas.CONSISTENT
    else:
        crosswalk.reconciliation_status = schemas.PARTIALLY_CONSISTENT
    return crosswalk
