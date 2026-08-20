"""Third public-source exhaustion overlay.

v0.3 preserves the v0.2 denominator and adds authoritative non-sensitive
manifestations discovered while exhausting remaining public source classes.
Precise current hardened/underground military asset locations are not enumerated;
former-site records remain handled at property/report level in v0.2.
"""
from __future__ import annotations

from .sources import SourceKind, SourceSpec, SourceStatus
from .sources_exhaustion import SOURCE_DENOMINATOR_V02

OPEN_CLASS_SOURCES_V03: tuple[SourceSpec, ...] = (
    SourceSpec(
        "LUMA_UNDERGROUND_DISTRIBUTION_MANUAL_2023",
        "UTILITIES_UNDERGROUND",
        "LUMA Energy",
        "Underground Electrical Distribution System Manual v03",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://lumapr.com/wp-content/uploads/2024/08/UNDERGROUND-ELECTRICAL-DISTRIBUTION-SYSTEM-MANUAL.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes=(
            "Authoritative operator design standard confirming underground electrical "
            "distribution system classes; not an asset-level public geometry denominator."
        ),
    ),
    SourceSpec(
        "PRDRNA_UPR_PORTO_RICO_1930_GEOREF",
        "HISTORICAL_CORROBORATION",
        "Puerto Rico Department of Natural and Environmental Resources / UPR",
        "Porto Rico 1930 Georeferenced coastal aerial mosaic",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://drna.pr.gov/wp-content/uploads/2017/08/pr1930georef_tecnical-report.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
        notes=(
            "Documents 1930-1931 aerial photography as the oldest known systematic "
            "island set; 432 coastal photographs were georeferenced into 15 mosaics. "
            "Image-byte/member enumeration remains separate."
        ),
    ),
)

SOURCE_DENOMINATOR_V03: tuple[SourceSpec, ...] = (
    SOURCE_DENOMINATOR_V02 + OPEN_CLASS_SOURCES_V03
)
