"""Remote observations and the detection-state → evidence-tier mapping.

A ``RemoteObservation`` is a single dated, geometry-bearing detection tied to an
AOI and one or more source scenes. It always starts life as a *candidate*: the
``evidence_tier`` records only what the raised signals can establish (per
``schemas.DETECTION_STATE_INTERPRETATION``), and ``candidate_status`` starts at
``CANDIDATE``. Promotion to ``CONFIRMED`` happens exclusively through
``adjudication.py`` — a detector cannot confirm itself.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import schemas


def interpret_signals(signals: List[str]) -> str:
    """Return the evidence tier a set of raised signals is permitted to support.

    Unknown / unlisted combinations fall back to the weakest defensible tier —
    ``radar_change_candidate`` if any radar signal is present, otherwise
    ``surface_decorrelation_candidate``. This fail-weak default guarantees a
    combination is never silently promoted above what it can establish.
    """
    key = frozenset(signals)
    tier = schemas.DETECTION_STATE_INTERPRETATION.get(key)
    if tier is not None:
        return tier
    # Fail weak: never invent corroboration that wasn't raised.
    if schemas.SIGNAL_FIELD_CONFIRMATION in key:
        return schemas.TIER_CONFIRMED
    if schemas.SIGNAL_MULTI_EPOCH_LIDAR in key:
        return schemas.TIER_MEASURED_ELEVATION
    if schemas.SIGNAL_SAR_AMPLITUDE in key:
        return schemas.TIER_RADAR_CHANGE
    return schemas.TIER_SURFACE_DECORRELATION


def _observation_id(aoi_uid: str, detector: str, change_start: str, geom: Dict) -> str:
    """Deterministic 32-hex id from the identifying fields (dedup-friendly)."""
    basis = f"{aoi_uid}|{detector}|{change_start}|{geom}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


@dataclass
class RemoteObservation:
    """One dated remote-sensing detection within an AOI."""

    aoi_uid: str
    scene_uids: List[str]
    detector_name: str
    detector_version: str
    signals: List[str]
    geometry: Dict[str, Any]
    change_start: Optional[str] = None
    change_end: Optional[str] = None
    measurement_value: Optional[float] = None
    measurement_unit: Optional[str] = None
    baseline_scene_uid: Optional[str] = None
    confidence: float = 0.0
    reason_codes: List[str] = field(default_factory=list)
    candidate_status: str = schemas.CANDIDATE
    review_status: str = "unreviewed"
    observation_uid: str = ""
    evidence_tier: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_tier:
            self.evidence_tier = interpret_signals(self.signals)
        if not self.observation_uid:
            self.observation_uid = _observation_id(
                self.aoi_uid,
                self.detector_name,
                self.change_start or "",
                self.geometry,
            )
        if self.candidate_status not in schemas.CANDIDATE_STATUSES:
            raise ValueError(f"invalid candidate_status: {self.candidate_status!r}")

    @property
    def is_confirmed(self) -> bool:
        return self.candidate_status == schemas.CONFIRMED

    def to_record(self) -> Dict[str, Any]:
        """Serialize to a ``remote_observation`` schema-shaped dict."""
        return {
            "observation_uid": self.observation_uid,
            "aoi_uid": self.aoi_uid,
            "scene_uids": list(self.scene_uids),
            "baseline_scene_uid": self.baseline_scene_uid,
            "detector_name": self.detector_name,
            "detector_version": self.detector_version,
            "signals": list(self.signals),
            "evidence_tier": self.evidence_tier,
            "geometry": self.geometry,
            "change_start": self.change_start,
            "change_end": self.change_end,
            "measurement_value": self.measurement_value,
            "measurement_unit": self.measurement_unit,
            "confidence": self.confidence,
            "candidate_status": self.candidate_status,
            "reason_codes": list(self.reason_codes),
            "review_status": self.review_status,
        }
