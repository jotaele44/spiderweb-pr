"""Public-source exhaustion overlay for unresolved subsurface classes.

This module preserves DEFAULT_SOURCES as the v0.1 snapshot and derives a v0.2
execution denominator by superseding only placeholder rows whose public source
class has been materially narrowed.  Supersession is denominator governance, not
identity promotion: source manifestations remain independent rows.
"""
from __future__ import annotations

from .sources import DEFAULT_SOURCES, SourceKind, SourceSpec, SourceStatus

USGS_MINES_FS = "https://energy.usgs.gov/arcgis/rest/services/Hosted/USMin_Symbols/FeatureServer"

# Placeholder rows replaced by narrower, evidence-backed residue definitions.
_SUPERSEDED = frozenset({
    "MINES_SHAFTS_EXACT_GEOMETRY",
    "MILITARY_SUBSURFACE_DENOMINATOR",
    "UNDERGROUND_NON_AAA_UTILITY_DENOMINATOR",
    "HISTORICAL_AERIAL_MAP_DENOMINATOR",
})

OPEN_CLASS_SOURCES: tuple[SourceSpec, ...] = (
    # Historic shafts/adits: authoritative map-derived point geometry exists.
    SourceSpec(
        "USGS_USMIN_MINE_SYMBOLS_0",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "USGS mine/prospect-related symbols from historical topographic maps v10",
        SourceKind.ARCGIS_LAYER,
        USGS_MINES_FS,
        SourceStatus.VERIFIED_QUERYABLE,
        layer_id=0,
        stable_id_fields=("OBJECTID",),
        evidence_role="DIRECT",
        notes=(
            "Authoritative locations of mapped mine/prospect symbols, including adits, "
            "digitized from HTMC maps; a mapped symbol does not prove current accessibility, "
            "condition, or a complete universe of every historic underground working."
        ),
    ),
    SourceSpec(
        "USGS_PR_MINERAL_ASSESSMENT_OFR_98_038",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "Puerto Rico geology/mineral occurrence assessment and complete MRDS appendix",
        SourceKind.REFERENCE_PAGE,
        "https://pubs.usgs.gov/of/1998/of98-038/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Appendix E contains complete Puerto Rico MRDS occurrence data for the release; exact member-byte denominator remains to be frozen.",
    ),
    SourceSpec(
        "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL",
        "MINES_QUARRIES_SHAFTS",
        "UNRESOLVED",
        "Historic shafts/adits not represented by USGS mine symbols or bound MRDS manifestations",
        SourceKind.PLACEHOLDER,
        "",
        SourceStatus.OPEN,
        evidence_role="DIRECT",
        notes="Prevents USGS map-symbol coverage from being promoted to universal historic-workings completeness.",
    ),

    # Former military sites: FUDS inventory/reports can corroborate former-site history.
    # Exact active-installation hardened assets are deliberately not inferred from these.
    SourceSpec(
        "USACE_FUDS_PR_INVENTORY",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Puerto Rico Formerly Used Defense Sites inventory",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://www.usace.army.mil/Portals/2/docs/Environmental/FUDS/FUDS_Inventory/FUDS_Inventory_PuertoRico.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="CANDIDATE",
        notes="Authoritative former-property/project denominator; categories and property identity do not prove subsurface structures.",
    ),
    SourceSpec(
        "USACE_CULEBRA_SUPPLEMENTAL_ASR_2005",
        "MILITARY_HARDENED_SUBSURFACE",
        "U.S. Army Corps of Engineers",
        "Culebra Supplemental Archives Search Report",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://www.saj.usace.army.mil/Portals/44/docs/FUDS/Culebra_Supplemental_%20ASR_2005.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Includes historical sketches, maps and aerial photography for a former defense property; not a Puerto Rico-wide hardened-asset register.",
    ),
    SourceSpec(
        "FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL",
        "MILITARY_HARDENED_SUBSURFACE",
        "UNRESOLVED",
        "Puerto Rico FUDS/Navy/Army public report corpus with structure-level historical plans",
        SourceKind.PLACEHOLDER,
        "",
        SourceStatus.OPEN,
        evidence_role="SUPPORTING",
        notes="Requires property-by-property public-report enumeration before bounded former-site structure completeness can certify.",
    ),
    SourceSpec(
        "ACTIVE_MILITARY_HARDENED_ASSET_CLASS",
        "MILITARY_HARDENED_SUBSURFACE",
        "OUT_OF_SCOPE_FOR_PRECISE_ENUMERATION",
        "Active-installation hardened/underground asset locations",
        SourceKind.PLACEHOLDER,
        "",
        SourceStatus.OPEN,
        required=False,
        evidence_role="CANDIDATE",
        notes="Not used for precise public-source enumeration; FUDS/former-site evidence cannot be generalized to active installations.",
    ),

    # Underground utilities: additional public manifestations are useful, but none
    # establishes a complete non-AAA/private buried-network universe.
    SourceSpec(
        "PRASA_SERVICE_LINE_INFORMATION_MAP",
        "UTILITIES_UNDERGROUND",
        "Puerto Rico Aqueduct and Sewer Authority",
        "PRASA Service Line Information public application",
        SourceKind.REFERENCE_PAGE,
        "https://gis.acueductospr.com/prasagis/apps/experiencebuilder/experience?id=b3ada73fbec746189f5cb8bf6432fe02",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Authoritative best-available service-line information; not a downloadable island-wide non-AAA/private utility denominator.",
    ),
    SourceSpec(
        "PRPB_INFRASTRUCTURE_TELECOM_27",
        "UTILITIES_UNDERGROUND",
        "Puerto Rico Planning Board",
        "MIPR Infraestructura - Telecomunicaciones group",
        SourceKind.REFERENCE_PAGE,
        "https://sige.pr.gov/server/rest/services/MIPR/Infraestructura/FeatureServer/layers",
        SourceStatus.DISCOVERY_ONLY,
        evidence_role="CANDIDATE",
        notes="Public telecom infrastructure context; visible layer taxonomy does not establish buried conduit/cable geometry.",
    ),
    SourceSpec(
        "NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL",
        "UTILITIES_UNDERGROUND",
        "UNRESOLVED",
        "Public non-AAA/private buried utility network denominator",
        SourceKind.PLACEHOLDER,
        "",
        SourceStatus.OPEN,
        evidence_role="DIRECT",
        notes="No authoritative public island-wide line dataset found that distinguishes buried electric/telecom/private sanitary networks from overhead or service-area data.",
    ),

    # Historical maps/aerials: enumerate authoritative collection-level sources and
    # retain a residue for collection/index temporal closure.
    SourceSpec(
        "USGS_EROS_AERIAL_SINGLE_FRAMES_PR",
        "HISTORICAL_CORROBORATION",
        "U.S. Geological Survey",
        "EROS Aerial Photography Single Frame Records",
        SourceKind.REFERENCE_PAGE,
        "https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-aerial-photo-single-frames",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Puerto Rico coverage is explicitly included; collection spans federal producers and 1937-2014-era holdings depending on producer. EarthExplorer scene/index denominator remains to be materialized for the AOI.",
    ),
    SourceSpec(
        "USGS_HTMC_TOPOVIEW_PR",
        "HISTORICAL_CORROBORATION",
        "U.S. Geological Survey",
        "Historical Topographic Map Collection / topoView",
        SourceKind.REFERENCE_PAGE,
        "https://ngmdb.usgs.gov/topoview/",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="HTMC includes all scanned editions held/discovered by USGS; Puerto Rico/USVI legacy mapping commonly uses 1:20,000 scale. Exact AOI map-cell/edition denominator remains to be enumerated.",
    ),
    SourceSpec(
        "USDA_NRCS_PR_USVI_2009_2010_ORTHO",
        "HISTORICAL_CORROBORATION",
        "USDA Natural Resources Conservation Service",
        "Puerto Rico/USVI 30 cm orthographic imagery 2009-2010",
        SourceKind.REFERENCE_PAGE,
        "https://apps.geo.fpac.usda.gov/nrcs-imagery/rest/services/ortho_imagery/puerto_rico_usvi_2010_to_2012_30cm/ImageServer",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Authoritative orthographic imagery created from imagery acquired October 2009-November 2010; ImageServer/tile manifestation must be snapshotted separately.",
    ),
    SourceSpec(
        "NOAA_DIGITAL_COAST_PR_NAIP_2021_2023",
        "HISTORICAL_CORROBORATION",
        "NOAA Digital Coast / USDA NAIP",
        "Puerto Rico and USVI NAIP 2021-2023 distribution",
        SourceKind.REFERENCE_PAGE,
        "https://coastalimagery.blob.core.windows.net/digitalcoast/PR_NAIP_2021_9825/index.html",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Public file index includes tile-index and metadata manifestations; exact AOI tile subset must be frozen when used.",
    ),
    SourceSpec(
        "NARA_RG23_PR_AERIAL_1954_1970",
        "HISTORICAL_CORROBORATION",
        "National Archives and Records Administration",
        "RG 23 Puerto Rico bridging aerial photographs for chart updates",
        SourceKind.REFERENCE_PAGE,
        "https://www.archives.gov/research/cartographic/aerial-photography/rg-23-uscgs-aerial-photography-non-sl",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Puerto Rico photographs exist for 1954-1970 but NARA states there are no indexes; accompanying reports provide coverage information.",
    ),
    SourceSpec(
        "NARA_RG71_NAVAL_PR_AERIAL_1941_1953",
        "HISTORICAL_CORROBORATION",
        "National Archives and Records Administration",
        "RG 71 aerial photographs of naval facilities and public works",
        SourceKind.REFERENCE_PAGE,
        "https://www.archives.gov/research/cartographic/aerial-photography/still-pictures-rg71-aerial-photography",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes="Includes Puerto Rico naval-facility aerials; finding-aid/series-level enumeration remains separate from image identity.",
    ),
    SourceSpec(
        "HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL",
        "HISTORICAL_CORROBORATION",
        "UNRESOLVED",
        "AOI-specific public historical aerial/map collection and temporal-coverage closure",
        SourceKind.PLACEHOLDER,
        "",
        SourceStatus.OPEN,
        evidence_role="SUPPORTING",
        notes="Collection universe is substantially bounded, but scene/frame/map-edition coverage must be enumerated before claiming temporal completeness for an AOI.",
    ),
)

