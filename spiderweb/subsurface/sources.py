"""Frozen public-source denominator for Puerto Rico subsurface relevance.

A SourceSpec is a source manifestation, not a canonical real-world entity. Multiple
specs may overlap and remain separate until independently resolved. `required=True`
means a family cannot certify while that manifestation is unresolved.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json
from typing import Iterable
from .dispatcher import LAYER_FAMILIES

class SourceKind(StrEnum):
    ARCGIS_LAYER = "ARCGIS_LAYER"
    OGC_FEATURES = "OGC_FEATURES"
    REFERENCE_DOWNLOAD = "REFERENCE_DOWNLOAD"
    REFERENCE_PAGE = "REFERENCE_PAGE"
    PLACEHOLDER = "PLACEHOLDER"

class SourceStatus(StrEnum):
    VERIFIED_QUERYABLE = "VERIFIED_QUERYABLE"
    VERIFIED_REFERENCE = "VERIFIED_REFERENCE"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"
    OPEN = "OPEN"

@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    family: str
    authority: str
    title: str
    kind: SourceKind
    endpoint: str
    status: SourceStatus
    required: bool = True
    layer_id: int | None = None
    query: tuple[tuple[str, str], ...] = ()
    stable_id_fields: tuple[str, ...] = ()
    evidence_role: str = "SUPPORTING"
    notes: str = ""
    def __post_init__(self) -> None:
        if self.family not in LAYER_FAMILIES:
            raise ValueError(f"unknown layer family: {self.family}")
        if not self.source_id:
            raise ValueError("source_id is required")
        if self.kind == SourceKind.ARCGIS_LAYER and self.layer_id is None:
            raise ValueError("ArcGIS source requires layer_id")
    @property
    def query_dict(self) -> dict[str, str]:
        return dict(self.query)

GEOLOGY_FS = "https://sige.pr.gov/server/rest/services/MIPR/Geologia_v10_N/FeatureServer"
ECOLOGY_FS = "https://sige.pr.gov/server/rest/services/MIPR/ValorEcologico_v10_N/FeatureServer"
TENURE_FS = "https://sige.pr.gov/server/rest/services/MIPR/Tenencia/FeatureServer"
ENV_MAP = "https://sige.pr.gov/server/rest/services/MIPR/CalidadAmbiente/MapServer"
AAA_MAP = "https://sige.pr.gov/server/rest/services/MIPR/AAA_v10_N/MapServer"
FUDS_MAP = "https://geospatial.sec.usace.army.mil/server/rest/services/Military/FUDS_Data/MapServer"

DEFAULT_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec("PRPB_GEOLOGY_3", "GEOLOGY_KARST_CAVES", "Puerto Rico Planning Board", "MIPR Geologia - Geologia", SourceKind.ARCGIS_LAYER, GEOLOGY_FS, SourceStatus.VERIFIED_QUERYABLE, layer_id=3, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING"),
    SourceSpec("PRPB_SINKHOLES_4", "GEOLOGY_KARST_CAVES", "Puerto Rico Planning Board", "MIPR Geologia - Sumideros", SourceKind.ARCGIS_LAYER, GEOLOGY_FS, SourceStatus.VERIFIED_QUERYABLE, layer_id=4, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING"),
    SourceSpec("PRPB_CAVES_31", "GEOLOGY_KARST_CAVES", "Puerto Rico Planning Board", "MIPR Valor Ecologico - Cuevas", SourceKind.ARCGIS_LAYER, ECOLOGY_FS, SourceStatus.VERIFIED_QUERYABLE, layer_id=31, stable_id_fields=("OBJECTID",), evidence_role="DIRECT"),
    SourceSpec("USGS_KARST_2010", "GEOLOGY_KARST_CAVES", "U.S. Geological Survey", "Karst Map of Puerto Rico OFR 2010-1104", SourceKind.REFERENCE_PAGE, "https://pubs.usgs.gov/of/2010/1104/", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING", notes="GIS files published with report; exact archive still must be bound and hashed."),

    SourceSpec("PRPB_AQUIFER_2", "AQUIFERS_WELLS_SPRINGS", "Puerto Rico Planning Board", "MIPR Geologia - Acuifero", SourceKind.ARCGIS_LAYER, GEOLOGY_FS, SourceStatus.VERIFIED_QUERYABLE, layer_id=2, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING"),
    SourceSpec("PRPB_SPRINGS_19", "AQUIFERS_WELLS_SPRINGS", "Puerto Rico Planning Board", "MIPR Valor Ecologico - Manatiales", SourceKind.ARCGIS_LAYER, ECOLOGY_FS, SourceStatus.VERIFIED_QUERYABLE, layer_id=19, stable_id_fields=("OBJECTID",), evidence_role="DIRECT"),
    SourceSpec("PRPB_WELLS_JCA_20", "AQUIFERS_WELLS_SPRINGS", "Puerto Rico Planning Board", "MIPR Valor Ecologico - Pozos Agua Potable JCA", SourceKind.ARCGIS_LAYER, ECOLOGY_FS, SourceStatus.VERIFIED_QUERYABLE, layer_id=20, stable_id_fields=("OBJECTID", "Id_Federal"), evidence_role="DIRECT"),
    SourceSpec("PRPB_WELLS_AAA_21", "AQUIFERS_WELLS_SPRINGS", "Puerto Rico Planning Board", "MIPR Valor Ecologico - Pozo AAA", SourceKind.ARCGIS_LAYER, ECOLOGY_FS, SourceStatus.VERIFIED_QUERYABLE, layer_id=21, stable_id_fields=("OBJECTID",), evidence_role="DIRECT"),
    SourceSpec("USGS_MONITORING_LOCATIONS_PR", "AQUIFERS_WELLS_SPRINGS", "U.S. Geological Survey", "Water Data OGC monitoring locations", SourceKind.OGC_FEATURES, "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items", SourceStatus.VERIFIED_QUERYABLE, query=(("state_code", "72"),), stable_id_fields=("id", "monitoring_location_number"), evidence_role="DIRECT", notes="AOI bbox plus PR state filter; raw response is preserved before downstream well/spring typing."),

    SourceSpec("USGS_NEOTECTONIC_DATA_P13KZZAZ", "FAULTS_STRUCTURES", "U.S. Geological Survey", "Datasets documenting neotectonic mapping of Puerto Rico", SourceKind.REFERENCE_PAGE, "https://www.usgs.gov/data/datasets-documenting-neotectonic-mapping-puerto-rico", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING", notes="Authoritative machine-readable linework exists; bind exact ScienceBase item/file manifestations before terminal promotion."),
    SourceSpec("USGS_NSHM2025_PRVI_P9ONHNOD", "FAULTS_STRUCTURES", "U.S. Geological Survey", "Earthquake geology inputs for NSHM 2025 Puerto Rico and USVI", SourceKind.REFERENCE_PAGE, "https://www.usgs.gov/data/earthquake-geology-inputs-national-seismic-hazard-model-nshm-2025-puerto-rico-and-us-virgin", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING", notes="Includes fault section/polygon GIS manifestations; exact file denominator remains to be frozen."),
    SourceSpec("USGS_GSPRFZ_P18SPREU", "FAULTS_STRUCTURES", "U.S. Geological Survey", "Supporting data for Great Southern Puerto Rico fault zone", SourceKind.REFERENCE_PAGE, "https://www.usgs.gov/data/supporting-data-late-pleistocene-kinematics-great-southern-puerto-rico-fault-zone-puerto-rico", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING", notes="Includes machine-readable fault linework; exact archive/member hashes remain OPEN."),

    SourceSpec("PRPB_QUARRIES_10", "MINES_QUARRIES_SHAFTS", "Puerto Rico Planning Board", "MIPR Calidad Ambiente - Canteras", SourceKind.ARCGIS_LAYER, ENV_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=10, stable_id_fields=("OBJECTID",), evidence_role="DIRECT"),
    SourceSpec("USGS_MRDS_PR_OFR_92_244", "MINES_QUARRIES_SHAFTS", "U.S. Geological Survey", "Puerto Rico industrial mineral mines, prospects and occurrences in MRDS", SourceKind.REFERENCE_DOWNLOAD, "https://pubs.usgs.gov/of/1992/0244/report.pdf", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING", notes="Historic mine/prospect/occurrence reference; exact structured MRDS record manifestation remains to be bound."),
    SourceSpec("USGS_INDUSTRIAL_MINERALS_PR_OFR_98_038", "MINES_QUARRIES_SHAFTS", "U.S. Geological Survey", "Industrial mineral mines and occurrences appendices", SourceKind.REFERENCE_DOWNLOAD, "https://pubs.usgs.gov/of/1998/of98-038/pdf/appendices.pdf", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING", notes="Historic mine/occurrence denominator reference, not proof of current operation or shaft geometry."),
    SourceSpec("MINES_SHAFTS_EXACT_GEOMETRY", "MINES_QUARRIES_SHAFTS", "UNRESOLVED", "Historic shaft/adit exact-geometry public denominator", SourceKind.PLACEHOLDER, "", SourceStatus.OPEN, evidence_role="DIRECT"),

    SourceSpec("PRPB_GUARDIA_NACIONAL_4", "MILITARY_HARDENED_SUBSURFACE", "Puerto Rico Planning Board", "MIPR Tenencia - Guardia Nacional", SourceKind.ARCGIS_LAYER, TENURE_FS, SourceStatus.DISCOVERY_ONLY, layer_id=4, stable_id_fields=("OBJECTID",), evidence_role="CANDIDATE", notes="Land tenure is discovery context, not evidence of a subsurface facility."),
    SourceSpec("USACE_FUDS_PROJECTS_2", "MILITARY_HARDENED_SUBSURFACE", "U.S. Army Corps of Engineers", "FUDS project points", SourceKind.ARCGIS_LAYER, FUDS_MAP, SourceStatus.DISCOVERY_ONLY, layer_id=2, stable_id_fields=("OBJECTID",), evidence_role="CANDIDATE", notes="FUDS project coordinates are general reference locations and do not prove hardened/subsurface assets."),
    SourceSpec("USACE_FUDS_MRS_3", "MILITARY_HARDENED_SUBSURFACE", "U.S. Army Corps of Engineers", "FUDS Munitions Response Sites", SourceKind.ARCGIS_LAYER, FUDS_MAP, SourceStatus.DISCOVERY_ONLY, layer_id=3, stable_id_fields=("OBJECTID",), evidence_role="CANDIDATE", notes="MRS geometry is site/remediation context, not subsurface-structure identity."),
    SourceSpec("USACE_FUDS_PROPERTIES_4", "MILITARY_HARDENED_SUBSURFACE", "U.S. Army Corps of Engineers", "FUDS property polygons", SourceKind.ARCGIS_LAYER, FUDS_MAP, SourceStatus.DISCOVERY_ONLY, layer_id=4, stable_id_fields=("OBJECTID",), evidence_role="CANDIDATE", notes="Property geometry is discovery context only."),
    SourceSpec("MILITARY_SUBSURFACE_DENOMINATOR", "MILITARY_HARDENED_SUBSURFACE", "UNRESOLVED", "Authoritative public hardened/underground military asset denominator", SourceKind.PLACEHOLDER, "", SourceStatus.OPEN, evidence_role="DIRECT"),

    SourceSpec("PRPB_UST_7", "INDUSTRIAL_REMEDIATION", "Puerto Rico Planning Board", "MIPR Calidad Ambiente - Tanques de Almacenamiento Soterrado", SourceKind.ARCGIS_LAYER, ENV_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=7, stable_id_fields=("OBJECTID",), evidence_role="DIRECT"),
    SourceSpec("PRPB_RCRA_13", "INDUSTRIAL_REMEDIATION", "Puerto Rico Planning Board", "MIPR Calidad Ambiente - Facilidades RCRA", SourceKind.ARCGIS_LAYER, ENV_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=13, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING"),
    SourceSpec("PRPB_SUPERFUND_17", "INDUSTRIAL_REMEDIATION", "Puerto Rico Planning Board", "MIPR Calidad Ambiente - Superfund Sites", SourceKind.ARCGIS_LAYER, ENV_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=17, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING"),
    SourceSpec("PRPB_EPA_NPL_30", "INDUSTRIAL_REMEDIATION", "Puerto Rico Planning Board", "MIPR Calidad Ambiente - Lista Prioritaria Nacional EPA", SourceKind.ARCGIS_LAYER, ENV_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=30, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING"),
    SourceSpec("EPA_ENVIROFACTS_PR", "INDUSTRIAL_REMEDIATION", "U.S. Environmental Protection Agency", "Envirofacts / FRS / RCRAInfo / SEMS public data services", SourceKind.REFERENCE_PAGE, "https://www.epa.gov/enviro/envirofacts-data-service-api", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING", notes="Exact table/query denominator must be frozen before machine-adapter activation."),

    SourceSpec("PRPB_WASTEWATER_PUMPS_5", "UTILITIES_UNDERGROUND", "Puerto Rico Planning Board", "MIPR Calidad Ambiente - Estaciones de Bomba de Aguas Usadas", SourceKind.ARCGIS_LAYER, ENV_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=5, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING"),
    SourceSpec("PRPB_AAA_WATER_MAIN_3", "UTILITIES_UNDERGROUND", "Puerto Rico Planning Board", "MIPR AAA - Linea Matriz", SourceKind.ARCGIS_LAYER, AAA_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=3, stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING", notes="Water-main geometry is infrastructure evidence; underground placement is not assumed solely from layer class."),
    SourceSpec("PRPB_AAA_SEWER_GRAVITY_5", "UTILITIES_UNDERGROUND", "Puerto Rico Planning Board", "MIPR AAA - Linea de Gravedad", SourceKind.ARCGIS_LAYER, AAA_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=5, stable_id_fields=("OBJECTID",), evidence_role="DIRECT", notes="Authoritative sewer-line manifestation; does not prove every segment depth or condition."),
    SourceSpec("PRPB_AAA_SEWER_PUMP_6", "UTILITIES_UNDERGROUND", "Puerto Rico Planning Board", "MIPR AAA - Tuberia de Bombeo", SourceKind.ARCGIS_LAYER, AAA_MAP, SourceStatus.VERIFIED_QUERYABLE, layer_id=6, stable_id_fields=("OBJECTID",), evidence_role="DIRECT", notes="Authoritative force-main manifestation; does not prove every segment depth or condition."),
    SourceSpec("UNDERGROUND_NON_AAA_UTILITY_DENOMINATOR", "UTILITIES_UNDERGROUND", "UNRESOLVED", "Authoritative public non-AAA/private underground utility-network denominator", SourceKind.PLACEHOLDER, "", SourceStatus.OPEN, evidence_role="DIRECT"),

    SourceSpec("USGS_GEOLOGIC_MAP_CATALOG_PR", "HISTORICAL_CORROBORATION", "U.S. Geological Survey", "USGS Puerto Rico geologic map publications/catalog", SourceKind.REFERENCE_PAGE, "https://pubs.usgs.gov/atlas/geologic/", SourceStatus.VERIFIED_REFERENCE, evidence_role="SUPPORTING"),
    SourceSpec("HISTORICAL_AERIAL_MAP_DENOMINATOR", "HISTORICAL_CORROBORATION", "UNRESOLVED", "Authoritative historical aerial/map denominator and temporal coverage", SourceKind.PLACEHOLDER, "", SourceStatus.OPEN, evidence_role="SUPPORTING"),
)

def validate_source_denominator(sources: Iterable[SourceSpec] = DEFAULT_SOURCES) -> dict[str, int]:
    rows = list(sources)
    ids = [s.source_id for s in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source_id in denominator")
    counts = {family: 0 for family in LAYER_FAMILIES}
    required = {family: 0 for family in LAYER_FAMILIES}
    for source in rows:
        counts[source.family] += 1
        required[source.family] += int(source.required)
    if any(counts[family] == 0 for family in LAYER_FAMILIES):
        raise ValueError("every layer family requires at least one source specification")
    if any(required[family] == 0 for family in LAYER_FAMILIES):
        raise ValueError("every layer family requires at least one required source")
    return {**{f"{k}:sources": v for k, v in counts.items()}, "sources": len(rows)}

def denominator_sha256(sources: Iterable[SourceSpec] = DEFAULT_SOURCES) -> str:
    rows = [asdict(source) for source in sources]
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()
