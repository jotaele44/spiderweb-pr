#!/usr/bin/env python3
"""Execute fully parameterized specialized calls from a LOCATION_QUERY plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.specialized_execution import execute_specialized_calls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = execute_specialized_calls(plan, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
