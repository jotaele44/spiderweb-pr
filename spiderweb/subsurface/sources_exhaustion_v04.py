"""Fourth bounded public-source exhaustion overlay.

v0.4 binds exact machine-queryable manifestations discovered during the
public-residual closure campaign while preserving unresolved classes that cannot
be certified from public material alone. Former military sources remain
property/report-level only; no precise current hardened-asset locator is created.
"""
from __future__ import annotations

from .sources import SourceKind, SourceSpec, SourceStatus
from .sources_exhaustion_v03 import SOURCE_DENOMINATOR_V03

USGS_USMIN_CONSOLIDATED = (
    "https://energy.usgs.gov/arcgis/rest/services/Hosted/"
    "USMin_Prospect_and_mine_related_map_features/FeatureServer"
)
USGS_MRDS = (
    "https://energy.usgs.gov/arcgis/rest/services/Hosted/"
    "Mineral_Resource_Data_System/FeatureServer"
)
TOPOVIEW = "https://ngmdb.usgs.gov/arcgis/rest/services/topoview/ustOverlay/MapServer"
PRPB_INFRA = "https://sige.pr.gov/server/rest/services/MIPR/Infraestructura/FeatureServer"

# Only these authoritative point-symbol values are treated as explicit opening
# classes. Generic Mine, Coal Mine, pits, dumps, tailings, quarries and prospects
# are intentionally excluded from the DIRECT opening manifestation.
USGS_OPENING_TYPES = ("Adit", "Air Shaft", "Mine Shaft")
USGS_OPENING_WHERE = "ftr_type IN ('Adit','Air Shaft','Mine Shaft')"

_SUPERSEDED_V03 = frozenset({"USGS_USMIN_MINE_SYMBOLS_0"})

