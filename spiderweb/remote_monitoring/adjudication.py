"""Candidate → confirmed adjudication.

A remote observation is a candidate until an explicit adjudication decision moves
it. This module records those decisions as ``AdjudicationEvent`` rows and applies
them to a ``RemoteObservation`` through a small, auditable state machine.

Two invariants from the brief are enforced here:

* Only ``CONFIRM`` (which requires an authoritative / field corroboration) can
  reach ``CONFIRMED`` — no accumulation of remote-only signals auto-confirms.
* Every decision captures ``previous_status`` and ``new_status`` plus the
  supporting/contradicting observations and the rule (or analyst) responsible,
  so the transition is reversible and reviewable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import schemas
from .detections import RemoteObservation


class AdjudicationError(ValueError):
    """Raised on an illegal state transition."""


# Allowed (decision -> resulting candidate_status), given the current status.
def _target_status(decision: str, current: str) -> str:
    if decision == schemas.DECISION_CONFIRM:
        return schemas.CONFIRMED
    if decision == schemas.DECISION_REJECT:
        return schemas.REJECTED
    if decision == schemas.DECISION_PROMOTE:
        return schemas.SUPPORTED_CANDIDATE
    if decision == schemas.DECISION_DOWNGRADE:
        return schemas.CANDIDATE
    if decision == schemas.DECISION_HOLD:
        return current
    raise AdjudicationError(f"unknown decision: {decision!r}")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    )


@dataclass
class AdjudicationEvent:
    """A single, reversible decision applied to one observation."""

    observation_uid: str
    decision: str
    previous_status: str
    new_status: str
    analyst_or_rule: str
    rule_version: str = "0.1"
    decision_reason: str = ""
    supporting_observations: List[str] = field(default_factory=list)
    contradicting_observations: List[str] = field(default_factory=list)
    decision_datetime: str = field(default_factory=_now_iso)
    adjudication_uid: str = ""

    def __post_init__(self) -> None:
        if self.decision not in schemas.ADJUDICATION_DECISIONS:
            raise AdjudicationError(f"unknown decision: {self.decision!r}")
        if not self.adjudication_uid:
            basis = f"{self.observation_uid}|{self.decision}|{self.decision_datetime}"
            self.adjudication_uid = hashlib.sha256(basis.encode("utf-8")).hexdigest()[
                :32
            ]

    def to_record(self) -> Dict[str, Any]:
        return {
            "adjudication_uid": self.adjudication_uid,
            "observation_uid": self.observation_uid,
            "decision": self.decision,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "supporting_observations": list(self.supporting_observations),
            "contradicting_observations": list(self.contradicting_observations),
            "analyst_or_rule": self.analyst_or_rule,
            "rule_version": self.rule_version,
            "decision_reason": self.decision_reason,
            "decision_datetime": self.decision_datetime,
        }


def adjudicate(
    observation: RemoteObservation,
    decision: str,
    *,
    analyst_or_rule: str,
    decision_reason: str = "",
    supporting_observations: Optional[List[str]] = None,
    contradicting_observations: Optional[List[str]] = None,
    rule_version: str = "0.1",
) -> AdjudicationEvent:
    """Apply ``decision`` to ``observation`` in place and return the event.

    ``CONFIRM`` is only permitted when the observation carries a field /
    authoritative corroboration signal — a confirmed classified event cannot
    rest on remote sensing alone. Illegal transitions raise ``AdjudicationError``
    and leave the observation untouched.
    """
    previous = observation.candidate_status
    if previous in (schemas.CONFIRMED, schemas.REJECTED) and decision not in (
        schemas.DECISION_HOLD,
    ):
        raise AdjudicationError(
            f"observation already terminal ({previous}); cannot {decision}"
        )

    if decision == schemas.DECISION_CONFIRM:
        if schemas.SIGNAL_FIELD_CONFIRMATION not in observation.signals:
            raise AdjudicationError(
                "cannot CONFIRM without a field/authoritative corroboration "
                "signal — remote sensing alone is a candidate, not a conclusion"
            )

    new_status = _target_status(decision, previous)
    event = AdjudicationEvent(
        observation_uid=observation.observation_uid,
        decision=decision,
        previous_status=previous,
        new_status=new_status,
        analyst_or_rule=analyst_or_rule,
        rule_version=rule_version,
        decision_reason=decision_reason,
        supporting_observations=supporting_observations or [],
        contradicting_observations=contradicting_observations or [],
    )
    observation.candidate_status = new_status
    return event
