"""Keep a cache's acquisition provenance when a fetch is rerun.

A fetch writes ``provenance.json`` next to the files it cached. A rerun may serve
some files from the cache, or select fewer files than before (for example
SRTMGL1N only, or one OpenTopography DEM type). Writing only that run's rows would
drop the original download records: when and from which host each file came.

The merge keeps them:

- a file served from the cache keeps its earlier record while its bytes are
  unchanged (same sha256);
- an earlier record for a file outside this run's selection is kept while that
  file is still in the cache with the same bytes, and dropped otherwise;
- a file downloaded in this run gets this run's record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def previous_rows(provenance_path: Path) -> list[dict]:
    """The ``files`` rows of an existing provenance file, or none."""
    try:
        return list(json.loads(Path(provenance_path).read_text(encoding="utf-8")).get("files", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def merge_rows(previous: Iterable[dict], current: Iterable[dict], cache_dir: Path, *,
               cache_hit_status: str = "cached_local") -> list[dict]:
    """This run's rows merged into the earlier ones, sorted by file name."""
    prior = {row["file_name"]: row for row in previous}
    merged: dict[str, dict] = {}
    for row in current:
        old = prior.get(row["file_name"])
        if row.get("review_status") == cache_hit_status and old and old.get("sha256") == row.get("sha256"):
            row = {**row, **old}
        merged[row["file_name"]] = row
    for name, old in prior.items():
        if name in merged:
            continue
        path = Path(cache_dir) / name
        if path.is_file() and old.get("sha256") == _sha256(path):
            merged[name] = old
    return [merged[name] for name in sorted(merged)]
