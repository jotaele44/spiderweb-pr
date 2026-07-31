"""Spiderweb-specific maintenance checks (workbook Adapter Rules).

- check_migration_remnants: FR24/RLSM/ADS-B airspace ingest belongs to
  skywatcher-pr now; any remnant outside legacy/archive is flagged as drift.
  The pattern set deliberately covers more than a root ``fr24/`` package: the
  2026-07 audit found remnants in the dashboard UI, ``server/ingestion/``,
  ``scripts/*adsb*`` and the RLSM schemas/configs while this check was green,
  because it only looked at ``fr24/`` and ``{pipeline,scripts}/fr24_*.py``.
  Extend GLOBS rather than narrowing them.
- check_gis_artifact_integrity: the sample export manifest and the sample JSONL
  streams must parse.

Read-only and audit-first.
"""

from __future__ import annotations

import json
from pathlib import Path

from prii_maintenance import MaintenanceFinding

_SAMPLE_DIR = "exports/samples"
_LEGACY_MARKERS = ("legacy", "archive")

# Directories that, if present at the repo root, are wholesale migrated subsystems.
_MIGRATED_DIRS = ("fr24",)

# Glob patterns for individual migrated modules/artifacts. Paths containing a
# legacy/archive marker are exempt (that is where retired code is parked).
_MIGRATED_GLOBS = (
    "pipeline/fr24*.py",
    "scripts/fr24*.py",
    "pipeline/rlsm*.py",
    "scripts/rlsm*.py",
    "scripts/*adsb*.py",
    "scripts/*fr24*.py",
    "server/ingestion/*fr24*.py",
    "server/ingestion/*adsb*.py",
    "server/ingestion/registration_alerts.py",
    "server/ingestion/reconcile_registrations.py",
    "dashboard/*fr24*",
    "schemas/rlsm_*.json",
    "configs/rlsm_*.yaml",
)


def _is_parked(rel: Path) -> bool:
    """True when a path sits under a legacy/archive directory.

    Only directory components count. Matching the whole relative path would let
    a filename exempt itself — ``scripts/parse_adsb_archive.py`` contains
    "archive", so a substring test silently skipped a real remnant.
    """
    return any(
        marker in part.lower() for part in rel.parts[:-1] for marker in _LEGACY_MARKERS
    )


def check_migration_remnants(
    repo: str, root: Path, state: dict
) -> list[MaintenanceFinding]:
    remnants: list[str] = []
    for name in _MIGRATED_DIRS:
        if (root / name).is_dir():
            remnants.append(f"{name}/")
    for pattern in _MIGRATED_GLOBS:
        for path in root.glob(pattern):
            rel = path.relative_to(root)
            if _is_parked(rel):
                continue
            if str(rel) not in remnants:
                remnants.append(str(rel))
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
                "Airspace ingest remnants outside legacy/archive "
                "(FR24/RLSM/ADS-B migrated to skywatcher-pr)"
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
