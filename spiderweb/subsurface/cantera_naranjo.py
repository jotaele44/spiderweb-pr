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


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    subject: str
    manifestations: tuple[str, ...]
    state: str
    reason: str


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

# Each coordinate below is the coordinate of its own source manifestation. None
# is treated as a tunnel entrance or property boundary. In particular, the PRPB
# Cantera Naranjo point is inside SZ-0015 while the independent USGS Juana Diaz
# Mine record point is just outside the frozen Santiago AOI. That spatial split
# is preserved as a contradiction/identity problem rather than reconciled by
# name, commodity, or proximity.
KNOWN_POINT_MANIFESTATIONS: tuple[PointManifestation, ...] = (
    PointManifestation(
        "PRPB_CANTERA_NARANJO_OBJECTID_38",
        "CANTERA NARANJO",
        -66.47027159432102,
        18.06533875942472,
        "PRPB_QUARRIES_10",
        "QUARRY_SOURCE_POINT",
        notes="Planning Board quarry row OBJECTID 38; source address CARR 551 KM 2.1 BO NARANJO; source status field CERRADO; GPS date is historical and is not a current-operation claim.",
    ),
    PointManifestation(
        "USGS_MRDS_CANTERO_NARANJO_200733",
        "Cantero Naranjo",
        -66.47027000007718,
        18.068469999666476,
        "USGS_MRDS_HOSTED_0_PR_AOI",
        "HISTORICAL_MINERAL_RECORD_POINT",
        notes="MRDS producer manifestation nearly aligned in longitude with PRPB quarry point but outside exact Santiago triangle; name/nearby geometry is insufficient for identity.",
    ),
    PointManifestation(
        "USGS_W701145_JUANA_DIAZ_MINE",
        "Juana Diaz Mine",
        -66.46527777777778,
        18.070833333333333,
        USGS_APPENDIX_SOURCE_ID,
        "HISTORICAL_MINE_RECORD_POINT",
        notes="USGS OFR 98-038 appendix: W701145; Mn; fissure fillings in limestone; Rio Descalabrado quadrangle. The record point is not tunnel-entrance geometry.",
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
        notes="Modern regulatory facility point associated with a different PR-551 chainage manifestation; name similarity cannot bind it to historic Site 78.",
    ),
)

CONTRADICTIONS: tuple[Contradiction, ...] = (
    Contradiction(
        "CN-CONTR-001",
        "PR-551 chainage",
        (SITE78_SOURCE_ID, "PROCAN_FIRST_PARTY_MAP"),
        "OPEN",
        "OECH Site 78 prints Km 4 with no decimal; modern Procan manifestations use approximately Km 4.4-4.5. The modern decimal must not be imported into the historical source.",
    ),
    Contradiction(
        "CN-CONTR-002",
        "Cantera Naranjo name/chainage",
        ("PRPB_CANTERA_NARANJO_OBJECTID_38", "EPA_PRODUCTOS_AGREGADOS_CANTERA_NARANJO", "PROCAN_EMBEDDED_MAP_CENTER"),
        "OPEN",
        "The corpus carries distinct Cantera/Productos de Cantera manifestations around PR-551 Km 2.1, Km 2.7 and Km 4.4-4.5; name normalization is forbidden.",
    ),
    Contradiction(
        "CN-CONTR-003",
        "Santiago exact spatial state",
        ("PRPB_CANTERA_NARANJO_OBJECTID_38", "USGS_MRDS_CANTERO_NARANJO_200733", "USGS_W701145_JUANA_DIAZ_MINE"),
        "OPEN",
        "The PRPB quarry point is within SZ-0015 while MRDS Cantero Naranjo and USGS W701145 are outside the exact Santiago polygon.",
    ),
    Contradiction(
        "CN-CONTR-004",
        "mapped opening symbols versus documentary tunnels",
        ("USGS_USMIN_EXPLICIT_OPENINGS_17", SITE78_SOURCE_ID),
        "EXPLAINED_DIFFERENT_UNIVERSES",
        "The AOI explicit Adit|Air Shaft|Mine Shaft symbol query is ZERO while Site 78 documents tunnels; the source universes and spatial manifestations differ, so ZERO is not real-world absence.",
    ),
    Contradiction(
        "CN-CONTR-005",
        "natural cave versus artificial historical workings",
        ("PRPB_CAVES_31:178", SITE78_SOURCE_ID, "USGS_W701145_JUANA_DIAZ_MINE"),
        "OPEN",
        "Cueva Naranjo is mapped inside SZ-0015; historical manganese-working geometry is not spatially bound inside the cell. Connectivity remains unresolved.",
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


def historical_working_score_eligible(rows: Iterable[dict[str, object]], *, zone_id: str) -> bool:
    """Return True only for an identity-bound historical working inside a zone.

    Documentary existence, nearby record points, quarry points, and unresolved
    identities are deliberately insufficient. This function is a promotion gate,
    not a scoring formula.
    """
    for row in rows:
        if row.get("role") != "HISTORICAL_MINE_RECORD_POINT":
            continue
        if row.get("identity_to_site78") == IdentityState.UNRESOLVED:
            continue
        if zone_id in row.get("containing_zones", []):
            return True
    return False


def write_lineage_receipt(
    path: str | Path,
    *,
    aoi: BaseGeometry,
    zones: Iterable[tuple[str, BaseGeometry]],
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    points = adjudicate_manifestations(aoi=aoi, zones=zones)
    payload = {
        "schema": "spiderweb.subsurface.cantera_naranjo_lineage.v1",
        "site78_claims": [asdict(row) for row in SITE78_CLAIMS],
        "point_manifestations": points,
        "contradictions": [asdict(row) for row in CONTRADICTIONS],
        "relevance_gate": {
            "SZ-0015_historical_working_score_eligible": historical_working_score_eligible(points, zone_id="SZ-0015"),
            "rule": "historical artificial-subsurface score requires identity-bound historical-working geometry inside exact zone",
        },
        "rules": [
            "no name-only identity",
            "no proximity-only identity or connectivity",
            "USGS record point is not tunnel geometry",
            "modern business/facility points are not quarry-property boundaries",
            "a quarry manifestation already counted by v1.1 is not a new historical-working score contribution",
            "historical working evidence changes relevance only after exact AOI/zone spatial binding",
        ],
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return out