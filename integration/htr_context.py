"""Import TheHub HTR relations into Spiderweb without identity collapse."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

ALLOWED_STATES = {"CONTEXT_SUPPORTED", "ADJUDICATED"}
FORBIDDEN_RELATIONS = {"SAME_AS", "IDENTICAL_TO", "CANONICAL_IDENTITY"}
ALLOWED_PAIR_BINDING_STATES = {"UNBOUND", "BOUND_RELATION_NOT_IDENTITY"}


class HTRContextError(ValueError):
    pass


def import_htr_graph(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise HTRContextError("HTR row must be an object")
        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise HTRContextError("missing candidate_id")
        if candidate_id in seen_candidates:
            raise HTRContextError(f"duplicate candidate_id: {candidate_id}")
        seen_candidates.add(candidate_id)
        state = row.get("state")
        if state not in ALLOWED_STATES:
            raise HTRContextError(
                f"unsupported HTR state {state!r}; allowed: {sorted(ALLOWED_STATES)}"
            )
        if row.get("identity_state") != "DISTINCT_ENTITIES":
            raise HTRContextError("HTR graph import requires distinct entities")
        if row.get("downstream_semantics") != "CONTEXT_ONLY_NOT_IDENTITY":
            raise HTRContextError("missing context-only contract")
        relation = row.get("relation_type")
        if not isinstance(relation, str) or not relation:
            raise HTRContextError("relation_type must be a non-empty string")
        if relation in FORBIDDEN_RELATIONS:
            raise HTRContextError("identity edge forbidden")
        pair_binding_state = row.get("pair_binding_state")
        if pair_binding_state not in ALLOWED_PAIR_BINDING_STATES:
            raise HTRContextError(
                "unsupported pair_binding_state "
                f"{pair_binding_state!r}; "
                f"allowed: {sorted(ALLOWED_PAIR_BINDING_STATES)}"
            )
        sid = row.get("source_observation_id")
        hid = row.get("hydro_entity_id")
        if not isinstance(sid, str) or not sid:
            raise HTRContextError("source_observation_id must be a non-empty string")
        if not isinstance(hid, str) or not hid:
            raise HTRContextError("hydro_entity_id must be a non-empty string")
        if sid == hid:
            raise HTRContextError("HTR endpoints must remain distinct")
        nodes.setdefault(
            sid,
            {
                "node_id": sid,
                "node_type": row.get("source_feature_type", "TOPONYM"),
                "identity_locked": True,
            },
        )
        nodes.setdefault(
            hid, {"node_id": hid, "node_type": "HYDRO_FEATURE", "identity_locked": True}
        )
        edge_relation = (
            relation
            if pair_binding_state == "BOUND_RELATION_NOT_IDENTITY"
            else "POSSIBLE_EPONYM_OF"
        )
        edges.append(
            {
                "edge_id": f"htr:{candidate_id}",
                "source_node_id": sid,
                "target_node_id": hid,
                "relationship_type": edge_relation,
                "candidate_id": candidate_id,
                "evidence_state": state,
                "identity_claim": False,
                "connectivity_claim": edge_relation
                in {"HYDRAULICALLY_CONNECTED_TO", "ELECTRICALLY_CONNECTED_TO"},
                "context_only": True,
            }
        )
    return {
        "nodes": sorted(nodes.values(), key=lambda n: n["node_id"]),
        "edges": sorted(edges, key=lambda e: e["edge_id"]),
        "invariants": {
            "identity_edge_count": 0,
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }
