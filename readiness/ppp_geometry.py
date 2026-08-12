"""Resolve geometry for moneysweep-pr's PPP concession projects.

moneysweep-pr owns the concession record and knows a project's municipality; it
holds no coordinates and deliberately does not invent them. This module is the
other half of that split: it reads the municipality moneysweep federated and
resolves it to a real WGS84 point using spiderweb's committed reference
geographies, so the Hub can join a public-money project to a place on the map.

This module does not import moneysweep-pr and does not discover or read sibling
checkouts implicitly. The caller must pass an explicit moneysweep canonical
export package path. Before any row is consumed, the package manifest, producer
identity, entities artifact hash, and declared record count are verified. That
keeps repository runtime isolation intact and makes the producer artifact a
content-addressed, fail-closed dependency rather than a filesystem convention.

Resolution is reference-backed or it does not happen:

* ``configs/airport_registry.yaml`` — FAA-derived airport locations, which cover
  the airport concessions.

Anything else is reported unresolved and stays in the geocode queue. A
municipality centroid is deliberately **not** used as a fallback point: a
concession's asset is not at the geographic middle of its municipality, and
emitting that as a location would manufacture precision moneysweep declined to
manufacture one repo earlier.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AIRPORT_REGISTRY = REPO_ROOT / "configs" / "airport_registry.yaml"
LAYER_ID = "ppp_geometry"
EXPORT_CONTRACT_VERSION = "0.2.0"
EXPECTED_PRODUCER = "moneysweep-pr"

RESOLVER_CONFIDENCE = {"airport_registry": 0.95}


class PPPGeometryError(ValueError):
    """Raised when the PPP geometry lane cannot be built safely."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fold(value: str) -> str:
    """Accent- and case-insensitive comparison key."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.upper().split())


def load_airport_index(path: Path | None = None) -> list[dict[str, Any]]:
    """Airport reference locations as match candidates."""
    path = path or AIRPORT_REGISTRY
    if not path.exists():
        raise PPPGeometryError(f"missing airport registry: {path}")
    registry = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    candidates: list[dict[str, Any]] = []
    for airport in registry.get("airports", []):
        names = [airport.get("canonical_name", "")] + list(airport.get("aliases", []) or [])
        candidates.append(
            {
                "reference_id": airport["airport_id"],
                "names": [_fold(n) for n in names if n],
                "municipality": airport.get("municipality", ""),
                "lat": float(airport["lat"]),
                "lon": float(airport["lon"]),
                "resolver": "airport_registry",
                "reference_path": str(path.relative_to(REPO_ROOT)),
            }
        )
    return candidates


def verify_moneysweep_package(package_dir: Path | str | None) -> dict[str, Any]:
    """Verify the explicit producer package before consuming any project row.

    Required invariants:
    * explicit package path;
    * manifest.json exists and parses;
    * manifest producer is exactly ``moneysweep-pr``;
    * one ``entities`` file entry exists;
    * declared SHA-256 equals the artifact bytes;
    * declared record_count equals the number of nonblank JSONL records.

    Returns immutable provenance metadata suitable for propagation downstream.
    """
    if package_dir is None:
        raise PPPGeometryError(
            "explicit moneysweep export package required; sibling checkout discovery is disabled"
        )
    package = Path(package_dir)
    manifest_path = package / "manifest.json"
    if not manifest_path.exists():
        raise PPPGeometryError(f"missing moneysweep manifest: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PPPGeometryError(f"invalid moneysweep manifest JSON: {exc}") from exc

    producer = manifest.get("producer")
    if producer != EXPECTED_PRODUCER:
        raise PPPGeometryError(
            f"unexpected producer identity: expected {EXPECTED_PRODUCER!r}, got {producer!r}"
        )

    matches = [entry for entry in manifest.get("files", []) if entry.get("stream") == "entities"]
    if len(matches) != 1:
        raise PPPGeometryError(
            f"expected exactly one entities artifact in manifest, found {len(matches)}"
        )
    entry = matches[0]
    filename = entry.get("filename")
    if not isinstance(filename, str) or not filename:
        raise PPPGeometryError("entities manifest entry is missing filename")
    entities = package / filename
    if not entities.exists():
        raise PPPGeometryError(f"declared entities artifact missing: {entities}")

    declared_sha = entry.get("sha256")
    if not isinstance(declared_sha, str) or len(declared_sha) != 64:
        raise PPPGeometryError("entities manifest entry is missing a valid sha256")
    actual_sha = _sha256(entities)
    if actual_sha != declared_sha:
        raise PPPGeometryError(
            f"entities sha256 mismatch: declared {declared_sha}, actual {actual_sha}"
        )

    actual_count = sum(1 for line in entities.read_text(encoding="utf-8").splitlines() if line.strip())
    declared_count = entry.get("record_count")
    if not isinstance(declared_count, int) or declared_count != actual_count:
        raise PPPGeometryError(
            f"entities record_count mismatch: declared {declared_count!r}, actual {actual_count}"
        )

    return {
        "producer": producer,
        "package_id": manifest.get("package_id"),
        "manifest_sha256": _sha256(manifest_path),
        "entities_filename": filename,
        "entities_sha256": actual_sha,
        "entities_record_count": actual_count,
    }


def read_producer_projects(
    package_dir: Path | str | None = None,
    *,
    verified_package: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Project entities from a verified explicit Moneysweep export package."""
    metadata = verified_package or verify_moneysweep_package(package_dir)
    if package_dir is None:
        raise PPPGeometryError("explicit package path required")
    package = Path(package_dir)
    entities = package / metadata["entities_filename"]
    projects: list[dict[str, Any]] = []
    for line in entities.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("entity_type") != "project":
            continue
        location = row.get("location") or {}
        if not location.get("municipality"):
            continue
        projects.append(row)
    return projects


