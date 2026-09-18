#!/usr/bin/env python3
"""Compatibility USACE root inventory.

This script preserves root bytes and may inventory root-level services only when
the ArcGIS service root advertises no folders. If folders are present it fails
closed: the canonical recursive path is provider_denominators.py +
denominator_chain.py so folder scope remains part of source-service identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT_URL = "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/ArcGIS/rest/services"
USER_AGENT = "spiderweb-pr-location-query-usace-inventory/1.0"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fetch(url: str, timeout: int) -> tuple[int | None, bytes, str | None]:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            return getattr(response, "status", 200), response.read(), None
    except HTTPError as exc:
        return exc.code, exc.read(), f"HTTPError: {exc}"
    except (URLError, TimeoutError) as exc:
        return None, b"", f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    root_url = ROOT_URL + "?f=pjson"
    status, raw, error = fetch(root_url, args.timeout)
    root_path = args.output_dir / "000_service_root.raw"
    if raw:
        root_path.write_bytes(raw)
    if status != 200 or not raw:
        raise SystemExit(f"FAIL: USACE service root unavailable status={status} error={error}")

    try:
        root_obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: USACE service root is not JSON: {exc}") from exc

    services = root_obj.get("services")
    if not isinstance(services, list):
        raise SystemExit("FAIL: USACE service root lacks services list")
    folders = root_obj.get("folders") or []
    if not isinstance(folders, list) or any(not isinstance(value, str) for value in folders):
        raise SystemExit("FAIL: USACE service root folders malformed")
    if folders:
        raise SystemExit(
            "FAIL: USACE service root advertises folders; root-only inventory is non-exhaustive. "
            "Use LOCATION_QUERY services_root_denominator -> freeze_location_provider_denominator.py "
            "-> build_location_denominator_stage.py -> merge_location_service_denominators.py"
        )

    normalized = []
    seen = set()
    for row in services:
        if not isinstance(row, dict):
            raise SystemExit("FAIL: non-object service row")
        name = str(row.get("name", "")).strip()
        service_type = str(row.get("type", "")).strip()
        if not name or not service_type:
            raise SystemExit("FAIL: service row lacks name/type")
        identity = (name, service_type)
        if identity in seen:
            raise SystemExit(f"FAIL: duplicate service identity {identity}")
        seen.add(identity)
        normalized.append(identity)
    normalized.sort(key=lambda value: (value[0].casefold(), value[1].casefold()))

    records = []
    failures = 0
    for ordinal, (name, service_type) in enumerate(normalized, 1):
        encoded_name = quote(name, safe="/")
        url = f"{ROOT_URL}/{encoded_name}/{quote(service_type, safe='')}?f=pjson"
        status, payload, error = fetch(url, args.timeout)
        raw_path = args.output_dir / f"{ordinal:04d}_{sha256_bytes((name+'|'+service_type).encode())[:16]}.raw"
        if payload:
            raw_path.write_bytes(payload)
        metadata = None
        parse_error = None
        if payload:
            try:
                metadata = json.loads(payload.decode("utf-8"))
            except Exception as exc:
                parse_error = f"{type(exc).__name__}: {exc}"
        state = "PASS" if status == 200 and isinstance(metadata, dict) and not metadata.get("error") else "FAIL"
        failures += int(state == "FAIL")
        layers = []
        tables = []
        if isinstance(metadata, dict):
            for key, target in (("layers", layers), ("tables", tables)):
                values = metadata.get(key) or []
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, dict):
                            target.append({"id": item.get("id"), "name": item.get("name")})
        records.append({
            "service_name": name,
            "service_type": service_type,
            "url": url,
            "http_status": status,
            "state": state,
            "error": error,
            "parse_error": parse_error,
            "raw_path": str(raw_path) if payload else None,
            "raw_sha256": sha256_bytes(payload) if payload else None,
            "layers": layers,
            "tables": tables,
        })

    result = {
        "schema_version": "spiderweb.usace_service_denominator.v1.0",
        "authority": "U.S. Army Corps of Engineers",
        "service_root": ROOT_URL,
        "root_raw_path": str(root_path),
        "root_raw_sha256": sha256_bytes(raw),
        "service_count": len(normalized),
        "unique_service_count": len(seen),
        "failure_count": failures,
        "state": "PASS" if failures == 0 else "PARTIAL_OR_BLOCKED",
        "puerto_rico_subset_classified": False,
        "records": records,
        "invariants": {
            "root_first": True,
            "service_identity_unique": len(normalized) == len(seen),
            "source_absence_not_inferred_from_query_omission": True,
            "folder_denominator_zero": True,
        },
    }
    write_json(args.output_dir / "USACE_SERVICE_DENOMINATOR.json", result)
    print(json.dumps({
        "state": result["state"],
        "service_count": result["service_count"],
        "failure_count": failures,
        "output": str(args.output_dir / "USACE_SERVICE_DENOMINATOR.json"),
    }, indent=2, sort_keys=True))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
