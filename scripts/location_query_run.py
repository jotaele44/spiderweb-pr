#!/usr/bin/env python3
"""Execute a complete LOCATION_QUERY plan across generic and specialized lanes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.execution_orchestrator import execute_location_query


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = execute_location_query(plan, args.output_dir, timeout=args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