BOUND_V04: tuple[SourceSpec, ...] = (
    SourceSpec(
        "USGS_USMIN_CONSOLIDATED_POINTS_17",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "Consolidated prospect- and mine-related point features",
        SourceKind.ARCGIS_LAYER,
        USGS_USMIN_CONSOLIDATED,
        SourceStatus.VERIFIED_QUERYABLE,
        layer_id=17,
        stable_id_fields=("objectid", "OBJECTID"),
        evidence_role="SUPPORTING",
        notes=(
            "September-2025 USGS consolidation of historical-topographic-map mine symbols. "
            "Mixed taxonomy includes openings and non-opening features; no direct subsurface "
            "promotion is permitted from the unfiltered manifestation."
        ),
    ),
    SourceSpec(
        "USGS_USMIN_EXPLICIT_OPENINGS_17",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "Consolidated mine symbols restricted to explicit opening classes",
        SourceKind.ARCGIS_LAYER,
        USGS_USMIN_CONSOLIDATED,
        SourceStatus.VERIFIED_QUERYABLE,
        layer_id=17,
        query=(("where", USGS_OPENING_WHERE),),
        stable_id_fields=("objectid", "OBJECTID"),
        evidence_role="DIRECT",
        notes=(
            "Exact authoritative ftr_type filter limited to Adit, Air Shaft, and Mine Shaft. "
            "DIRECT means the historical map explicitly depicts that opening class; it does "
            "not imply current accessibility, condition, ownership, or continued existence."
        ),
    ),
    SourceSpec(
        "USGS_USMIN_CONSOLIDATED_POLYGONS_18",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "Consolidated prospect- and mine-related polygon features",
        SourceKind.ARCGIS_LAYER,
        USGS_USMIN_CONSOLIDATED,
        SourceStatus.VERIFIED_QUERYABLE,
        layer_id=18,
        stable_id_fields=("objectid", "OBJECTID"),
        evidence_role="SUPPORTING",
        notes=(
            "Polygon companion to consolidated mine-symbol point layer. Polygon overlap is "
            "mine-feature context and does not by itself establish a shaft/adit opening."
        ),
    ),
    SourceSpec(
        "USGS_MRDS_HOSTED_0_PR_AOI",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "Hosted Mineral Resources Data System feature layer",
        SourceKind.ARCGIS_LAYER,
        USGS_MRDS,
        SourceStatus.VERIFIED_QUERYABLE,
        layer_id=0,
        stable_id_fields=("objectid", "OBJECTID", "dep_id", "site_name"),
        evidence_role="SUPPORTING",
        notes=(
            "Current hosted structured MRDS manifestation. Records may represent producers, "
            "past producers, prospects, or occurrences and may be historically stale; a point "
            "record does not prove an accessible underground opening."
        ),
    ),
    SourceSpec(
        "USGS_TOPOVIEW_OVERLAY_0",
        "HISTORICAL_CORROBORATION",
        "U.S. Geological Survey",
        "topoView HTMC/US Topo map-footprint overlay",
        SourceKind.ARCGIS_LAYER,
        TOPOVIEW,
        SourceStatus.VERIFIED_QUERYABLE,
        layer_id=0,
        stable_id_fields=("OBJECTID", "MAP_NAME"),
        evidence_role="SUPPORTING",
        notes=(
            "Queryable polygon footprint/index manifestation for historical map editions. "
            "Returned map metadata closes AOI map-edition discovery only after pagination "
            "and count arithmetic; actual map payload bytes remain separate manifestations."
        ),
    ),
    SourceSpec(
        "PRPB_BROADBAND_SERVICE_ROAD_24",
        "UTILITIES_UNDERGROUND",
        "Puerto Rico Planning Board",
        "MIPR Infraestructura - Servicio por Carretera",
        SourceKind.ARCGIS_LAYER,
        PRPB_INFRA,
        SourceStatus.DISCOVERY_ONLY,
        layer_id=24,
        stable_id_fields=("OBJECTID",),
        evidence_role="CANDIDATE",
        notes=(
            "Polyline broadband service-by-road manifestation with transmission technology. "
            "It is not buried-conduit geometry and cannot close the underground-network residual."
        ),
    ),
    SourceSpec(
        "PR_BROADBAND_SMART_ISLAND_DOWNLOAD",
        "UTILITIES_UNDERGROUND",
        "Puerto Rico Broadband Program / OGP",
        "Smart Island public GIS/download portal",
        SourceKind.REFERENCE_PAGE,
        "https://smartislandmaps.pr.gov/download-data",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes=(
            "Official continuously updated broadband GIS/download portal. Public download "
            "content must be frozen per dataset; coverage/project data do not imply buried paths."
        ),
    ),
    SourceSpec(
        "USACE_FUDS_CULEBRA_REPORT_INDEX",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Culebra FUDS project/report index",
        SourceKind.REFERENCE_PAGE,
        "https://www.saj.usace.army.mil/Culebra/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Public former-site report index; no current protected-asset inference permitted.",
    ),
    SourceSpec(
        "USACE_FUDS_DESECHEO_REPORT_INDEX",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Desecheo FUDS project/report index",
        SourceKind.REFERENCE_PAGE,
        "https://www.saj.usace.army.mil/Desecheo/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Public former-site inventory, archives-search, inspection, and RI/FS corpus index.",
    ),
    SourceSpec(
        "USACE_FUDS_FORT_BROOKE_REPORT_INDEX",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Fort Brooke FUDS project/report index",
        SourceKind.REFERENCE_PAGE,
        "https://www.saj.usace.army.mil/FortBrooke/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Public former-site report index; structure identity must come from the documents themselves.",
    ),
    SourceSpec(
        "USACE_FUDS_MONITO_REPORT_INDEX",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Monito FUDS project/report index",
        SourceKind.REFERENCE_PAGE,
        "https://www.saj.usace.army.mil/Monito/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Public former bombing-range report index; no active-asset extrapolation permitted.",
    ),
    SourceSpec(
        "USACE_FORT_BROOKE_ADMIN_RECORD_2025",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Fort Brooke Administrative Record Index - July 2025",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://www.saj.usace.army.mil/Portals/44/Fort%20Brooke%20-%20Administrative%20Record%20Index%20-%20July%202025.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Document-level former-site administrative-record denominator for Fort Brooke.",
    ),
)

SOURCE_DENOMINATOR_V04: tuple[SourceSpec, ...] = tuple(
    s for s in SOURCE_DENOMINATOR_V03 if s.source_id not in _SUPERSEDED_V03
) + BOUND_V04
