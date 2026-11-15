#!/usr/bin/env python3
"""Build the committed access-point registry documents from repository inputs.

Offline and deterministic: the same inputs always produce byte-identical
documents under ``registry/access_points/``.

    python scripts/build_access_point_registries.py           # rebuild
    python scripts/build_access_point_registries.py --check   # fail if stale
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.access_points.seeding import (  # noqa: E402
    REGISTRY_DIR,
    build_all,
    write_documents,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="verify committed documents are current"
    )
    args = parser.parse_args(argv)

    result = build_all(REPO_ROOT)
    if args.check:
        with tempfile.TemporaryDirectory() as scratch:
            fresh = write_documents(result, scratch)
            stale = []
            for name, digest in sorted(fresh.items()):
                committed = REPO_ROOT / REGISTRY_DIR / name
                if not committed.is_file():
                    stale.append(f"{name}: missing")
                elif hashlib.sha256(committed.read_bytes()).hexdigest() != digest:
                    stale.append(f"{name}: differs from a fresh build")
        if stale:
            print("STALE registry documents:\n  " + "\n  ".join(stale))
            return 1
        print("registry documents are current")
        return 0

    hashes = write_documents(result, REPO_ROOT)
    for name, digest in sorted(hashes.items()):
        print(f"{digest}  {REGISTRY_DIR}/{name}")
    print(
        f"inland features: {result.inland.counts()['features']}  "
        f"offshore features: {result.offshore.counts()['features']}  "
        f"relationships: {len(result.ledger.relationships)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
