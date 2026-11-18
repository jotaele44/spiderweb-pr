"""Comparing the closed-basin detector with a published sinkhole map.

Until now the detector was checked only against surfaces it was handed the
answer to.  This module compares it with somebody else's answer: the outlines
of individual sinkholes a geological survey mapped.  That is a comparison with
another interpretation, which has its own positional error, not a field
check; the result is labelled ``REFERENCE_COMPARED`` and never ``MEASURED``.

How the comparison is made
--------------------------
Two measures are taken, because they answer different questions.

* **Does the detector report the mapped sinkhole as an object?**  A mapped
  sinkhole is *found* when a detected basin's centroid lies within the
  outline's equivalent radius plus the publisher's stated positional offset.
  Matching is the package's existing one-to-one, nearest-first
  :func:`~spiderweb.access_points.detection.evaluate`.
* **Is there a closed depression in the surface where the map puts one?**
  The fill depth (how far below its spill level the ground lies) is read
  inside each mapped outline.  This does not depend on how the detector
  groups cells into objects, so it separates "the surface disagrees with
  the map" from "the detector draws its objects differently".

Both are repeated at several depths and against a displaced control:
* Karst ground is full of small hollows, so "some basin is nearby" proves
  little.  Each measure is therefore taken for depths of at least 1, 2, 5,
  10, 20 and 30 m, and against a **displaced control**: the same outlines
  moved by a fixed distance, where any agreement is chance.  What counts is
  how far the real figure stands above the displaced one.
* Only detections are counted that the method stands behind: a basin on a
  survey seam or mostly interpolated cells is excluded and reported.
* Precision is not stated.  The map lists only sinkholes deeper than 30 m, so
  a shallower basin it does not list is not an error.

A run has two halves, like a survey run.  The whole-tile comparison needs the
held products and is sealed with their hashes.  One window at native
resolution is committed so the comparison can be recomputed from the
repository alone.  No registry record is read for its status or changed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import shapely
import yaml
from shapely.affinity import translate
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry

from federation.spatial_core import canonical_json_sha256

from . import CONTRACT_VERSION, survey, survey_run
from . import reference as refsets
from .detection import (
    Detection,
    DetectionParameters,
    ReferenceLabel,
    TruthKind,
    detect_inland,
    evaluate,
)
from .products import held_product
from .raster import SurfaceGrid, coarsen, depression_depth

VALIDATION_VERSION = "access-point-detector-validation/1.0"
VALIDATION_DIR = "evidence/access_points/validation"
POINTER_NAME = "CURRENT.json"
POINTER_SCHEMA = "access_point_validation_pointer/1.0"
REPORT_NAME = "validation_report.json"
REPORT_SCHEMA = "access_point_validation_report/1.0"
TILE_NAME = "tile_evaluation.json"
TILE_SCHEMA = "access_point_validation_tile/1.0"
MIN_COVERAGE = 0.99


class ValidationError(ValueError):
    """The validation run or its committed evidence is not usable."""


# -- the declared run ------------------------------------------------------


def load_validation_run(config_path: str | Path, run_id: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    for run in (data or {}).get("validation_runs") or []:
        if str(run.get("run_id")) == run_id:
            run = dict(run)
            break
    else:
        raise ValidationError(f"no validation run {run_id!r} is declared")
    for key in ("label_set", "context_area_set", "karst_limit_set", "survey_run"):
        if not str(run.get(key) or "").strip():
            raise ValidationError(f"validation run must name its {key}")
    for key in (
        "window_half_size_m",
        "cluster_radius_m",
        "displaced_control_offset_m",
    ):
        if not isinstance(run.get(key), (int, float)) or run[key] <= 0:
            raise ValidationError(f"{key} must be a positive number")
    if (
        not isinstance(run.get("tile_coarsen_factor"), int)
        or run["tile_coarsen_factor"] < 2
    ):
        raise ValidationError("tile_coarsen_factor must be an integer of at least 2")
    thresholds = run.get("depth_thresholds_m")
    if (
        not isinstance(thresholds, list)
        or not thresholds
        or any(not isinstance(t, (int, float)) or t <= 0 for t in thresholds)
        or sorted(thresholds) != thresholds
    ):
        raise ValidationError("depth_thresholds_m must be increasing positive numbers")
    return run


# -- labels in a grid ------------------------------------------------------


@dataclass(frozen=True)
class GridLabel:
    label_id: str
    polygon: BaseGeometry  # in the grid's CRS
    centroid: tuple[float, float]
    match_radius: float


def labels_for_grid(
    layer: refsets.ReferenceLayer, grid: SurfaceGrid
) -> tuple[list[GridLabel], dict[str, int]]:
    """Reference outlines that lie wholly inside a grid and on surveyed cells.

    An outline is used only if it, grown by its match radius, lies inside the
    grid, and at least 99% of the cells under its bounding box hold data.  The
    rest are counted, by reason, and not scored: a label the survey does not
    cover says nothing about the method.
    """

    ref = layer.ref
    if ref.role is not refsets.ReferenceRole.LABELS:
        raise ValidationError(f"{ref.set_id} is not a label set")
    assert ref.bound_crs is not None and ref.positional_offset_m is not None
    rows, cols = grid.shape
    west, north = grid.origin
    east = west + cols * grid.cell_size_crs[0]
    south = north - rows * grid.cell_size_crs[1]
    extent = box(west, south, east, north)
    counts = {"in_set": len(layer.features), "outside_grid": 0, "not_covered": 0}
    usable: list[GridLabel] = []
    # A quick reject in the set's own CRS keeps reprojection to what matters.
    extent_native = refsets.reproject(extent, grid.crs, ref.bound_crs).buffer(2000.0)
    for feature in layer.features:
        if not extent_native.intersects(feature.geometry):
            counts["outside_grid"] += 1
            continue
        polygon = refsets.reproject(feature.geometry, ref.bound_crs, grid.crs)
        radius = refsets.equivalent_radius_m(polygon) + float(ref.positional_offset_m)
        centroid = polygon.centroid
        if not extent.contains(centroid.buffer(radius)) or not extent.contains(polygon):
            counts["outside_grid"] += 1
            continue
        bw, bs, be, bn = polygon.bounds
        c0 = max(0, int((bw - west) / grid.cell_size_crs[0]))
        c1 = min(cols, int(math.ceil((be - west) / grid.cell_size_crs[0])))
        r0 = max(0, int((north - bn) / grid.cell_size_crs[1]))
        r1 = min(rows, int(math.ceil((north - bs) / grid.cell_size_crs[1])))
        cells = grid.values[r0:r1, c0:c1]
        if cells.size == 0 or float(np.isfinite(cells).mean()) < MIN_COVERAGE:
            counts["not_covered"] += 1
            continue
        usable.append(
            GridLabel(feature.feature_id, polygon, (centroid.x, centroid.y), radius)
        )
    counts["scored"] = len(usable)
    return usable, counts


def _reference_labels(
    labels: Sequence[GridLabel],
    ref: refsets.ReferenceSet,
    source_id: str,
    dx: float = 0.0,
) -> list[ReferenceLabel]:
    assert ref.label_class is not None
    return [
        ReferenceLabel(
            label_id=label.label_id,
            feature_class=ref.label_class,
            xy=(label.centroid[0] + dx, label.centroid[1]),
            match_radius=label.match_radius,
            truth_kind=TruthKind.PUBLISHED_MAP_REFERENCE,
            source_id=source_id,
        )
        for label in labels
    ]


# -- scoring ---------------------------------------------------------------


def fill_depth_in(
    polygon: BaseGeometry, grid: SurfaceGrid, fill: np.ndarray
) -> float | None:
    """Deepest fill depth among the cells whose centres lie in an outline.

    An outline smaller than a cell takes the cell under its centroid.
    ``None`` when the outline is off the grid or on cells with no data.
    """

    rows, cols = grid.shape
    west, north = grid.origin
    dx, dy = grid.cell_size_crs
    bw, bs, be, bn = polygon.bounds
    c0, c1 = max(0, int((bw - west) / dx)), min(cols, int(math.ceil((be - west) / dx)))
    r0, r1 = max(0, int((north - bn) / dy)), min(
        rows, int(math.ceil((north - bs) / dy))
    )
    if c0 >= c1 or r0 >= r1:
        return None
    xs = west + (np.arange(c0, c1) + 0.5) * dx
    ys = north - (np.arange(r0, r1) + 0.5) * dy
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(polygon, gx, gy)
    block = fill[r0:r1, c0:c1]
    if not inside.any():
        centroid = polygon.centroid
        col, row = int((centroid.x - west) / dx), int((north - centroid.y) / dy)
        if not (0 <= row < rows and 0 <= col < cols):
            return None
        value = fill[row, col]
        return float(value) if np.isfinite(value) else None
    values = block[inside]
    values = values[np.isfinite(values)]
    return float(values.max()) if values.size else None


def surface_agreement(
    labels: Sequence[GridLabel],
    grid: SurfaceGrid,
    *,
    thresholds: Sequence[float],
    displaced_offset_m: float,
    positional_offset_m: float,
) -> dict[str, Any]:
    """Is the ground a closed depression where the map draws a sinkhole?

    Read twice: inside the outline as drawn, and inside the outline grown by
    the publisher's positional offset, since the map says its outlines may be
    that far from where the ground feature is.  The displaced control is read
    the same two ways.
    """

    fill = depression_depth(grid)

    def depths(grow: float, shift: float) -> list[float]:
        out = []
        for label in labels:
            polygon = label.polygon.buffer(grow) if grow else label.polygon
            if shift:
                polygon = translate(polygon, xoff=shift)
            value = fill_depth_in(polygon, grid, fill)
            if value is not None:
                out.append(value)
        return out

    real_values = depths(0.0, 0.0)
    moved_values = depths(0.0, displaced_offset_m)
    grown_real = depths(positional_offset_m, 0.0)
    grown_moved = depths(positional_offset_m, displaced_offset_m)

    def fraction(values: list[float], threshold: float) -> float | None:
        if not values:
            return None
        return round(sum(1 for v in values if v >= threshold) / len(values), 4)

    rows = []
    for threshold in thresholds:
        hit = sum(1 for v in real_values if v >= threshold)
        chance = sum(1 for v in moved_values if v >= threshold)
        rows.append(
            {
                "min_depth_m": threshold,
                "outlines": len(real_values),
                "outlines_on_a_depression": hit,
                "fraction": fraction(real_values, threshold),
                "displaced_outlines": len(moved_values),
                "displaced_on_a_depression": chance,
                "displaced_fraction": fraction(moved_values, threshold),
                "fraction_within_positional_offset": fraction(grown_real, threshold),
                "displaced_fraction_within_positional_offset": fraction(
                    grown_moved, threshold
                ),
            }
        )
    return {
        "measure": "deepest fill depth below spill level inside each mapped outline",
        "positional_offset_m": positional_offset_m,
        "by_depth_threshold": rows,
        "fill_depth_m": (
            {
                "median": round(float(np.median(real_values)), 2),
                "p10": round(float(np.percentile(real_values, 10)), 2),
                "p90": round(float(np.percentile(real_values, 90)), 2),
                "displaced_median": (
                    round(float(np.median(moved_values)), 2) if moved_values else None
                ),
            }
            if real_values
            else None
        ),
    }


def _depth(detection: Detection) -> float:
    assert detection.region is not None
    return detection.region.max_depth_m


def score(
    detections: Sequence[Detection],
    labels: Sequence[GridLabel],
    ref: refsets.ReferenceSet,
    *,
    grid: SurfaceGrid,
    source_id: str,
    thresholds: Sequence[float],
    displaced_offset_m: float,
) -> dict[str, Any]:
    """How many mapped features the method finds, by depth, against chance."""

    counted = [d for d in detections if not d.possible_artifact]
    excluded = len(detections) - len(counted)
    rows, cols = grid.shape
    west, north = grid.origin
    extent = box(
        west,
        north - rows * grid.cell_size_crs[1],
        west + cols * grid.cell_size_crs[0],
        north,
    )
    real = _reference_labels(labels, ref, source_id)
    displaced_labels = [
        label
        for label in labels
        if extent.contains(
            Point(label.centroid[0] + displaced_offset_m, label.centroid[1]).buffer(
                label.match_radius
            )
        )
    ]
    displaced = _reference_labels(
        displaced_labels, ref, source_id, dx=displaced_offset_m
    )

    by_threshold = []
    state = statement = None
    base_matched: dict[str, str] = {}
    for threshold in thresholds:
        kept = [d for d in counted if _depth(d) >= threshold]
        report = evaluate(kept, real, class_sensitive=False)
        state, statement = report.state.value, report.statement
        found = len(report.matched)
        chance = evaluate(kept, displaced, class_sensitive=False) if displaced else None
        chance_found = len(chance.matched) if chance is not None else None
        by_threshold.append(
            {
                "min_depth_m": threshold,
                "detections": len(kept),
                "labels": len(real),
                "labels_found": found,
                "found_fraction": round(found / len(real), 4) if real else None,
                "displaced_labels": len(displaced),
                "displaced_found": chance_found,
                "displaced_fraction": (
                    round(chance_found / len(displaced), 4)
                    if displaced and chance_found is not None
                    else None
                ),
            }
        )
        if threshold == thresholds[0]:
            base_matched = {label: det for det, label in report.matched}

    depth_of = {d.native_record_id: _depth(d) for d in counted}
    matched_depths = sorted(depth_of[det] for det in base_matched.values())
    missed = []
    for label in labels:
        if label.label_id in base_matched:
            continue
        x, y = label.centroid
        enclosing = [
            d
            for d in counted
            if d.region is not None
            and d.region.bbox_xy[0] <= x <= d.region.bbox_xy[2]
            and d.region.bbox_xy[1] <= y <= d.region.bbox_xy[3]
        ]
        missed.append(
            {
                "label_id": label.label_id,
                "reason": (
                    "INSIDE_A_LARGER_BASIN"
                    if enclosing
                    else "NO_BASIN_WITHIN_MATCH_RADIUS"
                ),
                "enclosing_basin_depth_m": (
                    round(max(_depth(d) for d in enclosing), 2) if enclosing else None
                ),
            }
        )
    stated = ref.stated_min_depth_m
    deep_unlisted = []
    if stated is not None:
        for detection in counted:
            if _depth(detection) < stated:
                continue
            x, y = detection.centroid_xy
            if any(math.dist((x, y), m.centroid) <= m.match_radius for m in labels):
                continue
            assert detection.region is not None
            deep_unlisted.append(
                {
                    "native_record_id": detection.native_record_id,
                    "max_depth_m": round(_depth(detection), 2),
                    "area_m2": round(detection.region.area_m2, 1),
                }
            )
        deep_unlisted.sort(key=lambda r: -r["max_depth_m"])
    reasons: dict[str, int] = {}
    for row in missed:
        reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    return {
        "evaluation_state": state,
        "evaluation_statement": statement,
        "surface_agreement": surface_agreement(
            labels,
            grid,
            thresholds=thresholds,
            displaced_offset_m=displaced_offset_m,
            positional_offset_m=float(ref.positional_offset_m or 0.0),
        ),
        "detections_total": len(detections),
        "detections_excluded_as_possible_artifacts": excluded,
        "object_detection_by_depth_threshold": by_threshold,
        "matched_basin_depth_m": (
            {
                "count": len(matched_depths),
                "median": round(float(np.median(matched_depths)), 2),
                "min": round(matched_depths[0], 2),
                "max": round(matched_depths[-1], 2),
                "at_least_stated_depth": (
                    None
                    if stated is None
                    else sum(1 for v in matched_depths if v >= stated)
                ),
            }
            if matched_depths
            else None
        ),
        "labels_missed_by_reason": dict(sorted(reasons.items())),
        "labels_missed": missed,
        "deep_detections_not_in_the_map": {
            "stated_depth_m": stated,
            "count": len(deep_unlisted),
            "deepest": deep_unlisted[:10],
        },
        "precision": None,
        "precision_note": (
            "not stated: the map lists only features deeper than its stated depth, so "
            "a shallower basin it does not list is not an error"
        ),
    }


# -- the two halves --------------------------------------------------------


def _parameters(run: Mapping[str, Any], cell_size_m: float) -> DetectionParameters:
    return DetectionParameters(
        min_depth_m=float(run["depth_thresholds_m"][0]),
        min_area_m2=max(100.0, 4.0 * cell_size_m * cell_size_m),
    )


def _run_dir(repo_root: Path, run: Mapping[str, Any]) -> Path:
    return repo_root / VALIDATION_DIR / str(run["run_id"])


def _subset_name(epoch: str) -> str:
    return f"window_{epoch}.tif"


def _layers(
    repo_root: Path, run: Mapping[str, Any]
) -> dict[str, refsets.ReferenceLayer]:
    sets = refsets.load_sets(repo_root / refsets.REFERENCE_PATH)
    try:
        return {
            key: refsets.read_layer(sets[run[key]], repo_root)
            for key in ("label_set", "context_area_set", "karst_limit_set")
        }
    except KeyError as exc:
        raise ValidationError(f"validation run names an unknown set: {exc}") from exc


def choose_window_centre(
    labels: Sequence[GridLabel],
    bounds: tuple[float, float, float, float],
    *,
    half_size_m: float,
    cluster_radius_m: float,
) -> tuple[str, tuple[float, float]]:
    """The label with the most mapped neighbours, by a stated rule.

    Among labels far enough from the tile edge for a whole window, take the
    one with the most label centroids within ``cluster_radius_m``; ties go to
    the smallest identifier.  The centre is that label's centroid, rounded to
    a whole metre.  Nothing is chosen by eye.
    """

    west, south, east, north = bounds
    eligible = [
        label
        for label in labels
        if west + half_size_m <= label.centroid[0] <= east - half_size_m
        and south + half_size_m <= label.centroid[1] <= north - half_size_m
    ]
    if not eligible:
        raise ValidationError("no label is far enough from the tile edge for a window")
    best = max(
        eligible,
        key=lambda a: (
            sum(
                1
                for b in labels
                if math.dist(a.centroid, b.centroid) <= cluster_radius_m
            ),
            [-ord(c) for c in a.label_id],
        ),
    )
    return best.label_id, (
        float(round(best.centroid[0])),
        float(round(best.centroid[1])),
    )


def _survey(repo_root: Path, run: Mapping[str, Any]) -> dict[str, Any]:
    return survey_run.load_run(repo_root / survey_run.RUNS_PATH, str(run["survey_run"]))


def _survey_report(repo_root: Path, declared: Mapping[str, Any]) -> dict[str, Any]:
    """The sealed report of the survey run this validation is declared against.

    Read by run id, not through the "current" pointer, so the comparison does
    not change when a later survey run becomes current.
    """

    path = survey_run._run_dir(repo_root, declared) / survey_run.REPORT_NAME
    if not path.is_file():
        raise ValidationError("the survey run's report is not committed")
    return _sealed(path, survey_run.REPORT_SCHEMA)


def _surface(
    window: survey.RasterWindow,
    product: Mapping[str, Any],
    source: Any,
    point: tuple[float, float],
) -> SurfaceGrid:
    reference, _ = survey.stated_vertical(
        window,
        stated_datum=product["stated_vertical_datum"],
        basis=product["vertical_statement_basis"],
        at_lonlat=point,
    )
    return survey.to_surface(
        window,
        vertical_reference=reference,
        source_id=source.source_id,
        uncertainty_m=product.get("vertical_uncertainty_m"),
    )


def _lithology_table(
    path: Path,
    expected_sha: str,
    bound_crs: str,
    windows: Mapping[str, BaseGeometry],
    crs: str,
) -> dict[str, Any]:
    data = path.read_bytes()
    if refsets.sha256_bytes(data) != expected_sha:
        raise ValidationError("the lithology file does not match its declared hash")
    from shapely.geometry import shape  # noqa: PLC0415

    document = json.loads(data)
    out: dict[str, dict[str, float]] = {name: {} for name in windows}
    native = {name: refsets.reproject(g, crs, bound_crs) for name, g in windows.items()}
    for feature in document["features"]:
        geometry = shape(feature["geometry"]).buffer(0)
        props = feature.get("properties") or {}
        unit = f"{props.get('MAP_UNIT')} | {props.get('Lithology')} | {props.get('Epoch') or 'epoch not stated'}"
        for name, window in native.items():
            area = geometry.intersection(window).area
            if area > 0:
                out[name][unit] = out[name].get(unit, 0.0) + area / window.area
    return {
        "source_sha256": expected_sha,
        "bound_crs": bound_crs,
        "fraction_of_window_by_unit": {
            name: {unit: round(v, 4) for unit, v in sorted(units.items())}
            for name, units in out.items()
        },
        "reproducible_from": "the owner's upload named by source_sha256; not committed",
    }


def extract(
    run: Mapping[str, Any],
    *,
    repo_root: str | Path,
    product_dir: str | Path,
    lithology_path: str | Path | None = None,
) -> dict[str, Any]:
    """Whole-tile comparison and the committed window.  Needs the held products."""

    root = Path(repo_root)
    declared = _survey(root, run)
    listed = survey_run._catalogue(root, declared)
    point = survey_run.target_point(root, declared)
    layers = _layers(root, run)
    label_ref = layers["label_set"].ref
    label_source = refsets.to_source(label_ref)
    factor = int(run["tile_coarsen_factor"])
    epochs: dict[str, Any] = {}
    centre_label = centre = tile_bounds = None
    for product in declared["products"]:
        epoch = product["epoch"]
        request = listed[product["filename"]]
        held = held_product(request, product_dir)
        if held is None:
            raise ValidationError(f"{product['filename']} is not held in {product_dir}")
        source = survey_run._source(request, product, held.sha256, held.retrieved_utc)
        tile = survey.read_raster(held.path)
        fine = _surface(tile, product, source, point)
        coarse = coarsen(fine, factor)
        del fine
        detections = detect_inland(
            coarse, source, _parameters(run, coarse.cell_size_m[0])
        )
        labels, counts = labels_for_grid(layers["label_set"], coarse)
        result = score(
            detections,
            labels,
            label_ref,
            grid=coarse,
            source_id=label_source.source_id,
            thresholds=run["depth_thresholds_m"],
            displaced_offset_m=float(run["displaced_control_offset_m"]),
        )
        epochs[epoch] = {
            "parent_sha256": held.sha256,
            "cell_size_m": coarse.cell_size_m[0],
            "shape": list(coarse.shape),
            "valid_cell_fraction": round(float(np.isfinite(coarse.values).mean()), 4),
            "label_counts": counts,
            **result,
        }
        if epoch == str(run["reproducible_epoch"]):
            tile_bounds = tile.bounds()
            centre_label, centre = choose_window_centre(
                labels,
                tile_bounds,
                half_size_m=float(run["window_half_size_m"]),
                cluster_radius_m=float(run["cluster_radius_m"]),
            )
            lon, lat = refsets.to_lonlat(centre, tile.crs)
            window = survey.read_window(
                held.path,
                center_lonlat=(lon, lat),
                half_size_m=float(run["window_half_size_m"]),
            )
            survey.write_subset(
                window, _run_dir(root, run) / "subsets" / _subset_name(epoch)
            )
            validation_window = box(*window.bounds())
            tile_crs = tile.crs
        del tile
    if centre is None or tile_bounds is None:
        raise ValidationError(
            "the reproducible epoch is not one of the survey products"
        )
    body: dict[str, Any] = {
        "schema": TILE_SCHEMA,
        "run_id": run["run_id"],
        "coarsen_factor": factor,
        "tile_bounds": [round(v, 6) for v in tile_bounds],
        "window_centre_label": centre_label,
        "window_centre_xy": list(centre),
        "epochs": epochs,
        "reproducible_from": (
            "the held products named by parent_sha256; not from the repository alone"
        ),
    }
    if lithology_path is not None:
        sets = refsets.load_sets(root / refsets.REFERENCE_PATH)
        lith = next(
            s for s in sets.values() if s.role is refsets.ReferenceRole.LITHOLOGY
        )
        survey_report = _survey_report(root, declared)
        windows = {"validation_window": validation_window}
        if survey_report is not None:
            windows["survey_window"] = box(
                *survey_report["products"][0]["result"]["surface"]["bounds"]
            )
        body["lithology"] = _lithology_table(
            Path(lithology_path),
            lith.sha256,
            str(label_ref.bound_crs),
            windows,
            tile_crs,
        )
    body = json.loads(json.dumps(body))
    body["content_sha256"] = canonical_json_sha256(body)
    _write_json(_run_dir(root, run) / TILE_NAME, body)
    return body


def _sealed(path: Path, schema: str) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    body = dict(document)
    stated = body.pop("content_sha256", None)
    if document.get("schema") != schema or canonical_json_sha256(body) != stated:
        raise ValidationError(f"{path.name} does not match its content hash")
    return document


def _context(
    root: Path,
    run: Mapping[str, Any],
    declared: Mapping[str, Any],
    layers: Mapping[str, refsets.ReferenceLayer],
    crs: str,
) -> dict[str, Any]:
    """What the reference maps say about the earlier survey run's record."""

    from rasterio.warp import transform as warp_transform  # noqa: PLC0415

    point = survey_run.target_point(root, declared)
    xs, ys = warp_transform("OGC:CRS84", crs, [point[0]], [point[1]])
    here = Point(float(xs[0]), float(ys[0]))
    limit = layers["karst_limit_set"]
    limit_polygon = refsets.reproject(
        limit.features[0].geometry, str(limit.ref.bound_crs), crs
    )
    areas = layers["context_area_set"]
    in_area = any(
        refsets.reproject(f.geometry, str(areas.ref.bound_crs), crs).contains(here)
        for f in areas.features
    )
    label_layer = layers["label_set"]
    native_here = refsets.reproject(here, crs, str(label_layer.ref.bound_crs))
    nearest = sorted(
        (round(f.geometry.distance(native_here), 1), f.feature_id)
        for f in label_layer.features
    )[:3]
    survey_report = _survey_report(root, declared)
    inside_window = None
    if survey_report is not None:
        window = refsets.reproject(
            box(*survey_report["products"][0]["result"]["surface"]["bounds"]),
            crs,
            str(label_layer.ref.bound_crs),
        )
        inside_window = sum(
            1 for f in label_layer.features if window.intersects(f.geometry)
        )
    return {
        "record": declared["target_feature"],
        "registered_point_inside_karst_limit": bool(limit_polygon.contains(here)),
        "distance_to_karst_limit_boundary_m": round(
            limit_polygon.exterior.distance(here), 0
        ),
        "registered_point_inside_an_area_of_sinkholes_5_to_30m": in_area,
        "mapped_sinkholes_over_30m_in_the_survey_window": inside_window,
        "nearest_mapped_sinkholes_over_30m": [
            {"feature_id": fid, "distance_m": distance} for distance, fid in nearest
        ],
        "basis": "geometry tests against published maps; nothing is attached to the record",
    }


