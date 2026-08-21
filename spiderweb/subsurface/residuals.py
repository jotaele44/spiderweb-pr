"""Bounded public-residual adjudication for the Puerto Rico subsurface denominator.

Residual state is deliberately separate from source execution state. A
FINAL_PUBLIC_GAP means the bounded authoritative public search was exhausted and
an authority explicitly documents that a complete public denominator does not
exist (or is not publicly indexed). It is not negative evidence about the real
world and it does not by itself make a records request permissible.

v0.5 is retained as a frozen historical assessment. v0.6 is the current state
and reopens the historic-workings residual because newly recovered authoritative
documentary evidence creates executable public identity/geometry vectors.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from pathlib import Path


class ResidualState(StrEnum):
    PASS = "PASS"
    FINAL_PUBLIC_GAP = "FINAL_PUBLIC_GAP"
    OPEN = "OPEN"


@dataclass(frozen=True)
class ResidualAssessment:
    source_id: str
    family: str
    state: ResidualState
    authority_basis: tuple[str, ...]
    reason: str
    negative_evidence_permitted: bool = False


# Frozen v0.5 lineage. Do not mutate: historical tests and certification records
# depend on this exact semantic state.
V05_RESIDUAL_ASSESSMENTS: tuple[ResidualAssessment, ...] = (
    ResidualAssessment(
        "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL",
        "MINES_QUARRIES_SHAFTS",
        ResidualState.FINAL_PUBLIC_GAP,
        (
            "https://www.usgs.gov/centers/gggsc/science/usmin-abandoned-mine-lands-inventory",
            "https://www.usgs.gov/data/consolidated-prospect-and-mine-related-features-us-geological-survey-75-and-15-minute",
        ),
        "USGS states that no comprehensive national abandoned-mine-feature inventory currently exists; the consolidated HTMC mine-feature release is authoritative for mapped symbols but does not address every feature destroyed, covered, undocumented, or never mapped.",
    ),
    ResidualAssessment(
        "FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL",
        "MILITARY_HARDENED_SUBSURFACE",
        ResidualState.OPEN,
        (
            "https://www.saj.usace.army.mil/FormerlyUsedDefenseSites/",
            "https://fudsportal.usace.army.mil/",
            "https://fudsportal.usace.army.mil/Resources/Home",
        ),
        "USACE exposes additional Puerto Rico FUDS project pages and a public portal/XDocs ecosystem; property-by-property public document enumeration is therefore not terminal yet. Precise current protected-asset enumeration remains excluded.",
    ),
    ResidualAssessment(
        "NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL",
        "UTILITIES_UNDERGROUND",
        ResidualState.FINAL_PUBLIC_GAP,
        (
            "https://sige.pr.gov/server/rest/services/MIPR/Infraestructura/FeatureServer/layers",
            "https://smartislandmaps.pr.gov/download-data",
            "https://energia.pr.gov/wp-content/uploads/sites/7/2021/02/Joint-Motion-by-Luma-and-Prepa-Submitting-Corrected-Work-Plan-in-Compliance-with-PREBS-Resolution-and-Order-of-December-31-NEPR-MI-2019-0011-1.pdf",
        ),
        "Authoritative public sources expose service/technology, selected infrastructure, and public feeder products, while operator filings establish richer internal GIS. No authoritative public island-wide dataset was found that distinguishes all non-AAA/private buried electric, telecom, and sanitary line geometry from overhead/service-area data.",
    ),
    ResidualAssessment(
        "HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL",
        "HISTORICAL_CORROBORATION",
        ResidualState.OPEN,
        (
            "https://earthexplorer.usgs.gov/",
            "https://www.usgs.gov/centers/eros/science/earthexplorer-help-index",
            "https://ngmdb.usgs.gov/topoview/",
        ),
        "EarthExplorer still provides AOI-searchable aerial inventories and metadata export, so the Santiago frame/scene denominator has not yet been exhaustively materialized even though some NARA Puerto Rico series lack indexes.",
    ),
)


V06_RESIDUAL_ASSESSMENTS: tuple[ResidualAssessment, ...] = (
    ResidualAssessment(
        "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL",
        "MINES_QUARRIES_SHAFTS",
        ResidualState.OPEN,
        (
            "https://docs.pr.gov/files/OECH/Publicaciones%20y%20Recursos/Libros/La%20Carretera%20Central%20Un%20viaje%20esc%C3%A9nico%20a%20la%20historia%20de%20Puerto%20Rico.pdf",
            "https://pubs.usgs.gov/of/1998/of98-038/pdf/manuscript.pdf",
            "https://pubs.usgs.gov/of/1998/of98-038/pdf/appendices.pdf",
            "https://www.usgs.gov/centers/gggsc/science/usmin-abandoned-mine-lands-inventory",
        ),
        "Reopened in v0.6. The OECH/UPR Site 78 guide provides a named documentary manifestation of historical manganese-mine tunnels at Cantera Naranjo that is not represented by the AOI's explicit USGS Adit|Air Shaft|Mine Shaft symbol query. USGS OFR 98-038 independently documents Atlantic Ore Company manganese production in Juana Diaz and the Juana Diaz Mine. The public historical-workings corpus therefore has newly executable identity, geometry, and archival vectors and is not terminal. This does not negate the USGS statement that no comprehensive national abandoned-mine-feature inventory exists.",
    ),
    V05_RESIDUAL_ASSESSMENTS[1],
    V05_RESIDUAL_ASSESSMENTS[2],
    V05_RESIDUAL_ASSESSMENTS[3],
)


def assessment_map() -> dict[str, ResidualAssessment]:
    return {row.source_id: row for row in V06_RESIDUAL_ASSESSMENTS}


def all_residuals_terminal() -> bool:
    return all(row.state != ResidualState.OPEN for row in V06_RESIDUAL_ASSESSMENTS)


def write_residual_assessment(path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "spiderweb.subsurface.public_residual_assessment.v2",
        "lineage": {"current": "v0.6", "preserved": ["v0.5"]},
        "rows": [asdict(row) for row in V06_RESIDUAL_ASSESSMENTS],
        "all_residuals_terminal": all_residuals_terminal(),
        "rule": "FINAL_PUBLIC_GAP is public-search exhaustion, never real-world absence and never negative evidence; new authoritative evidence reopens a previously terminal residual.",
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out