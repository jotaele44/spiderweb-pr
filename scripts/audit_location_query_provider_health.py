#!/usr/bin/env python3
"""Audit LOCATION_QUERY provider readiness and optionally probe metadata surfaces.

Default mode is offline: validate registry structure, adapter references, readiness
semantics, and compute a deterministic canonical registry hash. --network performs
bounded metadata GETs only for explicit health URLs and never fetches production
GIS payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/location_query_providers.json"
ALLOWED = {
    "READY", "READY_WITH_CREDENTIALS", "READY_SPECIALIZED", "RESOLVER_ONLY",
    "PROVIDER_BINDING_OPEN", "SCHEMA_ONLY", "NOT_IMPLEMENTED", "BLOCKED",
}

def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()

def health_url(provider: dict) -> str | None:
    for key in ("feature_service", "service_root", "map_service", "wms_capabilities", "wfs_endpoint", "layer_url"):
        value = provider.get(key)
        if isinstance(value, str) and value:
            return value
    layers = provider.get("layers")
    if isinstance(layers, list) and layers:
        value = layers[0].get("url")
        if isinstance(value, str) and value:
            return value.rsplit("/", 1)[0] + "?f=json"
    return None

def probe(url: str, timeout: int) -> dict:
    req = Request(
        url,
        headers={
            "User-Agent": "spiderweb-pr-location-query-health/1.0",
            "Accept": "*/*",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            data = response.read(65536)
    except HTTPError as exc:
        return {
            "state": "FAIL_HTTP",
            "http_status": exc.code,
            "error": f"HTTPError: {exc}",
            "coverage_inference_allowed": False,
        }
    except (URLError, TimeoutError) as exc:
        return {
            "state": "FAIL_TRANSPORT",
            "http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
            "coverage_inference_allowed": False,
        }

    state = "RESPONSIVE"
    semantic_note = None
    stripped = data.lstrip()
    lowered = stripped[:4096].lower()

    if b"<serviceexception" in lowered or b"<exceptionreport" in lowered:
        state = "FAIL_PROVIDER_ERROR"
        semantic_note = "OGC exception document observed in health sample"
    elif "json" in content_type.casefold() or stripped.startswith((b"{", b"[")):
        try:
            obj = json.loads(data.decode("utf-8"))
        except Exception:
            state = "RESPONSIVE_UNPARSED_SAMPLE"
            semantic_note = "sample may be truncated; no metadata certification inferred"
        else:
            if isinstance(obj, dict) and obj.get("error"):
                state = "FAIL_PROVIDER_ERROR"
                semantic_note = f"provider JSON error: {obj['error']}"

    return {
        "state": state,
        "http_status": status,
        "content_type": content_type,
        "sample_bytes": len(data),
        "sample_sha256": hashlib.sha256(data).hexdigest(),
        "semantic_note": semantic_note,
        "health_is_not_coverage": True,
        "coverage_inference_allowed": False,
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", action="store_true")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    obj = json.loads(REGISTRY.read_text(encoding="utf-8"))
    providers = obj.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise SystemExit("FAIL: malformed provider registry")
    states = obj.get("readiness_states")
    if set(states or []) != ALLOWED:
        raise SystemExit("FAIL: readiness-state denominator drift")

    rows = []
    counts: dict[str, int] = {}
    network_failure_count = 0
    for provider_id, provider in sorted(providers.items()):
        status = provider.get("status")
        if status not in ALLOWED:
            raise SystemExit(f"FAIL: {provider_id}: invalid status {status!r}")
        modes = provider.get("query_modes")
        if not isinstance(modes, list) or not modes:
            raise SystemExit(f"FAIL: {provider_id}: empty query_modes")
        counts[status] = counts.get(status, 0) + 1
        url = health_url(provider)
        row = {"provider_id": provider_id, "family": provider.get("family"), "status": status,
               "query_modes": modes, "health_url": url, "network_probe": "NOT_RUN"}
        if args.network and url:
            row["network_probe"] = probe(url, args.timeout)
            if str(row["network_probe"].get("state", "")).startswith("FAIL"):
                network_failure_count += 1
        rows.append(row)

    result = {
        "schema_version": "spiderweb.location_query_provider_health.v1.0",
        "registry_path": str(REGISTRY.relative_to(ROOT)),
        "provider_count": len(rows),
        "readiness_counts": dict(sorted(counts.items())),
        "canonical_registry_sha256": canonical_hash(obj),
        "network_enabled": args.network,
        "network_failure_count": network_failure_count,
        "health_is_not_coverage": True,
        "health_failure_is_not_source_absence": True,
        "providers": rows,
        "state": (
            "PASS"
            if not args.network
            else ("PASS" if network_failure_count == 0 else "PARTIAL_OR_BLOCKED")
        ),
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["state"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
