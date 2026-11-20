"""Bounded third-manifestation adjudication; agreement cannot select authority."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal
from pathlib import Path

from shapely.geometry import shape

from .usgs_document_review import review_documents
from .usgs_source_review import _attributes, _load, review_source_manifestations

NS = "{http://www.opengis.net/kml/2.2}"
GEOMETRIES = {NS + s for s in ("Point", "LineString", "Polygon", "MultiGeometry")}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _tuples(node):
    raw = node.text or ""
    values = [[Decimal(v) for v in part.split(",")] for part in raw.split()]
    if not values or len({len(v) for v in values}) != 1:
        raise ValueError("Empty or mixed-dimensional KML coordinates")
    for v in values:
        if len(v) not in (2, 3) or not all(x.is_finite() for x in v):
            raise ValueError("Unsupported KML coordinate dimensions/values")
        if not -180 <= v[0] <= 180 or not -90 <= v[1] <= 90:
            raise ValueError("KML longitude/latitude range")
    return [[float(v) for v in row] for row in values]


def _geometry(node):
    kind = node.tag.removeprefix(NS)
    if kind in ("Point", "LineString"):
        coordinates = node.findall(NS + "coordinates")
        if len(coordinates) != 1:
            raise ValueError("KML coordinate element cardinality")
        rows = _tuples(coordinates[0])
        if (kind == "Point" and len(rows) != 1) or (
            kind == "LineString" and len(rows) < 2
        ):
            raise ValueError("KML geometry cardinality")
        return {"type": kind, "coordinates": rows[0] if kind == "Point" else rows}
    if kind == "Polygon":
        outer = node.findall(NS + "outerBoundaryIs")
        inner = node.findall(NS + "innerBoundaryIs")
        if len(outer) != 1:
            raise ValueError("KML exterior ring cardinality")
        rings = []
        for boundary in outer + inner:
            coordinates = boundary.findall(NS + "LinearRing/" + NS + "coordinates")
            if len(coordinates) != 1:
                raise ValueError("KML ring coordinate cardinality")
            ring = _tuples(coordinates[0])
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Unclosed KML ring; auto-repair prohibited")
            rings.append(ring)
        return {"type": "Polygon", "coordinates": rings}
    if kind == "MultiGeometry":
        children = list(node)
        if not children or any(c.tag not in GEOMETRIES for c in children):
            raise ValueError("Unsupported KML multipart child")
        parts = [_geometry(c) for c in children]
        types = {p["type"] for p in parts}
        if len(types) != 1 or next(iter(types)) not in ("Polygon", "LineString"):
            raise ValueError("Unsupported mixed/nested KML multipart")
        return {
            "type": "Multi" + next(iter(types)),
            "coordinates": [p["coordinates"] for p in parts],
        }
    raise ValueError("Unsupported KML geometry")


def _positions(coords):
    if isinstance(coords[0], (int, float)):
        yield coords
    else:
        for child in coords:
            yield from _positions(child)


def _structure(value):
    if isinstance(value[0], (int, float)):
        return len(value)
    return [_structure(child) for child in value]


def parse_kml(raw, source_key):
    """Parse this release's declared fields and native geometry without repairs."""
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("KML DTD/entity declarations prohibited")
    root = ET.fromstring(raw)
    if root.tag != NS + "kml" or root.findall(".//" + NS + "NetworkLink"):
        raise ValueError("Unsupported KML namespace or network link")
    schemas = root.findall(".//" + NS + "Schema")
    if len(schemas) != 1 or not schemas[0].get("id"):
        raise ValueError("KML schema cardinality")
    schema = schemas[0]
    fields = [dict(f.attrib) for f in schema.findall(NS + "SimpleField")]
    names = [f.get("name") for f in fields]
    if (
        not all(names)
        or len(set(names)) != len(names)
        or any(f.get("type") not in ("float", "string") for f in fields)
    ):
        raise ValueError("KML duplicate/unsupported declared field")
    types = {f["name"]: f["type"] for f in fields}
    rows = {}
    for mark in root.findall(".//" + NS + "Placemark"):
        allowed = GEOMETRIES | {
            NS + n for n in ("ExtendedData", "Style", "name", "description")
        }
        if any(c.tag not in allowed for c in mark):
            raise ValueError("Unsupported KML placemark child")
        data = mark.findall(NS + "ExtendedData/" + NS + "SchemaData")
        if len(data) != 1 or data[0].get("schemaUrl") != "#" + schema.get("id"):
            raise ValueError("KML schema binding mismatch")
        props = {}
        for field in data[0].findall(NS + "SimpleData"):
            name = field.get("name")
            if name not in names or name in props:
                raise ValueError("KML undeclared/duplicate property")
            props[name] = field.text if field.text is not None else ""
            if types[name] == "float" and props[name] != "":
                if not Decimal(props[name]).is_finite():
                    raise ValueError("Nonfinite declared KML numeric field")
        key = props.get(source_key)
        if not isinstance(key, str) or not key or key in rows:
            raise ValueError("KML empty/duplicate stable key")
        geometries = [c for c in mark if c.tag in GEOMETRIES]
        if len(geometries) != 1:
            raise ValueError("KML geometry element cardinality")
        geometry = _geometry(geometries[0])
        positions = list(_positions(geometry["coordinates"]))
        dims = Counter(len(v) for v in positions)
        obj = shape(geometry)
        if len(dims) != 1 or obj.is_empty or not obj.is_valid:
            raise ValueError("Invalid KML geometry; repair prohibited")
        rows[key] = {
            "properties_raw": props,
            "missing_declared_fields": [n for n in names if n not in props],
            "coordinate_text_raw": [
                c.text for c in mark.findall(".//" + NS + "coordinates")
            ],
            "native_geometry_tag": geometries[0].tag,
            "comparison_geometry": geometry,
            "dimensions": dict(dims),
        }
    if not rows:
        raise ValueError("Empty KML feature set")
    return {"schema_raw": dict(schema.attrib), "fields_raw": fields, "rows": rows}


def _membership(a, b):
    a, b = set(a), set(b)
    return {
        "intersection": len(a & b),
        "a_only": sorted(a - b),
        "b_only": sorted(b - a),
        "union": len(a | b),
        "symmetric_difference": len(a ^ b),
    }


def review_kml_manifestations(input_path, source_root):
    """Exhaust supplied KML assets; preserve contrary evidence and authority gaps."""
    root = Path(source_root).resolve()
    spec_raw = Path(input_path).read_bytes()
    spec = json.loads(spec_raw)
    if spec["contract"] != "prii.usgs-kml-review-input/v1":
        raise ValueError("KML review contract mismatch")
    prior_path = (root / spec["source_review_input"]).resolve()
    prior_path.relative_to(root)
    if _sha(prior_path.read_bytes()) != spec["source_review_input_sha256"]:
        raise ValueError("Prior review input binding mismatch")
    prior_spec = json.loads(prior_path.read_bytes())
    prior = review_source_manifestations(prior_path, root)
    native = json.loads((root / prior_spec["native_input_manifest"]).read_bytes())
    entries = {e["geojson_asset_id"]: e for e in spec["assets"]}
    if len(entries) != len(spec["assets"]) or set(entries) != {
        e["asset_id"] for e in native["assets"]
    }:
        raise ValueError("KML/native asset membership mismatch")
    tolerance = Decimal(spec["raw_numeric_tolerance"])
    if not tolerance.is_finite() or not 0 <= tolerance <= Decimal("1e-10"):
        raise ValueError("Excessive/nonfinite KML comparison tolerance")
    native_features = {}
    reviews = []
    for asset in native["assets"]:
        entry = entries[asset["asset_id"]]
        sid = asset["source_item_id"]
        if entry["asset_id"] != sid + ":2" or entry["csv_asset_id"] != sid + ":0":
            raise ValueError("KML paired-item binding mismatch")
        kml = parse_kml(_load(root, entry), asset["source_key"])
        krows = kml.pop("rows")
        raw = gzip.decompress((root / asset["raw_file"]).read_bytes())
        if _sha(raw) != asset["raw_sha256"]:
            raise ValueError("Native bytes changed during KML review")
        geo = json.loads(raw)
        grows = {f["properties"][asset["source_key"]]: f for f in geo["features"]}
        native_features[asset["source_key"]] = geo["features"]
        csv_entry = next(
            e for e in prior_spec["assets"] if e["asset_id"] == entry["csv_asset_id"]
        )
        table = list(
            csv.DictReader(io.StringIO(_load(root, csv_entry).decode("utf-8-sig")))
        )
        crows = {r[asset["source_key"]]: r for r in table}
        if len(crows) != len(table):
            raise ValueError("CSV stable-key join multiplication")
        csv_keys = set(crows)
        csv_coordinate_conflicts = []
        for key in sorted(csv_keys & set(krows)):
            geometry = krows[key]["comparison_geometry"]
            if geometry["type"] == "Point" and {"X", "Y"} <= set(crows[key]):
                declared = [Decimal(crows[key]["X"]), Decimal(crows[key]["Y"])]
                actual = [Decimal(str(v)) for v in geometry["coordinates"][:2]]
                differences = [abs(a - b) for a, b in zip(declared, actual)]
                if any(v > tolerance for v in differences):
                    csv_coordinate_conflicts.append(
                        {
                            "source_key": key,
                            "csv_xy_raw": [crows[key]["X"], crows[key]["Y"]],
                            "kml_coordinate_text_raw": krows[key][
                                "coordinate_text_raw"
                            ],
                            "absolute_raw_numeric_deltas": [
                                str(v) for v in differences
                            ],
                        }
                    )
        comparisons = Counter()
        deltas = []
        geometry_rows = []
        for key in sorted(set(krows) & set(grows)):
            kr, gr = krows[key], grows[key]
            fields = set(kr["properties_raw"]) | set(gr["properties"])
            for field in sorted(fields):
                if field not in kr["properties_raw"]:
                    category = (
                        "KML_MISSING_GEOJSON_NULL"
                        if gr["properties"][field] is None
                        else "KML_MISSING"
                    )
                elif field not in gr["properties"]:
                    category = "GEOJSON_MISSING"
                else:
                    category = _attributes(
                        kr["properties_raw"][field], gr["properties"][field]
                    )
                if (
                    category == "VALUE_DIFFERENCE"
                    and field in kr["properties_raw"]
                    and field in gr["properties"]
                    and isinstance(gr["properties"][field], (int, float))
                    and not isinstance(gr["properties"][field], bool)
                    and next(f["type"] for f in kml["fields_raw"] if f["name"] == field)
                    == "float"
                ):
                    numeric_delta = abs(
                        Decimal(kr["properties_raw"][field])
                        - Decimal(str(gr["properties"][field]))
                    )
                    if numeric_delta <= tolerance:
                        category = "NUMERIC_SERIALIZATION_DIFFERENCE"
                comparisons[category] += 1
                if category not in ("EXACT_TEXT", "NUMERIC_EQUIVALENT"):
                    deltas.append(
                        {
                            "source_key": key,
                            "field": field,
                            "category": category,
                            "kml_present": field in kr["properties_raw"],
                            "kml_raw": kr["properties_raw"].get(field),
                            "geojson_present": field in gr["properties"],
                            "geojson_raw": gr["properties"].get(field),
                        }
                    )
            a, b = kr["comparison_geometry"], gr["geometry"]
            apos, bpos = (
                list(_positions(a["coordinates"])),
                list(_positions(b["coordinates"])),
            )
            dimensions_equal = Counter(len(v) for v in apos) == Counter(
                len(v) for v in bpos
            )
            same_structure = a["type"] == b["type"] and _structure(
                a["coordinates"]
            ) == _structure(b["coordinates"])
            pointwise = same_structure and dimensions_equal
            differences = []
            if pointwise:
                differences = [
                    abs(Decimal(str(x)) - Decimal(str(y)))
                    for av, bv in zip(apos, bpos)
                    for x, y in zip(av, bv)
                ]
            maximum = max(differences) if differences else None
            sa, sb = shape(a), shape(b)
            geometry_rows.append(
                {
                    "source_key": key,
                    "native_kml": kr,
                    "native_geojson_type": b["type"],
                    "dimensions_and_vertex_count_equal": dimensions_equal,
                    "comparison_type_equal": a["type"] == b["type"],
                    "exact_comparison_object": json.dumps(a, sort_keys=True)
                    == json.dumps(b, sort_keys=True),
                    "planar_topological_equal": sa.equals(sb),
                    "hausdorff_raw_coordinate_units": sa.hausdorff_distance(sb),
                    "symmetric_difference_area_raw_units_squared": (
                        sa.symmetric_difference(sb).area
                    ),
                    "max_pointwise_raw_numeric_delta": str(maximum)
                    if maximum is not None
                    else None,
                    "within_pointwise_tolerance": maximum is not None
                    and maximum <= tolerance,
                }
            )
        if any(
            not math.isfinite(row["hausdorff_raw_coordinate_units"])
            for row in geometry_rows
        ):
            raise ValueError("Nonfinite geometry comparison")
        reviews.append(
            {
                "asset_id": entry["asset_id"],
                "geojson_asset_id": asset["asset_id"],
                "raw_sha256": entry["raw_sha256"],
                "native_schema": kml,
                "source_key": asset["source_key"],
                "kml_features": len(krows),
                "geojson_features": len(grows),
                "kml_to_geojson": _membership(krows, grows),
                "csv_to_kml": _membership(csv_keys, krows),
                "csv_to_kml_coordinate_conflicts": csv_coordinate_conflicts,
                "csv_coordinate_scope": (
                    "Raw numeric comparison only; CSV CRS/axis semantics unverified"
                ),
                "property_comparisons": dict(comparisons),
                "property_differences": deltas,
                "geometry_comparisons": geometry_rows,
                "unmatched_kml_rows": [
                    krows[k] for k in sorted(set(krows) - set(grows))
                ],
                "authority_state": "UNRESOLVED",
                "source_repair_performed": False,
            }
        )
    return {
        "contract": "prii.usgs-kml-adjudication/v1",
        "state": "AUDIT_ONLY",
        "input_sha256": _sha(spec_raw),
        "prior_review_report_sha256": spec["source_review_report_sha256"],
        "asset_count": len(reviews),
        "support_documents": review_documents(
            spec["supporting_documents"], root, native_features
        ),
        "features": sum(a["kml_features"] for a in reviews),
        "scope": spec["scope"],
        "assets": reviews,
        "evidence_types": {
            "membership": "BINDING",
            "geometry": "COMPUTED",
            "authoritative_format": "UNKNOWN",
        },
        "adjudication": (
            "KML agreement is corroboration only; "
            "no majority vote or canonical selection"
        ),
        "prior_cross_format_failures": prior["cross_format_failures"],
        "scientific_staging": "BLOCKED",
        "certification": "BLOCKED",
        "activated": 0,
    }
