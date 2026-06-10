"""Federation hub: deterministic cross-repo query over validated packages.

The hub loads each producer's export package (manifest + JSONL) from disk,
validates it fail-closed, builds in-memory indexes, and resolves shared anchors
into joined evidence with provenance. It never imports a producer's code.
"""
from __future__ import annotations

from .package_loader import load_package
from .query import (
    correlate_entities,
    correlate_temporal,
    filter_by_confidence,
    query_federation,
)

__all__ = [
    "load_package",
    "query_federation",
    "correlate_entities",
    "correlate_temporal",
    "filter_by_confidence",
]
