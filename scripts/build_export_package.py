"""
Build a spiderweb federation export package from a source directory of streams.

Default behavior copies the four sample JSONL streams from `exports/samples/`,
recomputes sha256 + record counts, and emits a deterministic `manifest.json`
that is round-trip valid against the federation contract.

This is intentionally a thin skeleton — the production producer that reads
the live SQLite pipeline is out of scope for this PR. The point is to give
downstream consumers and CI a build → validate path with zero DB or network.

Usage:
    python scripts/build_export_package.py --out <dir>
    python scripts/build_export_package.py --out <dir> --source-dir exports/samples \\
        --producer-id spiderweb-pr --producer-version 0.1.0 --mode test
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_export import (  # noqa: E402
    compute_package_id,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

STREAM_TO_SCHEMA = {
    "events":       "spiderweb_event",
    "observations": "spiderweb_observation",
    "tracks":       "spiderweb_track",
    "sources":      "spiderweb_source",
}

SOURCE_FILENAMES = {
    "events":       "airspace_events.sample.jsonl",
    "observations": "observations.sample.jsonl",
    "tracks":       "tracks.sample.jsonl",
    "sources":      "sources.sample.jsonl",
}

OUT_FILENAMES = {
    "events":       "airspace_events.jsonl",
    "observations": "observations.jsonl",
    "tracks":       "tracks.jsonl",
    "sources":      "sources.jsonl",
}


def _count_jsonl_rows(path: Path) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _first_and_last_time(jsonl_path: Path, time_field: str) -> tuple[str | None, str | None]:
    times: list[str] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row.get(time_field), str):
                times.append(row[time_field])
    if not times:
        return None, None
    return min(times), max(times)


def build_package(
    out_dir: Path,
    source_dir: Path,
    producer_id: str,
    producer_version: str,
    schema_version: str,
    mode: str,
    generated_at: str | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    for stream, src_name in SOURCE_FILENAMES.items():
        src = source_dir / src_name
        dst = out_dir / OUT_FILENAMES[stream]
        if not src.exists():
            raise FileNotFoundError(f"source stream missing: {src}")
        shutil.copyfile(src, dst)

    files = []
    all_starts: list[str] = []
    all_ends: list[str] = []
    for stream in ["events", "observations", "tracks", "sources"]:
        out_path = out_dir / OUT_FILENAMES[stream]
        files.append({
            "filename":     OUT_FILENAMES[stream],
            "stream":       stream,
            "record_count": _count_jsonl_rows(out_path),
            "sha256":       sha256_file(out_path),
            "schema_id":    STREAM_TO_SCHEMA[stream],
        })
        time_field = {
            "events": "event_time",
            "observations": "observed_at",
            "tracks": "observed_at",
            "sources": "first_seen_at",
        }[stream]
        end_field = "last_seen_at" if stream == "sources" else time_field
        s, _ = _first_and_last_time(out_path, time_field)
        _, e = _first_and_last_time(out_path, end_field)
        if s:
            all_starts.append(s)
        if e:
            all_ends.append(e)

    ts = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not all_starts or not all_ends:
        raise ValueError("no time-bearing rows in any stream; cannot compute time_range")

    manifest_body = {
        "producer_id":      producer_id,
        "producer_version": producer_version,
        "schema_version":   schema_version,
        "generated_at":     ts,
        "mode":             mode,
        "time_range":       {"start": min(all_starts), "end": max(all_ends)},
        "files":            files,
        "notes":            None,
    }
    manifest_body["package_id"] = compute_package_id(manifest_body)

    with open(out_dir / "manifest.json", "w") as f:
        json.dump(manifest_body, f, indent=2, sort_keys=True)
        f.write("\n")

    return manifest_body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a spiderweb federation export package.")
    parser.add_argument("--out", required=True, help="Output directory for the package")
    parser.add_argument("--source-dir", default=str(REPO_ROOT / "exports" / "samples"),
                        help="Directory containing input *.sample.jsonl streams")
    parser.add_argument("--producer-id", default="spiderweb-pr")
    parser.add_argument("--producer-version", default="0.1.0")
    parser.add_argument("--schema-version", default="1.0")
    parser.add_argument("--mode", default="test", choices=["test", "production"])
    parser.add_argument("--generated-at", default=None,
                        help="Override generated_at (RFC3339, UTC). Default: now().")
    args = parser.parse_args(argv)

    manifest = build_package(
        out_dir=Path(args.out).resolve(),
        source_dir=Path(args.source_dir).resolve(),
        producer_id=args.producer_id,
        producer_version=args.producer_version,
        schema_version=args.schema_version,
        mode=args.mode,
        generated_at=args.generated_at,
    )
    print(f"Built package at {args.out} (package_id={manifest['package_id'][:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
