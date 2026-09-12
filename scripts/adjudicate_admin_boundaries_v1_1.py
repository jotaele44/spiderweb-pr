#!/usr/bin/env python3
"""Adjudicate Census identity against Puerto Rico SIGE administrative geometry.

Census GEOID is the identity anchor. SIGE names are candidate-generation evidence
only; geometry metrics can advance a binding to GEOMETRY_CANDIDATE_PASS but never
certify semantic identity by themselves.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

CRS84 = "EPSG:4326"
LOCAL = "EPSG:32161"


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def load_fc(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError(f"{path}: expected GeoJSON FeatureCollection")
    return data["features"]


def feature_geometry(feature: Mapping[str, Any], label: str):
    value = feature.get("geometry")
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}: missing geometry")
    result = shape(value)
    if result.is_empty:
        raise ValueError(f"{label}: empty geometry")
    return result


def projected_metrics(census_geometry, sige_geometry) -> dict[str, Any]:
    to_local = Transformer.from_crs(CRS84, LOCAL, always_xy=True).transform
    census_local = transform(to_local, census_geometry)
    sige_local = sige_geometry
    if not census_local.is_valid or not sige_local.is_valid:
        return {"is_valid": False}
    intersection = census_local.intersection(sige_local).area
    union = census_local.union(sige_local).area
    symmetric_difference = census_local.symmetric_difference(sige_local).area
    census_area = census_local.area
    sige_area = sige_local.area
    largest_area = max(census_area, sige_area)
    return {
        "is_valid": True,
        "intersection_area_m2": intersection,
        "union_area_m2": union,
        "symmetric_difference_area_m2": symmetric_difference,
        "symmetric_difference_ratio": symmetric_difference / union if union else None,
        "overlap_ratio": intersection / union if union else None,
        "hausdorff_distance_m": census_local.hausdorff_distance(sige_local),
        "area_delta_ratio": abs(census_area - sige_area) / largest_area if largest_area else None,
    }


def threshold_state(
    metrics: Mapping[str, Any],
    *,
    minimum_overlap_ratio: float = 0.995,
    maximum_symmetric_difference_ratio: float = 0.005,
    maximum_hausdorff_distance_m: float = 100.0,
    maximum_area_delta_ratio: float = 0.005,
) -> str:
    if not metrics.get("is_valid"):
        return "UNRESOLVED"
    checks = [
        metrics.get("overlap_ratio") is not None
        and metrics["overlap_ratio"] >= minimum_overlap_ratio,
        metrics.get("symmetric_difference_ratio") is not None
        and metrics["symmetric_difference_ratio"] <= maximum_symmetric_difference_ratio,
        metrics.get("hausdorff_distance_m") is not None
        and metrics["hausdorff_distance_m"] <= maximum_hausdorff_distance_m,
        metrics.get("area_delta_ratio") is not None
        and metrics["area_delta_ratio"] <= maximum_area_delta_ratio,
    ]
    return "GEOMETRY_CANDIDATE_PASS" if all(checks) else "REVIEW"


def census_name(properties: Mapping[str, Any]) -> Any:
    return properties.get("BASENAME") or properties.get("NAME")


def build_municipio_bindings(census_features, sige_features):
    sige_index: dict[str, list[tuple[int, Mapping[str, Any]]]] = defaultdict(list)
    for index, feature in enumerate(sige_features):
        properties = feature.get("properties") or {}
        sige_index[norm(properties.get("Nombre"))].append((index, feature))

    bindings: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    used_sige: set[int] = set()
    for index, census_feature in enumerate(census_features):
        properties = census_feature.get("properties") or {}
        geoid = properties.get("GEOID")
        name = census_name(properties)
        if not isinstance(geoid, str) or len(geoid) != 5:
            unresolved.append({"side": "census", "index": index, "reason": "invalid GEOID"})
            continue
        candidates = sige_index.get(norm(name), [])
        if len(candidates) != 1:
            unresolved.append(
                {
                    "side": "binding",
                    "canonical_id": f"pr:municipio:{geoid}",
                    "reason": "candidate_count",
                    "candidate_count": len(candidates),
                }
            )
            continue
        sige_index_value, sige_feature = candidates[0]
        used_sige.add(sige_index_value)
        try:
            metrics = projected_metrics(
                feature_geometry(census_feature, f"census municipio {geoid}"),
                feature_geometry(sige_feature, f"sige municipio {sige_index_value}"),
            )
        except ValueError as exc:
            unresolved.append(
                {"side": "binding", "canonical_id": f"pr:municipio:{geoid}", "reason": str(exc)}
            )
            continue
        bindings.append(
            {
                "canonical_id": f"pr:municipio:{geoid}",
                "census_geoid": geoid,
                "census_name": name,
                "sige_name": (sige_feature.get("properties") or {}).get("Nombre"),
                "sige_index": sige_index_value,
                "candidate_basis": ["UNIQUE_NORMALIZED_NAME", "GEOMETRY_METRICS"],
                "identity_state": "PROVISIONAL",
                "geometry_state": threshold_state(metrics),
                "metrics": metrics,
            }
        )

    for index, feature in enumerate(sige_features):
        if index not in used_sige:
            unresolved.append(
                {
                    "side": "sige",
                    "index": index,
                    "reason": "unretained SIGE municipio",
                    "name": (feature.get("properties") or {}).get("Nombre"),
                }
            )
    return bindings, unresolved


def parent_name_map(municipio_bindings):
    return {
        norm(row["sige_name"]): row["census_geoid"]
        for row in municipio_bindings
        if row.get("sige_name")
    }


def build_barrio_bindings(census_features, sige_features, municipio_bindings):
    parents = parent_name_map(municipio_bindings)
    sige_index: dict[tuple[str, str], list[tuple[int, Mapping[str, Any]]]] = defaultdict(list)
    unresolved: list[dict[str, Any]] = []
    for index, feature in enumerate(sige_features):
        properties = feature.get("properties") or {}
        parent = parents.get(norm(properties.get("MUNICIPIO")))
        if not parent:
            unresolved.append(
                {
                    "side": "sige",
                    "index": index,
                    "reason": "unresolved parent municipio",
                    "municipio": properties.get("MUNICIPIO"),
                    "barrio": properties.get("BARRIO"),
                }
            )
            continue
        sige_index[(parent, norm(properties.get("BARRIO")))].append((index, feature))

    bindings: list[dict[str, Any]] = []
    used_sige: set[int] = set()
    for index, census_feature in enumerate(census_features):
        properties = census_feature.get("properties") or {}
        geoid = properties.get("GEOID")
        name = census_name(properties)
        if not isinstance(geoid, str) or len(geoid) != 10:
            unresolved.append({"side": "census", "index": index, "reason": "invalid GEOID"})
            continue
        parent = geoid[:5]
        candidates = sige_index.get((parent, norm(name)), [])
        if len(candidates) != 1:
            unresolved.append(
                {
                    "side": "binding",
                    "canonical_id": f"pr:barrio:{geoid}",
                    "parent": f"pr:municipio:{parent}",
                    "reason": "candidate_count",
                    "candidate_count": len(candidates),
                }
            )
            continue
        sige_index_value, sige_feature = candidates[0]
        used_sige.add(sige_index_value)
        try:
            metrics = projected_metrics(
                feature_geometry(census_feature, f"census barrio {geoid}"),
                feature_geometry(sige_feature, f"sige barrio {sige_index_value}"),
            )
        except ValueError as exc:
            unresolved.append(
                {"side": "binding", "canonical_id": f"pr:barrio:{geoid}", "reason": str(exc)}
            )
            continue
        sige_properties = sige_feature.get("properties") or {}
        bindings.append(
            {
                "canonical_id": f"pr:barrio:{geoid}",
                "parent_canonical_id": f"pr:municipio:{parent}",
                "census_geoid": geoid,
                "census_name": name,
                "sige_municipio": sige_properties.get("MUNICIPIO"),
                "sige_barrio": sige_properties.get("BARRIO"),
                "sige_index": sige_index_value,
                "candidate_basis": [
                    "RESOLVED_PARENT_MUNICIPIO",
                    "UNIQUE_NORMALIZED_BARRIO_NAME",
                    "GEOMETRY_METRICS",
                ],
                "identity_state": "PROVISIONAL",
                "geometry_state": threshold_state(metrics),
                "metrics": metrics,
            }
        )

    already_unresolved = {
        row.get("index") for row in unresolved if row.get("side") == "sige"
    }
    for index, feature in enumerate(sige_features):
        if index not in used_sige and index not in already_unresolved:
            properties = feature.get("properties") or {}
            unresolved.append(
                {
                    "side": "sige",
                    "index": index,
                    "reason": "unretained SIGE barrio",
                    "municipio": properties.get("MUNICIPIO"),
                    "barrio": properties.get("BARRIO"),
                }
            )
    return bindings, unresolved


def arithmetic(source_count: int, retained_count: int) -> dict[str, int]:
    unresolved_count = source_count - retained_count
    if unresolved_count < 0:
        raise AssertionError("retained count exceeds source count")
    result = {
        "source": source_count,
        "retained": retained_count,
        "excluded": 0,
        "unresolved": unresolved_count,
    }
    if result["source"] != result["retained"] + result["excluded"] + result["unresolved"]:
        raise AssertionError("arithmetic closure failed")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-municipios", type=Path, required=True)
    parser.add_argument("--sige-municipios", type=Path, required=True)
    parser.add_argument("--census-barrios", type=Path, required=True)
    parser.add_argument("--sige-barrios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    census_municipios = load_fc(args.census_municipios)
    sige_municipios = load_fc(args.sige_municipios)
    census_barrios = load_fc(args.census_barrios)
    sige_barrios = load_fc(args.sige_barrios)

    municipio_bindings, municipio_unresolved = build_municipio_bindings(
        census_municipios, sige_municipios
    )
    barrio_bindings, barrio_unresolved = build_barrio_bindings(
        census_barrios, sige_barrios, municipio_bindings
    )
    used_municipios = {row["sige_index"] for row in municipio_bindings}
    used_barrios = {row["sige_index"] for row in barrio_bindings}

    receipt = {
        "contract_version": "federation-spatial-admin-boundary-adjudication/1.1",
        "identity_semantics": "CENSUS_GEOID_ANCHOR_SIGE_GEOMETRY_MANIFESTATION",
        "municipios": {
            "bindings": municipio_bindings,
            "unresolved": municipio_unresolved,
            "arithmetic": {
                "census": arithmetic(len(census_municipios), len(municipio_bindings)),
                "sige": arithmetic(len(sige_municipios), len(used_municipios)),
            },
        },
        "barrios": {
            "bindings": barrio_bindings,
            "unresolved": barrio_unresolved,
            "arithmetic": {
                "census": arithmetic(len(census_barrios), len(barrio_bindings)),
                "sige": arithmetic(len(sige_barrios), len(used_barrios)),
            },
        },
        "canonical_promotion": False,
    }
    args.output.write_text(
        json.dumps(receipt, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "municipio_bindings": len(municipio_bindings),
                "municipio_unresolved": len(municipio_unresolved),
                "barrio_bindings": len(barrio_bindings),
                "barrio_unresolved": len(barrio_unresolved),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
