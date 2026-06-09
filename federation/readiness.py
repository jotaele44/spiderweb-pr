"""Live-execution readiness gate for federation (T9-75).

``federation.json`` ships ``federation_readiness_gate.ready_for_hub_live_execution``
as ``false``. This module encodes — in code, not just prose — the exact criteria
that must hold before that flag may flip to ``true``, so the decision is testable
and auditable rather than a manual judgement call.

The two blocking conditions mirror ``docs/federation_readiness.md`` and the
``blocking_conditions`` array in ``federation.json``:

1. **Real data** — the production export must contain no ``synthetic: true`` rows.
2. **Correlation coverage** — downstream hub staging must have validated every
   cross-producer correlation strategy: temporal, normalized-name, spatial, and
   external-id.
"""

from __future__ import annotations

from typing import Any, Dict, List

# The correlation strategies the hub must have validated before live execution.
REQUIRED_CORRELATIONS = ("temporal", "normalized_name", "spatial", "external_id")


def evaluate_live_execution_readiness(
    *,
    has_synthetic_rows: bool,
    validated_correlations: List[str],
    discovery_ready: bool = True,
) -> Dict[str, Any]:
    """Return a readiness verdict for flipping live-execution to true.

    Args:
        has_synthetic_rows: True if any row in the production package is synthetic.
        validated_correlations: correlation strategy names the hub has validated
            against the production package.
        discovery_ready: whether ``ready_for_hub_discovery`` is already true
            (live execution cannot precede discovery).

    Returns:
        ``{"ready": bool, "blockers": [str, ...]}`` — ``ready`` is True only when
        ``blockers`` is empty.
    """
    blockers: List[str] = []

    if not discovery_ready:
        blockers.append("discovery_gate_not_passed")

    if has_synthetic_rows:
        blockers.append("synthetic_rows_present")

    validated = set(validated_correlations)
    missing = [c for c in REQUIRED_CORRELATIONS if c not in validated]
    if missing:
        blockers.append("correlations_unvalidated:" + ",".join(missing))

    return {"ready": not blockers, "blockers": blockers}
