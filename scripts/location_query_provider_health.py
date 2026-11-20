#!/usr/bin/env python3
"""NONCANONICAL compatibility provider-health probe.

Canonical health auditing is scripts/audit_location_query_provider_health.py,
which separates transport/provider errors from coverage and source identity.
This legacy probe is retained only for compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "spiderweb-pr-location-query-health/1.0"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def probe_urls(provider_id: str, provider: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if provider.get("feature_service"):
        rows.append(("feature_service", provider["feature_service"].rstrip("/") + "?f=json"))
    if provider.get("layer_url"):
        rows.append(("layer", provider["layer_url"].rstrip("/") + "?f=json"))
    if provider.get("service_root"):
        rows.append(("service_root", provider["service_root"].rstrip("/") + "?f=pjson"))
    if provider.get("map_service"):
        rows.append(("map_service", provider["map_service"].rstrip("/") + "?f=json"))
    if provider.get("wfs_endpoint"):
        params = urlencode({"SERVICE": "WFS", "REQUEST": "GetCapabilities"})
        rows.append(("wfs_capabilities", provider["wfs_endpoint"] + "?" + params))
    if provider.get("wms_capabilities"):
        rows.append(("wms_capabilities", provider["wms_capabilities"]))
    for index, item in enumerate(provider.get("layers") or [], 1):
        if isinstance(item, dict) and item.get("url"):
            rows.append((f"layer_{index}_{item.get('role','unknown')}", str(item["url"]).rstrip("/") + "?f=json"))
    return rows


def fetch(url: str, timeout: int) -> tuple[int | None, str, bytes, str | None]:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            return (
                getattr(response, "status", 200),
                response.headers.get("Content-Type", ""),
                response.read(),
                None,
            )
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read(), f"HTTPError: {exc}"
    except (URLError, TimeoutError) as exc:
        return None, "", b"", f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("configs/location_query_providers.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--allow-noncanonical-compat", action="store_true")
    args = parser.parse_args()
    if not args.allow_noncanonical_compat:
        raise SystemExit(
            "FAIL: location_query_provider_health.py is NONCANONICAL compatibility only; "
            "use scripts/audit_location_query_provider_health.py"
        )

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    providers = registry.get("providers")
    if not isinstance(providers, dict):
        raise SystemExit("FAIL: provider registry malformed")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    records = []
    probe_count = 0
    failures = 0
    for provider_id, provider in sorted(providers.items()):
        urls = probe_urls(provider_id, provider)
        if not urls:
            records.append({
                "provider_id": provider_id,
                "state": "NOT_PROBED_NO_METADATA_URL",
                "probe_count": 0,
                "coverage_inference_allowed": False,
            })
            continue

        provider_rows = []
        for label, url in urls:
            probe_count += 1
            status, content_type, payload, error = fetch(url, args.timeout)
            raw_path = args.output_dir / f"{probe_count:04d}_{provider_id}_{label}.raw"
            if payload:
                raw_path.write_bytes(payload)
            state = "PASS" if status == 200 and payload else "FAIL"
            failures += int(state == "FAIL")
            provider_rows.append({
                "label": label,
                "url": url,
                "http_status": status,
                "content_type": content_type,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload) if payload else None,
                "raw_path": str(raw_path) if payload else None,
                "error": error,
                "state": state,
            })

        records.append({
            "provider_id": provider_id,
            "state": "PASS" if all(row["state"] == "PASS" for row in provider_rows) else "PARTIAL_OR_BLOCKED",
            "probe_count": len(provider_rows),
            "coverage_inference_allowed": False,
            "probes": provider_rows,
        })

    result = {
        "schema_version": "spiderweb.location_query_provider_health.v1.1",
        "classification": "NONCANONICAL_COMPATIBILITY",
        "canonical_certification": False,
        "provider_count": len(providers),
        "probe_count": probe_count,
        "failure_count": failures,
        "state": "PASS" if failures == 0 else "PARTIAL_OR_BLOCKED",
        "health_is_not_coverage": True,
        "health_failure_is_not_source_absence": True,
        "providers": records,
    }
    write_json(args.output_dir / "provider_health.json", result)
    print(json.dumps({
        "state": result["state"],
        "provider_count": len(providers),
        "probe_count": probe_count,
        "failure_count": failures,
    }, indent=2, sort_keys=True))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
