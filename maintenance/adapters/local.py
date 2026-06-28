"""Spiderweb-specific maintenance checks (workbook Adapter Rules).

- check_migration_remnants: FR24 ingest belongs to skywatcher-pr now; any FR24
  remnant outside legacy/archive (a root fr24/ package or pipeline/scripts
  fr24_*.py) is flagged as drift.
- check_gis_artifact_integrity: the sample export manifest and the sample JSONL
  streams must parse.

Read-only and audit-first.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import MaintenanceFinding

_SAMPLE_DIR = "exports/samples"
_LEGACY_MARKERS = ("legacy", "archive")


def check_migration_remnants(
    repo: str, root: Path, state: dict
) -> list[MaintenanceFinding]:
    remnants: list[str] = []
    if (root / "fr24").is_dir():
        remnants.append("fr24/")
    for pattern in ("pipeline/fr24*.py", "scripts/fr24*.py"):
        for path in root.glob(pattern):
            rel = str(path.relative_to(root))
            if not any(marker in rel.lower() for marker in _LEGACY_MARKERS):
                remnants.append(rel)
    if not remnants:
        return []
    return [
        MaintenanceFinding(
            finding_id=f"{repo}:dependency_drift:fr24_remnants",
            repo=repo,
            category="dependency_drift",
            severity="warning",
            action="none",
            message=(
                "FR24 ingest remnants outside legacy/archive "
                "(migrated to skywatcher-pr)"
            ),
            detail={"paths": sorted(remnants)},
        )
    ]


def _count_bad_jsonl(path: Path) -> int:
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            bad += 1
    return bad


def check_gis_artifact_integrity(
    repo: str, root: Path, state: dict
) -> list[MaintenanceFinding]:
    findings: list[MaintenanceFinding] = []
    sample_dir = root / _SAMPLE_DIR
    if not sample_dir.is_dir():
        return findings
    manifest = sample_dir / "manifest.sample.json"
    if manifest.exists():
        try:
            json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                MaintenanceFinding(
                    finding_id=f"{repo}:export_integrity:manifest_sample",
                    repo=repo,
                    category="export_integrity",
                    severity="error",
                    action="quarantined",
                    message=f"sample manifest does not parse: {exc}",
                    path=f"{_SAMPLE_DIR}/manifest.sample.json",
                )
            )
    for jsonl in sorted(sample_dir.glob("*.sample.jsonl")):
        bad = _count_bad_jsonl(jsonl)
        if bad:
            findings.append(
                MaintenanceFinding(
                    finding_id=f"{repo}:export_integrity:{jsonl.stem}",
                    repo=repo,
                    category="export_integrity",
                    severity="error",
                    action="quarantined",
                    message=f"{bad} unparseable row(s) in {jsonl.name}",
                    path=str(jsonl.relative_to(root)),
                    detail={"bad_rows": bad},
                )
            )
    return findings


CHECKS = (check_migration_remnants, check_gis_artifact_integrity)


def run_checks(repo: str, root: Path, state: dict) -> list[MaintenanceFinding]:
    findings: list[MaintenanceFinding] = []
    for check in CHECKS:
        findings.extend(check(repo, root, state))
    return findings
