"""Sixth bounded public-source exhaustion overlay.

v0.6 preserves v0.5 and adds source manifestations surfaced by the Cantera
Naranjo / Juana Diaz manganese-workings reconstruction.  These rows are
provenance manifestations, not automatic proof that every named quarry, mine,
cave, facility point, or historical working is the same real-world entity.
"""
from __future__ import annotations

from .sources import SourceKind, SourceSpec, SourceStatus
from .sources_exhaustion_v05 import SOURCE_DENOMINATOR_V05

BOUND_V06: tuple[SourceSpec, ...] = (
    SourceSpec(
        "OECH_CARRETERA_CENTRAL_CANTERA_NARANJO_1996",
        "MINES_QUARRIES_SHAFTS",
        "Puerto Rico State Historic Preservation Office / UPR Mayaguez",
        "La Carretera Central: un viaje escenico a la historia de Puerto Rico - Site 78 Cantera Naranjo",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://docs.pr.gov/files/OECH/Publicaciones%20y%20Recursos/Libros/La%20Carretera%20Central%20Un%20viaje%20esc%C3%A9nico%20a%20la%20historia%20de%20Puerto%20Rico.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes=(
            "Site 78 is a named historical documentary manifestation west of Juana Diaz on PR-551 Km 4. "
            "It describes a marble quarry containing tunnels of an early-1900s manganese mine worked by a U.S. company, "
            "states most tunnels were destroyed by later quarrying, and mentions a surviving small stone mine-office building. "
            "It does not provide exact tunnel geometry and does not by itself bind the historical site to any modern quarry or cave."
        ),
    ),
    SourceSpec(
        "USGS_OFR98_038_MANUSCRIPT_MANGANESE",
        "MINES_QUARRIES_SHAFTS",
        "U.S. Geological Survey",
        "USGS OFR 98-038 manuscript - Puerto Rico manganese deposits",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://pubs.usgs.gov/of/1998/of98-038/pdf/manuscript.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes=(
            "Independent authoritative historical-mineral source. It reports Atlantic Ore Company production beginning in 1915 "
            "in the Tijeras/Guayabal area and identifies the Juana Diaz Mine as active 1915-1939. "
            "Operator/date agreement is corroboration; exact equality with OECH Site 78 remains an identity question."
        ),
    ),
    SourceSpec(
        "PRPB_KARST_EXTRACTION_AREAS_ANNEX",
        "MINES_QUARRIES_SHAFTS",
        "Puerto Rico Planning Board",
        "Karst special-planning-area annex - extraction-area inventory",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://gis.jp.pr.gov/Externo_Econ/Otras%20Areas%20-%20Vistas%20Publicas/Anejos%20Plan%20y%20Reglamento%20Area%20de%20Planificacion%20Especial%20del%20Carso.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes=(
            "Official planning inventory distinguishes Productos de Cantera on PR-551 around Km 4.6 from a Cantera Naranjo "
            "manifestation around Km 2.7. This is strong evidence against name-only identity collapse."
        ),
    ),
    SourceSpec(
        "PR_DPW_MINERAL_RESOURCES_JUANA_DIAZ_1935",
        "MINES_QUARRIES_SHAFTS",
        "Puerto Rico Department of Public Works - historical periodical manifestation",
        "Revista de Obras Publicas de Puerto Rico - Juana Diaz manganese / Atlantic Ore Company",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://upload.wikimedia.org/wikipedia/commons/d/d4/Revista_de_Obras_P%C3%BAblicas_de_Puerto_Rico_%28IA_acd4789.0012.001.umich.edu%29.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes=(
            "Digitized manifestation of the Puerto Rico public-works periodical describing Atlantic Ore Company operations, "
            "mine/mill improvements, projected 1935 shipments, and subsurface exploration questions at the Juana Diaz manganese deposits. "
            "The mirror is not treated as a modern agency endpoint; provenance must preserve the historical publication identity."
        ),
    ),
)

SOURCE_DENOMINATOR_V06: tuple[SourceSpec, ...] = SOURCE_DENOMINATOR_V05 + BOUND_V06
