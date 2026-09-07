#!/usr/bin/env python3
"""Fail-closed arithmetic/cardinality validator for spatial migration receipts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "federation-spatial-migration/1.1"
CARDINALITIES = {"1:1", "1:N", "N:1", "N:N", "0:1", "UNRESOLVED"}
PRODUCERS = {
    "spiderweb-pr",
    "aguayluz-pr",
    "moneysweep-pr",
    "skywatcher-pr",
    "thehub-pr",
}
REQUIRED_FIELDS = {
    "contract_version",
    "migration_id",
    "producer_repo",
    "source_count",
    "retained_count",
    "excluded_count",
    "unresolved_count",
    "join_output_count",
    "declared_cardinality",
    "multiplication_expected",
    "provenance",
}
OPTIONAL_FIELDS = {
    "multiplication_reason",
    "source_manifestation_ids",
    "output_manifestation_ids",
    "notes",
}


def validate(receipt: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(receipt, Mapping):
        return ["receipt root must be an object"]

    missing = sorted(REQUIRED_FIELDS - set(receipt))
    if missing:
        problems.append(f"missing required fields: {missing}")
    unexpected = sorted(set(receipt) - REQUIRED_FIELDS - OPTIONAL_FIELDS)
    if unexpected:
        problems.append(f"unexpected fields: {unexpected}")

    if receipt.get("contract_version") != CONTRACT_VERSION:
        problems.append("contract_version mismatch")

    migration_id = receipt.get("migration_id")
    if not isinstance(migration_id, str) or not migration_id.strip():
        problems.append("migration_id must be a non-empty string")

    producer = receipt.get("producer_repo")
    if producer not in PRODUCERS:
        problems.append(f"unsupported producer_repo {producer!r}")

    if not isinstance(receipt.get("provenance"), Mapping):
        problems.append("provenance must be an object")

    multiplication_expected = receipt.get("multiplication_expected")
    if not isinstance(multiplication_expected, bool):
        problems.append("multiplication_expected must be a boolean")

    multiplication_reason = receipt.get("multiplication_reason")
    if multiplication_reason is not None and (
        not isinstance(multiplication_reason, str) or not multiplication_reason.strip()
    ):
        problems.append("multiplication_reason must be a non-empty string or null")

    for field in ("source_manifestation_ids", "output_manifestation_ids"):
        values = receipt.get(field)
        if values is None:
            continue
        if not isinstance(values, list):
            problems.append(f"{field} must be an array")
            continue
        if any(not isinstance(value, str) or not value.strip() for value in values):
            problems.append(f"{field} must contain only non-empty strings")
        elif len(values) != len(set(values)):
            problems.append(f"{field} must not contain duplicates")

    numeric = [
        "source_count",
        "retained_count",
        "excluded_count",
        "unresolved_count",
        "join_output_count",
    ]
    numeric_valid = True
    for field in numeric:
        value = receipt.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"{field} must be a non-negative integer")
            numeric_valid = False

    card = receipt.get("declared_cardinality")
    if card not in CARDINALITIES:
        problems.append(f"unsupported declared_cardinality {card!r}")

    if not numeric_valid or card not in CARDINALITIES:
        return problems

    source = receipt["source_count"]
    retained = receipt["retained_count"]
    excluded = receipt["excluded_count"]
    unresolved = receipt["unresolved_count"]
    output = receipt["join_output_count"]

    if source != retained + excluded + unresolved:
        problems.append(
            f"arithmetic closure failed: source={source} != retained={retained} "
            f"+ excluded={excluded} + unresolved={unresolved}"
        )

    expected_multiplication = multiplication_expected is True
    if expected_multiplication and not multiplication_reason:
        problems.append("multiplication_expected requires multiplication_reason")
    if multiplication_expected is False and multiplication_reason is not None:
        problems.append("multiplication_reason requires multiplication_expected=true")

    # 1:1 and 0:1 cannot increase row count. N:1 should not increase it either.
    if card in {"1:1", "0:1", "N:1"} and output > retained:
        problems.append(
            f"unexpected join multiplication for cardinality {card}: "
            f"output={output} retained={retained}"
        )

    # 1:N/N:N may multiply, but only when explicitly acknowledged.
    if card in {"1:N", "N:N"} and output > retained and not expected_multiplication:
        problems.append(
            f"join multiplication not declared for cardinality {card}: "
            f"output={output} retained={retained}"
        )
    if expected_multiplication and output <= retained:
        problems.append(
            "declared join multiplication was not observed: "
            f"output={output} retained={retained}"
        )

    if card == "UNRESOLVED" and unresolved == 0:
        problems.append("UNRESOLVED cardinality requires unresolved_count > 0")

    # Any row that is retained should have at least one output unless the declared
    # state itself is unresolved. This prevents silent post-retention loss.
    if retained > 0 and output == 0 and card != "UNRESOLVED":
        problems.append("retained rows vanished from join output")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    problems = validate(receipt)
    if problems:
        print("FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
