"""Read-only HTTP API for the two access point registries.

The registries are the committed documents under ``registry/access_points/``:
Inland Access Points (``inland``) and Off-Shore Access Points (``offshore``),
plus the relationship ledger that may relate records across them. This module
is a thin HTTP wrapper over
:class:`spiderweb.access_points.service.AccessPointService`; filtering, paging,
evidence tiers and path assessment all live there and are not repeated here.

``/v1/access-points`` is the first versioned prefix in this backend. Every
other route is unversioned; the prefix is here so the response contract of the
registries can change later without breaking a client that pinned ``v1``.

Routes (all ``GET``):

    GET /v1/access-points
    GET /v1/access-points/vocabulary
    GET /v1/access-points/relationships?feature_id=&render_class=
    GET /v1/access-points/paths?start=&goal=&max_hops=
    GET /v1/access-points/controls/cross-section
    GET /v1/access-points/{registry}/features?bbox=&status=&feature_class=&limit=&cursor=
    GET /v1/access-points/{registry}/features/{feature_id}
    GET /v1/access-points/{registry}/features/{feature_id}/evidence
    GET /v1/access-points/{registry}/sources

Boundaries that are deliberate:

* There is no write, adjudication or promotion endpoint. Promoting a record
  requires an independent human reviewer, and no authorised write path exists;
  an HTTP route would be a way around that review, so none is offered.
* ``{registry}`` accepts exactly ``inland`` or ``offshore``. The value is looked
  up in a fixed table and is never joined into a file path. The fixed-path
  routes are declared before the ``{registry}`` routes so ``vocabulary``,
  ``relationships``, ``paths`` and ``controls`` are never read as a registry.
* A feature id is answered only by the registry it belongs to. An id of the
  other registry, a raw provisional label or an identifier from one of the
  older naming schemes answers 404 with no data; an ambiguous or unrecognised
  identifier answers 400.
* A record is returned as its evidence describes it. A candidate with no
  source-backed coordinates has ``geometry: null`` and is counted in
  ``unlocated_count``; nothing here gives it a position, and nothing here turns
  a nearby record into the same record or a connected one.
* A registry document that is missing or fails its integrity check answers 503
  for that registry only. The other registry and the summary route keep working.
* ``controls/cross-section`` is analytic test data labelled ``SYNTHETIC_CONTROL``.
  A section that does not carry that label is refused rather than served.

Errors follow the backend convention: ``HTTPException`` with a plain-string
``detail``. Bounds declared on query parameters are enforced by FastAPI, which
answers 422 for them.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Callable, Iterator

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from pydantic import StringConstraints

from spiderweb.access_points import CONTRACT_VERSION
from spiderweb.access_points.namespaces import (
    REGISTRY_CODE,
    REGISTRY_TITLE,
    IdentifierKind,
    Namespace,
    NamespaceCollisionError,
    classify_identifier,
)
from spiderweb.access_points.relationships import PathState, RenderClass
from spiderweb.access_points.rules import RULES_VERSION
from spiderweb.access_points.service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    REGISTRY_SLUG,
    AccessPointService,
    InvalidQuery,
    RegistryUnavailable,
    UnknownRegistry,
    control_cross_section,
    parse_bbox,
)
from spiderweb.access_points.vocabulary import (
    RELATIONSHIP_CONNECTIVITY_KIND,
    VERIFIED_RELATIONSHIP_TYPES,
    AdjudicationStatus,
    AssertionRung,
    ClaimClass,
    ConnectivityKind,
    EvidenceDimension,
    EvidenceTier,
    GeometryBasis,
    InlandFeatureClass,
    OffshoreFeatureClass,
    ProvenanceState,
    RegistryStatus,
    RelationshipType,
)

log = logging.getLogger("priis.backend.access_points")

ROOT = Path(__file__).resolve().parents[2]
API_VERSION = "v1"
PREFIX = "/v1/access-points"
GEOJSON_MEDIA_TYPE = "application/geo+json"
SYNTHETIC_CONTROL = "SYNTHETIC_CONTROL"

DEFAULT_MAX_HOPS = 6
MAX_HOPS = 8
MAX_IDENTIFIER_LENGTH = 64
MAX_BBOX_LENGTH = 120
MAX_FILTER_VALUES = 16

# The feature classes each registry may hold, taken from the vocabulary enums.
FEATURE_CLASSES: dict[Namespace, type] = {
    Namespace.ACCESS_POINT_INLAND: InlandFeatureClass,
    Namespace.ACCESS_POINT_OFFSHORE: OffshoreFeatureClass,
}

_UNKNOWN_REGISTRY = "unknown registry; expected one of: " + ", ".join(REGISTRY_SLUG)
_FEATURE_NOT_FOUND = "feature not found in this registry"
_AMBIGUOUS_IDENTIFIER = (
    "identifier is ambiguous: it names several unrelated things; use a full record identifier"
)
_UNRECOGNISED_IDENTIFIER = "identifier is not a recognised record identifier"

_Token = Annotated[str, StringConstraints(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)]


class GeoJSONResponse(JSONResponse):
    """A JSON response served as ``application/geo+json``."""

    media_type = GEOJSON_MEDIA_TYPE


def vocabulary_document() -> dict[str, Any]:
    """Controlled vocabularies for legends and filters, read from the enums.

    Nothing here is typed by hand: a value added to an enum appears in this
    document, and a value that is not in an enum cannot appear.
    """

    registries = []
    feature_classes: dict[str, list[str]] = {}
    for slug, namespace in REGISTRY_SLUG.items():
        classes = [member.value for member in FEATURE_CLASSES[namespace]]
        feature_classes[slug] = classes
        registries.append(
            {
                "registry": slug,
                "namespace": namespace.value,
                "code": REGISTRY_CODE[namespace],
                "title": REGISTRY_TITLE[namespace],
                "feature_classes": classes,
            }
        )
    return {
        "api_version": API_VERSION,
        "contract_version": CONTRACT_VERSION,
        "rules_version": RULES_VERSION,
        "registries": registries,
        "feature_classes": feature_classes,
        "evidence_dimensions": [member.value for member in EvidenceDimension],
        "evidence_tiers": [member.name for member in EvidenceTier],
        "assertion_rungs": [
            {"name": member.name, "rank": int(member.value)}
            for member in sorted(AssertionRung, key=lambda rung: rung.value)
        ],
        "registry_statuses": [member.value for member in RegistryStatus],
        "claim_classes": [member.value for member in ClaimClass],
        "geometry_bases": [member.value for member in GeometryBasis],
        "adjudication_statuses": [member.value for member in AdjudicationStatus],
        "provenance_states": [member.value for member in ProvenanceState],
        "render_classes": [member.value for member in RenderClass],
        "path_states": [member.value for member in PathState],
        "connectivity_kinds": [member.value for member in ConnectivityKind],
        "relationship_types": [
            {
                "relationship_type": member.value,
                # Whether this type can ever be drawn as verified. A single
                # relationship of such a type still needs direct evidence and an
                # independent review before it is; see ``is_verified`` per row.
                "verifiable": member in VERIFIED_RELATIONSHIP_TYPES,
                "connectivity_kind": (
                    RELATIONSHIP_CONNECTIVITY_KIND[member].value
                    if member in RELATIONSHIP_CONNECTIVITY_KIND
                    else None
                ),
            }
            for member in RelationshipType
        ],
        "note": (
            "an anomaly is not an access point, an access point is not a passage and a "
            "passage is not a connection; each step needs its own evidence"
        ),
    }


@contextmanager
def _service_errors() -> Iterator[None]:
    """Translate the service's failures into the backend's HTTP convention."""

    try:
        yield
    except UnknownRegistry:
        raise HTTPException(404, _UNKNOWN_REGISTRY) from None
    except RegistryUnavailable as exc:
        log.warning("access point registry unavailable: %s", exc)
        raise HTTPException(503, str(exc)) from exc
    except InvalidQuery as exc:
        raise HTTPException(400, str(exc)) from None
    except NamespaceCollisionError:
        # The service refused to answer for an identifier that belongs to a
        # different registry or naming scheme. No data crosses that line.
        raise HTTPException(404, _FEATURE_NOT_FOUND) from None
    except KeyError:
        raise HTTPException(404, _FEATURE_NOT_FOUND) from None


def _namespace_or_404(registry: str) -> Namespace:
    namespace = REGISTRY_SLUG.get(registry)
    if namespace is None:
        raise HTTPException(404, _UNKNOWN_REGISTRY)
    return namespace


def _classified_or_400(identifier: str):
    """Classify an identifier, refusing one that is ambiguous or unrecognised."""

    try:
        found = classify_identifier(identifier)
    except NamespaceCollisionError:
        raise HTTPException(400, _AMBIGUOUS_IDENTIFIER) from None
    except ValueError:
        raise HTTPException(400, "identifier must be a non-empty string") from None
    if found is None:
        raise HTTPException(400, _UNRECOGNISED_IDENTIFIER)
    return found


def _require_feature_id(namespace: Namespace, feature_id: str) -> None:
    """Admit only an identifier spelled as a feature id of *this* registry."""

    found = _classified_or_400(feature_id)
    if found.namespace is not namespace or found.kind is not IdentifierKind.FEATURE:
        raise HTTPException(404, _FEATURE_NOT_FOUND)


def create_router(
    repo_root: Path = ROOT,
    registry_dir: Path | None = None,
    service_factory: Callable[[], AccessPointService] | None = None,
    cross_section: Callable[[], dict[str, Any]] = control_cross_section,
) -> APIRouter:
    """Build the router.

    ``repo_root`` and ``registry_dir`` say where the registry documents are, so
    a test can point the router at a temporary directory. The service is
    constructed on the first request, not here, so building the router never
    reads a file.
    """

    lock = threading.Lock()
    state: dict[str, Any] = {}

    def service() -> AccessPointService:
        with lock:
            if "service" not in state:
                state["service"] = (
                    service_factory()
                    if service_factory is not None
                    else AccessPointService(repo_root, registry_dir=registry_dir)
                )
            return state["service"]

    router = APIRouter(prefix=PREFIX, tags=["access-points"])

    # ── Fixed paths. Declared before the {registry} routes on purpose. ────────

    @router.get("")
    def list_registries() -> dict[str, Any]:
        """Both registries with their provenance. One being unavailable is reported, not raised."""
        with _service_errors():
            return service().registries()

    @router.get("/vocabulary")
    def vocabulary() -> dict[str, Any]:
        """Controlled vocabularies for legends and filters."""
        return vocabulary_document()

    @router.get("/relationships")
    def relationships(
        feature_id: Annotated[
            str | None, Query(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
        ] = None,
        render_class: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    ) -> dict[str, Any]:
        """Recorded relationships, each with the class it may be drawn as."""
        if feature_id is not None:
            _classified_or_400(feature_id)
        if render_class is not None and render_class not in {m.value for m in RenderClass}:
            raise HTTPException(400, "render_class is not a known render class")
        with _service_errors():
            return service().relationships(feature_id=feature_id, render_class=render_class)

    @router.get("/paths")
    def paths(
        start: Annotated[str, Query(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)],
        goal: Annotated[str, Query(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)],
        max_hops: Annotated[int, Query(ge=1, le=MAX_HOPS)] = DEFAULT_MAX_HOPS,
    ) -> dict[str, Any]:
        """Paths recorded between two records, each with its own verification state."""
        _classified_or_400(start)
        _classified_or_400(goal)
        with _service_errors():
            return service().path(start, goal, max_hops=max_hops)

    @router.get("/controls/cross-section")
    def controls_cross_section() -> dict[str, Any]:
        """A synthetic land-to-sea section for exercising displays. Not a survey."""
        with lock:
            document = state.get("cross_section")
        if document is None:
            try:
                document = cross_section()
            except ImportError as exc:
                log.warning("control cross-section unavailable: %s", exc)
                raise HTTPException(503, "control cross-section is unavailable") from exc
            if not isinstance(document, dict) or document.get("truth_kind") != SYNTHETIC_CONTROL:
                log.error("control cross-section is not labelled %s", SYNTHETIC_CONTROL)
                raise HTTPException(503, "control cross-section is not labelled as synthetic")
            with lock:
                state["cross_section"] = document
        return document

    # ── Per-registry routes. ─────────────────────────────────────────────────

    @router.get("/{registry}/features", response_class=GeoJSONResponse)
    def features(
        registry: str,
        bbox: Annotated[str | None, Query(min_length=1, max_length=MAX_BBOX_LENGTH)] = None,
        status: Annotated[list[_Token] | None, Query(max_length=MAX_FILTER_VALUES)] = None,
        feature_class: Annotated[
            list[_Token] | None, Query(max_length=MAX_FILTER_VALUES)
        ] = None,
        limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
        cursor: Annotated[
            str | None, Query(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
        ] = None,
    ) -> dict[str, Any]:
        """A page of the registry as a GeoJSON FeatureCollection."""
        namespace = _namespace_or_404(registry)
        if feature_class:
            known = {member.value for member in FEATURE_CLASSES[namespace]}
            if any(value not in known for value in feature_class):
                raise HTTPException(400, "feature_class is not a feature class of this registry")
        with _service_errors():
            return service().feature_collection(
                registry,
                bbox=parse_bbox(bbox) if bbox is not None else None,
                status=status,
                feature_class=feature_class,
                limit=limit,
                cursor=cursor,
            )

    @router.get("/{registry}/features/{feature_id}", response_class=GeoJSONResponse)
    def feature(
        registry: str,
        feature_id: Annotated[str, PathParam(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)],
    ) -> dict[str, Any]:
        """One record as a GeoJSON Feature."""
        _require_feature_id(_namespace_or_404(registry), feature_id)
        with _service_errors():
            return service().feature(registry, feature_id)

    @router.get("/{registry}/features/{feature_id}/evidence")
    def feature_evidence(
        registry: str,
        feature_id: Annotated[str, PathParam(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)],
    ) -> dict[str, Any]:
        """Every assertion with the tier it is worth, its sources and what blocks promotion."""
        _require_feature_id(_namespace_or_404(registry), feature_id)
        with _service_errors():
            return service().evidence(registry, feature_id)

    @router.get("/{registry}/sources")
    def sources(registry: str) -> dict[str, Any]:
        """Sources the registry holds. A listed source is a reference, not a measurement."""
        _namespace_or_404(registry)
        with _service_errors():
            return service().source_coverage(registry)

    return router


router = create_router()
