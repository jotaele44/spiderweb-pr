"""Record publisher definitions and stable-key change logs without source repair."""

import csv
import io
from collections import Counter

from .usgs_source_review import _load


def review_documents(entries, root, native_features):
    """Exhaust the four declared support documents; keep null-key rows separate."""
    roles = {e["role"]: e for e in entries}
    if len(roles) != len(entries) or set(roles) != {
        "README",
        "REFERENCES",
        "POLYGON_CHANGELOG",
        "FAULT_CHANGELOG",
    }:
        raise ValueError("Support-document role denominator mismatch")
    texts = {role: _load(root, e).decode("utf-8-sig") for role, e in roles.items()}
    readme = texts["README"]
    lines = readme.splitlines()
    # These are publisher statements, not independent geometry/value certification.
    definitions = [line for line in lines if line and line[0].isdigit()]
    claims = {
        "spatial_datum": (
            "All files with spatial information (Fault Sections, Fault Polygons, "
            "and Earthquake Geology Database) use geographic coordinates in the "
            "WGS84 datum. "
        ),
        "complete_observation_text": (
            "7. Obsern: observations used to derive slip rate, paleoseismic "
            "trench, or paleoliquefaction features as reported in the Reference "
            "field. See .csv file for complete descriptions. "
        ),
        "x_definition": "27. X: latitude of site (Decimal Degrees, WGS84).",
        "y_definition": "28. Y: longitude of site (Decimal Degrees, WGS84).",
    }
    for value in claims.values():
        if value not in lines:
            raise ValueError("Publisher definition changed; review required")
    outside = [
        line for line in lines if "outside of the hazard area of interest" in line
    ]
    if len(outside) != 1:
        raise ValueError("Publisher hazard-scope statement changed")
    tables = {}
    for role, key in [("POLYGON_CHANGELOG", "PolyID"), ("FAULT_CHANGELOG", "FaultID")]:
        table = list(csv.reader(io.StringIO(texts[role]), strict=True))
        header = table[0]
        if len(header) != len(set(header)) or any(not h for h in header):
            raise ValueError("Duplicate/empty changelog field")
        if any(len(row) != len(header) for row in table[1:]):
            raise ValueError("Changelog row width mismatch")
        rows = [dict(zip(header, row)) for row in table[1:]]
        keyed = [r[key] for r in rows if r[key] != ""]
        if len(keyed) != len(set(keyed)):
            raise ValueError("Duplicate nonempty changelog stable key")
        targets = {f["properties"][key] for f in native_features[key]}
        source = set(keyed)
        tables[role] = {
            "asset_id": roles[role]["asset_id"],
            "header_raw": header,
            "row_count": len(rows),
            "keyed_rows": len(keyed),
            "null_key_rows": [r for r in rows if r[key] == ""],
            "rows_raw": rows,
            "membership": {
                "intersection": len(source & targets),
                "a_only": sorted(source - targets),
                "b_only": sorted(targets - source),
                "union": len(source | targets),
                "symmetric_difference": len(source ^ targets),
            },
            "change_types_raw": dict(Counter(r["Change Type"] for r in rows)),
        }
    # Source-specific definitions are recorded as facts; aliases remain unapproved.
    site_features = native_features["SiteID"]
    axis_evidence = [
        {
            "source_key": f["properties"]["SiteID"],
            "x_raw": f["properties"]["X"],
            "y_raw": f["properties"]["Y"],
            "geometry_raw": f["geometry"],
        }
        for f in site_features
    ]
    fault_rows = tables["FAULT_CHANGELOG"]["rows_raw"]
    fs6 = next(r for r in fault_rows if r["FaultID"] == "FS6")
    return {
        "state": "AUDIT_ONLY",
        "asset_count": len(entries),
        "published_claims_raw": claims,
        "outside_hazard_claim_raw": outside[0],
        "field_definitions_raw": definitions,
        "unit_definitions_state": "RECORDED",
        "unit_value_validation": "UNRESOLVED",
        "csv_complete_observation_text": "PUBLISHER_DIRECTED",
        "axis_definition_state": "CONTRADICTORY_WITH_VALUES_AND_GEOMETRY",
        "axis_evidence": axis_evidence,
        "schema_label_conflict": {
            "readme_raw": "RecurUn",
            "data_raw": "RecurUnc",
            "alias_state": "UNRESOLVED",
        },
        "changelogs": tables,
        "fs6_changelog_row_raw": fs6,
        "references_text_raw": texts["REFERENCES"],
        "references_scope": (
            "Bibliography preserved; cited publications not acquired by this review"
        ),
        "shapefile_scope": (
            "README mentions SHP; no SHP file descriptor in frozen release "
            "inventory. Availability unresolved."
        ),
        "canonical_authority_selection": "UNRESOLVED",
        "source_repairs": 0,
    }
