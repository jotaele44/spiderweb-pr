"""Certification-gated runtime boundary for PR_ARCHIPELAGO_GEOGRAPHY.

This provider deliberately does not replace legacy Spiderweb geography yet.
It can load only a snapshot whose manifest explicitly certifies the bounded
current Puerto Rico archipelago. OPEN/PROVISIONAL/malformed inputs fail closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ArchipelagoSnapshotError(RuntimeError):
    """Raised when a geography snapshot cannot be admitted to runtime."""


@dataclass(frozen=True)
class CertifiedArchipelagoSnapshot:
    root: Path
    manifest_path: Path
    manifest_sha256: str
    schema_version: str
    feature_count: int
    geometry_path: Path
    feature_path: Path
    manifest: dict[str, Any]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_certified_snapshot(root: str | Path) -> CertifiedArchipelagoSnapshot:
    """Load a certified current-archipelago snapshot or fail closed.

    Required manifest contract:
      certification.CURRENT_PR_ARCHIPELAGO == "PASS"
      unresolved_current_identity_residue == 0
      arithmetic_closed is true
      features_file + geometry_file exist
      optional recorded SHA256 values, when present, match actual bytes

    This loader proves only admission against the supplied manifest contract;
    it does not itself certify the underlying source universe.
    """
    root = Path(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ArchipelagoSnapshotError("missing manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ArchipelagoSnapshotError(f"invalid manifest.json: {exc}") from exc

    certification = manifest.get("certification") or {}
    if certification.get("CURRENT_PR_ARCHIPELAGO") != "PASS":
        raise ArchipelagoSnapshotError("CURRENT_PR_ARCHIPELAGO is not PASS")
    if manifest.get("unresolved_current_identity_residue") != 0:
        raise ArchipelagoSnapshotError("unresolved current identity residue is nonzero or missing")
    if manifest.get("arithmetic_closed") is not True:
        raise ArchipelagoSnapshotError("current denominator arithmetic is not closed")

    feature_rel = manifest.get("features_file")
    geometry_rel = manifest.get("geometry_file")
    if not isinstance(feature_rel, str) or not isinstance(geometry_rel, str):
        raise ArchipelagoSnapshotError("features_file/geometry_file must be declared")
    feature_path = root / feature_rel
    geometry_path = root / geometry_rel
    if not feature_path.is_file() or not geometry_path.is_file():
        raise ArchipelagoSnapshotError("declared feature or geometry artifact is missing")

    hashes = manifest.get("sha256") or {}
    for key, path in (("features_file", feature_path), ("geometry_file", geometry_path)):
        expected = hashes.get(key)
        if expected is not None and expected != _sha256(path):
            raise ArchipelagoSnapshotError(f"SHA256 mismatch for {key}")

    count = manifest.get("canonical_feature_count")
    if not isinstance(count, int) or count <= 0:
        raise ArchipelagoSnapshotError("canonical_feature_count must be a positive integer")

    return CertifiedArchipelagoSnapshot(
        root=root,
        manifest_path=manifest_path,
        manifest_sha256=_sha256(manifest_path),
        schema_version=str(manifest.get("schema_version", "")),
        feature_count=count,
        geometry_path=geometry_path,
        feature_path=feature_path,
        manifest=manifest,
    )
