"""Federation producer for spiderweb-pr.

This package emits a validated spatial/operational export package (manifest +
JSONL streams) shaped to the shared evidence envelope, with namespaced IDs,
guarded by a fail-closed validator
(``envelope``/``namespace``/``validator``/``export_writer``).

The parent hub (thehub-pr) discovers, validates, and aggregates this package;
cross-producer correlation lives there and in the downstream PRIIS consumer.
The former in-repo query-hub is retired under ``docs/legacy/federation/hub/``
(see ``docs/REPO_BOUNDARY.md``).
"""
from __future__ import annotations

from .envelope import EvidenceEnvelope, entity_ref
from .namespace import PREFIX, PRODUCER, is_namespaced, namespaced_id
from .validator import validate_envelope, validate_financial, validate_package

__all__ = [
    "EvidenceEnvelope",
    "entity_ref",
    "PREFIX",
    "PRODUCER",
    "is_namespaced",
    "namespaced_id",
    "validate_envelope",
    "validate_financial",
    "validate_package",
]
