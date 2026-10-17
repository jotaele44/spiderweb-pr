"""Compare frozen USGS manifestations without repairing source disagreements."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

import shapely
from shapely.geometry import GeometryCollection, box, shape

from .usgs_native_reference import build_native_streams


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _load(root, entry):
    path = (root / entry["path"]).resolve()
    path.relative_to(root)
    packed = path.read_bytes()
    if len(packed) > 8 * 1024 * 1024 or _sha(packed) != entry["packed_sha256"]:
        raise ValueError("Frozen supporting container mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as source:
        raw = source.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024 or _sha(raw) != entry["raw_sha256"]:
        raise ValueError("Frozen supporting payload mismatch")
    if "descriptor" in entry:
        d = entry["descriptor"]
        c = d["checksum"]
        algorithm = c["type"].lower().replace("-", "")
        if algorithm not in ("md5", "sha1", "sha256", "sha512"):
            raise ValueError("Unsupported source checksum")
        if (
            len(raw) != d["size"]
            or hashlib.new(algorithm, raw).hexdigest() != c["value"]
        ):
            raise ValueError("Supporting source checksum disagreement")
    return raw


def _state(geometry, domain):
    if geometry.is_empty:
        return "NULL_EMPTY"
    if geometry.disjoint(domain):
        return "OUTSIDE"
    if geometry.touches(domain):
        return "TOUCH_ONLY"
    if domain.covers(geometry):
        return "FULLY_WITHIN"
    return "PARTIAL"


def _coordinates(value):
    if not isinstance(value, list) or not value:
        raise ValueError("Empty or malformed coordinates")
    if isinstance(value[0], (int, float)) and not isinstance(value[0], bool):
        yield value
    else:
        for part in value:
            yield from _coordinates(part)


def _attributes(csv_value, geo_value):
    if isinstance(geo_value, (int, float)) and not isinstance(geo_value, bool):
        try:
            if Decimal(csv_value) == Decimal(str(geo_value)):
                return "NUMERIC_EQUIVALENT"
        except InvalidOperation:
            pass
    if isinstance(geo_value, str) and csv_value == geo_value:
        return "EXACT_TEXT"
    if csv_value == "" and geo_value is None:
        return "BLANK_NULL_DIFFERENCE"
    if csv_value == "" and geo_value == "N/A":
        return "BLANK_NA_DIFFERENCE"
    if isinstance(geo_value, str) and csv_value.strip() == geo_value.strip():
        return "WHITESPACE_DIFFERENCE"
    if isinstance(geo_value, str) and geo_value and csv_value.startswith(geo_value):
        return "PREFIX_SHORTENING"
    return "VALUE_DIFFERENCE"


def review_source_manifestations(review_input, source_root):
    """Audit all paired rows; a successful audit can report failing source gates."""
    root = Path(source_root).resolve()
    raw_spec = Path(review_input).read_bytes()
    spec = json.loads(raw_spec)
    if spec.get("contract") != "prii.usgs-source-review-input/v1":
        raise ValueError("Unknown source review contract")
    native_path = (root / spec["native_input_manifest"]).resolve()
    native_path.relative_to(root)
    if _sha(native_path.read_bytes()) != spec["native_input_sha256"]:
        raise ValueError("Native input binding mismatch")
    build_native_streams(
        native_path, root
    )  # Byte/ID/feature checks, no export mutation.
    native_spec = json.loads(native_path.read_bytes())
    release = json.loads(_load(root, spec["release_metadata"]))
    if release["id"] != spec["root_release_id"]:
        raise ValueError("Release identity mismatch")
    supporting = {a["asset_id"]: a for a in spec["assets"]}
    if len(supporting) != len(spec["assets"]):
        raise ValueError("Duplicate supporting asset")
    fgdc_assets = [a for a in supporting.values() if a["role"] == "FGDC"]
    if (
        len(fgdc_assets) != 1
        or fgdc_assets[0]["asset_id"].rsplit(":", 1)[0] != release["id"]
    ):
        raise ValueError("FGDC/release binding mismatch")
    xml_raw = _load(root, fgdc_assets[0])
    if b"<!DOCTYPE" in xml_raw.upper() or b"<!ENTITY" in xml_raw.upper():
        raise ValueError("DTD/entity declarations unsupported")
    metadata = ET.fromstring(xml_raw)
    constraints = {
        tag: [n.text for n in metadata.iter(tag)] for tag in ("accconst", "useconst")
    }
    constraint_state = (
        "PASS"
        if constraints == {"accconst": ["none"], "useconst": ["none"]}
        else "OPEN"
    )
    bounds = [
        float(metadata.findtext(".//" + tag))
        for tag in ("westbc", "southbc", "eastbc", "northbc")
    ]
    if not all(math.isfinite(v) for v in bounds) or not (
        bounds[0] < bounds[2] and bounds[1] < bounds[3]
    ):
        raise ValueError("Invalid publisher bounding box")
    domain = box(*bounds)
    tolerance = Decimal(spec["raw_numeric_serialization_tolerance"])
    if not Decimal("0") <= tolerance <= Decimal("0.0000000001"):
        raise ValueError("Excessive coordinate serialization tolerance")
    reviews = []
    for asset in native_spec["assets"]:
        if asset["root_release_ids"] != [release["id"]]:
            raise ValueError("Foreign release membership")
        path = (root / asset["raw_file"]).resolve()
        path.relative_to(root)
        raw = gzip.decompress(path.read_bytes())
        if _sha(raw) != asset["raw_sha256"]:
            raise ValueError("Native payload changed during review")
        native = json.loads(raw)
        features = native["features"]
        csv_entry = supporting[asset["source_item_id"] + ":0"]
        if csv_entry["role"] != "CSV":
            raise ValueError("Expected paired CSV")
        csv_raw = _load(root, csv_entry)
        table = list(csv.reader(io.StringIO(csv_raw.decode("utf-8-sig")), strict=True))
        if (
            not table
            or not table[0]
            or len(table[0]) != len(set(table[0]))
            or any(not h for h in table[0])
        ):
            raise ValueError("Invalid/duplicate CSV header")
        header = table[0]
        if any(len(row) != len(header) for row in table[1:]):
            raise ValueError("CSV row-width conservation failure")
        records = [dict(zip(header, row)) for row in table[1:]]
        key = asset["source_key"]
        csv_ids = [r[key] for r in records]
        geo_ids = [f["properties"][key] for f in features]
        if (
            len(csv_ids) != len(set(csv_ids))
            or any(not k for k in csv_ids)
            or len(geo_ids) != len(set(geo_ids))
        ):
            raise ValueError("Duplicate or empty source key")
        if any(not isinstance(k, str) for k in geo_ids):
            raise ValueError("Cross-format key type not supported in this release")
        a, b = set(csv_ids), set(geo_ids)
        membership = {
            "intersection": len(a & b),
            "a_only": sorted(a - b),
            "b_only": sorted(b - a),
            "union": len(a | b),
            "symmetric_difference": len(a ^ b),
        }
        by_csv = {r[key]: r for r in records}
        by_geo = {f["properties"][key]: f for f in features}
        field_map = spec["field_mappings"].get(asset["asset_id"], {})
        changes = []
        comparisons = Counter()
        coordinate_conflicts = []
        for identity in sorted(a & b):
            source = by_csv[identity]
            feature = by_geo[identity]
            props = feature["properties"]
            for column, value in source.items():
                target = field_map.get(column, column)
                if target not in props:
                    raise ValueError("Unmapped CSV column")
                category = _attributes(value, props[target])
                comparisons[category] += 1
                if category not in ("EXACT_TEXT", "NUMERIC_EQUIVALENT"):
                    changes.append(
                        {
                            "source_key": identity,
                            "csv_field": column,
                            "geojson_field": target,
                            "category": category,
                            "csv_raw": value,
                            "geojson_raw": props[target],
                        }
                    )
            if feature["geometry"]["type"] == "Point" and {"X", "Y"} <= set(source):
                declared = [Decimal(source["X"]), Decimal(source["Y"])]
                actual = [Decimal(str(v)) for v in feature["geometry"]["coordinates"]]
                deltas = [abs(x - y) for x, y in zip(declared, actual)]
                if any(delta > tolerance for delta in deltas):
                    coordinate_conflicts.append(
                        {
                            "source_key": identity,
                            "csv_xy_raw": [source["X"], source["Y"]],
                            "geojson_xy_raw": feature["geometry"]["coordinates"],
                            "absolute_numeric_delta": [str(v) for v in deltas],
                        }
                    )
        formats = []
        geometries = []
        extent_rows = []
        dimensions = Counter()
        crs_ok = native.get("crs") == {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        }
        for feature in features:
            geometry = shape(feature["geometry"])
            geometries.append(geometry)
            coords = list(_coordinates(feature["geometry"]["coordinates"]))
            valid = geometry.is_valid and not geometry.is_empty and crs_ok
            for xy in coords:
                dimensions[len(xy)] += 1
                valid = (
                    valid
                    and len(xy) == 2
                    and all(
                        isinstance(v, (int, float))
                        and not isinstance(v, bool)
                        and math.isfinite(v)
                        for v in xy
                    )
                )
                valid = valid and -180 <= xy[0] <= 180 and -90 <= xy[1] <= 90
            formats.append(bool(valid))
            extent_rows.append(
                {
                    "source_key": feature["properties"][key],
                    "state": _state(geometry, domain) if valid else "UNRESOLVED",
                }
            )
        extent = (
            _state(GeometryCollection(geometries), domain)
            if all(formats)
            else "UNRESOLVED"
        )
        mismatch = (
            membership["symmetric_difference"] > 0
            or bool(changes)
            or bool(coordinate_conflicts)
        )
        reviews.append(
            {
                "asset_id": asset["asset_id"],
                "csv_asset_id": csv_entry["asset_id"],
                "raw_sha256": asset["raw_sha256"],
                "csv_raw_sha256": csv_entry["raw_sha256"],
                "source_key": key,
                "csv_header_raw": header,
                "csv_rows": len(records),
                "geojson_features": len(features),
                "membership": membership,
                "identity_state": "PASS" if a == b else "FAIL",
                "field_mapping_explicit": field_map,
                "attribute_comparisons": dict(comparisons),
                "attribute_differences": changes,
                "coordinate_conflicts": coordinate_conflicts,
                "unmatched_csv_rows": [by_csv[k] for k in sorted(a - b)],
                "unmatched_geojson_features": [by_geo[k] for k in sorted(b - a)],
                "cross_format_state": "FAIL" if mismatch else "PASS",
                "native_geometry_format_state": "PASS" if all(formats) else "FAIL",
                "raw_crs": native.get("crs"),
                "coordinate_dimensions": dict(dimensions),
                "raw_geometry_transformed": False,
                "declared_bbox_state": extent,
                "declared_bbox_feature_states": dict(
                    Counter(r["state"] for r in extent_rows)
                ),
                "declared_bbox_exceptions": [
                    r for r in extent_rows if r["state"] != "FULLY_WITHIN"
                ],
                "pr_jurisdiction_state": "UNRESOLVED",
                "production_export_state": "BLOCKED",
            }
        )
    eligible = constraint_state == "PASS" and all(
        r["cross_format_state"] == "PASS"
        and r["native_geometry_format_state"] == "PASS"
        and r["declared_bbox_state"] == "FULLY_WITHIN"
        for r in reviews
    )
    return {
        "contract": "prii.usgs-source-review/v1",
        "state": "PASS" if eligible else "FAIL",
        "scope": (
            "Frozen native geometry format, source constraint fields and paired "
            "CSV/GeoJSON manifestations; not scientific certification"
        ),
        "review_input_sha256": _sha(raw_spec),
        "native_input_sha256": spec["native_input_sha256"],
        "source_release_id": release["id"],
        "release_title_raw": release["title"],
        "release_dates_raw": release.get("dates"),
        "release_provenance_raw": release.get("provenance"),
        "constraints": {
            "state": constraint_state,
            "raw": constraints,
            "fgdc_asset_id": fgdc_assets[0]["asset_id"],
            "fgdc_sha256": fgdc_assets[0]["raw_sha256"],
        },
        "publisher_declared_bbox": bounds,
        "bbox_scope": "Publisher PRVI study extent, NOT Puerto Rico jurisdiction",
        "raw_numeric_serialization_tolerance": str(tolerance),
        "assets": reviews,
        "asset_count": len(reviews),
        "native_feature_count": sum(r["geojson_features"] for r in reviews),
        "supporting_file_count": len(supporting),
        "native_geometry_format_pass": sum(
            r["native_geometry_format_state"] == "PASS" for r in reviews
        ),
        "cross_format_failures": sum(
            r["cross_format_state"] == "FAIL" for r in reviews
        ),
        "extent_failures": sum(
            r["declared_bbox_state"] != "FULLY_WITHIN" for r in reviews
        ),
        "staging_eligibility": "BLOCKED",
        "remaining_production_gates": [
            "PR_jurisdiction",
            "consumer_fitness",
            "scientific_semantics",
            "units",
            "current_version_lineage",
        ],
        "geometry_engine": {"name": "Shapely", "version": shapely.__version__},
        "coordinate_comparison_scope": (
            "Raw numeric CSV X/Y and GeoJSON tuples only; "
            "CSV CRS/axis semantics are unverified"
        ),
        "evidence_types": {
            "constraints": "FACT",
            "geometry_format": "COMPUTED",
            "cross_format_keys": "BINDING",
            "latest_version": "UNKNOWN",
        },
        "activation_state": "BLOCKED",
        "activated": 0,
        "production_export_state": "BLOCKED",
        "latest_version_state": "UNRESOLVED",
        "identity_repair_performed": False,
        "geometry_repair_performed": False,
    }
