"""Bounded reference-run planning for Guayama–Punta Tuna marine validation.

This module deliberately separates a broad discovery corridor from any
registered screenshot footprint.  The discovery corridor is suitable for
source enumeration only; it must not be used to certify screenshot-visible
features.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from pipeline.marine_lidar_sources import LidarInventoryLayer, build_usiei_query_url
from pipeline.marine_sources import (
    BoundingBox,
    CatalogFamily,
    build_ncei_catalog_url,
    build_nos_bag_query_url,
)


class GeometryRole(StrEnum):
    DISCOVERY_CORRIDOR = "discovery_corridor"
    REGISTERED_VISUALIZATION = "registered_visualization"


class SpatialRelation(StrEnum):
    FULLY_WITHIN = "FULLY_WITHIN"
    PARTIAL = "PARTIAL"
    TOUCH_ONLY = "TOUCH_ONLY"
    OUTSIDE = "OUTSIDE"
    NULL_EMPTY = "NULL_EMPTY"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ReferenceAOI:
    aoi_id: str
    bbox: BoundingBox
    role: GeometryRole
    provenance: str
    certified: bool = False

    def __post_init__(self) -> None:
        if not self.aoi_id.strip():
            raise ValueError("aoi_id must not be empty")
        if not self.provenance.strip():
            raise ValueError("provenance must not be empty")
        if self.role is GeometryRole.DISCOVERY_CORRIDOR and self.certified:
            raise ValueError("discovery corridor cannot be promoted as a certified visualization footprint")

    def require_visualization_certification(self) -> None:
        if self.role is not GeometryRole.REGISTERED_VISUALIZATION or not self.certified:
            raise ValueError("feature certification requires a certified registered visualization footprint")


# Bounded discovery seed only.  It spans Guayama to Punta Tuna and extends
# offshore for source enumeration; it is NOT inferred from screenshot pixels.
GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1 = ReferenceAOI(
    aoi_id="guayama_punta_tuna_discovery_v0_1",
    bbox=BoundingBox(-66.20, 17.50, -65.80, 18.05),
    role=GeometryRole.DISCOVERY_CORRIDOR,
    provenance=(
        "Analyst-defined source-discovery corridor covering the Guayama–Punta Tuna "
        "south-coast sector; exact screenshot footprint remains separately unresolved."
    ),
    certified=False,
)


def build_reference_queries(
    aoi: ReferenceAOI,
    *,
    ncei_page_size: int = 100,
    arcgis_page_size: int = 2000,
) -> Mapping[str, str]:
    """Return the canonical source-query denominator for a bounded reference AOI."""

    return {
        "ncei_multibeam": build_ncei_catalog_url(
            CatalogFamily.MULTIBEAM,
            aoi.bbox,
            page_size=ncei_page_size,
        ),
        "ncei_sounding": build_ncei_catalog_url(
            CatalogFamily.SOUNDING,
            aoi.bbox,
            page_size=ncei_page_size,
        ),
        "nos_bag": build_nos_bag_query_url(
            aoi.bbox,
            page_size=arcgis_page_size,
        ),
        "usiei_topobathy": build_usiei_query_url(
            LidarInventoryLayer.TOPOBATHY_SHORELINE,
            aoi.bbox,
            page_size=arcgis_page_size,
        ),
        "usiei_bathymetric": build_usiei_query_url(
            LidarInventoryLayer.BATHYMETRIC,
            aoi.bbox,
            page_size=arcgis_page_size,
        ),
        "usiei_other_bathymetric": build_usiei_query_url(
            LidarInventoryLayer.OTHER_BATHYMETRIC_SURVEYS,
            aoi.bbox,
            page_size=arcgis_page_size,
        ),
    }


def classify_bbox_relation(aoi: BoundingBox, feature: BoundingBox | None) -> SpatialRelation:
    """Classify an axis-aligned footprint envelope against an AOI envelope.

    Envelope classification is intentionally conservative.  It is appropriate
    for acquisition planning and cannot substitute for polygon-level geometry
    intersection when certification requires exact boundaries.
    """

    if feature is None:
        return SpatialRelation.NULL_EMPTY

    ix_min = max(aoi.min_lon, feature.min_lon)
    iy_min = max(aoi.min_lat, feature.min_lat)
    ix_max = min(aoi.max_lon, feature.max_lon)
    iy_max = min(aoi.max_lat, feature.max_lat)

    if ix_min > ix_max or iy_min > iy_max:
        return SpatialRelation.OUTSIDE
    if ix_min == ix_max or iy_min == iy_max:
        return SpatialRelation.TOUCH_ONLY

    if (
        feature.min_lon >= aoi.min_lon
        and feature.max_lon <= aoi.max_lon
        and feature.min_lat >= aoi.min_lat
        and feature.max_lat <= aoi.max_lat
    ):
        return SpatialRelation.FULLY_WITHIN
    return SpatialRelation.PARTIAL


def esri_feature_envelope(feature: Mapping[str, object]) -> BoundingBox | None:
    """Extract an envelope from Esri polygon rings without changing geometry."""

    geometry = feature.get("geometry")
    if geometry is None:
        return None
    if not isinstance(geometry, Mapping):
        raise ValueError("feature geometry must be an object")
    rings = geometry.get("rings")
    if not isinstance(rings, list) or not rings:
        return None

    xs: list[float] = []
    ys: list[float] = []
    for ring in rings:
        if not isinstance(ring, list):
            raise ValueError("Esri ring must be a list")
        for point in ring:
            if not isinstance(point, list) or len(point) < 2:
                raise ValueError("Esri ring point must contain x and y")
            x, y = point[0], point[1]
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise ValueError("Esri ring coordinates must be numeric")
            xs.append(float(x))
            ys.append(float(y))

    if not xs:
        return None
    return BoundingBox(min(xs), min(ys), max(xs), max(ys))
