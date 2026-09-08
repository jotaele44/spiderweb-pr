"""Opt-in strict lineage gate. Passing the DAG does not certify geography."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

from .archipelago import GeometryDerivationState as D
from .archipelago import GeometryManifestation, GeometryOrigin


@dataclass(frozen=True)
class LineageReceipt:
    node_count: int
    edge_count: int
    roots: tuple[str, ...]
    topological_order: tuple[str, ...]
    state: str = "PASS_STRUCTURAL_ONLY"
    canonical_identity_certified: bool = False


def validate_manifestation_dag(rows: Iterable[GeometryManifestation]) -> LineageReceipt:
    """Reject duplicates, missing parents, cycles and MVT authority reversal.

    Legacy records can still be constructed, but UNRESOLVED lineage cannot pass
    this gate. Validation is performed on the complete candidate graph before
    persistence: removing a referenced parent therefore fails as well.
    """
    items = list(rows)
    if not items:
        raise ValueError("EMPTY_LINEAGE_SCOPE")
    by_id: dict[str, GeometryManifestation] = {}
    states: dict[str, D] = {}
    for row in items:
        key = row.geometry_manifestation_id
        if not isinstance(key, str) or not key.strip():
            raise ValueError("EMPTY_MANIFESTATION_ID")
        if key in by_id:
            raise ValueError(f"DUPLICATE_MANIFESTATION_ID:{key}")
        by_id[key] = row
        try:
            states[key] = D(row.derivation_state)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"INVALID_DERIVATION_STATE:{key}") from exc
        if states[key] == D.UNRESOLVED:
            raise ValueError(f"UNRESOLVED_LINEAGE:{key}")

    children: dict[str, list[str]] = {k: [] for k in by_id}
    indegree = {k: 0 for k in by_id}
    for key, row in by_id.items():
        parent = row.parent_manifestation_id
        native = states[key] == D.SOURCE_NATIVE
        if native:
            if parent is not None:
                raise ValueError(f"SOURCE_NATIVE_HAS_PARENT:{key}")
            if row.origin != GeometryOrigin.SOURCE_NATIVE:
                raise ValueError(f"ORIGIN_STATE_CONFLICT:{key}")
        else:
            if not isinstance(parent, str) or not parent.strip():
                raise ValueError(f"MISSING_PARENT:{key}")
            if row.origin != GeometryOrigin.DERIVED:
                raise ValueError(f"ORIGIN_STATE_CONFLICT:{key}")
        if parent is not None:
            if parent == key:
                raise ValueError(f"SELF_EDGE:{key}")
            if parent not in by_id:
                raise ValueError(f"PARENT_NOT_FOUND:{key}:{parent}")
            children[parent].append(key)
            indegree[key] += 1
            if states[parent] == D.MVT and states[key] != D.MVT:
                raise ValueError(f"MVT_AUTHORITY_REVERSAL:{parent}:{key}")

    roots = tuple(sorted(k for k, v in indegree.items() if not v))
    queue = deque(roots)
    order: list[str] = []
    while queue:
        key = queue.popleft()
        order.append(key)
        for child in sorted(children[key]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(items):
        residue = sorted(k for k, d in indegree.items() if d)
        raise ValueError(f"LINEAGE_CYCLE:{','.join(residue)}")
    return LineageReceipt(len(items), sum(len(v) for v in children.values()), roots, tuple(order))
