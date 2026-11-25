"""Provenance rows for cached SRTMGL1 / SRTMGL1N files."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cached_row(path: Path, source_url: str) -> dict[str, object]:
    """Describe a file already in the cache (no network)."""
    path = Path(path)
    return {
        "source_url": source_url,
        "final_host": None,
        "accessed_at": None,
        "file_name": path.name,
        "file_size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "raw_commit_allowed": False,
        "review_status": "cached_local",
    }


def build_provenance(rows: list[dict[str, object]], *, generated_at: str) -> dict[str, object]:
    return {
        "adapter": "nasa_srtmgl1",
        "collection": "SRTMGL1 v003 (C2763266360-LPCLOUD) + SRTMGL1N v003 (C2763266368-LPCLOUD)",
        "generated_at": generated_at,
        "raw_commit_allowed": False,
        "files": sorted(rows, key=lambda r: str(r["file_name"])),
    }
