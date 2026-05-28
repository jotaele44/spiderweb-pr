"""Cross-repo federation for spiderweb-pr.

Two responsibilities live here:

* **Producer** (``envelope``/``namespace``/``validator``/``export_writer``):
  emit a validated airspace export package (manifest + JSONL streams) shaped to
  the shared evidence envelope, with namespaced IDs, guarded by a fail-closed
  validator.
* **Hub** (``federation.hub``): a deterministic cross-repo query layer that
  loads BOTH producers' export packages from disk and returns joined evidence
  with provenance. The hub reads packages as JSONL files; it does not import the
  other producer's code.
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
