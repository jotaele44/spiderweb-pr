"""``spiderweb.remote_monitoring`` — remote-sensing monitoring provenance backbone.

Phase 0 of the monitoring architecture: the mandatory candidate-vs-confirmed
logic and scene-level provenance, built stdlib-only so it runs offline. Live STAC
fetch, SAR amplitude/coherence processing and the GPKG sink are later phases; the
optional ``discovery`` seam is the forward hook to them.

Public surface is intentionally small — the dataclasses and the pure-logic
entry points. Importing this package pulls in no network or geospatial
dependency; ``discovery`` imports ``imagery`` lazily and only when called.
"""

from __future__ import annotations

from . import schemas
from .adjudication import AdjudicationError, AdjudicationEvent, adjudicate
from .aoi import MonitoringAOI, active_aois, load_aois
from .catalog import (
    compatible_pairs,
    insar_pair_compatibility,
    observed_revisit_days,
)
from .confidence import assess, classify, score_confidence
from .crosswalk import PhysicalContractCrosswalk, reconcile
from .detections import RemoteObservation, interpret_signals

__all__ = [
    "schemas",
    # AOIs
    "MonitoringAOI",
    "load_aois",
    "active_aois",
    # Catalog / cadence
    "observed_revisit_days",
    "insar_pair_compatibility",
    "compatible_pairs",
    # Detections
    "RemoteObservation",
    "interpret_signals",
    # Adjudication
    "AdjudicationEvent",
    "AdjudicationError",
    "adjudicate",
    # Confidence
    "score_confidence",
    "classify",
    "assess",
    # Crosswalk
    "PhysicalContractCrosswalk",
    "reconcile",
]
