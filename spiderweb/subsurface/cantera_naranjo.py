"""Fail-closed historical lineage model for Cantera Naranjo / Juana Diaz Mn workings.

This module records documentary claims and point manifestations without collapsing
historic Site 78, the USGS Juana Diaz Mine, modern quarry businesses/facilities,
Cueva Naranjo, or visible quarry morphology into one entity. Spatial proximity,
shared commodity, and shared names are discovery evidence only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from pathlib import Path
from typing import Iterable

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry


class IdentityState(StrEnum):
    SAME_ENTITY = "SAME_ENTITY"
    SAME_PROPERTY_DIFFERENT_FEATURE = "SAME_PROPERTY_DIFFERENT_FEATURE"
    HISTORICAL_PREDECESSOR = "HISTORICAL_PREDECESSOR"
    SUCCESSOR = "SUCCESSOR"
    CONTAINED_WITHIN = "CONTAINED_WITHIN"
    ADJACENT = "ADJACENT"
    NAME_COLLISION = "NAME_COLLISION"
    UNRESOLVED = "UNRESOLVED"


class ClaimState(StrEnum):
    SUPPORTED = "SUPPORTED"
    CORROBORATED = "CORROBORATED"
    CONTRADICTED = "CONTRADICTED"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class HistoricalClaim:
    claim_id: str
    text: str
    source_id: str
    state: ClaimState = ClaimState.SUPPORTED


@dataclass(frozen=True)
class PointManifestation:
    manifestation_id: str
    name: str
    longitude: float
    latitude: float
    source_id: str
    role: str
    identity_to_site78: IdentityState = IdentityState.UNRESOLVED
    notes: str = ""

    @property
    def point(self) -> Point:
        return Point(self.longitude, self.latitude)


SITE78_SOURCE_ID = "OECH_CARRETERA_CENTRAL_CANTERA_NARANJO_1996"
USGS_MN_SOURCE_ID = "USGS_OFR98_038_MANUSCRIPT_MANGANESE"
USGS_APPENDIX_SOURCE_ID = "USGS_INDUSTRIAL_MINERALS_PR_OFR_98_038"
PRPB_EXTRACTION_SOURCE_ID = "PRPB_KARST_EXTRACTION_AREAS_ANNEX"

SITE78_CLAIMS: tuple[HistoricalClaim, ...] = (
    HistoricalClaim("CN78-C01", "A historical site named Cantera Naranjo was identified west of Juana Diaz.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C02", "The publication locates Site 78 on PR-551 at kilometer 4 (no decimal is printed in the source).", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C03", "The site is described as a marble quarry.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C04", "The marble quarry is described as containing tunnels of a manganese mine.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C05", "The manganese mine is described as having been worked in the early 1900s.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C06", "The operator is described generically as a United States company.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C07", "Extracted material is described as ground to a black powder.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C08", "The processed manganese material is described as exported.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C09", "The tunnels are described as following the mineral vein through marble.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C10", "Most tunnels are described as destroyed by later quarry exploitation.", SITE78_SOURCE_ID),
    HistoricalClaim("CN78-C11", "A small stone building used as the mine office is described as surviving at publication time.", SITE78_SOURCE_ID),
)

# USGS appendix W701145 is an independent mine manifestation. The coordinate is
# the published record point, not a tunnel-entrance coordinate and not a quarry
# boundary. Identity with OECH Site 78 remains UNRESOLVED until property/chainage
# or documentary evidence explicitly binds them.
KNOWN_POINT_MANIFESTATIONS: tuple[PointManifestation, ...] = (
    PointManifestation(
        "USGS_W701145_JUANA_DIAZ_MINE",
        "Juana Diaz Mine",
        -66.46527777777778,
        18.070833333333333,
        USGS_APPENDIX_SOURCE_ID,
        "HISTORICAL_MINE_RECORD_POINT",
        notes="USGS OFR 98-038 appendix: W701145; Mn; fissure fillings in limestone; Rio Descalabrado quadrangle.",
    ),
    PointManifestation(
        "PROCAN_EMBEDDED_MAP_CENTER",
        "Productos de Cantera Inc. / Procan",
        -66.47586222915297,
        18.07100376391198,
        "PROCAN_FIRST_PARTY_MAP",
        "MODERN_QUARRY_MAP_CENTER",
        notes="First-party website gives PR-551 Km 4.4; embedded-map center is a business/map anchor, not a quarry centroid.",
    ),
    PointManifestation(
        "EPA_PRODUCTOS_AGREGADOS_CANTERA_NARANJO",
        "Productos de Agregados - Cantera Naranjo",
        -66.500278,
        18.054444,
        "EPA_ECHO_FACILITY_MANIFESTATION",
        "MODERN_FACILITY_POINT",
        notes="Modern regulatory facility point at PR-551 Km 2.7; name similarity cannot bind it to historic Site 78.",
    ),
)


def point_spatial_state(point: Point, geometry: BaseGeometry) -> str:
    if geometry.is_empty:
        return "UNRESOLVED"
    if geometry.covers(point):
        return "WITHIN"
    if geometry.touches(point):
        return "TOUCH_ONLY"
    return "OUTSIDE"


def adjudicate_manifestations(
    *,
    aoi: BaseGeometry,
    zones: Iterable[tuple[str, BaseGeometry]],
    manifestations: Iterable[PointManifestation] = KNOWN_POINT_MANIFESTATIONS,
) -> list[dict[str, object]]:
    """Return spatial states without changing identity states.

    A manifestation can be close to or inside a zone and still remain identity
    UNRESOLVED. No nearest-zone assignment is performed for outside points.
    """
    zone_rows = tuple(zones)
    output: list[dict[str, object]] = []
    for item in manifestations:
        containing = [zone_id for zone_id, geom in zone_rows if geom.covers(item.point)]
        output.append(
            {
                **asdict(item),
                "aoi_spatial_state": point_spatial_state(item.point, aoi),
                "containing_zones": containing,
                "promotion_permitted": False,
                "connectivity_inference_permitted": False,
            }
        )
    return output


def write_lineage_receipt(
    path: str | Path,
    *,
    aoi: BaseGeometry,
    zones: Iterable[tuple[str, BaseGeometry]],
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "spiderweb.subsurface.cantera_naranjo_lineage.v1",
        "site78_claims": [asdict(row) for row in SITE78_CLAIMS],
        "point_manifestations": adjudicate_manifestations(aoi=aoi, zones=zones),
        "rules": [
            "no name-only identity",
            "no proximity-only identity or connectivity",
            "USGS record point is not tunnel geometry",
            "modern business/facility points are not quarry-property boundaries",
            "historical working evidence changes relevance only after exact AOI/zone spatial binding",
        ],
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return out
