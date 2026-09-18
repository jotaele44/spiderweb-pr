"""Offline closure of LOCATION_QUERY discovery denominators.

Consumes an existing discovery/resolver-stage fetch receipt and its preserved raw
files. No network requests are performed. Provider-specific denominator parsers
remain authoritative; this module only orchestrates them and emits restartable
next-stage plans where the denominator is not yet exhaustive.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spiderweb.denominator_chain import build_usace_service_metadata_plan
from spiderweb.provider_denominators import (
    freeze_arcgis_layer_denominator,
    freeze_arcgis_service_denominator,
    freeze_wms_layer_denominator,
)
from spiderweb.provider_promotion import adjudicate_layer_denominator


class DenominatorClosureError(ValueError):
    """Fail-closed offline closure error."""


def _receipt(
    fetch: dict[str, Any],
    provider_id: str,
    request_role: str,
) -> dict[str, Any] | None:
    requests = fetch.get("requests")
    if not isinstance(requests, list):
        raise DenominatorClosureError("fetch receipt lacks requests list")
    rows = [
        row for row in requests
        if isinstance(row, dict)
        and row.get("provider_id") == provider_id
        and row.get("request_role") == request_role
    ]
    if not rows:
        return None
    if len(rows) != 1:
        raise DenominatorClosureError(
            f"expected at most one {provider_id}/{request_role} receipt; got {len(rows)}"
        )
    return rows[0]


def _raw_bytes(receipt: dict[str, Any]) -> bytes:
    path_raw = receipt.get("raw_path")
    if not isinstance(path_raw, str) or not path_raw:
        raise DenominatorClosureError(
            f"{receipt.get('provider_id')}/{receipt.get('request_role')}: raw_path missing"
        )
    path = Path(path_raw)
    if not path.is_file():
        raise DenominatorClosureError(f"preserved raw file missing: {path}")
    return path.read_bytes()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise DenominatorClosureError(
            f"closure output already exists: {path}; use a new versioned output directory"
        )
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def close_discovery_denominators(
    *,
    fetch: dict[str, Any],
    registry: dict[str, Any],
    query: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    if fetch.get("execution_scope") != "DISCOVERY_OR_RESOLVER_STAGE":
        raise DenominatorClosureError(
            "fetch receipt is not DISCOVERY_OR_RESOLVER_STAGE"
        )
    if fetch.get("state") not in {"DISCOVERY_PASS", "PARTIAL_OR_BLOCKED"}:
        raise DenominatorClosureError("discovery fetch state is not usable")
    providers = registry.get("providers")
    if not isinstance(providers, dict):
        raise DenominatorClosureError("provider registry malformed")

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    # 3DHP: raw FeatureServer metadata -> frozen layer denominator -> stable-ID
    # adjudication against the provisional registry candidate set.
    if "USGS_3DHP_NHD" in providers:
        receipt = _receipt(fetch, "USGS_3DHP_NHD", "feature_service_metadata")
        if receipt is not None and receipt.get("state") == "PASS":
            denominator = freeze_arcgis_layer_denominator(
                raw=_raw_bytes(receipt),
                receipt=receipt,
                provider_id="USGS_3DHP_NHD",
                request_role="feature_service_metadata",
            )
            denom_path = output_dir / "USGS_3DHP_NHD_LAYER_DENOMINATOR.json"
            _write(denom_path, denominator)
            adjudication = adjudicate_layer_denominator(
                provider_id="USGS_3DHP_NHD",
                provider=providers["USGS_3DHP_NHD"],
                denominator=denominator,
            )
            adjudication_path = output_dir / "USGS_3DHP_NHD_PROMOTION_ADJUDICATION.json"
            _write(adjudication_path, adjudication)
            records.append({
                "provider_id": "USGS_3DHP_NHD",
                "state": adjudication["state"],
                "promotion_eligible": adjudication["promotion_eligible"],
                "denominator_path": str(denom_path),
                "adjudication_path": str(adjudication_path),
            })

    # FEMA NFHL: WMS named-layer denominator is metadata only. It cannot by
    # itself promote vector feature identity.
    if "FEMA_NFHL" in providers:
        receipt = _receipt(fetch, "FEMA_NFHL", "nfhl_wms_capabilities")
        if receipt is not None and receipt.get("state") == "PASS":
            denominator = freeze_wms_layer_denominator(
                raw=_raw_bytes(receipt),
                receipt=receipt,
                provider_id="FEMA_NFHL",
                request_role="nfhl_wms_capabilities",
            )
            path = output_dir / "FEMA_NFHL_WMS_LAYER_DENOMINATOR.json"
            _write(path, denominator)
            records.append({
                "provider_id": "FEMA_NFHL",
                "state": "METADATA_DENOMINATOR_PASS_VECTOR_IDENTITY_OPEN",
                "promotion_eligible": False,
                "denominator_path": str(path),
            })

    # Puerto Rico ABFE: ArcGIS MapServer layer denominator. Stable layer IDs are
    # frozen, but feature acquisition stays a dependent stage.
    if "FEMA_PR_ABFE_1PCT" in providers:
        receipt = _receipt(fetch, "FEMA_PR_ABFE_1PCT", "abfe_map_service_denominator")
        if receipt is not None and receipt.get("state") == "PASS":
            denominator = freeze_arcgis_layer_denominator(
                raw=_raw_bytes(receipt),
                receipt=receipt,
                provider_id="FEMA_PR_ABFE_1PCT",
                request_role="abfe_map_service_denominator",
            )
            path = output_dir / "FEMA_PR_ABFE_LAYER_DENOMINATOR.json"
            _write(path, denominator)
            records.append({
                "provider_id": "FEMA_PR_ABFE_1PCT",
                "state": "LAYER_DENOMINATOR_PASS_DEPENDENT_AOI_OPEN",
                "promotion_eligible": False,
                "denominator_path": str(path),
            })

    # USACE general: root services + folders. A nonempty folder denominator is
    # explicitly OPEN until every folder listing is frozen and merged.
    if "USACE_GENERAL_GIS" in providers:
        receipt = _receipt(fetch, "USACE_GENERAL_GIS", "services_root_denominator")
        if receipt is not None and receipt.get("state") == "PASS":
            denominator = freeze_arcgis_service_denominator(
                raw=_raw_bytes(receipt),
                receipt=receipt,
                provider_id="USACE_GENERAL_GIS",
                request_role="services_root_denominator",
            )
            path = output_dir / "USACE_GENERAL_GIS_ROOT_SERVICE_DENOMINATOR.json"
            _write(path, denominator)
            next_plan = build_usace_service_metadata_plan(
                query=query,
                service_root=providers["USACE_GENERAL_GIS"]["service_root"],
                denominator=denominator,
            )
            next_path = output_dir / "USACE_GENERAL_GIS_NEXT_STAGE_PLAN.json"
            _write(next_path, next_plan)
            state = (
                "OPEN_RECURSIVE_FOLDER_DENOMINATOR"
                if denominator.get("folder_count", 0)
                else "ROOT_DENOMINATOR_PASS_SERVICE_METADATA_OPEN"
            )
            records.append({
                "provider_id": "USACE_GENERAL_GIS",
                "state": state,
                "promotion_eligible": False,
                "service_count": denominator.get("service_count"),
                "folder_count": denominator.get("folder_count"),
                "denominator_path": str(path),
                "next_stage_plan_path": str(next_path),
            })

    return {
        "schema_version": "spiderweb.location_query_denominator_closure.v1.0",
        "state": "PASS",
        "network_requests": 0,
        "source_redownloads": 0,
        "provider_record_count": len(records),
        "records": records,
        "policy": {
            "raw_receipt_hash_binding_required": True,
            "stable_id_set_equality_required_for_promotion": True,
            "wms_layer_names_not_vector_identity": True,
            "usace_folder_recursion_required": True,
            "automatic_registry_mutation": False,
        },
    }
