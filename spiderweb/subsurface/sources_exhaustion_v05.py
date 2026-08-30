"""Fifth bounded public-source exhaustion overlay.

v0.5 preserves the v0.4 live denominator and adds authoritative manifestations
found while closing the four remaining public-source classes.  New rows are
additive: they do not erase v0.4 receipts and they do not convert a documented
public-data gap into negative evidence.
"""
from __future__ import annotations

from .sources import SourceKind, SourceSpec, SourceStatus
from .sources_exhaustion_v04 import SOURCE_DENOMINATOR_V04

FUDS_PORTAL = "https://fudsportal.usace.army.mil"
PRPB_INFRA = "https://sige.pr.gov/server/rest/services/MIPR/Infraestructura/FeatureServer"

BOUND_V05: tuple[SourceSpec, ...] = (
    SourceSpec(
        "USGS_ABANDONED_MINE_INVENTORY_STATUS_2026",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "USMIN Abandoned Mine Lands Inventory status",
        SourceKind.REFERENCE_PAGE,
        "https://www.usgs.gov/centers/gggsc/science/usmin-abandoned-mine-lands-inventory",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="USGS explicitly states that a comprehensive national abandoned-mine-feature inventory does not yet exist; this is denominator-status evidence, not a mine-location layer.",
    ),
    SourceSpec(
        "USGS_CONSOLIDATED_MINE_RELEASE_2025",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "Consolidated prospect- and mine-related features data release",
        SourceKind.REFERENCE_PAGE,
        "https://www.usgs.gov/data/consolidated-prospect-and-mine-related-features-us-geological-survey-75-and-15-minute",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Authoritative release-level scope/limitation manifestation for the v0.4 queryable layers.",
    ),
    SourceSpec(
        "USACE_FUDS_PORTAL_PUBLIC_HOME",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "FUDS Portal public home",
        SourceKind.REFERENCE_PAGE,
        FUDS_PORTAL + "/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="CANDIDATE",
        notes="Official portal identifies EMS, GIS, XDocs, and Resources as distinct FUDS information systems. No current protected-asset inference is permitted.",
    ),
    SourceSpec(
        "USACE_FUDS_PORTAL_PUBLIC_RESOURCES",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "FUDS Portal public resources",
        SourceKind.REFERENCE_PAGE,
        FUDS_PORTAL + "/Resources/Home",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="CANDIDATE",
        notes="Official public-files/public-links resource surface; it does not establish property-level document completeness by itself.",
    ),
    SourceSpec(
        "USACE_FUDS_RAMEY_REPORT_INDEX",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Ramey Air Force Base FUDS project/report index",
        SourceKind.REFERENCE_PAGE,
        "https://www.saj.usace.army.mil/Ramey/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Public former-site report index. Former-site environmental records cannot be promoted to current protected-asset identity.",
    ),
    SourceSpec(
        "PRPB_BROADBAND_CABLE_TAKEOFF_23",
        "UTILITIES_UNDERGROUND",
        "Puerto Rico Planning Board",
        "MIPR Infraestructura - Cable Take off",
        SourceKind.ARCGIS_LAYER,
        PRPB_INFRA,
        SourceStatus.DISCOVERY_ONLY,
        layer_id=23,
        stable_id_fields=("OBJECTID",),
        evidence_role="CANDIDATE",
        notes="Broadband line/service manifestation with transmission technology. It is not a certified buried-conduit route and cannot close the private buried-network class.",
    ),
    SourceSpec(
        "USGS_EARTHEXPLORER_AERIAL_DICTIONARY",
        "HISTORICAL_CORROBORATION",
        "U.S. Geological Survey",
        "Aerial Photo Single Frames data dictionary",
        SourceKind.REFERENCE_PAGE,
        "https://www.usgs.gov/centers/eros/science/aerial-photo-single-frames-data-dictionary",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Defines frame-level metadata fields needed for deterministic AOI scene/frame enumeration.",
    ),
    SourceSpec(
        "USGS_EARTHEXPLORER_SEARCH_SURFACE",
        "HISTORICAL_CORROBORATION",
        "U.S. Geological Survey",
        "EarthExplorer aerial inventory search/export surface",
        SourceKind.REFERENCE_PAGE,
        "https://earthexplorer.usgs.gov/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Authoritative AOI-searchable inventory surface; frame/scene enumeration remains OPEN until Santiago metadata export is materialized.",
    ),
    SourceSpec(
        "USGS_TOPOVIEW_INVENTORY_SURFACE",
        "HISTORICAL_CORROBORATION",
        "U.S. Geological Survey",
        "topoView HTMC/US Topo inventory/download surface",
        SourceKind.REFERENCE_PAGE,
        "https://ngmdb.usgs.gov/topoview/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Publishes map record metadata and downloadable product formats; complements the v0.4 queryable footprint manifestation.",
    ),
)

SOURCE_DENOMINATOR_V05: tuple[SourceSpec, ...] = SOURCE_DENOMINATOR_V04 + BOUND_V05
