"""Access-point registry records as rows of the hub's canonical streams.

The federation hub (thehub-pr) aggregates every producer's canonical package:
``sources``, ``entities`` and ``relationships`` rows, among others.  This
module turns the two committed access-point registries into such rows, for
``scripts/federation_export.py --access-point-registries``.

What is exported, and how it is labelled, follows the registries' own rules:

* Only records whose status is CANDIDATE, UNDER_REVIEW or VERIFIED are
  exported.  A PROVISIONAL_DISCOVERY record has no evidence and usually no
  coordinates; a REJECTED or SUPERSEDED one is not a current claim.  They are
  counted, never exported.
* Every exported record is a candidate as far as identity goes: its evidence
  state says ``identity_state CANDIDATE`` and ``identity_scope
  PRODUCER_LOCAL``, so no hub correlation can read it as the same thing as a
  record from another producer.  Its ``epistemic_class`` is INTERPRETIVE: an
  access point is the registry's interpretation of its sources.
* A record carries a ``location`` only where one of its own observations
  states a point.  That point is a REPRESENTATIVE_POINT for the record, with
  the coordinate method saying where it came from
  (``LEGACY_REGISTRY_POINT_CRS_ASSUMED`` where the source never declared its
  coordinate system); nothing is computed or moved here.
* ``confidence`` is required by the hub's schema.  It is an ordering by
  status (see ``STATUS_CONFIDENCE``), not a probability.
* Detections from survey runs, relationships between records and the
  provisional seeds are not exported.

Each registry document is loaded through ``AccessPointRegistry.load``, which
refuses a document that does not match its content hash.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from .namespaces import Namespace
from .registry import AccessPointRegistry
from .rules import assertion_rung
from .vocabulary import RegistryStatus

REGISTRY_FILES = {
    Namespace.ACCESS_POINT_INLAND: "inland.json",
    Namespace.ACCESS_POINT_OFFSHORE: "offshore.json",
}
ENTITY_TYPE = {
    Namespace.ACCESS_POINT_INLAND: "inland_access_point",
    Namespace.ACCESS_POINT_OFFSHORE: "offshore_access_point",
}
REGISTRY_ENTITY_TYPE = "access_point_registry"
EXPORTED_STATUSES = (
    RegistryStatus.CANDIDATE,
    RegistryStatus.UNDER_REVIEW,
    RegistryStatus.VERIFIED,
)
# An ordering for a field the hub requires; not a probability.
STATUS_CONFIDENCE = {
    RegistryStatus.CANDIDATE: 0.3,
    RegistryStatus.UNDER_REVIEW: 0.5,
    RegistryStatus.VERIFIED: 0.9,
}
REGISTRY_CONFIDENCE = 0.5
POINT_METHOD = {
    "SOURCE_DIGITIZED": "REGISTRY_OBSERVATION_POINT_SOURCE_DIGITIZED",
    "DERIVED_FROM_RASTER": "REGISTRY_OBSERVATION_POINT_DERIVED_FROM_RASTER",
}
# A point whose coordinate reference system the source never declared.
CRS_ASSUMED_METHOD = "LEGACY_REGISTRY_POINT_CRS_ASSUMED"
LANE_PHASE = "ACCESS_POINT_REGISTRY"


class AccessPointExportError(ValueError):
    """A registry document could not be exported."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_access_point_streams(
    registry_dir: str | Path,
    *,
    now: str,
    fid: Callable[..., str],
    norm: Callable[[str], str],
    evidence_state: Callable[..., dict[str, Any]],
    lineage: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Rows for the hub's ``sources``, ``entities`` and ``relationships`` streams.

    The id, name-normalisation, evidence-state and lineage helpers are the
    export script's own, passed in so that this lane makes rows exactly the way
    every other lane does.  Returns the three row lists and a ``summary``.
    """

    base = Path(registry_dir)
    sources: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"registries": {}}
    for namespace, filename in REGISTRY_FILES.items():
        path = base / filename
        if not path.is_file():
            raise AccessPointExportError(f"{path} is missing")
        try:
            registry = AccessPointRegistry.load(path)
        except Exception as exc:  # noqa: BLE001 - any failure to verify stops the lane
            raise AccessPointExportError(f"{path}: {exc}") from exc
        if registry.namespace is not namespace:
            raise AccessPointExportError(f"{path} holds {registry.namespace.value}")
        document_sha = _file_sha256(path)
        document = registry.to_document()
        content_sha = document["content_sha256"]
        inputs = [f"{path.name}:sha256:{document_sha}"]
        ref = f"spiderweb-pr:{namespace.value}"
        sid = fid("src", ref)
        sources.append(
            {
                "source_id": sid,
                "source_type": "access_point_registry",
                "source_name": f"{namespace.value} registry",
                "source_ref": ref,
                "confidence": REGISTRY_CONFIDENCE,
                "lineage": lineage(LANE_PHASE, inputs, "registry_record_projection"),
                "synthetic": False,
                "created_at": now,
                "extracted_at": now,
                "evidence_state": evidence_state(epistemic_class="CURATED"),
            }
        )
        registry_entity = fid("ent", "access_point_registry", namespace.value)
        entities.append(
            {
                "entity_id": registry_entity,
                "source_id": sid,
                "name": f"{namespace.value} registry",
                "normalized_name": norm(f"{namespace.value} registry"),
                "entity_type": REGISTRY_ENTITY_TYPE,
                "jurisdiction": "PR",
                "confidence": REGISTRY_CONFIDENCE,
                "lineage": lineage(LANE_PHASE, inputs, "registry_record_projection"),
                "synthetic": False,
                "created_at": now,
                "extracted_at": now,
                "attributes": {
                    "namespace": namespace.value,
                    "registry_code": document["registry_code"],
                    "registry_content_sha256": content_sha,
                },
                "evidence_state": evidence_state(epistemic_class="CURATED"),
            }
        )
        exported = 0
        withheld: dict[str, int] = {}
        for feature_id in sorted(registry.features):
            feature = registry.features[feature_id]
            if feature.status not in EXPORTED_STATUSES:
                withheld[feature.status.value] = (
                    withheld.get(feature.status.value, 0) + 1
                )
                continue
            point = None
            basis = None
            crs_basis = None
            uncertainty = None
            for oid in feature.observation_ids:
                observation = registry.observations[oid]
                geometry = observation.geometry
                if geometry and geometry.get("type") == "Point":
                    lon, lat = geometry["coordinates"][:2]
                    point = {"lat": round(float(lat), 6), "lon": round(float(lon), 6)}
                    basis = getattr(observation.geometry_basis, "value", None)
                    crs_basis = (observation.raw_attributes or {}).get(
                        "horizontal_crs_basis"
                    )
                    uncertainty = observation.horizontal_uncertainty_m
                    break
            tiers = {
                assertion.dimension.value: assertion.tier.name
                for assertion in feature.assertions
            }
            name = " ".join(
                part for part in (feature_id, (feature.raw_names or ("",))[0]) if part
            )
            ent_id = fid("ent", "access_point", feature_id)
            row: dict[str, Any] = {
                "entity_id": ent_id,
                "source_id": sid,
                "name": name,
                "normalized_name": norm(name),
                "entity_type": ENTITY_TYPE[namespace],
                "jurisdiction": "PR",
                "confidence": STATUS_CONFIDENCE[feature.status],
                "lineage": lineage(LANE_PHASE, inputs, "registry_record_projection"),
                "synthetic": False,
                "created_at": feature.created_utc or now,
                "extracted_at": now,
                "attributes": {
                    "feature_id": feature_id,
                    "namespace": namespace.value,
                    "feature_class": feature.feature_class,
                    "status": feature.status.value,
                    "assertion_rung": assertion_rung(feature, registry.sources).name,
                    "tiers_by_dimension": dict(sorted(tiers.items())),
                    "identity_default": "CANDIDATE_NOT_IDENTITY",
                    "registry_content_sha256": content_sha,
                    "horizontal_crs_basis": crs_basis,
                    "horizontal_uncertainty_m": uncertainty,
                },
            }
            if point is not None:
                row["location"] = point
                row["evidence_state"] = evidence_state(
                    epistemic_class="INTERPRETIVE",
                    identity_state="CANDIDATE",
                    identity_scope="PRODUCER_LOCAL",
                    geometry_precision="REPRESENTATIVE_POINT",
                    coordinate_method=(
                        CRS_ASSUMED_METHOD
                        if str(crs_basis or "").startswith("ASSUMED")
                        else POINT_METHOD.get(basis or "", "REGISTRY_OBSERVATION_POINT")
                    ),
                )
            else:
                row["evidence_state"] = evidence_state(
                    epistemic_class="INTERPRETIVE",
                    identity_state="CANDIDATE",
                    identity_scope="PRODUCER_LOCAL",
                )
            entities.append(row)
            rid = fid("rel", ent_id, "reported_by", registry_entity)
            relationships.append(
                {
                    "relationship_id": rid,
                    "source_id": sid,
                    "source_entity_id": ent_id,
                    "target_entity_id": registry_entity,
                    "relationship_type": "reported_by",
                    "evidence_source_id": sid,
                    "confidence": STATUS_CONFIDENCE[feature.status],
                    "lineage": lineage(
                        LANE_PHASE, inputs, "registry_record_projection"
                    ),
                    "synthetic": False,
                    "created_at": feature.created_utc or now,
                    "extracted_at": now,
                    "evidence_state": evidence_state(epistemic_class="CURATED"),
                }
            )
            exported += 1
        summary["registries"][namespace.value] = {
            "document_sha256": document_sha,
            "content_sha256": content_sha,
            "exported": exported,
            "withheld_by_status": dict(sorted(withheld.items())),
        }
    summary["not_exported"] = [
        "PROVISIONAL_DISCOVERY, REJECTED and SUPERSEDED records",
        "detections from survey runs",
        "relationships between records",
    ]
    return {
        "sources": sources,
        "entities": entities,
        "relationships": relationships,
        "summary": summary,
    }
