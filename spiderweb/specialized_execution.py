"""Canonical execution of fully parameterized LOCATION_QUERY specialized calls.

Provider-specific libraries remain acquisition authority. This module only
orchestrates calls explicitly frozen into a LOCATION_QUERY plan and preserves
their returned source bytes + provenance in the LOCATION_QUERY snapshot.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class SpecializedExecutionError(RuntimeError):
    """Fail-closed specialized execution error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256_bytes(payload)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _safe_name(provider_id: str, ordinal: int) -> str:
    token = f"{ordinal:03d}_{provider_id}"
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in token)


def _bbox_equal(left: list[float], right: list[float], tolerance: float = 1e-10) -> bool:
    if len(left) != 4 or len(right) != 4:
        return False
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))


def _execute_imagery(call: dict[str, Any], output_dir: Path, ordinal: int) -> dict[str, Any]:
    from imagery.providers import ProviderError, get_provider

    provider_name = str(call.get("provider", "")).strip()
    provider_id = str(call.get("provider_id", "")).strip()
    bbox = call.get("bbox_wgs84")
    date_range = str(call.get("date_range", "")).strip()
    if not provider_id or not provider_name:
        raise SpecializedExecutionError("imagery call lacks provider identity")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise SpecializedExecutionError(f"{provider_id}: imagery call bbox malformed")
    if not date_range:
        raise SpecializedExecutionError(f"{provider_id}: imagery call lacks date_range")

    try:
        provider = get_provider(provider_name)
        result = provider.fetch([float(value) for value in bbox], date_range)
    except ProviderError as exc:
        return {
            "provider_id": provider_id,
            "execution_kind": "IMAGERY_PROVIDER_CALL",
            "state": "FAIL_PROVIDER",
            "error": str(exc),
            "call_spec_sha256": canonical_json_sha256(call),
        }

    returned_bbox = [float(value) for value in result.bbox]
    planned_bbox = [float(value) for value in bbox]
    if not _bbox_equal(planned_bbox, returned_bbox):
        raise SpecializedExecutionError(
            f"{provider_id}: returned bbox drift planned={planned_bbox} returned={returned_bbox}"
        )
    if not result.image_bytes:
        raise SpecializedExecutionError(f"{provider_id}: imagery provider returned empty bytes")

    base = _safe_name(provider_id, ordinal)
    suffix = ".jpg" if result.media_type == "image/jpeg" else ".bin"
    raw_path = output_dir / f"{base}{suffix}"
    if raw_path.exists():
        raise SpecializedExecutionError(f"specialized raw output already exists: {raw_path}")
    raw_path.write_bytes(result.image_bytes)
    digest = sha256_bytes(result.image_bytes)

    metadata = result.to_dict(include_image=False)
    metadata_path = output_dir / f"{base}.metadata.json"
    if metadata_path.exists():
        raise SpecializedExecutionError(
            f"specialized metadata output already exists: {metadata_path}"
        )
    write_json(metadata_path, metadata)

    return {
        "provider_id": provider_id,
        "execution_kind": "IMAGERY_PROVIDER_CALL",
        "provider": provider_name,
        "identity_state": str(call.get("identity_state", "SPECIALIZED_SOURCE_ACQUISITION")),
        "state": "PASS",
        "call_spec_sha256": canonical_json_sha256(call),
        "planned_bbox_wgs84": planned_bbox,
        "returned_bbox_wgs84": returned_bbox,
        "bbox_equal": True,
        "date_range": date_range,
        "media_type": result.media_type,
        "bytes": len(result.image_bytes),
        "sha256": digest,
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "scene_id": result.scene_id,
        "source_uri": result.source_uri,
        "acquired_at": result.acquired_at,
        "collection": result.collection,
        "platform": result.platform,
        "instrument": result.instrument,
        "cloud_cover_pct": result.cloud_cover_pct,
        "resolution_m": result.resolution_m,
        "provider_cache_path": result.cache_path,
    }


def execute_specialized_calls(
    plan: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    query = plan.get("query") or {}
    if query.get("mode") != "fetch":
        raise SpecializedExecutionError("specialized execution requires query.mode=fetch")
    if plan.get("fetch_gate") not in {"READY", "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS"}:
        raise SpecializedExecutionError(
            f"plan fetch_gate blocks specialized execution: {plan.get('fetch_gate')}"
        )
    calls = plan.get("specialized_calls")
    if not isinstance(calls, list):
        raise SpecializedExecutionError("plan.specialized_calls must be a list")

    output_dir.mkdir(parents=True, exist_ok=True)
    final_receipt = output_dir / "specialized_receipt.json"
    if final_receipt.exists():
        raise SpecializedExecutionError(
            f"specialized receipt already exists: {final_receipt}"
        )

    records: list[dict[str, Any]] = []
    failures = 0
    for ordinal, call in enumerate(calls, 1):
        if not isinstance(call, dict):
            raise SpecializedExecutionError(f"specialized call {ordinal} is not an object")
        kind = str(call.get("execution_kind", ""))
        if kind == "IMAGERY_PROVIDER_CALL":
            record = _execute_imagery(call, output_dir, ordinal)
        else:
            raise SpecializedExecutionError(
                f"unsupported specialized execution kind: {kind or 'MISSING'}"
            )
        records.append(record)
        failures += int(record.get("state") != "PASS")

    result = {
        "schema_version": "spiderweb.location_query_specialized_receipt.v1.0",
        "state": "PASS" if failures == 0 else "PARTIAL_OR_BLOCKED",
        "plan_sha256": canonical_json_sha256(plan),
        "provider_registry_sha256": plan.get("provider_registry_sha256"),
        "call_count": len(calls),
        "pass_count": sum(record.get("state") == "PASS" for record in records),
        "failure_count": failures,
        "records": records,
        "raw_bytes_preserved_before_derivation": True,
    }
    write_json(final_receipt, result)
    return result
