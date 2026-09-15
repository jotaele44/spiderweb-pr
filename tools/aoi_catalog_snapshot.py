"""Approved metadata bootstrap. Run from repository root using python -m tools.aoi_catalog_snapshot.

Successful output is a registry proposal, not automatic activation. Review it
and its frozen manifest before updating configs/spatial_dataset_providers.json.
"""
import argparse
import json
from pathlib import Path
from server.backend.aoi_catalog_snapshot import freeze_catalog
from server.backend.aoi_planner import strict_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--work-dir", required=True, type=Path,
                        help="Reuse this directory after a downstream failure; use a new directory for a new snapshot")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    specs = strict_json((root / "configs/aoi_catalog_sources.json").read_bytes())["sources"]
    if args.source not in specs:
        parser.error("source must be an explicitly registered dataset ID")
    try:
        proposal = freeze_catalog(specs[args.source], args.work_dir, root)
    except (ValueError, OSError) as error:
        parser.exit(1, f"BLOCKED: {error}\nNo registry activation or asset acquisition performed.\n")
    print(json.dumps(proposal, indent=2))


if __name__ == "__main__":
    main()
