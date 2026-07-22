#!/usr/bin/env python3
"""
consolidate_missing_persons.py — merge the per-source redacted canonical CSVs
produced by the landed missing-persons harvesters into a single combined
canonical that the layer emitter consumes.

Every harvester already writes the *same* redacted schema
(`_harvest_base.CANONICAL_COLUMNS`, with names/photos/DOB/narrative dropped and
`case_id_hash` hashed at harvest), so consolidation is a concat + per-source
dedup — not a schema merge:

  data/sources/namus/<date>/namus_mp_pr_canonical.csv
  data/sources/prpb_alertas_amber/<date>/prpb_alertas_amber_pr_canonical.csv
  data/sources/prpb_alertas_rosa/<date>/...
  data/sources/prpb_alertas_silver/<date>/...
  data/sources/prpb_alertas_ashanti/<date>/...
  data/sources/prpb_desaparecidos/<date>/...
        ↓ (this script)
  data/sources/_consolidated/<today>/missing_persons_pr_canonical.csv

`scripts/populate_dataset_layers.py::main()` prefers this consolidated file over
the NamUs-only canonical when present. Cross-source identity linkage
(`linkage_keys_json` / `coord_disagreement_km`) is intentionally left for a later
pass — this only dedups within a source by `case_id_hash`. Raw PII never enters
the canonical (dropped at harvest); only the municipio aggregate is federation-safe
(see docs/DATA_POLICY.md).
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

try:  # support direct execution and package import
    from _harvest_base import CANONICAL_COLUMNS, latest_snapshot_dir
except ImportError:  # pragma: no cover - fallback when cwd differs
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _harvest_base import CANONICAL_COLUMNS, latest_snapshot_dir

log = logging.getLogger("consolidate_missing_persons")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES_DIR = REPO_ROOT / "data" / "sources"

# Sources whose latest canonical CSV feeds the missing-persons layers. Each is a
# subdir under data/sources/ matching the harvester's SOURCE_DIR_NAME/SOURCE_ID.
MISSING_PERSONS_SOURCES = [
    "namus",
    "prpb_alertas_amber",
    "prpb_alertas_rosa",
    "prpb_alertas_silver",
    "prpb_alertas_ashanti",
    "prpb_desaparecidos",
]

CONSOLIDATED_FILENAME = "missing_persons_pr_canonical.csv"


def find_latest_canonical(source_root: Path) -> Optional[Path]:
    """Latest ``*_canonical.csv`` under the most recent dated snapshot of a source.

    Handles both filename conventions — NamUs' ``namus_mp_pr_canonical.csv`` and
    the HarvestBase ``<source_id>_pr_canonical.csv`` — by globbing.
    """
    snap = latest_snapshot_dir(source_root)
    if snap is None:
        return None
    cands = sorted(snap.glob("*_canonical.csv"))
    return cands[0] if cands else None


def consolidate(sources_dir: Path) -> tuple[list[dict], dict[str, int]]:
    """Return ``(rows, per_source_counts)`` merged across all sources present.

    Rows keep every canonical column and their per-row ``source_id`` (already set
    by each harvester). Dedup is within a source by ``case_id_hash``.
    """
    rows: list[dict] = []
    per_source: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for source_id in MISSING_PERSONS_SOURCES:
        canonical = find_latest_canonical(sources_dir / source_id)
        if canonical is None:
            log.info("no canonical for %s — skipped", source_id)
            continue
        count = 0
        with canonical.open(encoding="utf-8") as fh:
            for raw in csv.DictReader(fh):
                # Normalise to the canonical column set (fill any missing, drop extras).
                row = {col: raw.get(col, "") for col in CANONICAL_COLUMNS}
                src = row.get("source_id") or source_id
                row["source_id"] = src
                key = (src, row.get("case_id_hash", ""))
                if not row.get("case_id_hash") or key in seen:
                    continue
                seen.add(key)
                rows.append(row)
                count += 1
        per_source[source_id] = count
        log.info("%s: %d rows from %s", source_id, count, canonical)
    return rows, per_source


def write_consolidated(rows: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / CONSOLIDATED_FILENAME
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def run(args: argparse.Namespace) -> int:
    sources_dir = Path(args.sources_dir)
    rows, per_source = consolidate(sources_dir)
    if not rows:
        log.warning("no source canonicals found under %s — nothing to consolidate", sources_dir)
        return 1
    snapshot = args.snapshot or date.today().isoformat()
    out_dir = sources_dir / "_consolidated" / snapshot
    out_path = write_consolidated(rows, out_dir)
    log.info("wrote %d consolidated rows → %s", len(rows), out_path)
    log.info("per-source: %s", per_source)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consolidate missing-persons canonical CSVs")
    parser.add_argument("--sources-dir", default=str(DEFAULT_SOURCES_DIR))
    parser.add_argument("--snapshot", default=None, help="Output snapshot date (default: today)")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