def build_report(run: Mapping[str, Any], *, repo_root: str | Path) -> dict[str, Any]:
    """The sealed report, computed from committed evidence only."""

    root = Path(repo_root)
    declared = _survey(root, run)
    listed = survey_run._catalogue(root, declared)
    point = survey_run.target_point(root, declared)
    layers = _layers(root, run)
    label_ref = layers["label_set"].ref
    label_source = refsets.to_source(label_ref)
    epoch = str(run["reproducible_epoch"])
    product = next((p for p in declared["products"] if p["epoch"] == epoch), None)
    if product is None:
        raise ValidationError(
            "the reproducible epoch is not one of the survey products"
        )
    manifest = survey_run._product_manifest(
        survey_run._run_dir(root, declared), product["filename"]
    )
    source = survey_run._source(
        listed[product["filename"]],
        product,
        manifest["response_sha256"],
        manifest["retrieved_utc"],
    )
    run_dir = _run_dir(root, run)
    subset_path = run_dir / "subsets" / _subset_name(epoch)
    if not subset_path.is_file():
        raise ValidationError("the committed window subset is missing")
    tile_eval = _sealed(run_dir / TILE_NAME, TILE_SCHEMA)
    window = survey.read_raster(subset_path)
    grid = _surface(window, product, source, point)

    # The committed window must be the one the stated rule picks.
    half = float(run["window_half_size_m"])
    cx, cy = tile_eval["window_centre_xy"]
    west, south, east, north = window.bounds()
    if (
        abs((west + east) / 2 - cx) > 1.5 * grid.cell_size_m[0]
        or abs((south + north) / 2 - cy) > 1.5 * grid.cell_size_m[1]
        or abs((east - west) - 2 * half) > 1.5 * grid.cell_size_m[0]
    ):
        raise ValidationError("the committed window is not the one the rule selects")

    detections = detect_inland(grid, source, _parameters(run, grid.cell_size_m[0]))
    labels, counts = labels_for_grid(layers["label_set"], grid)
    result = score(
        detections,
        labels,
        label_ref,
        grid=grid,
        source_id=label_source.source_id,
        thresholds=run["depth_thresholds_m"],
        displaced_offset_m=min(
            float(run["displaced_control_offset_m"]), float(run["window_half_size_m"])
        ),
    )
    body: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "validation_version": VALIDATION_VERSION,
        "run_id": run["run_id"],
        "survey_run": run["survey_run"],
        "reference_sets": [layer.summary() for layer in layers.values()],
        "method": {
            "match_rule": (
                "a mapped outline is found when a detected basin's centroid lies within "
                "the outline's equivalent radius plus the publisher's positional offset; "
                "one-to-one, nearest first"
            ),
            "depth_thresholds_m": run["depth_thresholds_m"],
            "displaced_control_offset_m": run["displaced_control_offset_m"],
            "min_label_coverage": MIN_COVERAGE,
            "thresholds_changed_by_this_run": False,
        },
        "window": {
            "epoch": epoch,
            "source_id": source.source_id,
            "subset_file": f"subsets/{_subset_name(epoch)}",
            "subset_sha256": survey.sha256_file(subset_path),
            "parent_sha256": manifest["response_sha256"],
            "bounds": [round(v, 6) for v in window.bounds()],
            "cell_size_m": grid.cell_size_m[0],
            "selection_rule": (
                "the label with the most mapped neighbours within the cluster radius, "
                "far enough from the tile edge; ties to the smallest identifier"
            ),
            "selected_label": tile_eval["window_centre_label"],
            "label_counts": counts,
            **result,
        },
        "whole_tile": tile_eval,
        "context_for_the_survey_run": _context(root, run, declared, layers, grid.crs),
        "registry_changes": 0,
        "limits": [
            "the reference is a published map compiled from topographic maps, not a field survey; its outlines may be offset by as much as 100 m",
            "a mapped sinkhole counted as found means a closed basin of at least the stated depth lies where the map puts it; it is a shape, not an opening or an identity",
            "the displaced control shows how often agreement arises by chance in ground this full of hollows",
            "the detector reports the outermost closed basin; a sinkhole nested inside a larger closed depression is not reported as its own object",
            "precision is not stated, because the map lists only sinkholes deeper than 30 m",
            "one tile of one karst terrain was compared; the result does not transfer to other ground or to the seabed",
            "no threshold was changed and no registry record was changed by this run",
        ],
    }
    body = json.loads(json.dumps(body))
    body["content_sha256"] = canonical_json_sha256(body)
    return body


