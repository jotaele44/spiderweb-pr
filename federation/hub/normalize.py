"""Validate a loaded package and report a per-producer PASS/FAIL.

Combines load-time errors with fail-closed envelope/financial validation so the
hub can refuse to query when either producer's package is not clean.
"""
from __future__ import annotations

from typing import Any, Dict

from ..validator import validate_package


def normalize_package(loaded: Dict[str, Any], *, reject_synthetic: bool = False) -> Dict[str, Any]:
    """Return {producer, status, errors, records} for a loaded package.

    ``status`` is "PASS" only when the package loaded cleanly AND validates.
    """
    producer = loaded.get("producer") or loaded.get("dir") or "unknown"
    errors = list(loaded.get("errors") or [])
    prefix = loaded.get("prefix")
    streams = loaded.get("streams") or {}

    if prefix:
        result = validate_package(
            streams,
            expected_prefix=prefix,
            require_financial=True,
            reject_synthetic=reject_synthetic,
        )
    else:
        # Unknown producer => cannot establish the namespace => fail closed.
        result = {"valid": False, "errors": ["unknown producer / prefix"], "count": 0}
    errors.extend(result.get("errors") or [])

    status = "PASS" if (not errors and result.get("valid")) else "FAIL"
    return {
        "producer": producer,
        "status": status,
        "errors": errors,
        "records": list(loaded.get("records") or []),
    }
