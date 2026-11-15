#!/usr/bin/env python3
"""Verify other producers' exported packages as read-only context sources.

Offline.  Reads exported package directories only; imports no sibling code.
For every producer it records whether a package was found, whether its
manifest closes (hashes and row counts), and what context it yields.  A
producer with no exported package is BLOCKED, not empty.

    python scripts/verify_access_point_federation_context.py \
        --package aguayluz-pr=../aguayluz-pr/exports/federation \
        --package moneysweep-pr=../moneysweep-pr/exports/federation \
        --package skywatcher-pr=../skywatcher-pr/exports/federation \
        --head aguayluz-pr=<sha> ... --output evidence/access_points/cross_repository_verification_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from federation.spatial_core import canonical_json_sha256  # noqa: E402
from spiderweb.access_points.federation_context import (  # noqa: E402
    CONTEXT_VERSION,
    PackageIntegrityError,
    aguayluz_context,
    lifecycle_from_documents,
    load_package,
    moneysweep_context,
)

_EXTRACTORS = {"aguayluz-pr": aguayluz_context, "moneysweep-pr": moneysweep_context}


def verify(producer: str, directory: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "producer": producer,
        "package_directory_name": directory.name,
    }
    if not (directory / "manifest.json").is_file():
        entry.update(
            state="BLOCKED",
            claim_class="FACT",
            detail="no exported package (manifest.json) exists at the producer's export location",
        )
        return entry
    try:
        package = load_package(directory, expected_producer=producer)
    except PackageIntegrityError as exc:
        entry.update(state="FAIL", claim_class="COMPUTED", detail=str(exc))
        return entry
    entry.update(
        state="PASS",
        claim_class="COMPUTED",
        detail="manifest closes: every listed file hashes and counts as stated",
        export_contract_version=package.contract_version,
        package_id=package.package_id,
        manifest_mode=package.mode,
        streams={name: len(rows) for name, rows in sorted(package.streams.items())},
        synthetic_rows_dropped=package.synthetic_rows_dropped,
        files=[
            {
                "filename": f["filename"],
                "sha256": f["sha256"],
                "record_count": f["record_count"],
            }
            for f in package.files
        ],
    )
    extractor = _EXTRACTORS.get(producer)
    if extractor is None:
        entry["context"] = {
            "state": "NOT_CONSUMED",
            "detail": "package verified; no access-point context is drawn from this producer",
        }
        return entry
    records = extractor(package)
    kinds = Counter(r.record_kind for r in records)
    entry["context"] = {
        "state": "PASS",
        "records": len(records),
        "by_kind": dict(sorted(kinds.items())),
        "by_coordinate_basis": dict(
            sorted(Counter(r.coordinate_basis.value for r in records).items())
        ),
        "placeable_records": sum(1 for r in records if r.placeable),
        "diagnostic_only_records": sum(1 for r in records if r.diagnostic_only),
        "furthest_lifecycle_documents_can_show": lifecycle_from_documents(kinds).value,
        "statement": (
            "context only: none of these records can create, locate or raise the evidence "
            "tier of an access-point feature"
        ),
    }
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--package", action="append", default=[], metavar="PRODUCER=DIR"
    )
    parser.add_argument("--head", action="append", default=[], metavar="PRODUCER=SHA")
    parser.add_argument("--generated-utc", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    heads = dict(item.split("=", 1) for item in args.head)
    producers = []
    for item in args.package:
        producer, directory = item.split("=", 1)
        entry = verify(producer, Path(directory))
        entry["producer_head_sha"] = heads.get(producer)
        producers.append(entry)
    body: dict[str, Any] = {
        "schema": "access_point_cross_repository_verification/1.0",
        "context_version": CONTEXT_VERSION,
        "generated_utc": args.generated_utc,
        "method": "exported packages read from sibling checkouts; no sibling code imported",
        "producers": producers,
        "invariants": [
            "foreign identifiers are referenced verbatim and never re-minted",
            "an absent stream or package is not zero records",
            "cross-producer correlation and identity belong to the hub, not to this repository",
        ],
    }
    body["content_sha256"] = canonical_json_sha256(body)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(body, indent=1))
    return 0 if all(p["state"] != "FAIL" for p in producers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
