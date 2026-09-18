#!/usr/bin/env python3
"""Execute bounded LOCATION_QUERY provider request specs.

Raw provider bytes are preserved before interpretation. ArcGIS feature layers
use an object-ID denominator followed by deterministic object-ID batches so an
HTTP-200 response cannot silently truncate an AOI at the service record limit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "spiderweb-pr-location-query/1.0"
ALLOWED_METHODS = {"GET", "POST"}
ARCGIS_BATCH_SIZE = 100


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_sha256(value: object) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256_bytes(body)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_name(provider: str, role: str, ordinal: int) -> str:
    token = f"{ordinal:03d}_{provider}_{role}"
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in token)


def _request_from_spec(spec: dict, ordinal: int) -> tuple[Request, str]:
    method = str(spec.get("method", "")).upper()
    if method not in ALLOWED_METHODS:
        raise SystemExit(f"FAIL: unsupported method for request {ordinal}: {method or 'MISSING'}")
    url = str(spec.get("url", ""))
    if not url:
        raise SystemExit(f"FAIL: empty URL for request {ordinal}")

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    data = None
    if method == "POST":
        body = spec.get("json_body")
        if not isinstance(body, dict):
            raise SystemExit(f"FAIL: POST request {ordinal} requires json_body object")
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
    return Request(url, data=data, headers=headers, method=method), method


def _perform(req: Request, timeout: int) -> tuple[int | None, str, bytes, str | None]:
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            return (
                getattr(response, "status", 200),
                response.headers.get("Content-Type", ""),
                response.read(),
                None,
            )
    except HTTPError as exc:
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, content_type, exc.read(), f"HTTPError: {exc}"
    except (URLError, TimeoutError) as exc:
        return None, "", b"", f"{type(exc).__name__}: {exc}"


def _write_raw(path: Path, payload: bytes) -> str | None:
    if not payload:
        return None
    path.write_bytes(payload)
    return sha256_bytes(payload)


def _json_bytes(payload: bytes, label: str) -> object:
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: {label} is not valid UTF-8 JSON: {exc}") from exc


def _xml_local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _semantic_simple_state(spec: dict, payload: bytes) -> tuple[str, str | None]:
    protocol = str(spec.get("protocol", ""))
    expected_media = str(spec.get("media_type", "")).casefold()

    if protocol in {"ARCGIS_METADATA", "OGC_FEATURES", "SDA_TABULAR"} or "json" in expected_media:
        obj = _json_bytes(payload, f"{spec.get('provider_id')}/{spec.get('request_role')} response")
        if isinstance(obj, dict) and obj.get("error"):
            return "FAIL_PROVIDER_ERROR", f"provider error: {obj['error']}"

        if protocol == "OGC_FEATURES":
            if not isinstance(obj, dict):
                return "FAIL_SEMANTIC", "OGC Features response is not an object"
            features = obj.get("features")
            if not isinstance(features, list):
                return "FAIL_SEMANTIC", "OGC Features response lacks features list"
            if not features:
                return "NO_COVERAGE", None
            matched = obj.get("numberMatched")
            returned = obj.get("numberReturned")
            if isinstance(matched, int) and isinstance(returned, int) and returned < matched:
                return "INCOMPLETE_PAGINATION_REQUIRED", f"numberReturned={returned} < numberMatched={matched}"
            links = obj.get("links", [])
            if isinstance(links, list) and any(
                isinstance(link, dict) and str(link.get("rel", "")).casefold() == "next"
                for link in links
            ):
                return "INCOMPLETE_PAGINATION_REQUIRED", "OGC response advertises rel=next"
            return "PASS", None

        if protocol == "SDA_TABULAR":
            if not isinstance(obj, dict) or not isinstance(obj.get("Table"), list):
                return "FAIL_SEMANTIC", "SDA response lacks Table list"
            return "PASS", None

        return "PASS", None

    if protocol in {"WFS_FEATURES", "WMS_CAPABILITIES"} or "xml" in expected_media or "gml" in expected_media:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            return "FAIL_SEMANTIC", f"XML parse failure: {exc}"
        locals_seen = [_xml_local(element.tag) for element in root.iter()]
        if any(name in {"ExceptionReport", "ServiceExceptionReport", "Exception", "ServiceException"} for name in locals_seen):
            return "FAIL_PROVIDER_ERROR", "OGC/WMS exception document returned"

        if protocol == "WFS_FEATURES":
            members = sum(name in {"featureMember", "member"} for name in locals_seen)
            if members == 0:
                return "NO_COVERAGE", None
            return "PASS", None

        if protocol == "WMS_CAPABILITIES":
            named_layers = 0
            for layer in root.iter():
                if _xml_local(layer.tag) != "Layer":
                    continue
                if any(_xml_local(child.tag) == "Name" and (child.text or "").strip() for child in list(layer)):
                    named_layers += 1
            if named_layers == 0:
                return "FAIL_SEMANTIC", "WMS capabilities contains zero named layers"
            return "PASS", None

        return "PASS", None

    return "PASS", None


def _extract_feature_ids(feature_collection: dict, oid_field: str) -> list[str]:
    features = feature_collection.get("features")
    if not isinstance(features, list):
        raise SystemExit("FAIL: ArcGIS batch response lacks GeoJSON features list")
    result: list[str] = []
    oid_cf = oid_field.casefold()
    for index, feature in enumerate(features, 1):
        if not isinstance(feature, dict):
            raise SystemExit(f"FAIL: ArcGIS feature {index} is not an object")
        props = feature.get("properties")
        if not isinstance(props, dict):
            raise SystemExit(f"FAIL: ArcGIS feature {index} lacks properties")
        matches = [value for key, value in props.items() if str(key).casefold() == oid_cf]
        if len(matches) != 1 or matches[0] is None:
            raise SystemExit(f"FAIL: ArcGIS feature {index} lacks unique object ID field {oid_field}")
        result.append(str(matches[0]))
    return result


def _execute_arcgis(
    spec: dict,
    output_dir: Path,
    *,
    ordinal: int,
    provider: str,
    role: str,
    identity_state: str,
    timeout: int,
) -> dict:
    base = safe_name(provider, role, ordinal)
    request_spec_sha = canonical_json_sha256(spec)
    parent_denominator_sha = spec.get("parent_denominator_sha256")
    denominator_req, _ = _request_from_spec(spec, ordinal)
    status, content_type, payload, error = _perform(denominator_req, timeout)
    denominator_raw = output_dir / (base + ".ids.raw")
    denominator_sha = _write_raw(denominator_raw, payload)

    if status != 200 or not payload:
        return {
            "provider_id": provider,
            "request_role": role,
            "identity_state": identity_state,
            "protocol": "ARCGIS_FEATURE_LAYER",
            "request_spec_sha256": request_spec_sha,
            "parent_denominator_sha256": parent_denominator_sha,
            "state": "FAIL",
            "http_status": status,
            "error": error,
            "id_denominator_raw_path": str(denominator_raw) if payload else None,
            "id_denominator_sha256": denominator_sha,
        }

    obj = _json_bytes(payload, f"{provider}/{role} ArcGIS ID denominator")
    if not isinstance(obj, dict):
        raise SystemExit(f"FAIL: {provider}/{role} ArcGIS ID denominator is not an object")
    if obj.get("error"):
        raise SystemExit(f"FAIL: {provider}/{role} ArcGIS ID denominator returned error: {obj['error']}")

    oid_field = obj.get("objectIdFieldName")
    object_ids = obj.get("objectIds")
    if not isinstance(oid_field, str) or not oid_field:
        raise SystemExit(f"FAIL: {provider}/{role} objectIdFieldName missing")
    if object_ids is None:
        object_ids = []
    if not isinstance(object_ids, list) or any(value is None for value in object_ids):
        raise SystemExit(f"FAIL: {provider}/{role} malformed objectIds")

    normalized_ids = [str(value) for value in object_ids]
    if len(set(normalized_ids)) != len(normalized_ids):
        raise SystemExit(f"FAIL: {provider}/{role} duplicate IDs in denominator")
    normalized_ids = sorted(normalized_ids, key=lambda value: (len(value), value))

    if not normalized_ids:
        return {
            "provider_id": provider,
            "request_role": role,
            "identity_state": identity_state,
            "protocol": "ARCGIS_FEATURE_LAYER",
            "request_spec_sha256": request_spec_sha,
            "parent_denominator_sha256": parent_denominator_sha,
            "state": "NO_COVERAGE",
            "http_status": status,
            "object_id_field": oid_field,
            "denominator_id_count": 0,
            "returned_id_count": 0,
            "batch_count": 0,
            "arithmetic_closure": True,
            "id_denominator_raw_path": str(denominator_raw),
            "id_denominator_sha256": denominator_sha,
        }

    layer_url = str(spec.get("layer_url", "")).rstrip("/")
    if not layer_url:
        raise SystemExit(f"FAIL: {provider}/{role} layer_url missing")
    out_fields = str(spec.get("out_fields", "*"))

    returned_ids: list[str] = []
    batch_receipts: list[dict] = []
    for batch_index, start in enumerate(range(0, len(normalized_ids), ARCGIS_BATCH_SIZE), 1):
        batch_ids = normalized_ids[start : start + ARCGIS_BATCH_SIZE]
        params = {
            "objectIds": ",".join(batch_ids),
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        }
        url = layer_url + "/query?" + urlencode(params)
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}, method="GET")
        b_status, b_type, b_payload, b_error = _perform(req, timeout)
        raw_path = output_dir / f"{base}.batch_{batch_index:04d}.raw"
        raw_sha = _write_raw(raw_path, b_payload)

        if b_status != 200 or not b_payload:
            raise SystemExit(
                f"FAIL: {provider}/{role} ArcGIS batch {batch_index} HTTP={b_status} error={b_error}"
            )

        batch_obj = _json_bytes(b_payload, f"{provider}/{role} batch {batch_index}")
        if not isinstance(batch_obj, dict):
            raise SystemExit(f"FAIL: {provider}/{role} batch {batch_index} is not an object")
        if batch_obj.get("error"):
            raise SystemExit(f"FAIL: {provider}/{role} batch {batch_index} returned error: {batch_obj['error']}")
        if batch_obj.get("exceededTransferLimit") is True:
            raise SystemExit(f"FAIL: {provider}/{role} batch {batch_index} exceeded transfer limit")

        batch_returned = _extract_feature_ids(batch_obj, oid_field)
        requested_set = set(batch_ids)
        returned_set = set(batch_returned)
        if len(batch_returned) != len(returned_set):
            raise SystemExit(f"FAIL: {provider}/{role} duplicate returned IDs in batch {batch_index}")
        missing = sorted(requested_set - returned_set)
        extra = sorted(returned_set - requested_set)
        if missing or extra:
            raise SystemExit(
                f"FAIL: {provider}/{role} batch {batch_index} ID mismatch missing={missing[:20]} extra={extra[:20]}"
            )

        returned_ids.extend(batch_returned)
        batch_receipts.append({
            "batch_index": batch_index,
            "request_url": url,
            "requested_id_count": len(batch_ids),
            "returned_id_count": len(batch_returned),
            "raw_path": str(raw_path),
            "sha256": raw_sha,
            "content_type": b_type,
            "id_set_equal": True,
        })

    returned_set = set(returned_ids)
    denominator_set = set(normalized_ids)
    if len(returned_ids) != len(returned_set):
        raise SystemExit(f"FAIL: {provider}/{role} duplicate IDs across ArcGIS batches")
    missing = sorted(denominator_set - returned_set)
    extra = sorted(returned_set - denominator_set)
    if missing or extra:
        raise SystemExit(
            f"FAIL: {provider}/{role} final ID mismatch missing={missing[:20]} extra={extra[:20]}"
        )

    return {
        "provider_id": provider,
        "request_role": role,
        "identity_state": identity_state,
        "protocol": "ARCGIS_FEATURE_LAYER",
        "request_spec_sha256": request_spec_sha,
        "parent_denominator_sha256": parent_denominator_sha,
        "state": "PASS",
        "http_status": status,
        "object_id_field": oid_field,
        "denominator_id_count": len(normalized_ids),
        "returned_id_count": len(returned_ids),
        "batch_count": len(batch_receipts),
        "arithmetic_closure": len(returned_ids) == len(normalized_ids),
        "id_set_equal": returned_set == denominator_set,
        "id_denominator_raw_path": str(denominator_raw),
        "id_denominator_sha256": denominator_sha,
        "batches": batch_receipts,
    }


def _execute_simple(
    spec: dict,
    output_dir: Path,
    *,
    ordinal: int,
    provider: str,
    role: str,
    identity_state: str,
    timeout: int,
) -> dict:
    req, method = _request_from_spec(spec, ordinal)
    request_spec_sha = canonical_json_sha256(spec)
    parent_denominator_sha = spec.get("parent_denominator_sha256")
    base = safe_name(provider, role, ordinal)
    raw_path = output_dir / (base + ".raw")
    status, content_type, payload, error = _perform(req, timeout)
    raw_sha = _write_raw(raw_path, payload)
    if status != 200 or not payload:
        state = "FAIL"
        semantic_error = error
    else:
        state, semantic_error = _semantic_simple_state(spec, payload)
    return {
        "provider_id": provider,
        "request_role": role,
        "identity_state": identity_state,
        "protocol": spec.get("protocol"),
        "request_spec_sha256": request_spec_sha,
        "parent_denominator_sha256": parent_denominator_sha,
        "request_method": method,
        "request_url": str(spec.get("url", "")),
        "request_body_sha256": sha256_bytes(req.data) if req.data else None,
        "http_status": status,
        "content_type": content_type,
        "bytes": len(payload),
        "sha256": raw_sha,
        "raw_path": str(raw_path) if payload else None,
        "error": error,
        "semantic_error": semantic_error,
        "state": state,
    }


def execute(
    plan: dict,
    output_dir: Path,
    *,
    timeout: int = 120,
    discovery_only: bool = False,
) -> dict:
    query = plan.get("query") or {}
    mode = str(query.get("mode", "")).lower()
    fetch_gate = str(plan.get("fetch_gate", "MISSING"))
    requests = plan.get("requests", [])
    if not isinstance(requests, list):
        raise SystemExit("FAIL: plan.requests must be a list")

    if discovery_only:
        if mode not in {"plan", "fetch"}:
            raise SystemExit(
                f"FAIL: discovery-only executor requires query.mode=plan|fetch; got {mode or 'MISSING'}"
            )
        selected = []
        for spec in requests:
            if not isinstance(spec, dict):
                continue
            identity = str(spec.get("identity_state", "")).upper()
            if "DISCOVERY" in identity or "RESOLVER_STAGE" in identity:
                selected.append(spec)
        if not selected:
            raise SystemExit(
                "FAIL: discovery-only execution found no discovery/resolver-stage request specs"
            )
        requests = selected
        execution_scope = "DISCOVERY_OR_RESOLVER_STAGE"
        effective_gate = "DISCOVERY_ONLY"
    else:
        if mode != "fetch":
            raise SystemExit(f"FAIL: network executor requires query.mode=fetch; got {mode or 'MISSING'}")
        if fetch_gate not in {"READY", "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS"}:
            raise SystemExit(
                f"FAIL: acquisition plan fetch_gate={fetch_gate}; "
                f"blockers={plan.get('fetch_blocker_provider_ids', [])}"
            )
        if not requests:
            raise SystemExit("FAIL: production executor refuses empty request set")
        execution_scope = "PRODUCTION_OR_BOUNDED_DEPENDENT"
        effective_gate = fetch_gate

    output_dir.mkdir(parents=True, exist_ok=True)
    final_receipt = output_dir / "fetch_receipt.json"
    if final_receipt.exists():
        raise SystemExit(
            f"FAIL: output snapshot already exists: {final_receipt}; "
            "use a new versioned output directory"
        )
    receipts: list[dict] = []
    failures = 0

    for ordinal, spec in enumerate(requests, 1):
        if not isinstance(spec, dict):
            raise SystemExit(f"FAIL: request {ordinal} must be an object")
        provider = str(spec.get("provider_id", "unknown"))
        role = str(spec.get("request_role", "unknown"))
        identity_state = str(spec.get("identity_state", "UNRESOLVED"))

        if spec.get("protocol") == "ARCGIS_FEATURE_LAYER":
            receipt = _execute_arcgis(
                spec,
                output_dir,
                ordinal=ordinal,
                provider=provider,
                role=role,
                identity_state=identity_state,
                timeout=timeout,
            )
        else:
            receipt = _execute_simple(
                spec,
                output_dir,
                ordinal=ordinal,
                provider=provider,
                role=role,
                identity_state=identity_state,
                timeout=timeout,
            )

        write_json(output_dir / (safe_name(provider, role, ordinal) + ".json"), receipt)
        receipts.append(receipt)
        if receipt["state"] not in {"PASS", "NO_COVERAGE"}:
            failures += 1

    if failures:
        overall_state = "PARTIAL_OR_BLOCKED"
    elif discovery_only:
        overall_state = "DISCOVERY_PASS"
    elif fetch_gate == "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS":
        overall_state = "PARTIAL"
    else:
        overall_state = "PASS"

    result = {
        "schema_version": "spiderweb.location_query_fetch_receipt.v1.5",
        "query_mode": mode,
        "plan_sha256": canonical_json_sha256(plan),
        "execution_scope": execution_scope,
        "fetch_gate": effective_gate,
        "fetch_blocker_provider_ids": plan.get("fetch_blocker_provider_ids", []),
        "request_count": len(receipts),
        "pass_count": sum(r["state"] in {"PASS", "NO_COVERAGE"} for r in receipts),
        "no_coverage_count": sum(r["state"] == "NO_COVERAGE" for r in receipts),
        "failure_count": failures,
        "state": overall_state,
        "raw_bytes_preserved_before_derivation": True,
        "arcgis_id_denominator_required": True,
        "requests": receipts,
    }
    write_json(final_receipt, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="execute only discovery metadata or explicit RESOLVER_STAGE request specs",
    )
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = execute(
        plan,
        args.output_dir,
        timeout=args.timeout,
        discovery_only=args.discovery_only,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] in {"PASS", "PARTIAL", "DISCOVERY_PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
