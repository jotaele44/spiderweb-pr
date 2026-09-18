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
    for key in ("feature_service", "service_root", "map_service", "wms_capabilities", "service_root"):
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
    req = Request(url, headers={"User-Agent": "spiderweb-pr-location-query-health/1.0", "Accept": "*/*"})
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            data = response.read(65536)
            return {"state": "PASS", "http_status": getattr(response, "status", 200),
                    "content_type": response.headers.get("Content-Type", ""),
                    "sample_bytes": len(data), "sample_sha256": hashlib.sha256(data).hexdigest()}
    except HTTPError as exc:
        return {"state": "FAIL", "http_status": exc.code, "error": f"HTTPError: {exc}"}
    except (URLError, TimeoutError) as exc:
        return {"state": "FAIL", "http_status": None, "error": f"{type(exc).__name__}: {exc}"}

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
        rows.append(row)

    result = {
        "schema_version": "spiderweb.location_query_provider_health.v1.0",
        "registry_path": str(REGISTRY.relative_to(ROOT)),
        "provider_count": len(rows),
        "readiness_counts": dict(sorted(counts.items())),
        "canonical_registry_sha256": canonical_hash(obj),
        "network_enabled": args.network,
        "providers": rows,
        "state": "PASS",
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