def _write_json(path: Path, document: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_report(report: Mapping[str, Any], *, repo_root: str | Path) -> str:
    root = Path(repo_root) / VALIDATION_DIR
    digest = _write_json(root / str(report["run_id"]) / REPORT_NAME, report)
    _write_json(
        root / POINTER_NAME,
        {
            "schema": POINTER_SCHEMA,
            "run_id": report["run_id"],
            "report": f"{report['run_id']}/{REPORT_NAME}",
            "report_sha256": digest,
        },
    )
    return digest


def current_report(repo_root: str | Path) -> dict[str, Any] | None:
    root = Path(repo_root) / VALIDATION_DIR
    pointer_path = root / POINTER_NAME
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    relative = Path(str(pointer.get("report")))
    if (
        pointer.get("schema") != POINTER_SCHEMA
        or relative.is_absolute()
        or ".." in relative.parts
    ):
        raise ValidationError(f"{pointer_path} is not a usable validation pointer")
    path = root / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != pointer["report_sha256"]:
        raise ValidationError(f"{relative} does not match the pointer's hash")
    return _sealed(path, REPORT_SCHEMA)


def check_report(run: Mapping[str, Any], *, repo_root: str | Path) -> list[str]:
    root = Path(repo_root)
    path = _run_dir(root, run) / REPORT_NAME
    if not path.is_file():
        return ["no report is committed for this run"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    try:
        rebuilt = build_report(run, repo_root=root)
    except (ValidationError, refsets.ReferenceSetError, ValueError, LookupError) as exc:
        return [f"{type(exc).__name__}: {exc}"]
    if rebuilt == committed:
        return []
    differing = sorted(
        key
        for key in set(rebuilt) | set(committed)
        if rebuilt.get(key) != committed.get(key)
    )
    return [f"the committed report is not reproduced; differing fields: {differing}"]
