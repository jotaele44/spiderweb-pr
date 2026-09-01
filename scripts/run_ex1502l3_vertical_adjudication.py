#!/usr/bin/env python3
"""Adjudicate EX1502L3 vertical-reference metadata without inferring equivalence to W00247 MLLW."""
from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE = Path("evidence/marine/ex1502l3_w00247_overlap_v0_1/EX1502L3_Multibeam.xml")
OUT = Path("evidence/marine/ex1502l3_vertical_adjudication_v0_1")


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8", errors="replace")
    unknown = bool(re.search(r'xlink:title=["\']Vertical Datum: Unknown["\']', text, flags=re.I))
    epsg5715 = bool(re.search(r'urn:ogc:def:crs:EPSG::5715', text, flags=re.I))
    msl_title = bool(re.search(r'xlink:title=["\']msl depth in meters["\']', text, flags=re.I))

    if unknown and epsg5715 and msl_title:
        state = "CONTRADICTORY_PRIMARY_METADATA"
        binding = "UNRESOLVED"
    elif epsg5715 and msl_title:
        state = "PROVISIONAL_EPSG_5715_MSL_DEPTH"
        binding = "EPSG:5715"
    else:
        state = "UNRESOLVED"
        binding = "UNRESOLVED"

    manifest = {
        "receipt_version": "0.1",
        "source": str(SOURCE),
        "signals": {
            "reference_system_title_vertical_datum_unknown": unknown,
            "vertical_extent_href_epsg_5715": epsg5715,
            "vertical_extent_title_msl_depth_in_meters": msl_title,
        },
        "adjudication_state": state,
        "bound_vertical_reference": binding,
        "w00247_vertical_reference": "EPSG:5866 / MLLW depth",
        "depth_subtraction_allowed": False,
        "reason": "The same authoritative NCEI ISO record contains an explicit 'Vertical Datum: Unknown' reference-system declaration and a vertical-extent link labeled EPSG:5715 / msl depth in meters. The contradiction must be resolved before numerical depth subtraction against W00247 MLLW.",
        "certification_boundary": "Metadata adjudication only; no datum transformation is inferred or applied.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "vertical_adjudication.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
