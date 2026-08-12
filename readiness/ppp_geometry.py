"""Resolve geometry for moneysweep-pr's PPP concession projects.

moneysweep-pr owns the concession record and knows a project's municipality; it
holds no coordinates and deliberately does not invent them. This module is the
other half of that split: it reads the municipality moneysweep federated and
resolves it to a real WGS84 point using spiderweb's committed reference
geographies, so the Hub can join a public-money project to a place on the map.

This module does not import moneysweep-pr and does not discover or read sibling
checkouts implicitly. The caller must pass an explicit moneysweep canonical
export package path. That keeps repository runtime isolation intact and makes the
producer artifact an explicit dependency rather than a filesystem convention.

Resolution is reference-backed or it does not happen:

* ``configs/airport_registry.yaml`` — FAA-derived airport locations, which cover
  the airport concessions.

Anything else is reported unresolved and stays in the geocode queue. A
municipality centroid is deliberately **not** used as a fallback point: a
concession's asset is not at the geographic middle of its municipality, and
emitting that as a location would manufacture precision moneysweep declined to
manufacture one repo earlier.

Only ``site``-extent projects are candidates at all. moneysweep withholds
locations from island-wide and corridor concessions because their municipality
records an administrative seat, so those never arrive here with a location to
upgrade.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AIRPORT_REGISTRY = REPO_ROOT / "configs" / "airport_registry.yaml"
LAYER_ID = "ppp_geometry"
EXPORT_CONTRACT_VERSION = "0.1.0"

# Confidence in a resolved point, by what resolved it. An FAA-derived airport
# location is a surveyed coordinate for a named facility; it should outrank
# moneysweep's 0.7 municipality attribution so a consumer picking the
# highest-confidence location picks the real point.
RESOLVER_CONFIDENCE = {"airport_registry": 0.95}


class PPPGeometryError(ValueError):
    """Raised when the PPP geometry lane cannot be built safely."""


def _fold(value: str) -> str:
    """Accent- and case-insensitive comparison key.

    'Luis Muñoz Marín' and 'Luis Munoz Marin' name the same airport; the
    registry carries both spellings as aliases but a project title may use
    either, so folding is what makes the match reliable.
    """
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


def read_producer_projects(package_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Project entities from an explicit moneysweep canonical export package.

    ``package_dir`` is mandatory. Implicit ``../moneysweep-pr`` discovery is
    intentionally forbidden so Spiderweb never couples runtime behavior to a
    sibling checkout layout.
    """
    if package_dir is None:
        raise PPPGeometryError(
            "explicit moneysweep export package required; sibling checkout discovery is disabled"
        )
    package_dir = Path(package_dir)
    entities = package_dir / "entities.jsonl"
    if not entities.exists():
        return []
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
    """First reference candidate whose name appears in the project's, in the
    same municipality.

    The municipality guard is what stops a name collision from placing a project
    in the wrong town: a candidate only wins if moneysweep and the reference
    geography independently agree on where it is.
    """
    title = _fold(project.get("name", ""))
    muni = _fold((project.get("location") or {}).get("municipality", ""))
    if not title:
        return None
    for candidate in candidates:
        if muni and _fold(candidate["municipality"]) != muni:
            continue
        for name in candidate["names"]:
            # Substring in either direction: a project titled "Luis Munoz Marin
            # Airport" and a registry entry named "Luis Munoz Marin
            # International Airport" are the same facility.
            if name and (name in title or title in name):
                return candidate
    return None


def resolve_projects(
    package_dir: Path | str | None = None, registry_path: Path | None = None
) -> dict[str, Any]:
    """Resolve producer project locations to points. Pure — no writes."""
    projects = read_producer_projects(package_dir)
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
                # What moneysweep asserted, kept so a reviewer can see the two
                # producers agreed before the point was accepted.
                "producer_municipality": location.get("municipality", ""),
                "producer_attribution_confidence": location.get("attribution_confidence"),
            }
        )

    resolved.sort(key=lambda r: r["entity_id"])
    unresolved.sort(key=lambda r: r["entity_id"])
    return {
        "layer_id": LAYER_ID,
        "export_contract_version": EXPORT_CONTRACT_VERSION,
        "producer_projects": len(projects),
        "resolved": resolved,
        "unresolved": unresolved,
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
    }
