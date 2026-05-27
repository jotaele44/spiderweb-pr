"""
Bulk-validate a directory of satellite source manifest JSON files.

Usage:
    python -m scripts.validate_satellite_batch <manifest_dir> [--dry-run] [--fail-fast]

Exits 0 if all manifests are accepted, 1 if any are rejected.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from readiness.satellite_ingest import SatelliteIngest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk validate satellite source manifest JSON files."
    )
    parser.add_argument("manifest_dir", help="Directory containing manifest .json files")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Validate only; do not write outputs")
    parser.add_argument("--fail-fast", action="store_true", default=False,
                        help="Stop on the first rejected manifest")
    args = parser.parse_args()

    manifest_dir = Path(args.manifest_dir)
    if not manifest_dir.is_dir():
        print(f"ERROR: {manifest_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    manifests = sorted(manifest_dir.glob("*.json"))
    if not manifests:
        print(f"No .json files found in {manifest_dir}")
        sys.exit(0)

    ingester = SatelliteIngest(dry_run=args.dry_run)
    accepted = 0
    rejected = 0

    for path in manifests:
        result = ingester.ingest(str(path))
        if result["status"] == "accepted":
            accepted += 1
            note = " (dry-run)" if args.dry_run else f" -> {result['output_path']}"
            print(f"  PASS  {path.name}{note}")
        else:
            rejected += 1
            print(f"  FAIL  {path.name}")
            for err in result["errors"]:
                print(f"        - {err}")
            if args.fail_fast:
                print(f"\nAborted after first failure (--fail-fast).")
                sys.exit(1)

    total = accepted + rejected
    print(f"\nResults: {accepted}/{total} accepted, {rejected}/{total} rejected")

    sys.exit(0 if rejected == 0 else 1)


if __name__ == "__main__":
    main()
