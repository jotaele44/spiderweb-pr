#!/usr/bin/env python3
"""Execute bounded LOCATION_QUERY provider request specs.

The executor preserves every raw response before interpretation, writes a
per-request SHA-256 receipt, and never promotes discovery responses to source
identity. It supports GET plus explicitly planned JSON POST requests for
dependent provider stages such as SSURGO SDA tabular acquisition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "spiderweb-pr-location-query/1.0"
ALLOWED_METHODS = {"GET", "POST"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def execute(plan: dict, output_dir: Path, *, timeout: int = 120) -> dict:
    query = plan.get("query") or {}
    mode = str(query.get("mode", "")).lower()
    if mode != "fetch":
        raise SystemExit(f"FAIL: network executor requires query.mode=fetch; got {mode or 'MISSING'}")
    requests = plan.get("requests", [])
    if not isinstance(requests, list):
        raise SystemExit("FAIL: plan.requests must be a list")

    output_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    failures = 0

    for ordinal, spec in enumerate(requests, 1):
        provider = str(spec.get("provider_id", "unknown"))
        role = str(spec.get("request_role", "unknown"))
        identity_state = str(spec.get("identity_state", "UNRESOLVED"))
        url = str(spec.get("url", ""))
        req, method = _request_from_spec(spec, ordinal)

        base = safe_name(provider, role, ordinal)
        raw_path = output_dir / (base + ".raw")
        receipt_path = output_dir / (base + ".json")

        status = None
        content_type = ""
        payload = b""
        error = None
        try:
            with urlopen(req, timeout=timeout) as response:  # noqa: S310
                status = getattr(response, "status", 200)
                content_type = response.headers.get("Content-Type", "")
                payload = response.read()
        except HTTPError as exc:
            status = exc.code
            payload = exc.read()
            error = f"HTTPError: {exc}"
        except (URLError, TimeoutError) as exc:
            error = f"{type(exc).__name__}: {exc}"

        if payload:
            raw_path.write_bytes(payload)

        state = "PASS" if status == 200 and payload else "FAIL"
        if state != "PASS":
            failures += 1

        receipt = {
            "provider_id": provider,
            "request_role": role,
            "identity_state": identity_state,
            "request_method": method,
            "request_url": url,
            "request_body_sha256": sha256_bytes(req.data) if req.data else None,
            "http_status": status,
            "content_type": content_type,
            "bytes": len(payload),
            "sha256": sha256_bytes(payload) if payload else None,
            "raw_path": str(raw_path) if payload else None,
            "error": error,
            "state": state,
        }
        write_json(receipt_path, receipt)
        receipts.append(receipt)

    result = {
        "schema_version": "spiderweb.location_query_fetch_receipt.v1.1",
        "query_mode": mode,
        "request_count": len(receipts),
        "pass_count": sum(r["state"] == "PASS" for r in receipts),
        "failure_count": failures,
        "state": "PASS" if failures == 0 else "PARTIAL_OR_BLOCKED",
        "raw_bytes_preserved_before_derivation": True,
        "requests": receipts,
    }
    write_json(output_dir / "fetch_receipt.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = execute(plan, args.output_dir, timeout=args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
