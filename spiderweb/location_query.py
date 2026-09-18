"""Canonical Spiderweb LOCATION_QUERY router.

The router is planning-first: it validates a location/AOI request, filters the
unified provider registry by family and geometry support, reports provider
readiness, credentials and blocked states, and never downloads bytes itself.
Existing provider-specific adapters remain authoritative for discovery/fetch.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .location_query_sources import build_request_specs

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "configs/location_query_providers.json"

READY_STATES = {"READY", "READY_WITH_CREDENTIALS", "READY_SPECIALIZED"}
INCOMPLETE_STATES = {"RESOLVER_ONLY", "PROVIDER_BINDING_OPEN", "SCHEMA_ONLY", "NOT_IMPLEMENTED", "BLOCKED"}
VALID_MODES = {"plan", "cache_only", "fetch"}
VALID_GEOMETRY_TYPES = {"point", "radius", "bbox", "polygon", "geojson"}


class LocationQueryError(ValueError):
    """Raised when the canonical LOCATION_QUERY contract is invalid."""


@dataclass(frozen=True)
class ProviderDecision:
    provider_id: str
    family: str
    status: str
    route_state: str
    reason: str | None
    adapter: str | None
    discovery: str | None
    acquisition: str | None
    missing_credentials: tuple[str, ...]
    execution_kind: str
    planned_request_count: int
    generic_executor_ready: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "family": self.family,
            "status": self.status,
            "route_state": self.route_state,
            "reason": self.reason,
            "adapter": self.adapter,
            "discovery": self.discovery,
            "acquisition": self.acquisition,
            "missing_credentials": list(self.missing_credentials),
            "execution_kind": self.execution_kind,
            "planned_request_count": self.planned_request_count,
            "generic_executor_ready": self.generic_executor_ready,
        }


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    providers = payload.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise LocationQueryError("provider registry is empty or malformed")
    return payload


def _require_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocationQueryError(f"{name} must be numeric")
    number = float(value)
    if not minimum <= number <= maximum:
        raise LocationQueryError(f"{name} outside [{minimum}, {maximum}]")
    return number


def validate_query(query: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(query, dict):
        raise LocationQueryError("query must be an object")
    query_id = str(query.get("query_id", "")).strip()
    if not query_id:
        raise LocationQueryError("query_id is required")
    geometry = query.get("geometry")
    if not isinstance(geometry, dict):
        raise LocationQueryError("geometry is required")
    geometry_type = str(geometry.get("type", "")).strip().lower()
    if geometry_type not in VALID_GEOMETRY_TYPES:
        raise LocationQueryError(f"unsupported geometry type: {geometry_type}")
    if geometry_type in {"point", "radius"}:
        _require_number(geometry.get("lat"), "lat", -90, 90)
        _require_number(geometry.get("lon"), "lon", -180, 180)
        if geometry_type == "radius":
            radius = geometry.get("radius_m")
            if isinstance(radius, bool) or not isinstance(radius, (int, float)) or float(radius) <= 0:
                raise LocationQueryError("radius_m must be > 0")
    elif geometry_type == "bbox":
        west = _require_number(geometry.get("west"), "west", -180, 180)
        east = _require_number(geometry.get("east"), "east", -180, 180)
        south = _require_number(geometry.get("south"), "south", -90, 90)
        north = _require_number(geometry.get("north"), "north", -90, 90)
        if west >= east or south >= north:
            raise LocationQueryError("bbox must satisfy west < east and south < north")
        crs = str(geometry.get("crs", "EPSG:4326")).strip().upper()
        if crs not in {"EPSG:4326", "CRS84", "OGC:CRS84"}:
            raise LocationQueryError(
                "LOCATION_QUERY bbox currently requires EPSG:4326/CRS84; "
                "provider-specific reprojection occurs downstream"
            )
    else:
        geojson = geometry.get("geojson")
        if not isinstance(geojson, dict):
            raise LocationQueryError("polygon/geojson geometry requires geojson object")
    mode = str(query.get("mode", "plan")).strip().lower()
    if mode not in VALID_MODES:
        raise LocationQueryError(f"unsupported mode: {mode}")
    families = query.get("families")
    if families is not None:
        if not isinstance(families, list) or any(not isinstance(v, str) or not v.strip() for v in families):
            raise LocationQueryError("families must be a list of non-empty strings")
    allow_partial = query.get("allow_partial", False)
    if not isinstance(allow_partial, bool):
        raise LocationQueryError("allow_partial must be boolean")

    normalized = dict(query)
    normalized["query_id"] = query_id
    normalized["mode"] = mode
    normalized["geometry"] = dict(geometry, type=geometry_type)
    if geometry_type == "bbox":
        normalized["geometry"]["crs"] = str(
            geometry.get("crs", "EPSG:4326")
        ).strip().upper()
    if families is not None:
        normalized["families"] = sorted({v.strip() for v in families})
    normalized["allow_partial"] = allow_partial
    return normalized


def _missing_credentials(provider: dict[str, Any], env: dict[str, str]) -> tuple[str, ...]:
    required = provider.get("required_environment", [])
    if not isinstance(required, list):
        return tuple()
    return tuple(name for name in required if not env.get(str(name)))


def route_query(
    query: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized = validate_query(query)
    registry = registry or load_registry()
    env = dict(os.environ if env is None else env)
    requested_families = set(normalized.get("families", []))
    geometry_type = normalized["geometry"]["type"]
    decisions: list[ProviderDecision] = []
    requests: list[dict[str, Any]] = []
    for provider_id, provider in sorted(registry["providers"].items()):
        family = str(provider.get("family", "unknown"))
        if requested_families and family not in requested_families:
            continue
        query_modes = provider.get("query_modes", [])
        if geometry_type not in query_modes:
            continue
        status = str(provider.get("status", "NOT_IMPLEMENTED"))
        missing_credentials = _missing_credentials(provider, env)
        if status == "READY_WITH_CREDENTIALS" and missing_credentials:
            route_state = "CREDENTIAL_REQUIRED"
        elif status in READY_STATES:
            route_state = "ROUTABLE"
        elif status == "PROVIDER_BINDING_OPEN":
            route_state = "PROVIDER_BINDING_OPEN"
        elif status == "BLOCKED":
            route_state = "BLOCKED"
        else:
            route_state = status
        provider_requests: list[dict[str, Any]] = []
        if route_state not in {"CREDENTIAL_REQUIRED", "BLOCKED", "NOT_IMPLEMENTED", "PROVIDER_BINDING_OPEN"}:
            provider_requests = build_request_specs(provider_id, provider, normalized)
            requests.extend(provider_requests)

        if provider_requests and provider.get("execution_requires_post_fetch"):
            execution_kind = "REQUEST_SPECS_PLUS_POSTPROCESSOR"
            generic_executor_ready = False
        elif provider_requests:
            execution_kind = "BOUNDED_REQUEST_SPECS"
            generic_executor_ready = route_state == "ROUTABLE"
        elif route_state == "ROUTABLE" and (
            provider.get("adapter")
            or provider.get("resolver")
            or provider.get("discovery")
            or provider.get("acquisition")
        ):
            execution_kind = "SPECIALIZED_ADAPTER"
            generic_executor_ready = False
        elif route_state in {"CREDENTIAL_REQUIRED", "PROVIDER_BINDING_OPEN", "BLOCKED", "NOT_IMPLEMENTED"}:
            execution_kind = route_state
            generic_executor_ready = False
        else:
            execution_kind = "RESOLUTION_ONLY"
            generic_executor_ready = False

        decisions.append(
            ProviderDecision(
                provider_id=provider_id,
                family=family,
                status=status,
                route_state=route_state,
                reason=provider.get("reason"),
                adapter=provider.get("adapter") or provider.get("resolver"),
                discovery=provider.get("discovery"),
                acquisition=provider.get("acquisition"),
                missing_credentials=missing_credentials,
                execution_kind=execution_kind,
                planned_request_count=len(provider_requests),
                generic_executor_ready=generic_executor_ready,
            )
        )
    counts = dict()
    for decision in decisions:
        counts[decision.route_state] = counts.get(decision.route_state, 0) + 1

    generic_executor_providers = [
        decision.provider_id for decision in decisions
        if decision.generic_executor_ready
    ]
    specialized_adapter_providers = [
        decision.provider_id for decision in decisions
        if decision.execution_kind in {"SPECIALIZED_ADAPTER", "REQUEST_SPECS_PLUS_POSTPROCESSOR"}
    ]
    incomplete_providers = [
        decision.provider_id for decision in decisions
        if decision.route_state != "ROUTABLE"
    ]
    execution_gap_providers = [
        decision.provider_id for decision in decisions
        if decision.route_state == "ROUTABLE" and not decision.generic_executor_ready
    ]
    blockers = sorted(set(incomplete_providers + execution_gap_providers))
    if normalized["mode"] != "fetch":
        fetch_gate = "NOT_REQUESTED"
    elif not decisions:
        fetch_gate = "BLOCKED_NO_MATCHING_PROVIDER"
        blockers = ["__NO_MATCHING_PROVIDER__"]
    elif not blockers:
        fetch_gate = "READY"
    elif normalized["allow_partial"]:
        fetch_gate = "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS"
    else:
        fetch_gate = "BLOCKED_INCOMPLETE_PROVIDER_EXECUTION"

    return {
        "schema_version": "spiderweb.location_query_plan.v1.0",
        "query": normalized,
        "provider_denominator_count": len(decisions),
        "route_state_counts": dict(sorted(counts.items())),
        "providers": [decision.as_dict() for decision in decisions],
        "request_count": len(requests),
        "requests": requests,
        "generic_executor_provider_ids": generic_executor_providers,
        "specialized_adapter_provider_ids": specialized_adapter_providers,
        "incomplete_provider_ids": incomplete_providers,
        "execution_gap_provider_ids": execution_gap_providers,
        "fetch_blocker_provider_ids": blockers,
        "fetch_gate": fetch_gate,
        "policy": {
            "plan_before_download": True,
            "raw_bytes_before_derivation": True,
            "no_coverage_is_not_source_absence": True,
            "missing_provider_binding_is_not_missing_dataset": True,
            "geocoder_is_discovery_until_spatially_bound": True,
            "cell_id_geography_requires_certified_transform": True,
        },
    }


def write_plan(query: dict[str, Any], output: Path, *, registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    plan = route_query(query, registry=load_registry(registry_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan
