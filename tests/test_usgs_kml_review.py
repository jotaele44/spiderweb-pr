import gzip
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from federation.usgs_kml_review import NS, parse_kml, review_kml_manifestations

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests/fixtures/usgs_kml_review/input.json"


def test_third_manifestation_corroborates_but_cannot_select_authority():
    r = review_kml_manifestations(INPUT, ROOT)
    assert r["state"] == "AUDIT_ONLY" and r["certification"] == "BLOCKED"
    assert (r["asset_count"], r["features"], r["activated"]) == (3, 92, 0)
    docs = r["support_documents"]
    assert docs["asset_count"] == 4 and len(docs["field_definitions_raw"]) == 44
    assert docs["axis_definition_state"] == "CONTRADICTORY_WITH_VALUES_AND_GEOMETRY"
    assert docs["csv_complete_observation_text"] == "PUBLISHER_DIRECTED"
    assert docs["changelogs"]["FAULT_CHANGELOG"]["row_count"] == 36
    assert docs["changelogs"]["FAULT_CHANGELOG"]["keyed_rows"] == 35
    assert len(docs["changelogs"]["FAULT_CHANGELOG"]["null_key_rows"]) == 1
    assert (
        docs["changelogs"]["FAULT_CHANGELOG"]["null_key_rows"][0]["FaultName"]
        == "Bowin"
    )
    assert (
        docs["changelogs"]["FAULT_CHANGELOG"]["membership"]["symmetric_difference"] == 0
    )
    assert docs["changelogs"]["POLYGON_CHANGELOG"]["membership"]["intersection"] == 6
    assert docs["fs6_changelog_row_raw"]["CountryTerritory"] == "Offshore"
    sites, polygons, sections = r["assets"]
    assert sites["csv_to_kml"] == {
        "intersection": 50,
        "a_only": ["EGQ5"],
        "b_only": ["EQG5"],
        "union": 52,
        "symmetric_difference": 2,
    }
    assert len(sites["csv_to_kml_coordinate_conflicts"]) == 15
    assert [a["kml_to_geojson"]["intersection"] for a in r["assets"]] == [51, 6, 35]
    assert all(a["kml_to_geojson"]["symmetric_difference"] == 0 for a in r["assets"])
    geometry = [g for a in r["assets"] for g in a["geometry_comparisons"]]
    assert len(geometry) == 92 and all(
        g["within_pointwise_tolerance"] for g in geometry
    )
    assert sum(g["exact_comparison_object"] for g in geometry) == 36
    assert sum(g["planar_topological_equal"] for g in geometry) == 36
    assert max(float(g["max_pointwise_raw_numeric_delta"]) for g in geometry) == 5e-14
    assert sites["property_comparisons"]["NUMERIC_SERIALIZATION_DIFFERENCE"] == 71
    assert (
        sum(
            a["property_comparisons"].get("KML_MISSING_GEOJSON_NULL", 0)
            for a in r["assets"]
        )
        == 43
    )
    fs6 = next(g for g in sections["geometry_comparisons"] if g["source_key"] == "FS6")
    assert fs6["native_kml"]["properties_raw"]["CountryTer"] == "Offshore"
    assert polygons["native_schema"]["schema_raw"]["id"].endswith("_v0")
    assert all(
        a["authority_state"] == "UNRESOLVED" and not a["source_repair_performed"]
        for a in r["assets"]
    )
    assert r == review_kml_manifestations(INPUT, ROOT)


@pytest.mark.parametrize(
    "attack",
    [
        "duplicate_key",
        "duplicate_field",
        "wrong_schema",
        "nonfinite",
        "network",
        "foreign_geometry",
    ],
)
def test_malformed_kml_cannot_silently_drop_or_multiply_rows(attack):
    raw = gzip.decompress(
        (
            ROOT / "tests/fixtures/usgs_kml_review/6516c8f9d34e5f8ef156488e_2.kml.gz"
        ).read_bytes()
    )
    tree = ET.fromstring(raw)
    marks = tree.findall(".//" + NS + "Placemark")
    if attack == "duplicate_key":
        tree.find(".//" + NS + "Folder").append(marks[0])
    elif attack == "duplicate_field":
        data = marks[0].find(NS + "ExtendedData/" + NS + "SchemaData")
        data.append(data[0])
    elif attack == "wrong_schema":
        marks[0].find(NS + "ExtendedData/" + NS + "SchemaData").set(
            "schemaUrl", "#foreign"
        )
    elif attack == "nonfinite":
        marks[0].find(".//" + NS + "coordinates").text = "NaN,18"
    elif attack == "network":
        ET.SubElement(tree, NS + "NetworkLink")
    else:
        ET.SubElement(marks[0], "{http://www.google.com/kml/ext/2.2}Track")
    with pytest.raises(ValueError):
        parse_kml(ET.tostring(tree), "SiteID")


def test_unclosed_ring_is_not_silently_repaired():
    raw = gzip.decompress(
        (
            ROOT / "tests/fixtures/usgs_kml_review/6516caf3d34e5f8ef1564898_2.kml.gz"
        ).read_bytes()
    )
    tree = ET.fromstring(raw)
    coords = tree.find(".//" + NS + "coordinates")
    coords.text = " ".join(coords.text.split()[:-1])
    with pytest.raises(ValueError, match="auto-repair"):
        parse_kml(ET.tostring(tree), "PolyID")
    with pytest.raises(ValueError, match="DTD"):
        parse_kml(b'<!DOCTYPE kml [<!ENTITY x "x">]><kml/>', "PolyID")


def test_rehashed_third_format_geometry_change_remains_a_conflict(tmp_path):
    for folder in ("usgs_native", "usgs_source_review", "usgs_kml_review"):
        shutil.copytree(
            ROOT / "tests/fixtures" / folder, tmp_path / "tests/fixtures" / folder
        )
    path = tmp_path / "tests/fixtures/usgs_kml_review/input.json"
    spec = json.loads(path.read_text())
    entry = spec["assets"][0]
    source = tmp_path / entry["path"]
    raw = gzip.decompress(source.read_bytes()).replace(
        b"-67.14162404,18.00133574", b"-67.14162404,18.10133574", 1
    )
    packed = gzip.compress(raw, mtime=0)
    source.write_bytes(packed)
    entry["packed_sha256"] = hashlib.sha256(packed).hexdigest()
    entry["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    entry["descriptor"]["size"] = len(raw)
    entry["descriptor"]["checksum"]["value"] = hashlib.md5(raw).hexdigest()
    path.write_text(json.dumps(spec))
    r = review_kml_manifestations(path, tmp_path)
    point = next(
        g for g in r["assets"][0]["geometry_comparisons"] if g["source_key"] == "EQG1"
    )
    assert (
        not point["within_pointwise_tolerance"]
        and not point["planar_topological_equal"]
    )
    assert r["activated"] == 0 and r["certification"] == "BLOCKED"
    spec["raw_numeric_tolerance"] = "100"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="tolerance"):
        review_kml_manifestations(path, tmp_path)
