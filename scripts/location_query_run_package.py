#!/usr/bin/env python3
"""Freeze a unified LOCATION_QUERY run into a cross-lane package manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_json_sha256(value: object) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _require_file(path_value: object, expected_sha: object, label: str) -> tuple[Path, str]:
    if not isinstance(path_value, str) or not path_value:
        raise SystemExit(f"FAIL: {label} path missing")
    path = Path(path_value)
    if not path.is_file():
        raise SystemExit(f"FAIL: {label} file missing: {path}")
    actual = sha256_file(path)
    if not isinstance(expected_sha, str) or actual != expected_sha:
        raise SystemExit(
            f"FAIL: {label} SHA256 mismatch expected={expected_sha} actual={actual}"
        )
    return path, actual


def _generic_raw_records(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for request in receipt.get("requests") or []:
        paths: list[tuple[object, object, str]] = []
        if request.get("raw_path"):
            paths.append((request["raw_path"], request.get("sha256"), "raw"))
        if request.get("id_denominator_raw_path"):
            paths.append(
                (
                    request["id_denominator_raw_path"],
                    request.get("id_denominator_sha256"),
                    "arcgis_id_denominator",
                )
            )
        for batch in request.get("batches") or []:
            if batch.get("raw_path"):
                paths.append((batch["raw_path"], batch.get("sha256"), "arcgis_batch"))
        for path_value, expected, kind in paths:
            path, actual = _require_file(path_value, expected, f"generic {kind}")
            records.append(
                {
                    "lane": "generic",
                    "kind": kind,
                    "provider_id": request.get("provider_id"),
                    "request_role": request.get("request_role"),
                    "path": str(path),
                    "sha256": actual,
                    "bytes": path.stat().st_size,
                }
            )
    return records


def _specialized_raw_records(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in receipt.get("records") or []:
        if row.get("state") != "PASS":
            continue
        path, actual = _require_file(
            row.get("raw_path"),
            row.get("sha256"),
            "specialized raw",
        )
        records.append(
            {
                "lane": "specialized",
                "kind": "source_bytes",
                "provider_id": row.get("provider_id"),
                "request_role": row.get("execution_kind"),
                "path": str(path),
                "sha256": actual,
                "bytes": path.stat().st_size,
            }
        )
        metadata_path = row.get("metadata_path")
        metadata_sha = row.get("metadata_sha256")
        if metadata_path:
            meta, meta_actual = _require_file(
                metadata_path,
                metadata_sha,
                "specialized metadata",
            )
            records.append(
                {
                    "lane": "specialized",
                    "kind": "provider_metadata",
                    "provider_id": row.get("provider_id"),
                    "request_role": row.get("execution_kind"),
                    "path": str(meta),
                    "sha256": meta_actual,
                    "bytes": meta.stat().st_size,
                }
            )
    return records


def build_package(
    *,
    plan_path: Path,
    run_receipt_path: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise SystemExit(
            f"FAIL: unified package manifest already exists: {output}"
        )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    run = json.loads(run_receipt_path.read_text(encoding="utf-8"))

    plan_sha = canonical_json_sha256(plan)
    if run.get("full_plan_sha256") != plan_sha:
        raise SystemExit("FAIL: run receipt full-plan SHA256 mismatch")
    if run.get("provider_registry_sha256") != plan.get("provider_registry_sha256"):
        raise SystemExit("FAIL: run/provider registry SHA256 mismatch")

    generic_info = run.get("generic") or {}
    specialized_info = run.get("specialized") or {}
    generic_path, generic_sha = _require_file(
        generic_info.get("receipt_path"),
        generic_info.get("receipt_sha256"),
        "generic subreceipt",
    )
    specialized_path, specialized_sha = _require_file(
        specialized_info.get("receipt_path"),
        specialized_info.get("receipt_sha256"),
        "specialized subreceipt",
    )

    generic = json.loads(generic_path.read_text(encoding="utf-8"))
    specialized = json.loads(specialized_path.read_text(encoding="utf-8"))

    if generic.get("request_count") != run.get("arithmetic", {}).get(
        "executed_generic_requests"
    ):
        raise SystemExit("FAIL: generic request-count drift")
    if specialized.get("call_count") != run.get("arithmetic", {}).get(
        "executed_specialized_calls"
    ):
        raise SystemExit("FAIL: specialized call-count drift")

    raw_records = _generic_raw_records(generic) + _specialized_raw_records(specialized)
    paths = [row["path"] for row in raw_records]
    if len(paths) != len(set(paths)):
        raise SystemExit("FAIL: duplicate artifact path across execution lanes")

    result = {
        "schema_version": "spiderweb.location_query_run_package.v1.0",
        "state": run.get("state"),
        "query_id": (plan.get("query") or {}).get("query_id"),
        "provider_registry_sha256": plan.get("provider_registry_sha256"),
        "plan": {
            "path": str(plan_path),
            "byte_sha256": sha256_file(plan_path),
            "canonical_json_sha256": plan_sha,
        },
        "run_receipt": {
            "path": str(run_receipt_path),
            "sha256": sha256_file(run_receipt_path),
        },
        "generic_receipt": {
            "path": str(generic_path),
            "sha256": generic_sha,
            "state": generic.get("state"),
        },
        "specialized_receipt": {
            "path": str(specialized_path),
            "sha256": specialized_sha,
            "state": specialized.get("state"),
        },
        "artifact_count": len(raw_records),
        "total_bytes": sum(row["bytes"] for row in raw_records),
        "artifacts": raw_records,
        "invariants": {
            "full_plan_hash_equal": True,
            "provider_registry_hash_equal": True,
            "subreceipt_hashes_equal": True,
            "artifact_paths_unique": len(paths) == len(set(paths)),
            "source_lanes_preserved": True,
            "source_rows_not_aggregated": True,
        },
    }
    write_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("run_receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = build_package(
        plan_path=args.plan,
        run_receipt_path=args.run_receipt,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
