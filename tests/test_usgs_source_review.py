import json
from pathlib import Path

import pytest

from federation.usgs_source_review import review_source_manifestations

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests/fixtures/usgs_source_review/input.json"


def test_frozen_manifestations_fail_closed_despite_valid_bytes_and_equal_counts():
    r = review_source_manifestations(INPUT, ROOT)
    assert r["state"] == "FAIL" and r["staging_eligibility"] == "BLOCKED"
    assert r["constraints"]["state"] == "PASS"
    assert r["constraints"]["raw"] == {"accconst": ["none"], "useconst": ["none"]}
    assert r["native_geometry_format_pass"] == 3
    assert (
        r["asset_count"],
        r["native_feature_count"],
        r["supporting_file_count"],
    ) == (3, 92, 4)
    assert r["cross_format_failures"] == 3 and r["extent_failures"] == 2
    sites, polygons, sections = r["assets"]
    assert sites["csv_rows"] == sites["geojson_features"] == 51
    assert sites["membership"] == {
        "intersection": 50,
        "a_only": ["EGQ5"],
        "b_only": ["EQG5"],
        "union": 52,
        "symmetric_difference": 2,
    }
    assert len(sites["coordinate_conflicts"]) == 15
    assert sites["declared_bbox_feature_states"] == {"FULLY_WITHIN": 46, "OUTSIDE": 5}
    assert (
        polygons["membership"]["symmetric_difference"]
        == sections["membership"]["symmetric_difference"]
        == 0
    )
    assert polygons["attribute_comparisons"]["WHITESPACE_DIFFERENCE"] == 1
    assert any(
        d["source_key"] == "FS6"
        and d["csv_field"] == "CountryTer"
        and d["csv_raw"] == "HIS"
        and d["geojson_raw"] == "Offshore"
        for d in sections["attribute_differences"]
    )
    assert sections["declared_bbox_feature_states"] == {
        "FULLY_WITHIN": 33,
        "PARTIAL": 2,
    }
    assert not r["identity_repair_performed"] and not r["geometry_repair_performed"]
    assert all(a["pr_jurisdiction_state"] == "UNRESOLVED" for a in r["assets"])
    assert all(
        a["native_geometry_format_state"] == "PASS"
        and not a["raw_geometry_transformed"]
        for a in r["assets"]
    )
    assert all(a["cross_format_state"] == "FAIL" for a in r["assets"])
    assert (
        r["production_export_state"] == r["activation_state"] == "BLOCKED"
        and r["activated"] == 0
    )


def test_repeatable_review_keeps_all_raw_whitespace_nulls_and_truncated_text():
    a = review_source_manifestations(INPUT, ROOT)
    b = review_source_manifestations(INPUT, ROOT)
    assert a == b
    sites = a["assets"][0]
    blank = next(
        d
        for d in sites["attribute_differences"]
        if d["category"] == "BLANK_NA_DIFFERENCE"
    )
    assert blank["csv_raw"] == "" and blank["geojson_raw"] == "N/A"
    prefix = next(
        d
        for d in sites["attribute_differences"]
        if d["category"] == "PREFIX_SHORTENING"
    )
    assert prefix["csv_raw"].startswith(prefix["geojson_raw"])
    assert len(prefix["csv_raw"]) > len(prefix["geojson_raw"])
    white = a["assets"][1]["attribute_differences"]
    assert any(
        d["csv_raw"] == "SW Puerto Rico " and d["geojson_raw"] == "SW Puerto Rico"
        for d in white
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "source_hash",
        "native_binding",
        "duplicate_support",
        "foreign_release",
        "tolerance",
    ],
)
def test_false_bindings_and_tolerance_inflation_are_rejected(tmp_path, mutation):
    spec = json.loads(INPUT.read_text())
    if mutation == "source_hash":
        spec["assets"][0]["raw_sha256"] = "0" * 64
    elif mutation == "native_binding":
        spec["native_input_sha256"] = "0" * 64
    elif mutation == "duplicate_support":
        spec["assets"].append(spec["assets"][0])
    elif mutation == "foreign_release":
        spec["root_release_id"] = "0" * 24
    elif mutation == "tolerance":
        spec["raw_numeric_serialization_tolerance"] = "1"
    path = tmp_path / "review.json"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError):
        review_source_manifestations(path, ROOT)
