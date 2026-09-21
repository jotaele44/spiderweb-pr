"""Adjudicate frozen provider denominators against provisional registry candidates.

This module never mutates provider readiness. It emits evidence for a later
promotion decision and treats layer IDs as the comparison key; names are
preserved as attributes and name equality is not identity.
"""
from __future__ import annotations

from typing import Any


class PromotionAdjudicationError(ValueError):
    """Fail-closed readiness adjudication error."""


def adjudicate_layer_denominator(
    *,
    provider_id: str,
    provider: dict[str, Any],
    denominator: dict[str, Any],
) -> dict[str, Any]:
    if denominator.get("state") != "PASS":
        raise PromotionAdjudicationError("frozen denominator is not PASS")
    if denominator.get("provider_id") != provider_id:
        raise PromotionAdjudicationError("provider mismatch")
    if denominator.get("schema_version") != "spiderweb.arcgis_layer_denominator.v1.0":
        raise PromotionAdjudicationError("unsupported denominator schema")

    provisional = provider.get("provisional_layers")
    if not isinstance(provisional, list) or not provisional:
        raise PromotionAdjudicationError("provider lacks provisional_layers denominator")

    provisional_by_id: dict[int, dict[str, Any]] = {}
    for row in provisional:
        if not isinstance(row, dict):
            raise PromotionAdjudicationError("provisional layer record is not object")
        layer_id = row.get("id")
        if isinstance(layer_id, bool) or not isinstance(layer_id, int):
            raise PromotionAdjudicationError("provisional layer id is invalid")
        if layer_id in provisional_by_id:
            raise PromotionAdjudicationError(f"duplicate provisional layer id: {layer_id}")
        provisional_by_id[layer_id] = row

    frozen_records = denominator.get("records")
    if not isinstance(frozen_records, list):
        raise PromotionAdjudicationError("frozen denominator records missing")

    frozen_by_id: dict[int, dict[str, Any]] = {}
    for row in frozen_records:
        if not isinstance(row, dict):
            raise PromotionAdjudicationError("frozen layer record is not object")
        layer_id = row.get("layer_id")
        if isinstance(layer_id, bool) or not isinstance(layer_id, int):
            raise PromotionAdjudicationError("frozen layer id is invalid")
        if layer_id in frozen_by_id:
            raise PromotionAdjudicationError(f"duplicate frozen layer id: {layer_id}")
        frozen_by_id[layer_id] = row

    a = set(provisional_by_id)
    b = set(frozen_by_id)
    intersection = sorted(a & b)
    a_only = sorted(a - b)
    b_only = sorted(b - a)
    union = sorted(a | b)
    symmetric_difference = sorted(a ^ b)

    name_deltas = []
    for layer_id in intersection:
        provisional_role = provisional_by_id[layer_id].get("role")
        frozen_name = frozen_by_id[layer_id].get("name_raw")
        if provisional_role is not None and frozen_name is not None:
            # Preserve the observation; role/name vocabulary is not an identity gate.
            name_deltas.append({
                "layer_id": layer_id,
                "provisional_role_raw": provisional_role,
                "frozen_name_raw": frozen_name,
                "name_used_as_identity": False,
            })

    eligible = not symmetric_difference and len(a) == len(b)
    return {
        "schema_version": "spiderweb.provider_layer_promotion_adjudication.v1.0",
        "provider_id": provider_id,
        "state": "PASS" if eligible else "REVIEW",
        "promotion_eligible": eligible,
        "identity_key": "layer_id",
        "provisional_count": len(a),
        "frozen_count": len(b),
        "intersection": intersection,
        "a_only_provisional": a_only,
        "b_only_frozen": b_only,
        "union": union,
        "symmetric_difference": symmetric_difference,
        "name_deltas": name_deltas,
        "policy": {
            "name_only_identity": False,
            "count_equality_identity": False,
            "stable_id_set_equality_required": True,
            "automatic_registry_mutation": False,
        },
        "frozen_denominator_sha256": denominator.get("canonical_records_sha256"),
    }
