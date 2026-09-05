#!/usr/bin/env python3
"""Fail-closed arithmetic/cardinality validator for spatial migration receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "federation-spatial-migration/1.1"
CARDINALITIES = {"1:1", "1:N", "N:1", "N:N", "0:1", "UNRESOLVED"}


def validate(receipt: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if receipt.get("contract_version") != CONTRACT_VERSION:
        problems.append("contract_version mismatch")

    numeric = ["source_count", "retained_count", "excluded_count", "unresolved_count", "join_output_count"]
    for field in numeric:
        value = receipt.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"{field} must be a non-negative integer")

    if problems:
        return problems

    source = receipt["source_count"]
    retained = receipt["retained_count"]
    excluded = receipt["excluded_count"]
    unresolved = receipt["unresolved_count"]
    output = receipt["join_output_count"]
    card = receipt.get("declared_cardinality")

    if source != retained + excluded + unresolved:
        problems.append(
            f"arithmetic closure failed: source={source} != retained={retained} + excluded={excluded} + unresolved={unresolved}"
        )

    if card not in CARDINALITIES:
        problems.append(f"unsupported declared_cardinality {card!r}")
        return problems

    expected_multiplication = bool(receipt.get("multiplication_expected", False))
    reason = receipt.get("multiplication_reason")
    if expected_multiplication and not reason:
        problems.append("multiplication_expected requires multiplication_reason")

    # 1:1 and 0:1 cannot increase row count. N:1 should not increase it either.
    if card in {"1:1", "0:1", "N:1"} and output > retained:
        problems.append(f"unexpected join multiplication for cardinality {card}: output={output} retained={retained}")

    # 1:N/N:N may multiply, but only when explicitly acknowledged.
    if card in {"1:N", "N:N"} and output > retained and not expected_multiplication:
        problems.append(f"join multiplication not declared for cardinality {card}: output={output} retained={retained}")

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
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
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