def _match(project: dict[str, Any], candidates: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Match project name and municipality against committed reference geography."""
    title = _fold(project.get("name", ""))
    muni = _fold((project.get("location") or {}).get("municipality", ""))
    if not title:
        return None
    for candidate in candidates:
        if muni and _fold(candidate["municipality"]) != muni:
            continue
        for name in candidate["names"]:
            if name and (name in title or title in name):
                return candidate
    return None


def resolve_projects(
    package_dir: Path | str | None = None, registry_path: Path | None = None
) -> dict[str, Any]:
    """Resolve producer project locations to points after package verification."""
    package_meta = verify_moneysweep_package(package_dir)
    projects = read_producer_projects(package_dir, verified_package=package_meta)
    candidates = load_airport_index(registry_path)

    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for project in projects:
        location = project.get("location") or {}
        match = _match(project, candidates)
        if not match:
            unresolved.append(
                {
                    "entity_id": project["entity_id"],
                    "name": project.get("name", ""),
                    "municipality": location.get("municipality", ""),
                    "reason": "no committed reference geography matched this project",
                }
            )
            continue
        resolved.append(
            {
                "entity_id": project["entity_id"],
                "name": project.get("name", ""),
                "municipality": match["municipality"],
                "lat": match["lat"],
                "lon": match["lon"],
                "geometry_type": "Point",
                "crs": "EPSG:4326",
                "resolver": match["resolver"],
                "reference_id": match["reference_id"],
                "reference_path": match["reference_path"],
                "geometry_confidence": RESOLVER_CONFIDENCE[match["resolver"]],
                "producer_municipality": location.get("municipality", ""),
                "producer_attribution_confidence": location.get("attribution_confidence"),
                "producer_package_id": package_meta.get("package_id"),
                "producer_entities_sha256": package_meta["entities_sha256"],
            }
        )

    resolved.sort(key=lambda r: r["entity_id"])
    unresolved.sort(key=lambda r: r["entity_id"])
    return {
        "layer_id": LAYER_ID,
        "export_contract_version": EXPORT_CONTRACT_VERSION,
        "producer_package": package_meta,
        "producer_projects": len(projects),
        "resolved": resolved,
        "unresolved": unresolved,
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
    }
