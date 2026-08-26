"""Reject tracked runtime and sensitive export artifacts under DATA_POLICY.md."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import PurePosixPath

RUNTIME_DIRECTORIES = frozenset({"outputs", "cache", "tile_cache"})
RUNTIME_PLACEHOLDER = ".gitkeep"
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".db",
        ".sqlite",
        ".sqlite3",
        ".parquet",
        ".nc",
    }
)
FORBIDDEN_ROOT_FILES = frozenset(
    {
        "outputs.zip",
        "registration_recovery_queue.csv",
        "spiderweb_overlay_candidates.geojson",
        "spiderweb_gap_audit.json",
        "calibration_report.json",
        "spiderweb_ingest_manifest.json",
        "prii_readiness_report.json",
    }
)
RAW_DATA_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif"})


def policy_violations(paths: Iterable[str]) -> list[str]:
    """Return DATA_POLICY violations for repository-relative tracked paths."""

    violations: list[str] = []
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        if path.is_absolute() or ".." in path.parts:
            violations.append(f"{raw_path}: path must be repository-relative")
            continue

        if path.name in FORBIDDEN_ROOT_FILES and len(path.parts) == 1:
            violations.append(f"{raw_path}: generated root export is not commit-safe")
            continue

        if path.parts and path.parts[0] in RUNTIME_DIRECTORIES:
            if len(path.parts) != 2 or path.name != RUNTIME_PLACEHOLDER:
                violations.append(
                    f"{raw_path}: runtime directories may track only their .gitkeep placeholder"
                )
            continue

        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES:
            violations.append(f"{raw_path}: {suffix} runtime artifact must not be committed")
            continue

        if path.parts and path.parts[0] == "data" and suffix in RAW_DATA_SUFFIXES:
            violations.append(f"{raw_path}: raw imagery must not be committed under data/")
            continue

        if suffix == ".jsonl" and not (
            path.parts[:2] == ("tests", "fixtures")
            or path.parts[:1] == ("exports",)
            or path.parts[:2] == ("reports", "federation")
        ):
            violations.append(f"{raw_path}: JSONL runtime output is not commit-safe")

    return violations


def tracked_paths() -> list[str]:
    """Read the committed path set without considering ignored local artifacts."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="Validate a repository-relative path (repeatable; used for focused checks).",
    )
    args = parser.parse_args(argv)
    violations = policy_violations(args.paths if args.paths is not None else tracked_paths())
    if violations:
        print("DATA_POLICY violations:", file=sys.stderr)
        print("\n".join(f"- {violation}" for violation in violations), file=sys.stderr)
        return 1
    print("DATA_POLICY tracked-path check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
