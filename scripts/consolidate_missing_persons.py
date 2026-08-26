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
the NamUs-only canonical when present. Within a source, rows are deduped by
`case_id_hash`. Likely *cross-source* duplicates are **annotated, not collapsed**
(`annotate_linkage`): rows sharing a deterministic blocking key
(`sex|age_band|last_seen_municipio|last_seen_date`) across ≥2 sources get a stable
`linkage_group_id` plus `linkage_keys_json` / `coord_disagreement_km`, so a
distinct-people count can be layered on later without changing today's aggregate.
This is deliberately conservative — no fuzzy name matching (names are dropped at
harvest). Raw PII never enters the canonical; only the municipio aggregate is
federation-safe (see docs/DATA_POLICY.md).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
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

# `linkage_group_id` is a consolidation-only provenance column appended to the
# output; the per-source harvester canonical contract (CANONICAL_COLUMNS) is left
# untouched so `tests/test_missing_persons_layer.py::test_harvest_*` stay valid.
CONSOLIDATED_COLUMNS = list(CANONICAL_COLUMNS) + ["linkage_group_id"]

# Blocking-key components — non-PII redacted fields already present on every row.
# All four must be non-empty for a row to be linkable (names are dropped at harvest,
# so this is deliberately conservative, not fuzzy identity matching).
_LINKAGE_KEY_FIELDS = ("sex", "age_band", "last_seen_municipio", "last_seen_date")


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


def _blocking_key(row: dict) -> Optional[str]:
    """Deterministic cross-source blocking key from non-PII redacted fields, or
    None when any component is missing (row is left un-linkable)."""
    parts = [(row.get(f) or "").strip() for f in _LINKAGE_KEY_FIELDS]
    return "|".join(parts) if all(parts) else None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _coords(row: dict) -> Optional[tuple[float, float]]:
    try:
        return float(row["last_seen_lat"]), float(row["last_seen_lon"])
    except (KeyError, TypeError, ValueError):
        return None


def annotate_linkage(rows: list[dict]) -> int:
    """Annotate (not collapse) likely cross-source duplicates in place.

    Rows sharing a blocking key across ≥2 distinct sources get a stable
    ``linkage_group_id``; ``linkage_keys_json`` records the key components and,
    when ≥2 rows in a group carry coordinates, ``coord_disagreement_km`` is set to
    the max pairwise haversine. Returns the number of cross-source groups found.
    The municipio aggregate is unaffected — this is auditable metadata only.
    """
    groups: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        row.setdefault("linkage_group_id", "")
        key = _blocking_key(row)
        if key is not None:
            groups.setdefault(key, []).append(i)

    linked = 0
    for key, idxs in groups.items():
        if len(idxs) < 2 or len({rows[i].get("source_id", "") for i in idxs}) < 2:
            continue  # only genuine cross-source groups
        linked += 1
        gid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        pts = [c for c in (_coords(rows[i]) for i in idxs) if c is not None]
        max_km = max(
            (_haversine_km(*pts[a], *pts[b])
             for a in range(len(pts)) for b in range(a + 1, len(pts))),
            default=None,
        )
        for i in idxs:
            rows[i]["linkage_group_id"] = gid
            rows[i]["linkage_keys_json"] = json.dumps(
                {f: rows[i].get(f, "") for f in _LINKAGE_KEY_FIELDS}, ensure_ascii=False)
            if max_km is not None:
                rows[i]["coord_disagreement_km"] = str(round(max_km, 3))
    return linked


def consolidate(sources_dir: Path) -> tuple[list[dict], dict[str, int]]:
    """Return ``(rows, per_source_counts)`` merged across all sources present.

    Rows keep every canonical column and their per-row ``source_id`` (already set
    by each harvester). Dedup is within a source by ``case_id_hash``; likely
    cross-source duplicates are annotated (not collapsed) via ``annotate_linkage``.
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
    linked = annotate_linkage(rows)
    log.info("cross-source linkage groups: %d", linked)
    return rows, per_source


def write_consolidated(rows: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / CONSOLIDATED_FILENAME
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CONSOLIDATED_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row.setdefault("linkage_group_id", "")
            writer.writerow(row)
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
