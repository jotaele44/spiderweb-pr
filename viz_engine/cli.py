"""Command line: ``python -m viz_engine render|verify``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import VIEWS, render, verify_artifact


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="viz_engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render a view from a frozen snapshot")
    r.add_argument("--view", choices=sorted(VIEWS), required=True)
    r.add_argument(
        "--snapshot", required=True, help="snapshot directory (contains snapshot.json)"
    )
    r.add_argument("--config", required=True, help="scene/config JSON")
    r.add_argument("--out", required=True)
    v = sub.add_parser("verify", help="check an artifact against its receipt hash")
    v.add_argument("--artifact", required=True)
    v.add_argument("--receipt", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "verify":
        ok = verify_artifact(args.artifact, args.receipt)
        print("OK" if ok else "HASH MISMATCH")
        return 0 if ok else 1
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    res = render(args.snapshot, args.view, config, args.out)
    print(f"{res.status} {res.artifact} {res.receipt['output']['sha256']}")
    return 0 if res.status == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