SOURCE_DENOMINATOR_V02: tuple[SourceSpec, ...] = tuple(
    source for source in DEFAULT_SOURCES if source.source_id not in _SUPERSEDED
) + OPEN_CLASS_SOURCES

SUPERSESSION_MAP = {
    "MINES_SHAFTS_EXACT_GEOMETRY": (
        "USGS_USMIN_MINE_SYMBOLS_0",
        "USGS_PR_MINERAL_ASSESSMENT_OFR_98_038",
        "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL",
    ),
    "MILITARY_SUBSURFACE_DENOMINATOR": (
        "USACE_FUDS_PR_INVENTORY",
        "USACE_CULEBRA_SUPPLEMENTAL_ASR_2005",
        "FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL",
        "ACTIVE_MILITARY_HARDENED_ASSET_CLASS",
    ),
    "UNDERGROUND_NON_AAA_UTILITY_DENOMINATOR": (
        "PRASA_SERVICE_LINE_INFORMATION_MAP",
        "PRPB_INFRASTRUCTURE_TELECOM_27",
        "NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL",
    ),
    "HISTORICAL_AERIAL_MAP_DENOMINATOR": (
        "USGS_EROS_AERIAL_SINGLE_FRAMES_PR",
        "USGS_HTMC_TOPOVIEW_PR",
        "USDA_NRCS_PR_USVI_2009_2010_ORTHO",
        "NOAA_DIGITAL_COAST_PR_NAIP_2021_2023",
        "NARA_RG23_PR_AERIAL_1954_1970",
        "NARA_RG71_NAVAL_PR_AERIAL_1941_1953",
        "HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL",
    ),
}
