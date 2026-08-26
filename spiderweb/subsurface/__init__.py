"""Reusable AOI-driven subsurface relevance analysis.

Spatial proximity is discovery, not identity or connectivity proof. Public-source
completeness is controlled by the frozen source denominator and family ledger.
"""
from .aoi import FrozenAOI, freeze_aoi
from .evidence import EvidenceRecord, EvidenceTier, SpatialState, adjudicate_feature, validate_records
from .runner import AuthoritativeSourceRunner, FamilyCertification, SourceLedgerRow
from .sources import DEFAULT_SOURCES, SourceKind, SourceSpec, SourceStatus, denominator_sha256

__all__ = [
    "AuthoritativeSourceRunner",
    "DEFAULT_SOURCES",
    "EvidenceRecord",
    "EvidenceTier",
    "FamilyCertification",
    "FrozenAOI",
    "SourceKind",
    "SourceLedgerRow",
    "SourceSpec",
    "SourceStatus",
    "SpatialState",
    "adjudicate_feature",
    "denominator_sha256",
    "freeze_aoi",
    "validate_records",
]
