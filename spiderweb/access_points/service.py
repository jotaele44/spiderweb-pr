"""Read-only query facade over the committed registry documents.

The backend router and any other consumer read the registries through this
module.  It writes nothing.  Every response carries a ``provenance`` block (the
document path, its SHA-256 and record counts) and a ``scope`` block stating
that the result has no identity effect, so a displayed record can always be
traced back to the file it came from.

A feature with no source-backed coordinates is returned with ``geometry: null``
and is counted as unlocated.  It is never given a position for display.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from federation.spatial_core import IDENTITY_DEFAULT

from . import CONTRACT_VERSION
from .models import Feature
from .namespaces import REGISTRY_CODE, REGISTRY_TITLE, Namespace, TypedRef, typed_ref
from .registry import AccessPointRegistry, RegistryIntegrityError
from .relationships import RelationshipLedger, effective_tier, ledger_from_document
from .rules import RULES_VERSION
from .rules import effective_tier as assertion_effective_tier
from .seeding import REGISTRY_DIR
from .vocabulary import EvidenceDimension, GeometryBasis, RegistryStatus

SERVICE_VERSION = "access-point-service/1.0"
MAX_LIMIT = 500
DEFAULT_LIMIT = 100

# Path segments used by the API.  They name the registry, not a terrain class.
REGISTRY_SLUG: dict[str, Namespace] = {
    "inland": Namespace.ACCESS_POINT_INLAND,
    "offshore": Namespace.ACCESS_POINT_OFFSHORE,
}
_DOCUMENT_NAME = {
    Namespace.ACCESS_POINT_INLAND: "inland.json",
    Namespace.ACCESS_POINT_OFFSHORE: "offshore.json",
}
_LEDGER_NAME = "relationships.json"


class RegistryUnavailable(RuntimeError):
    """A registry document is missing or failed verification."""


class UnknownRegistry(KeyError):
    """The requested registry slug is not one of the two registries."""


class InvalidQuery(ValueError):
    """A query parameter is malformed."""


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    """``min_lon,min_lat,max_lon,max_lat`` in WGS84.  Antimeridian boxes are refused."""

    parts = text.split(",")
    if len(parts) != 4:
        raise InvalidQuery("bbox must be min_lon,min_lat,max_lon,max_lat")
    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError:
        raise InvalidQuery("bbox values must be numbers") from None
    if not (
        -180 <= west <= 180
        and -180 <= east <= 180
        and -90 <= south <= 90
        and -90 <= north <= 90
    ):
        raise InvalidQuery("bbox is outside WGS84 bounds")
    if west >= east or south >= north:
        raise InvalidQuery("bbox minimums must be less than maximums")
    return west, south, east, north


def _positions(node: Any):
    if (
        isinstance(node, (list, tuple))
        and len(node) >= 2
        and all(isinstance(v, (int, float)) for v in node[:2])
    ):
        yield float(node[0]), float(node[1])
        return
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from _positions(child)


def _envelope(geometry: Mapping[str, Any]) -> tuple[float, float, float, float]:
    xs, ys = zip(*_positions(geometry["coordinates"]))
    return min(xs), min(ys), max(xs), max(ys)


def _intersects(
    envelope: tuple[float, float, float, float], bbox: tuple[float, float, float, float]
) -> bool:
    return not (
        envelope[2] < bbox[0]
        or envelope[0] > bbox[2]
        or envelope[3] < bbox[1]
        or envelope[1] > bbox[3]
    )


@dataclass(frozen=True)
class _Loaded:
    registry: AccessPointRegistry
    path: Path
    sha256: str


class AccessPointService:
    """Loads and verifies the registry documents once, then answers queries."""

    def __init__(
        self, repo_root: str | Path, *, registry_dir: str | Path | None = None
    ) -> None:
        self._root = Path(repo_root)
        self._dir = (
            Path(registry_dir)
            if registry_dir is not None
            else self._root / REGISTRY_DIR
        )
        self._registries: dict[Namespace, _Loaded] = {}
        self._ledger: tuple[RelationshipLedger, Path, str] | None = None

    # -- loading ---------------------------------------------------------

    def _display(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._root))
        except ValueError:
            return path.name

    def _registry(self, slug: str) -> _Loaded:
        try:
            namespace = REGISTRY_SLUG[slug]
        except KeyError:
            raise UnknownRegistry(slug) from None
        loaded = self._registries.get(namespace)
        if loaded is not None:
            return loaded
        path = self._dir / _DOCUMENT_NAME[namespace]
        if not path.is_file():
            raise RegistryUnavailable(
                f"registry document {self._display(path)} has not been built"
            )
        raw = path.read_bytes()
        try:
            registry = AccessPointRegistry.from_document(
                json.loads(raw.decode("utf-8"))
            )
        except (
            RegistryIntegrityError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            raise RegistryUnavailable(
                f"registry document failed verification: {exc}"
            ) from exc
        if registry.namespace is not namespace:
            raise RegistryUnavailable("registry document holds a different registry")
        loaded = _Loaded(registry, path, hashlib.sha256(raw).hexdigest())
        self._registries[namespace] = loaded
        return loaded

    def _ledger_loaded(self) -> tuple[RelationshipLedger, Path, str]:
        if self._ledger is None:
            path = self._dir / _LEDGER_NAME
            if not path.is_file():
                raise RegistryUnavailable(
                    f"relationship ledger {self._display(path)} has not been built"
                )
            raw = path.read_bytes()
            try:
                ledger = ledger_from_document(json.loads(raw.decode("utf-8")))
            except (
                RegistryIntegrityError,
                json.JSONDecodeError,
                UnicodeDecodeError,
            ) as exc:
                raise RegistryUnavailable(
                    f"relationship ledger failed verification: {exc}"
                ) from exc
            self._ledger = (ledger, path, hashlib.sha256(raw).hexdigest())
        return self._ledger

    # -- shared blocks ---------------------------------------------------

    def _provenance(self, loaded: _Loaded) -> dict[str, Any]:
        counts = loaded.registry.counts()
        return {
            "path": self._display(loaded.path),
            "sha256": loaded.sha256,
            "exists": True,
            "row_count": counts["features"],
            "counts": counts,
            "counts_close": AccessPointRegistry.counts_close(counts),
            "contract_version": CONTRACT_VERSION,
            "rules_version": RULES_VERSION,
        }

    @staticmethod
    def _scope() -> dict[str, str]:
        return {
            "identity_effect": "NONE",
            "identity_default": IDENTITY_DEFAULT,
            "state": "PROVISIONAL",
            "note": (
                "candidate records for review; nothing here establishes a physical opening, "
                "a passage or a connection unless its evidence says so"
            ),
        }

    # -- features --------------------------------------------------------

    def _geometry(
        self, loaded: _Loaded, feature: Feature
    ) -> tuple[Mapping[str, Any] | None, str, bool]:
        """Display geometry, its basis, and whether it is modelled."""

        registry = loaded.registry
        if feature.geometry_id is not None:
            derived = registry.geometries[feature.geometry_id]
            return (
                derived.geometry,
                GeometryBasis.DERIVED_FROM_RASTER.value,
                derived.modeled,
            )
        for oid in feature.observation_ids:
            observation = registry.observations[oid]
            if observation.geometry is not None:
                return observation.geometry, observation.geometry_basis.value, False
        bases = {
            registry.observations[o].geometry_basis.value
            for o in feature.observation_ids
        }
        return None, sorted(bases)[0] if bases else GeometryBasis.NONE.value, False

    def _properties(self, loaded: _Loaded, feature: Feature) -> dict[str, Any]:
        registry = loaded.registry
        tiers = registry.dimensions(feature.feature_id)
        geometry, basis, modeled = self._geometry(loaded, feature)
        uncertainty = None
        localities = []
        for oid in feature.observation_ids:
            observation = registry.observations[oid]
            if observation.horizontal_uncertainty_m is not None:
                uncertainty = max(
                    uncertainty or 0.0, observation.horizontal_uncertainty_m
                )
            if observation.locality_label:
                localities.append(observation.locality_label)
        return {
            "feature_id": feature.feature_id,
            "registry": loaded.registry.namespace.value,
            "registry_code": REGISTRY_CODE[loaded.registry.namespace],
            "feature_class": feature.feature_class,
            "status": feature.status.value,
            "is_verified": feature.status is RegistryStatus.VERIFIED,
            "assertion_rung": registry.rung(feature.feature_id).name,
            "dimensions": {d.value: tiers[d].name for d in EvidenceDimension},
            "has_geometry": geometry is not None,
            "geometry_basis": basis,
            "geometry_is_modeled": modeled,
            "horizontal_uncertainty_m": uncertainty,
            "horizontal_uncertainty_state": (
                "STATED" if uncertainty is not None else "UNKNOWN"
            ),
            "locality_labels": localities,
            "provisional_labels": list(feature.provisional_labels),
            "raw_names": list(feature.raw_names),
            "observation_count": len(feature.observation_ids),
            "created_utc": feature.created_utc,
            "updated_utc": feature.updated_utc,
            "notes": feature.notes,
        }

    def registries(self) -> dict[str, Any]:
        """Summary of both registries.  One being unavailable does not hide the other."""

        items = []
        for slug, namespace in REGISTRY_SLUG.items():
            entry: dict[str, Any] = {
                "registry": slug,
                "namespace": namespace.value,
                "code": REGISTRY_CODE[namespace],
                "title": REGISTRY_TITLE[namespace],
            }
            try:
                loaded = self._registry(slug)
            except RegistryUnavailable as exc:
                entry.update({"available": False, "reason": str(exc)})
            else:
                entry.update(
                    {"available": True, "provenance": self._provenance(loaded)}
                )
            items.append(entry)
        return {
            "service_version": SERVICE_VERSION,
            "registries": items,
            "scope": self._scope(),
        }

    def feature_collection(
        self,
        slug: str,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        status: Sequence[str] | None = None,
        feature_class: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= MAX_LIMIT:
            raise InvalidQuery(f"limit must be within 1..{MAX_LIMIT}")
        loaded = self._registry(slug)
        wanted_status = None
        if status:
            try:
                wanted_status = {RegistryStatus(s) for s in status}
            except ValueError as exc:
                raise InvalidQuery(str(exc)) from None
        wanted_class = set(feature_class) if feature_class else None

        matched: list[tuple[Feature, Mapping[str, Any] | None]] = []
        unlocated = 0
        for feature_id in sorted(loaded.registry.features):
            feature = loaded.registry.features[feature_id]
            if wanted_status is not None and feature.status not in wanted_status:
                continue
            if wanted_class is not None and feature.feature_class not in wanted_class:
                continue
            geometry, _, _ = self._geometry(loaded, feature)
            if geometry is None:
                unlocated += 1
                if bbox is not None:
                    continue
            elif bbox is not None and not _intersects(_envelope(geometry), bbox):
                continue
            matched.append((feature, geometry))

        start = 0
        if cursor is not None:
            ids = [feature.feature_id for feature, _ in matched]
            if cursor not in ids:
                raise InvalidQuery("cursor does not belong to this result set")
            start = ids.index(cursor) + 1
        page = matched[start : start + limit]
        more = start + limit < len(matched)
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": feature.feature_id,
                    "geometry": geometry,
                    "properties": self._properties(loaded, feature),
                }
                for feature, geometry in page
            ],
            "number_matched": len(matched),
            "number_returned": len(page),
            "unlocated_count": unlocated,
            "next_cursor": page[-1][0].feature_id if more and page else None,
            "crs": "OGC:CRS84",
            "provenance": self._provenance(loaded),
            "scope": self._scope(),
        }

    def feature(self, slug: str, feature_id: str) -> dict[str, Any]:
        loaded = self._registry(slug)
        feature = loaded.registry.feature(feature_id)
        geometry, _, _ = self._geometry(loaded, feature)
        return {
            "type": "Feature",
            "id": feature.feature_id,
            "geometry": geometry,
            "properties": self._properties(loaded, feature),
            "provenance": self._provenance(loaded),
            "scope": self._scope(),
        }

    def evidence(self, slug: str, feature_id: str) -> dict[str, Any]:
        """Every assertion with the tier it is actually worth, and its sources."""

        loaded = self._registry(slug)
        registry = loaded.registry
        feature = registry.feature(feature_id)
        sources = registry.sources
        cited: set[str] = set()
        assertions = []
        for assertion in feature.assertions:
            cited.update(assertion.source_ids)
            assertions.append(
                {
                    "dimension": assertion.dimension.value,
                    "asserted_tier": assertion.tier.name,
                    "effective_tier": assertion_effective_tier(assertion, sources).name,
                    "claim_class": assertion.claim_class.value,
                    "basis": list(assertion.basis),
                    "statement": assertion.statement,
                    "method": assertion.method,
                    "method_version": assertion.method_version,
                    "adjudication": assertion.adjudication.value,
                    "adjudicated_by": assertion.adjudicated_by,
                    "source_ids": list(assertion.source_ids),
                    "connectivity_kind": (
                        None
                        if assertion.connectivity_kind is None
                        else assertion.connectivity_kind.value
                    ),
                    "valid_from": assertion.valid_from,
                    "valid_to": assertion.valid_to,
                }
            )
        observations = []
        for oid in feature.observation_ids:
            observation = registry.observations[oid]
            cited.add(observation.source_id)
            observations.append(observation.to_dict())
        return {
            "feature_id": feature.feature_id,
            "status": feature.status.value,
            "assertion_rung": registry.rung(feature_id).name,
            "promotion_blockers": list(registry.blockers(feature_id)),
            "assertions": assertions,
            "observations": observations,
            "sources": [sources[s].to_dict() for s in sorted(cited) if s in sources],
            "provenance": self._provenance(loaded),
            "scope": self._scope(),
        }

    def source_coverage(self, slug: str) -> dict[str, Any]:
        """Sources held by a registry, grouped by provider and provenance state."""

        loaded = self._registry(slug)
        sources = loaded.registry.sources
        cited: dict[str, int] = {sid: 0 for sid in sources}
        for feature in loaded.registry.features.values():
            seen: set[str] = set()
            for assertion in feature.assertions:
                seen.update(assertion.source_ids)
            for oid in feature.observation_ids:
                seen.add(loaded.registry.observations[oid].source_id)
            for sid in seen:
                if sid in cited:
                    cited[sid] += 1
        by_provider: dict[str, dict[str, int]] = {}
        rows = []
        for sid in sorted(sources):
            source = sources[sid]
            bucket = by_provider.setdefault(source.provider, {})
            bucket[source.provenance_state.value] = (
                bucket.get(source.provenance_state.value, 0) + 1
            )
            rows.append(
                {
                    "source_id": sid,
                    "provider": source.provider,
                    "title": source.title,
                    "native_identifier": source.native_identifier,
                    "provenance_state": source.provenance_state.value,
                    "product_stage": source.product_stage.value,
                    "sensor_type": (
                        None if source.sensor_type is None else source.sensor_type.value
                    ),
                    "coverage_state": source.coverage_state.value,
                    "is_direct_measurement": source.is_direct_measurement,
                    "survey_date": source.survey_date,
                    "published_date": source.published_date,
                    "retrieved_utc": source.retrieved_utc,
                    "manifestation_sha256": source.manifestation_sha256,
                    "features_citing": cited[sid],
                }
            )
        return {
            "sources": rows,
            "by_provider": {
                k: dict(sorted(v.items())) for k, v in sorted(by_provider.items())
            },
            "direct_measurement_sources": sum(
                1 for r in rows if r["is_direct_measurement"]
            ),
            "note": "a listed source is a reference; inventory coverage is not a measurement",
            "provenance": self._provenance(loaded),
            "scope": self._scope(),
        }

    # -- relationships ---------------------------------------------------

    def relationships(
        self, *, feature_id: str | None = None, render_class: str | None = None
    ) -> dict[str, Any]:
        ledger, path, digest = self._ledger_loaded()
        selected = (
            ledger.touching(typed_ref(feature_id))
            if feature_id is not None
            else sorted(ledger.relationships.values(), key=lambda r: r.relationship_id)
        )
        rows = []
        for relationship in selected:
            style = ledger.render_class(relationship).value
            if render_class is not None and style != render_class:
                continue
            rows.append(
                {
                    "relationship_id": relationship.relationship_id,
                    "relationship_type": relationship.relationship_type.value,
                    "source": {
                        "namespace": relationship.source.namespace.value,
                        "identifier": relationship.source.identifier,
                    },
                    "target": {
                        "namespace": relationship.target.namespace.value,
                        "identifier": relationship.target.identifier,
                    },
                    "render_class": style,
                    "is_verified": ledger.is_verified(relationship),
                    "connectivity_kind": (
                        None
                        if relationship.connectivity_kind is None
                        else relationship.connectivity_kind.value
                    ),
                    "asserted_tier": relationship.tier.name,
                    "effective_tier": effective_tier(relationship, ledger.sources).name,
                    "claim_class": relationship.claim_class.value,
                    "basis": list(relationship.basis),
                    "statement": relationship.statement,
                    "distance_m": relationship.distance_m,
                    "adjudication": relationship.adjudication.value,
                    "valid_from": relationship.valid_from,
                    "valid_to": relationship.valid_to,
                }
            )
        return {
            "relationships": rows,
            "number_returned": len(rows),
            "render_classes": [
                "verified",
                "context",
                "hypothesized",
                "contradicted",
                "unresolved",
            ],
            "provenance": {
                "path": self._display(path),
                "sha256": digest,
                "exists": True,
                "row_count": len(ledger.relationships),
            },
            "scope": self._scope(),
        }

    def path(self, start: str, goal: str, *, max_hops: int = 6) -> dict[str, Any]:
        """Paths between two records, each with its own verification state."""

        ledger, path, digest = self._ledger_loaded()
        a: TypedRef = typed_ref(start)
        b: TypedRef = typed_ref(goal)
        assessments = ledger.paths(a, b, max_hops=max_hops)
        return {
            "start": str(a),
            "goal": str(b),
            "best_state": ledger.best_path_state(a, b, max_hops=max_hops).value,
            "paths": [
                {
                    "state": p.state.value,
                    "may_render_as_verified": p.may_render_as_verified,
                    "connectivity_kind": (
                        None
                        if p.connectivity_kind is None
                        else p.connectivity_kind.value
                    ),
                    "relationship_ids": list(p.relationship_ids),
                    "unverified_relationship_ids": list(p.unverified_relationship_ids),
                }
                for p in assessments
            ],
            "provenance": {
                "path": self._display(path),
                "sha256": digest,
                "exists": True,
            },
            "scope": self._scope(),
        }


def control_cross_section() -> dict[str, Any]:
    """A synthetic land-to-sea section for exercising displays.

    It is built from analytic control surfaces, not from any survey, and says
    so in ``truth_kind``.  The land and sea surfaces are on different datums
    with no transform, and a strip between them is unsurveyed, so it shows the
    two honest outcomes a real section can have: separate vertical references
    and a coverage gap.
    """

    import numpy as np

    from gebco.marine_evidence import VerticalReference

    from .controls import CONTROLS_VERSION, add_gaussian_basin, tilted_plane
    from .raster import SurfaceKind, make_grid
    from .transects import build_cross_section, cross_section_to_dict

    crs = "EPSG:32620"
    land_values = add_gaussian_basin(
        tilted_plane(60, 200, base_m=1.0, slope_x=0.04, slope_y=0.0),
        30.0,
        120.0,
        depth_m=4.0,
        sigma_cells=10.0,
    )
    land = make_grid(
        land_values,
        cell_size_m=(5.0, 5.0),
        origin=(1000.0, 300.0),
        crs=crs,
        kind=SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=VerticalReference(crs, None, "PRVD02", None, "up"),
        uncertainty_m=0.15,
        source_id=None,
    )
    depth = np.tile(np.linspace(18.0, 2.0, 160), (60, 1))
    sea = make_grid(
        depth,
        cell_size_m=(5.0, 5.0),
        origin=(100.0, 300.0),
        crs=crs,
        kind=SurfaceKind.BATHYMETRY,
        vertical_reference=VerticalReference(crs, None, None, "MLLW", "down"),
        uncertainty_m=0.4,
        source_id=None,
    )
    section = build_cross_section(
        [land, sea], [(120.0, 150.0), (1900.0, 150.0)], spacing_m=20.0
    )
    document = cross_section_to_dict(section, truth_kind="SYNTHETIC_CONTROL")
    document["controls_version"] = CONTROLS_VERSION
    document["statement"] = (
        "synthetic control surfaces; not a survey and not evidence about any real place"
    )
    return document
