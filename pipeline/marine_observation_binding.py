"""Conservative binding from marine source metadata into analysis records.

Inventory footprints and survey catalog rows describe acquisition coverage; they
are not depth samples.  Bindings produced here intentionally carry ``value_m=None``
and non-direct coverage until a downstream parser supplies an actual measured
sample with explicit vertical reference and provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from gebco.marine_evidence import (
    CoverageState,
    MarineObservation,
    ProductStage,
    SensorType,
    VerticalReference,
)
from pipeline.marine_lidar_sources import LidarInventoryLayer


@dataclass(frozen=True, slots=True)
class SourceBinding:
    source_id: str
    source_family: str
    project_name: str | None
    sensor: SensorType
    root_survey_id: str | None
    metadata_uri: str | None
    data_access_uri: str | None
    vertical_reference: VerticalReference
    collection_date_raw: str | None
    attributes: Mapping[str, object]


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _attributes(feature: Mapping[str, object]) -> dict[str, object]:
    raw = feature.get("attributes")
    if not isinstance(raw, Mapping):
        raise ValueError("inventory feature is missing an attributes object")
    return {str(k): v for k, v in raw.items()}


def _stable_root(attrs: Mapping[str, object]) -> str | None:
    """Use authoritative stable identifiers only; names are not identity proof."""

    for key in ("GlobalID", "UUID", "InvID", "OBJECTID"):
        value = _clean_text(attrs.get(key))
        if value:
            return f"USIEI:{key}:{value}"
    return None


def _sensor_for_layer(layer: LidarInventoryLayer) -> SensorType:
    if layer is LidarInventoryLayer.TOPOBATHY_SHORELINE:
        return SensorType.TOPOBATHYMETRIC_LIDAR
    if layer is LidarInventoryLayer.BATHYMETRIC:
        return SensorType.BATHYMETRIC_LIDAR
    if layer is LidarInventoryLayer.OTHER_BATHYMETRIC_SURVEYS:
        return SensorType.DERIVED_BATHYMETRIC_GRID
    raise ValueError(f"layer {layer.name} is not a marine lidar source family")


def bind_usiei_inventory_feature(
    layer: LidarInventoryLayer,
    feature: Mapping[str, object],
) -> SourceBinding:
    attrs = _attributes(feature)
    root = _stable_root(attrs)
    if root is None:
        raise ValueError("USIEI feature has no authoritative stable identifier")

    horizontal = _clean_text(attrs.get("HorizontalDatum")) or "UNKNOWN"
    vertical_datum = _clean_text(attrs.get("VerticalDatum"))
    vertical = VerticalReference(
        horizontal_crs=horizontal,
        vertical_crs=None,
        vertical_datum=vertical_datum,
        tidal_datum=None,
        depth_positive="down",
    )

    return SourceBinding(
        source_id=root,
        source_family=f"USIEI_LAYER_{int(layer)}",
        project_name=_clean_text(attrs.get("ProjectName")),
        sensor=_sensor_for_layer(layer),
        root_survey_id=root,
        metadata_uri=_clean_text(attrs.get("MetadataLink")),
        data_access_uri=_clean_text(attrs.get("DataAccess")),
        vertical_reference=vertical,
        collection_date_raw=_clean_text(attrs.get("CollectionDate")),
        attributes=attrs,
    )


def inventory_binding_to_observation(binding: SourceBinding) -> MarineObservation:
    """Represent inventory metadata without manufacturing a measured depth.

    Coverage stays UNKNOWN and stage stays DERIVED_PRODUCT.  This record can
    participate in provenance/crosswalk operations but cannot satisfy the direct
    sensor gate in :mod:`gebco.marine_evidence`.
    """

    return MarineObservation(
        observation_id=f"inventory:{binding.source_id}",
        sensor=binding.sensor,
        stage=ProductStage.DERIVED_PRODUCT,
        root_survey_id=binding.root_survey_id,
        vertical_reference=binding.vertical_reference,
        coverage=CoverageState.UNKNOWN,
        value_m=None,
        uncertainty_m=None,
        observed_at=None,
        parent_ids=(),
        source_uri=binding.metadata_uri or binding.data_access_uri,
        source_sha256=None,
    )


def bind_measured_sample(
    *,
    observation_id: str,
    sensor: SensorType,
    root_survey_id: str,
    vertical_reference: VerticalReference,
    value_m: float,
    uncertainty_m: float | None,
    observed_at: datetime | None,
    source_uri: str,
    source_sha256: str,
    parent_ids: tuple[str, ...] = (),
) -> MarineObservation:
    """Promote only a real parsed sample into direct sensor evidence."""

    if not root_survey_id.strip():
        raise ValueError("root_survey_id is required for direct sensor evidence")
    if not source_uri.strip():
        raise ValueError("source_uri is required for direct sensor evidence")
    if len(source_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in source_sha256):
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest")
    if not vertical_reference.is_fully_bound():
        raise ValueError("direct sensor sample requires a bound vertical reference")

    return MarineObservation(
        observation_id=observation_id,
        sensor=sensor,
        stage=ProductStage.PROCESSED_OBSERVATION,
        root_survey_id=root_survey_id,
        vertical_reference=vertical_reference,
        coverage=CoverageState.DIRECTLY_OBSERVED,
        value_m=value_m,
        uncertainty_m=uncertainty_m,
        observed_at=observed_at,
        parent_ids=parent_ids,
        source_uri=source_uri,
        source_sha256=source_sha256.lower(),
    )
