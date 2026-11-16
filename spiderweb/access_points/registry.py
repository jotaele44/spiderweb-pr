"""The two access-point registries and their on-disk document.

Each registry is independent: it has its own namespace, its own identifier
sequence, its own observations and its own features.  Nothing is shared by
reference between the inland and the off-shore registry; cross-registry
statements live in :mod:`spiderweb.access_points.relationships`.

Guarantees
----------
* Ingestion is idempotent.  Re-adding an identical record is a no-op; adding a
  different record under an existing identifier is refused.
* A feature can never be stored with a status stronger than
  :func:`spiderweb.access_points.rules.permitted_status` allows.
* ``VERIFIED`` is reachable only through :meth:`AccessPointRegistry.promote`,
  which re-checks every blocker.  There is no bulk or automatic promotion.
* A saved document carries the hash of its own content and closing record
  counts.  A document that does not hash or count correctly does not load.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from federation.spatial_core import canonical_json_sha256
from gebco.marine_evidence import (
    CoverageState,
    ProductStage,
    SensorType,
    VerticalReference,
)

from . import CONTRACT_VERSION
from .models import (
    DerivedGeometry,
    EvidenceAssertion,
    Feature,
    Observation,
    SourceManifestation,
)
from .namespaces import (
    REGISTRY_CODE,
    Namespace,
    NamespaceCollisionError,
    classify_identifier,
    feature_id,
    feature_sequence,
    require_registry_namespace,
)
from .rules import (
    RULES_VERSION,
    assertion_rung,
    dimension_tiers,
    permitted_status,
    promotion_blockers,
    status_is_permitted,
)
from .vocabulary import (
    AdjudicationStatus,
    ClaimClass,
    ConnectivityKind,
    EvidenceDimension,
    EvidenceTier,
    GeometryBasis,
    Origin,
    ProvenanceState,
    RegistryStatus,
)

DOCUMENT_SCHEMA = "access_point_registry/1.0"


class RegistryConflictError(ValueError):
    """An identifier is already bound to different content."""


class PromotionError(ValueError):
    """A status was requested that the evidence does not allow."""

    def __init__(self, message: str, blockers: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.blockers = tuple(blockers)


class RegistryIntegrityError(ValueError):
    """A stored registry document is corrupt, truncated or inconsistent."""


def _opt_enum(enum_cls: Any, value: Any) -> Any:
    return None if value is None else enum_cls(value)


def source_from_dict(data: Mapping[str, Any]) -> SourceManifestation:
    return SourceManifestation(
        source_id=data["source_id"],
        provider=data["provider"],
        title=data["title"],
        native_identifier=data.get("native_identifier"),
        source_uri=data.get("source_uri"),
        manifestation_sha256=data.get("manifestation_sha256"),
        retrieved_utc=data.get("retrieved_utc"),
        published_date=data.get("published_date"),
        survey_date=data.get("survey_date"),
        lineage_root_id=data.get("lineage_root_id"),
        parent_source_ids=tuple(data.get("parent_source_ids") or ()),
        product_stage=ProductStage(
            data.get("product_stage", ProductStage.DERIVED_PRODUCT.value)
        ),
        sensor_type=_opt_enum(SensorType, data.get("sensor_type")),
        coverage_state=CoverageState(
            data.get("coverage_state", CoverageState.UNKNOWN.value)
        ),
        provenance_state=ProvenanceState(
            data.get("provenance_state", ProvenanceState.UNREGISTERED.value)
        ),
        license_note=data.get("license_note"),
    )


def _vertical_from(data: Mapping[str, Any] | None) -> VerticalReference | None:
    if data is None:
        return None
    return VerticalReference(
        horizontal_crs=data["horizontal_crs"],
        vertical_crs=data.get("vertical_crs"),
        vertical_datum=data.get("vertical_datum"),
        tidal_datum=data.get("tidal_datum"),
        depth_positive=data.get("depth_positive", "down"),
    )


def observation_from_dict(data: Mapping[str, Any]) -> Observation:
    return Observation(
        observation_id=data["observation_id"],
        namespace=Namespace(data["namespace"]),
        source_id=data["source_id"],
        native_record_id=data["native_record_id"],
        geometry_basis=GeometryBasis(data["geometry_basis"]),
        raw_label=data.get("raw_label"),
        raw_attributes=dict(data.get("raw_attributes") or {}),
        geometry=data.get("geometry"),
        horizontal_crs=data.get("horizontal_crs"),
        horizontal_uncertainty_m=data.get("horizontal_uncertainty_m"),
        value_m=data.get("value_m"),
        vertical_reference=_vertical_from(data.get("vertical_reference")),
        vertical_uncertainty_m=data.get("vertical_uncertainty_m"),
        observed_date=data.get("observed_date"),
        discovered_utc=data.get("discovered_utc"),
        claim_class=ClaimClass(data.get("claim_class", ClaimClass.UNKNOWN.value)),
        locality_label=data.get("locality_label"),
    )


def assertion_from_dict(data: Mapping[str, Any]) -> EvidenceAssertion:
    return EvidenceAssertion(
        dimension=EvidenceDimension(data["dimension"]),
        tier=EvidenceTier[data["tier"]],
        claim_class=ClaimClass(data["claim_class"]),
        basis=tuple(data.get("basis") or ()),
        statement=data["statement"],
        observation_ids=tuple(data.get("observation_ids") or ()),
        source_ids=tuple(data.get("source_ids") or ()),
        method=data.get("method"),
        method_version=data.get("method_version"),
        valid_from=data.get("valid_from"),
        valid_to=data.get("valid_to"),
        adjudication=AdjudicationStatus(
            data.get("adjudication", AdjudicationStatus.UNREVIEWED.value)
        ),
        adjudicated_by=data.get("adjudicated_by"),
        adjudicated_utc=data.get("adjudicated_utc"),
        connectivity_kind=_opt_enum(ConnectivityKind, data.get("connectivity_kind")),
        origin=_opt_enum(Origin, data.get("origin")),
    )


def geometry_from_dict(data: Mapping[str, Any]) -> DerivedGeometry:
    return DerivedGeometry(
        geometry_id=data["geometry_id"],
        observation_ids=tuple(data["observation_ids"]),
        method=data["method"],
        method_version=data["method_version"],
        geometry=data["geometry"],
        geometry_logical_sha256=data["geometry_logical_sha256"],
        horizontal_uncertainty_m=data.get("horizontal_uncertainty_m"),
        modeled=bool(data.get("modeled", True)),
    )


def feature_from_dict(data: Mapping[str, Any]) -> Feature:
    return Feature(
        feature_id=data["feature_id"],
        namespace=Namespace(data["namespace"]),
        feature_class=data["feature_class"],
        status=RegistryStatus(
            data.get("status", RegistryStatus.PROVISIONAL_DISCOVERY.value)
        ),
        observation_ids=tuple(data.get("observation_ids") or ()),
        assertions=tuple(assertion_from_dict(a) for a in data.get("assertions") or ()),
        geometry_id=data.get("geometry_id"),
        provisional_labels=tuple(data.get("provisional_labels") or ()),
        raw_names=tuple(data.get("raw_names") or ()),
        supersedes=tuple(data.get("supersedes") or ()),
        created_utc=data.get("created_utc"),
        updated_utc=data.get("updated_utc"),
        notes=data.get("notes"),
    )


class AccessPointRegistry:
    """One registry: either inland or off-shore, never both."""

    def __init__(self, namespace: Namespace, *, producer_identity: str) -> None:
        self.namespace = require_registry_namespace(namespace)
        if not producer_identity or not producer_identity.strip():
            raise ValueError("producer_identity is required")
        self.producer_identity = producer_identity.strip()
        self._sources: dict[str, SourceManifestation] = {}
        self._observations: dict[str, Observation] = {}
        self._geometries: dict[str, DerivedGeometry] = {}
        self._features: dict[str, Feature] = {}
        self._last_sequence = 0

    # -- read access -----------------------------------------------------
    # The mapping properties are read-only live views, not copies.

    @property
    def code(self) -> str:
        return REGISTRY_CODE[self.namespace]

    @property
    def sources(self) -> Mapping[str, SourceManifestation]:
        return MappingProxyType(self._sources)

    @property
    def observations(self) -> Mapping[str, Observation]:
        return MappingProxyType(self._observations)

    @property
    def geometries(self) -> Mapping[str, DerivedGeometry]:
        return MappingProxyType(self._geometries)

    @property
    def features(self) -> Mapping[str, Feature]:
        return MappingProxyType(self._features)

    def feature(self, identifier: str) -> Feature:
        try:
            return self._features[identifier]
        except KeyError:
            found = classify_identifier(identifier) if identifier else None
            if found is not None and found.namespace is not self.namespace:
                raise NamespaceCollisionError(
                    f"{identifier!r} belongs to {found.namespace.value}, "
                    f"not to {self.namespace.value}"
                ) from None
            raise KeyError(identifier) from None

    def rung(self, identifier: str):
        return assertion_rung(self.feature(identifier), self._sources)

    def dimensions(self, identifier: str):
        return dimension_tiers(self.feature(identifier), self._sources)

    def blockers(self, identifier: str) -> tuple[str, ...]:
        return promotion_blockers(
            self.feature(identifier),
            self._sources,
            self._observations,
            producer_identity=self.producer_identity,
        )

    # -- ingestion -------------------------------------------------------

    @staticmethod
    def _put(store: dict[str, Any], key: str, record: Any, what: str) -> bool:
        existing = store.get(key)
        if existing is None:
            store[key] = record
            return True
        if existing.logical_sha256() != record.logical_sha256():
            raise RegistryConflictError(
                f"{what} {key} already exists with different content; "
                "records are immutable -- register a new one instead"
            )
        return False

    def add_source(self, source: SourceManifestation) -> bool:
        for parent in source.parent_source_ids:
            if parent not in self._sources:
                raise RegistryIntegrityError(
                    f"source {source.source_id} names unknown parent {parent}; "
                    "register the parent first so lineage is never lost"
                )
        return self._put(self._sources, source.source_id, source, "source")

    def add_observation(self, observation: Observation) -> bool:
        if observation.namespace is not self.namespace:
            raise NamespaceCollisionError(
                f"observation belongs to {observation.namespace.value}, "
                f"not to {self.namespace.value}"
            )
        if observation.source_id not in self._sources:
            raise RegistryIntegrityError(
                f"observation cites unknown source {observation.source_id}"
            )
        return self._put(
            self._observations, observation.observation_id, observation, "observation"
        )

    def add_geometry(self, geometry: DerivedGeometry) -> bool:
        missing = [o for o in geometry.observation_ids if o not in self._observations]
        if missing:
            raise RegistryIntegrityError(
                f"derived geometry cites unknown observations: {missing}"
            )
        return self._put(
            self._geometries, geometry.geometry_id, geometry, "derived geometry"
        )

    def next_feature_id(self) -> str:
        return feature_id(self.namespace, self._last_sequence + 1)

    def _store_feature(self, feature: Feature) -> None:
        self._features[feature.feature_id] = feature
        self._last_sequence = max(
            self._last_sequence, feature_sequence(feature.feature_id, self.namespace)
        )

    def _check_feature(self, feature: Feature) -> None:
        if feature.namespace is not self.namespace:
            raise NamespaceCollisionError(
                f"feature belongs to {feature.namespace.value}, not to {self.namespace.value}"
            )
        missing = [o for o in feature.observation_ids if o not in self._observations]
        if missing:
            raise RegistryIntegrityError(
                f"feature cites unknown observations: {missing}"
            )
        if (
            feature.geometry_id is not None
            and feature.geometry_id not in self._geometries
        ):
            raise RegistryIntegrityError(
                f"feature cites unknown geometry {feature.geometry_id}"
            )
        for assertion in feature.assertions:
            unknown = [s for s in assertion.source_ids if s not in self._sources]
            if unknown:
                raise RegistryIntegrityError(
                    f"assertion cites unknown sources: {unknown}"
                )
            foreign = [
                o for o in assertion.observation_ids if o not in self._observations
            ]
            if foreign:
                raise RegistryIntegrityError(
                    f"assertion cites unknown observations: {foreign}"
                )
        for prior in feature.supersedes:
            if prior not in self._features:
                raise RegistryIntegrityError(
                    f"feature supersedes unknown feature {prior}"
                )
        if not status_is_permitted(
            feature,
            self._sources,
            self._observations,
            producer_identity=self.producer_identity,
        ):
            ceiling = permitted_status(
                feature,
                self._sources,
                self._observations,
                producer_identity=self.producer_identity,
            )
            raise PromotionError(
                f"{feature.feature_id}: status {feature.status.value} exceeds what the evidence "
                f"allows ({ceiling.value})",
                promotion_blockers(
                    feature,
                    self._sources,
                    self._observations,
                    producer_identity=self.producer_identity,
                ),
            )

    def add_feature(self, feature: Feature) -> bool:
        self._check_feature(feature)
        added = self._put(self._features, feature.feature_id, feature, "feature")
        if added:
            self._store_feature(feature)
        return added

    def register_candidate(
        self,
        feature_class: str,
        *,
        observation_ids: tuple[str, ...] = (),
        assertions: tuple[EvidenceAssertion, ...] = (),
        geometry_id: str | None = None,
        provisional_labels: tuple[str, ...] = (),
        raw_names: tuple[str, ...] = (),
        created_utc: str | None = None,
        notes: str | None = None,
    ) -> Feature:
        """Create a feature at the strongest non-verified status it qualifies for."""

        draft = Feature(
            feature_id=self.next_feature_id(),
            namespace=self.namespace,
            feature_class=feature_class,
            status=RegistryStatus.PROVISIONAL_DISCOVERY,
            observation_ids=observation_ids,
            assertions=assertions,
            geometry_id=geometry_id,
            provisional_labels=provisional_labels,
            raw_names=raw_names,
            created_utc=created_utc,
            updated_utc=created_utc,
            notes=notes,
        )
        self._check_feature(draft)
        ceiling = permitted_status(
            draft,
            self._sources,
            self._observations,
            producer_identity=self.producer_identity,
        )
        status = (
            RegistryStatus.PROVISIONAL_DISCOVERY
            if ceiling is RegistryStatus.PROVISIONAL_DISCOVERY
            else RegistryStatus.CANDIDATE
        )
        feature = replace(draft, status=status)
        self._store_feature(feature)
        return feature

    # -- status changes --------------------------------------------------

    def replace_feature(self, feature: Feature) -> Feature:
        """Store a revised version of an existing feature (same id)."""

        if feature.feature_id not in self._features:
            raise KeyError(feature.feature_id)
        self._check_feature(feature)
        self._features[feature.feature_id] = feature
        return feature

    def promote(self, identifier: str, *, reviewer: str, utc: str) -> Feature:
        """Mark a feature ``VERIFIED``.  Refused while any blocker remains.

        ``reviewer`` must be someone other than this registry's producer: the
        process that built the evidence cannot also certify it.
        """

        if not reviewer or not reviewer.strip():
            raise PromotionError("a named reviewer is required")
        if reviewer.strip() == self.producer_identity:
            raise PromotionError(
                "the producer cannot verify its own evidence; an independent reviewer is required"
            )
        feature = self.feature(identifier)
        if feature.status in {RegistryStatus.REJECTED, RegistryStatus.SUPERSEDED}:
            raise PromotionError(
                f"{identifier} is {feature.status.value} and cannot be promoted"
            )
        blockers = self.blockers(identifier)
        if blockers:
            raise PromotionError(
                f"{identifier} cannot be verified: " + "; ".join(blockers), blockers
            )
        promoted = replace(feature, status=RegistryStatus.VERIFIED, updated_utc=utc)
        self._check_feature(promoted)
        self._features[identifier] = promoted
        return promoted

    def set_status(
        self, identifier: str, status: RegistryStatus, *, utc: str
    ) -> Feature:
        """Move between non-verified statuses.  ``VERIFIED`` only via :meth:`promote`."""

        if status is RegistryStatus.VERIFIED:
            raise PromotionError("use promote(); VERIFIED cannot be set directly")
        revised = replace(self.feature(identifier), status=status, updated_utc=utc)
        self._check_feature(revised)
        self._features[identifier] = revised
        return revised

    # -- accounting ------------------------------------------------------

    def counts(self) -> dict[str, Any]:
        bound = {o for f in self._features.values() for o in f.observation_ids}
        by_status = {status.value: 0 for status in RegistryStatus}
        for feature in self._features.values():
            by_status[feature.status.value] += 1
        return {
            "sources": len(self._sources),
            "observations": len(self._observations),
            "observations_bound": len(bound),
            "observations_unbound": len(self._observations) - len(bound),
            "derived_geometries": len(self._geometries),
            "features": len(self._features),
            "features_by_status": by_status,
        }

    @staticmethod
    def counts_close(counts: Mapping[str, Any]) -> bool:
        return (
            counts["observations_bound"] + counts["observations_unbound"]
            == counts["observations"]
            and sum(counts["features_by_status"].values()) == counts["features"]
        )

    # -- documents -------------------------------------------------------

    def to_document(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": DOCUMENT_SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "rules_version": RULES_VERSION,
            "namespace": self.namespace.value,
            "registry_code": self.code,
            "producer_identity": self.producer_identity,
            "sources": [self._sources[k].to_dict() for k in sorted(self._sources)],
            "observations": [
                self._observations[k].to_dict() for k in sorted(self._observations)
            ],
            "derived_geometries": [
                self._geometries[k].to_dict() for k in sorted(self._geometries)
            ],
            "features": [self._features[k].to_dict() for k in sorted(self._features)],
            "counts": self.counts(),
        }
        body["content_sha256"] = canonical_json_sha256(body)
        return body

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "AccessPointRegistry":
        if not isinstance(document, Mapping):
            raise RegistryIntegrityError("registry document must be an object")
        if document.get("schema") != DOCUMENT_SCHEMA:
            raise RegistryIntegrityError(
                f"unsupported registry document schema: {document.get('schema')!r}"
            )
        body = {k: v for k, v in document.items() if k != "content_sha256"}
        try:
            digest = canonical_json_sha256(body)
        except (TypeError, ValueError) as exc:
            raise RegistryIntegrityError(
                f"registry document is not canonical JSON: {exc}"
            ) from exc
        if document.get("content_sha256") != digest:
            raise RegistryIntegrityError(
                "registry document hash mismatch: the file was altered or truncated"
            )
        try:
            registry = cls(
                Namespace(document["namespace"]),
                producer_identity=document["producer_identity"],
            )
            pending = [source_from_dict(s) for s in document.get("sources", [])]
            # Parents before children, whatever order the file lists them in.
            while pending:
                ready = [
                    s
                    for s in pending
                    if all(p in registry._sources for p in s.parent_source_ids)
                ]
                if not ready:
                    raise RegistryIntegrityError(
                        "source lineage is cyclic or names a parent that is not in the document"
                    )
                for source in ready:
                    registry.add_source(source)
                pending = [s for s in pending if s.source_id not in registry._sources]
            for item in document.get("observations", []):
                registry.add_observation(observation_from_dict(item))
            for item in document.get("derived_geometries", []):
                registry.add_geometry(geometry_from_dict(item))
            features = [
                feature_from_dict(item) for item in document.get("features", [])
            ]
            # Features that supersede others load after the ones they replace.
            remaining = features
            while remaining:
                ready_f = [
                    f
                    for f in remaining
                    if all(p in registry._features for p in f.supersedes)
                ]
                if not ready_f:
                    raise RegistryIntegrityError(
                        "feature supersession is cyclic or dangling"
                    )
                for feature in ready_f:
                    registry.add_feature(feature)
                remaining = [
                    f for f in remaining if f.feature_id not in registry._features
                ]
        except RegistryIntegrityError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise RegistryIntegrityError(
                f"registry document is invalid: {exc}"
            ) from exc
        counts = registry.counts()
        if counts != document.get("counts") or not cls.counts_close(counts):
            raise RegistryIntegrityError("registry record counts do not close")
        return registry

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (
            json.dumps(self.to_document(), indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        )
        target.write_text(text, encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "AccessPointRegistry":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RegistryIntegrityError(
                f"registry document is not valid JSON: {exc}"
            ) from exc
        return cls.from_document(document)
