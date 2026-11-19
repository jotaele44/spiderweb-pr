"""Processing a real gridded survey, end to end.

The rest of the package was built and tested on synthetic surfaces with known
answers.  This module is where a real product enters: a window is cut from a
held, hashed GeoTIFF, bound to the vertical reference *the product itself*
states, run through the shared basin delineation and candidate detection, and
reported.  Two surveys of the same ground can then be compared, which is the
one check available without field truth: a depression that a second,
independent survey does not show is more likely an artefact than a landform.

What a result means
-------------------
* A detection is a closed basin in a gridded surface.  It is a *shape*.  It is
  not an opening, a passage or a connection, and it is not an identity.
* A gridded elevation model is a derived product, never a direct measurement,
  so shape evidence taken from it cannot rise above ``SUPPORTING``.
* Nothing here registers a feature.  :func:`dry_registration` shows what a
  scratch registry would hold, so the path is exercised without the committed
  registries changing.
* A stated vertical datum is recorded as stated and checked for regional
  plausibility.  Closed-basin shape does not depend on the datum, so an
  implausible statement does not stop single-surface analysis; it does stop
  any join to a surface on a different reference.

A gridded seabed survey enters the same way (:func:`read_depth_grid`,
:func:`process_seabed`), with two differences: the uncertainty is the
product's own, one value per cell, and the report says how much of the survey
that uncertainty leaves unable to show a depression of the minimum depth.

``rasterio`` is needed to read and write GeoTIFFs and to read gridded
bathymetric survey files (the ``dem`` extra).  It is imported lazily so the
rest of the package does not depend on it.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from gebco.marine_evidence import VerticalReference

from .detection import (
    Detection,
    DetectionParameters,
    detect_inland,
    detect_offshore,
)
from .models import HORIZONTAL_INTERCHANGE_CRS, SourceManifestation
from .raster import (
    SurfaceGrid,
    SurfaceKind,
    coverage,
    delineate_depressions,
    make_grid,
)
from .vertical import bind, regional_plausibility

SURVEY_VERSION = "access-point-survey-processing/1.0"


class SurveyReadError(ValueError):
    """A product cannot be read as the surface it is claimed to be."""


def _rasterio():
    try:
        import rasterio  # noqa: PLC0415 - optional dependency, imported on use
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SurveyReadError(
            "reading a GeoTIFF needs rasterio (install the 'dem' extra)"
        ) from exc
    return rasterio


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -- reading ---------------------------------------------------------------


@dataclass(frozen=True)
class RasterWindow:
    """A rectangular piece of a north-up, metre-gridded raster."""

    values: np.ndarray  # float64, NaN where the product has no data
    crs: str
    origin: tuple[float, float]  # outer corner of the north-west cell
    cell_size: tuple[float, float]
    row_off: int
    col_off: int
    source_shape: tuple[int, int]
    source_nodata: float | None

    @property
    def shape(self) -> tuple[int, int]:
        return self.values.shape  # type: ignore[return-value]

    def bounds(self) -> tuple[float, float, float, float]:
        rows, cols = self.shape
        west, north = self.origin
        return (
            west,
            north - rows * self.cell_size[1],
            west + cols * self.cell_size[0],
            north,
        )


def _checked_grid(src: Any) -> tuple[float, float]:
    transform = src.transform
    if src.count != 1:
        raise SurveyReadError("an elevation product must have exactly one band")
    if src.crs is None:
        raise SurveyReadError("the product states no horizontal CRS")
    if not src.crs.is_projected or abs(src.crs.linear_units_factor[1] - 1.0) > 1e-9:
        raise SurveyReadError(
            "the product must be on a projected CRS in metres; reproject a "
            "geographic grid first (tools/pr_dem_one_tile_pilot.read_dem does this)"
        )
    if transform.b != 0 or transform.d != 0 or transform.e >= 0 or transform.a <= 0:
        raise SurveyReadError("the product must be north-up with no rotation")
    return float(transform.a), float(-transform.e)


def _to_array(raw: np.ndarray, nodata: float | None) -> np.ndarray:
    values = raw.astype(np.float64)
    if nodata is not None and not math.isnan(nodata):
        values[raw == raw.dtype.type(nodata)] = np.nan
    values[~np.isfinite(values)] = np.nan
    return values


def read_window(
    path: str | Path, *, center_lonlat: tuple[float, float], half_size_m: float
) -> RasterWindow:
    """Cut a square window around a longitude/latitude from a held product.

    The window is clipped to the product; a centre outside it is an error.
    No resampling is done: cells come out exactly as the product holds them.
    """

    if half_size_m <= 0:
        raise ValueError("half_size_m must be positive")
    rasterio = _rasterio()
    from rasterio.warp import transform as warp_transform  # noqa: PLC0415
    from rasterio.windows import Window  # noqa: PLC0415

    with rasterio.open(path) as src:
        dx, dy = _checked_grid(src)
        xs, ys = warp_transform(
            HORIZONTAL_INTERCHANGE_CRS, src.crs, [center_lonlat[0]], [center_lonlat[1]]
        )
        row, col = src.index(xs[0], ys[0])
        if not (0 <= row < src.height and 0 <= col < src.width):
            raise SurveyReadError("the requested centre lies outside the product")
        half_cols = int(round(half_size_m / dx))
        half_rows = int(round(half_size_m / dy))
        c0, c1 = max(0, col - half_cols), min(src.width, col + half_cols)
        r0, r1 = max(0, row - half_rows), min(src.height, row + half_rows)
        raw = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
        west = float(src.transform.c) + c0 * dx
        north = float(src.transform.f) - r0 * dy
        return RasterWindow(
            values=_to_array(raw, src.nodata),
            crs=src.crs.to_string(),
            origin=(float(west), float(north)),
            cell_size=(dx, dy),
            row_off=r0,
            col_off=c0,
            source_shape=(src.height, src.width),
            source_nodata=src.nodata,
        )


def read_raster(path: str | Path) -> RasterWindow:
    """Read a whole (small) GeoTIFF, such as a subset written by :func:`write_subset`."""

    rasterio = _rasterio()
    with rasterio.open(path) as src:
        dx, dy = _checked_grid(src)
        return RasterWindow(
            values=_to_array(src.read(1), src.nodata),
            crs=src.crs.to_string(),
            origin=(float(src.transform.c), float(src.transform.f)),
            cell_size=(dx, dy),
            row_off=0,
            col_off=0,
            source_shape=(src.height, src.width),
            source_nodata=src.nodata,
        )


def write_subset(window: RasterWindow, path: str | Path) -> str:
    """Write a window as a lossless float32 GeoTIFF; return its SHA-256.

    The values are the product's own 32-bit cells, so nothing is rounded.
    """

    rasterio = _rasterio()
    from rasterio.transform import from_origin  # noqa: PLC0415

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    nodata = -9999.0
    data = np.where(np.isfinite(window.values), window.values, nodata).astype(
        np.float32
    )
    if np.isfinite(window.values).any() and float(np.nanmin(window.values)) <= nodata:
        raise SurveyReadError("the surface reaches the no-data sentinel")
    rows, cols = data.shape
    with rasterio.open(
        target,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=window.crs,
        transform=from_origin(
            window.origin[0], window.origin[1], window.cell_size[0], window.cell_size[1]
        ),
        nodata=nodata,
        compress="deflate",
        predictor=3,
        zlevel=9,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(data, 1)
    return sha256_file(target)


# -- vertical reference ----------------------------------------------------


def stated_vertical(
    window: RasterWindow,
    *,
    stated_datum: str,
    basis: str,
    at_lonlat: tuple[float, float],
) -> tuple[VerticalReference, dict[str, Any]]:
    """Bind the datum a product states, and say whether it can be true here.

    ``basis`` records *where* the statement was found (a structured metadata
    element, a sentence in an abstract, an inventory field ...), because a
    datum taken from boilerplate is weaker than one taken from a definition.
    """

    reference = VerticalReference(
        horizontal_crs=window.crs,
        vertical_crs=None,
        vertical_datum=stated_datum,
        tidal_datum=None,
        depth_positive="up",
    )
    bound = bind(reference)
    plausibility, reason = regional_plausibility(bound.datum, *at_lonlat)
    return reference, {
        "stated_datum": stated_datum,
        "resolved_datum": bound.datum.value,
        "statement_basis": basis,
        "positive": "up",
        "regional_plausibility": plausibility.value,
        "regional_plausibility_reason": reason,
        "joinable_to_other_references": plausibility.value == "PLAUSIBLE",
    }


def to_surface(
    window: RasterWindow,
    *,
    vertical_reference: VerticalReference,
    source_id: str,
    uncertainty_m: float | None,
) -> SurfaceGrid:
    return make_grid(
        window.values,
        cell_size_m=window.cell_size,
        origin=window.origin,
        crs=window.crs,
        kind=SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=vertical_reference,
        uncertainty_m=uncertainty_m,
        source_id=source_id,
        expect="emergent",
    )


# -- processing ------------------------------------------------------------


def _lonlat(
    crs: str, xs: Sequence[float], ys: Sequence[float]
) -> list[tuple[float, float]]:
    from rasterio.warp import transform as warp_transform  # noqa: PLC0415

    _rasterio()
    lon, lat = warp_transform(crs, HORIZONTAL_INTERCHANGE_CRS, list(xs), list(ys))
    return [(round(float(a), 7), round(float(b), 7)) for a, b in zip(lon, lat)]


def _detection_row(detection: Detection, lonlat: tuple[float, float]) -> dict[str, Any]:
    region = detection.region
    assert region is not None
    return {
        "native_record_id": detection.native_record_id,
        "proposed_class": detection.proposed_class,
        "centroid_xy": [round(v, 3) for v in detection.centroid_xy],
        "deepest_xy": [round(v, 3) for v in region.deepest_xy],
        "bbox_xy": [round(v, 3) for v in region.bbox_xy],
        "centroid_lonlat": list(lonlat),
        "max_depth_m": round(region.max_depth_m, 3),
        "mean_depth_m": round(region.mean_depth_m, 3),
        "area_m2": round(region.area_m2, 1),
        "volume_m3": round(region.volume_m3, 1),
        "equivalent_diameter_m": round(region.equivalent_diameter_m, 2),
        "circularity": round(region.circularity, 3),
        "rectangularity": round(region.rectangularity, 3),
        "spill_elevation_m": round(region.spill_elevation_m, 3),
        "floor_elevation_m": round(region.floor_elevation_m, 3),
        "depth_uncertainty_m": (
            None
            if region.depth_uncertainty_m is None
            else round(region.depth_uncertainty_m, 4)
        ),
        "significance": (
            None if region.significance is None else round(region.significance, 2)
        ),
        "adjoins_edge": region.adjoins_edge,
        "adjoins_nodata": region.adjoins_nodata,
        "flags": [flag.value for flag in detection.flags],
        "possible_artifact": detection.possible_artifact,
        "discovery_score": round(detection.discovery_score, 2),
        "assertions": [
            {
                "dimension": a.dimension.value,
                "tier": a.tier.name,
                "claim_class": a.claim_class.value,
                "statement": a.statement,
            }
            for a in detection.assertions
        ],
    }


@dataclass(frozen=True)
class SurveyResult:
    grid: SurfaceGrid
    detections: tuple[Detection, ...]
    report: dict[str, Any]


def process_terrain(
    window: RasterWindow,
    source: SourceManifestation,
    *,
    vertical_reference: VerticalReference,
    uncertainty_m: float | None,
    parameters: DetectionParameters,
) -> SurveyResult:
    """Delineate and describe closed basins in one bare-earth window."""

    grid = to_surface(
        window,
        vertical_reference=vertical_reference,
        source_id=source.source_id,
        uncertainty_m=uncertainty_m,
    )
    detections = detect_inland(grid, source, parameters)
    lonlats = _lonlat(
        grid.crs,
        [d.centroid_xy[0] for d in detections],
        [d.centroid_xy[1] for d in detections],
    )
    summary = coverage(grid)
    finite = grid.values[np.isfinite(grid.values)]
    tiers: dict[str, int] = {}
    for detection in detections:
        for assertion in detection.assertions:
            tiers[assertion.tier.name] = tiers.get(assertion.tier.name, 0) + 1
    report = {
        "source_id": source.source_id,
        "surface": {
            "kind": grid.kind.value,
            "crs": grid.crs,
            "shape": list(grid.shape),
            "cell_size_m": list(grid.cell_size_m),
            "origin": [round(v, 6) for v in grid.origin],
            "bounds": [round(v, 6) for v in window.bounds()],
            "valid_cells": summary.valid_cells,
            "nodata_cells": summary.nodata_cells,
            "elevation_min_m": round(float(finite.min()), 3) if finite.size else None,
            "elevation_max_m": round(float(finite.max()), 3) if finite.size else None,
            "stated_uncertainty_m": uncertainty_m,
        },
        "parameters": {
            "min_depth_m": parameters.min_depth_m,
            "min_area_m2": parameters.min_area_m2,
            "significance_floor": parameters.significance_floor,
        },
        "detection_count": len(detections),
        "possible_artifacts": sum(1 for d in detections if d.possible_artifact),
        "assertions_by_tier": dict(sorted(tiers.items())),
        "detections": [_detection_row(d, ll) for d, ll in zip(detections, lonlats)],
    }
    return SurveyResult(grid, tuple(detections), report)


# -- two surveys of the same ground ----------------------------------------


def _footprint(grid: SurfaceGrid, detection: Detection) -> np.ndarray:
    """Boolean mask of a basin's bounding box cells, in grid coordinates."""

    region = detection.region
    assert region is not None
    mask = np.zeros(grid.shape, dtype=bool)
    mask[region.slices] = True
    return mask


def compare_surveys(
    earlier: SurveyResult,
    later: SurveyResult,
    *,
    min_overlap: float = 0.5,
    grid_tolerance_m: float = 0.01,
) -> dict[str, Any]:
    """Which basins does a second survey of the same ground also show?

    Two basins correspond when their bounding boxes overlap by at least
    ``min_overlap`` of the smaller one.  That is a statement about two shapes
    in two rasters.  It supports "this is a landform rather than an artefact
    of one survey"; it is not an identity and it says nothing about what the
    landform is.

    The cell-by-cell elevation difference is summarised only when the two
    grids hold the same cells to within ``grid_tolerance_m``.
    """

    a, b = earlier.grid, later.grid
    same_cells = (
        a.shape == b.shape
        and a.crs == b.crs
        and all(
            abs(x - y) <= grid_tolerance_m
            for x, y in zip(a.origin + a.cell_size_crs, b.origin + b.cell_size_crs)
        )
    )
    if not same_cells:
        raise SurveyReadError("the two surveys do not hold the same cells")

    pairs: list[dict[str, Any]] = []
    matched_later: set[int] = set()
    for i, first in enumerate(earlier.detections):
        fa = _footprint(a, first)
        best: tuple[float, int] | None = None
        for j, second in enumerate(later.detections):
            if j in matched_later:
                continue
            fb = _footprint(b, second)
            inter = int(np.logical_and(fa, fb).sum())
            if not inter:
                continue
            overlap = inter / min(int(fa.sum()), int(fb.sum()))
            if overlap >= min_overlap and (best is None or overlap > best[0]):
                best = (overlap, j)
        if best is not None:
            matched_later.add(best[1])
            second = later.detections[best[1]]
            assert first.region is not None and second.region is not None
            pairs.append(
                {
                    "earlier": first.native_record_id,
                    "later": second.native_record_id,
                    "bbox_overlap": round(best[0], 3),
                    "max_depth_m": [
                        round(first.region.max_depth_m, 3),
                        round(second.region.max_depth_m, 3),
                    ],
                    "area_m2": [
                        round(first.region.area_m2, 1),
                        round(second.region.area_m2, 1),
                    ],
                    "deepest_point_separation_m": round(
                        math.dist(first.region.deepest_xy, second.region.deepest_xy), 2
                    ),
                }
            )
    replicated_earlier = {p["earlier"] for p in pairs}
    only_earlier = [
        d.native_record_id
        for d in earlier.detections
        if d.native_record_id not in replicated_earlier
    ]
    only_later = [
        d.native_record_id
        for j, d in enumerate(later.detections)
        if j not in matched_later
    ]

    both = np.isfinite(a.values) & np.isfinite(b.values)
    delta = (b.values - a.values)[both]
    difference = None
    if delta.size:
        absolute = np.abs(delta)
        difference = {
            "cells_compared": int(delta.size),
            "median_m": round(float(np.median(delta)), 4),
            "mean_m": round(float(delta.mean()), 4),
            "median_absolute_m": round(float(np.median(absolute)), 4),
            "p95_absolute_m": round(float(np.percentile(absolute, 95)), 4),
            "max_absolute_m": round(float(absolute.max()), 3),
            "within_0_3_m_fraction": round(float(np.mean(absolute <= 0.3)), 4),
        }
    total = len(earlier.detections)
    return {
        "method": "bounding-box overlap of closed basins on a shared cell grid",
        "min_overlap": min_overlap,
        "earlier_detections": total,
        "later_detections": len(later.detections),
        "replicated": len(pairs),
        "replicated_fraction_of_earlier": (
            round(len(pairs) / total, 4) if total else None
        ),
        "only_in_earlier": only_earlier,
        "only_in_later": only_later,
        "pairs": pairs,
        "elevation_difference_later_minus_earlier": difference,
        "meaning": (
            "a replicated basin is seen by two independent surveys and is unlikely "
            "to be an artefact of either; it is a shape, not an identity"
        ),
    }


# -- relation to registered records ----------------------------------------


def nearest_detections(
    result: SurveyResult, *, lonlat: tuple[float, float], limit: int = 3
) -> dict[str, Any]:
    """Where a registered point falls relative to the basins found.

    Proximity is discovery.  This reports distances and containment so a
    reviewer can look; it does not attach a detection to a record.
    """

    from rasterio.warp import transform as warp_transform  # noqa: PLC0415

    _rasterio()
    xs, ys = warp_transform(
        HORIZONTAL_INTERCHANGE_CRS, result.grid.crs, [lonlat[0]], [lonlat[1]]
    )
    x, y = float(xs[0]), float(ys[0])
    rows = []
    for detection in result.detections:
        region = detection.region
        assert region is not None
        west, south, east, north = region.bbox_xy
        rows.append(
            {
                "native_record_id": detection.native_record_id,
                "distance_to_deepest_point_m": round(
                    math.dist((x, y), region.deepest_xy), 1
                ),
                "point_inside_basin_bbox": west <= x <= east and south <= y <= north,
                "max_depth_m": round(region.max_depth_m, 3),
                "area_m2": round(region.area_m2, 1),
            }
        )
    rows.sort(key=lambda r: r["distance_to_deepest_point_m"])
    west, south, east, north = (
        result.grid.origin[0],
        result.grid.origin[1] - result.grid.shape[0] * result.grid.cell_size_crs[1],
        result.grid.origin[0] + result.grid.shape[1] * result.grid.cell_size_crs[0],
        result.grid.origin[1],
    )
    return {
        "point_xy": [round(x, 2), round(y, 2)],
        "point_inside_window": west <= x <= east and south <= y <= north,
        "inside_any_basin_bbox": any(r["point_inside_basin_bbox"] for r in rows),
        "nearest": rows[:limit],
        "basis": "DISTANCE_ONLY_DISCOVERY",
    }


def dry_registration(
    result: SurveyResult,
    source: SourceManifestation,
    *,
    created_utc: str,
    namespace: Any = None,
) -> dict[str, Any]:
    """What a scratch registry would hold if these detections were filed.

    The registry is the inland one unless ``namespace`` says otherwise.

    Nothing is written anywhere.  The point is to show that a real survey's
    detections pass the registry's own rules and where its ladder puts them.
    """

    from .models import Observation  # noqa: PLC0415
    from .namespaces import Namespace, observation_id  # noqa: PLC0415
    from .registry import AccessPointRegistry  # noqa: PLC0415
    from .rules import assertion_rung  # noqa: PLC0415
    from .vocabulary import GeometryBasis  # noqa: PLC0415

    target = Namespace.ACCESS_POINT_INLAND if namespace is None else namespace
    registry = AccessPointRegistry(target, producer_identity="dry-run:survey")
    registry.add_source(source)
    rungs: dict[str, int] = {}
    statuses: dict[str, int] = {}
    lonlats = _lonlat(
        result.grid.crs,
        [d.centroid_xy[0] for d in result.detections],
        [d.centroid_xy[1] for d in result.detections],
    )
    for detection, (lon, lat) in zip(result.detections, lonlats):
        oid = observation_id(target, source.source_id, detection.native_record_id)
        registry.add_observation(
            Observation(
                observation_id=oid,
                namespace=target,
                source_id=source.source_id,
                native_record_id=detection.native_record_id,
                geometry={"type": "Point", "coordinates": [lon, lat]},
                horizontal_crs=HORIZONTAL_INTERCHANGE_CRS,
                geometry_basis=GeometryBasis.DERIVED_FROM_RASTER,
            )
        )
        feature = registry.register_candidate(
            str(detection.proposed_class),
            observation_ids=(oid,),
            assertions=detection.assertions,
            created_utc=created_utc,
        )
        rung = assertion_rung(feature, registry.sources).name
        rungs[rung] = rungs.get(rung, 0) + 1
        statuses[feature.status.value] = statuses.get(feature.status.value, 0) + 1
    return {
        "features_that_would_be_filed": len(result.detections),
        "by_status": dict(sorted(statuses.items())),
        "by_assertion_rung": dict(sorted(rungs.items())),
        "verified": 0,
        "written_to_committed_registry": False,
    }


def gridded_source(
    *,
    provider: str,
    native_identifier: str,
    title: str,
    source_uri: str,
    sha256: str,
    retrieved_utc: str,
    published_date: str | None,
    survey_date: str | None,
    lineage_root_id: str | None,
    parent_source_ids: tuple[str, ...] = (),
    sensor_type: Any = None,
) -> SourceManifestation:
    """A held, hashed gridded elevation product as a registered source.

    It is a grid, so it is registered but is not a direct measurement.
    """

    from gebco.marine_evidence import CoverageState, ProductStage  # noqa: PLC0415

    from .namespaces import source_id as make_source_id  # noqa: PLC0415
    from .vocabulary import ProvenanceState  # noqa: PLC0415

    return SourceManifestation(
        source_id=make_source_id(provider, native_identifier, source_uri, sha256),
        provider=provider,
        title=title,
        native_identifier=native_identifier,
        source_uri=source_uri,
        manifestation_sha256=sha256,
        retrieved_utc=retrieved_utc,
        published_date=published_date,
        survey_date=survey_date,
        lineage_root_id=lineage_root_id,
        parent_source_ids=parent_source_ids,
        product_stage=ProductStage.GRID,
        sensor_type=sensor_type,
        coverage_state=CoverageState.INTERPOLATED,
        provenance_state=ProvenanceState.REGISTERED,
        license_note="US_GOVERNMENT_PUBLIC_DOMAIN",
    )


def wide_summary(
    result: SurveyResult, *, lonlat: tuple[float, float], deep_m: float
) -> dict[str, Any]:
    """A compact account of a larger window: how many basins, how deep, how near.

    Used for a window too large to keep in the repository.  It answers one
    question -- is there a deep closed basin anywhere near this point? -- and
    is reproducible only from the held, hashed product.
    """

    near = nearest_detections(result, lonlat=lonlat, limit=len(result.detections))
    by_id = {row["native_record_id"]: row for row in near["nearest"]}
    deep = [
        {
            "native_record_id": d.native_record_id,
            "max_depth_m": round(d.region.max_depth_m, 2),
            "area_m2": round(d.region.area_m2, 1),
            "distance_to_point_m": by_id[d.native_record_id][
                "distance_to_deepest_point_m"
            ],
            "adjoins_edge": d.region.adjoins_edge,
        }
        for d in result.detections
        if d.region is not None and d.region.max_depth_m >= deep_m
    ]
    deep.sort(key=lambda r: r["distance_to_point_m"])
    depths = [d.region.max_depth_m for d in result.detections if d.region is not None]
    valid = float(np.isfinite(result.grid.values).mean())
    return {
        "shape": list(result.grid.shape),
        "valid_cell_fraction": round(valid, 4),
        "detection_count": len(result.detections),
        "deepest_m": round(max(depths), 2) if depths else None,
        "deep_threshold_m": deep_m,
        "deep_basins": len(deep),
        "nearest_deep_basins": deep[:5],
        "point_inside_any_basin_bbox": near["inside_any_basin_bbox"],
        "note": (
            "a basin cut by the window edge or by an area the product does not "
            "cover is not closed inside the window and is not reported; absence "
            "here is absence of a basin closed within the covered part"
        ),
    }


# -- gridded bathymetry ----------------------------------------------------


def horizontal_crs(crs: Any) -> str:
    """The horizontal part of a product's CRS, as an EPSG string.

    Hydrographic grids often carry a compound system -- a projected CRS plus a
    vertical one.  Only the horizontal part is used to place cells; the
    vertical part is bound separately, from what the product states.
    """

    import re  # noqa: PLC0415

    code = crs.to_epsg()
    if code is not None:
        return f"EPSG:{code}"
    match = re.search(
        r'PROJCS\[.*?AUTHORITY\["EPSG","(\d+)"\]\]\s*,\s*VERT_CS', crs.to_wkt(), re.S
    )
    if match is None:
        raise SurveyReadError("the product's horizontal CRS cannot be determined")
    return f"EPSG:{match.group(1)}"


@dataclass(frozen=True)
class DepthGrid:
    """A gridded seabed surface with the uncertainty the product publishes."""

    window: RasterWindow  # elevation, metres, positive up (negative below datum)
    uncertainty: np.ndarray  # metres, per cell; NaN where not published
    facts: dict[str, Any]


def _two_bands(src: Any) -> tuple[np.ndarray, np.ndarray, str, tuple[float, float]]:
    rasterio = _rasterio()
    if src.count != 2:
        raise SurveyReadError(
            "a depth grid must hold an elevation and an uncertainty band"
        )
    crs = horizontal_crs(src.crs)
    plane = rasterio.crs.CRS.from_string(crs)
    transform = src.transform
    if not plane.is_projected or abs(plane.linear_units_factor[1] - 1.0) > 1e-9:
        raise SurveyReadError("the depth grid must be on a projected CRS in metres")
    if transform.b != 0 or transform.d != 0 or transform.e >= 0 or transform.a <= 0:
        raise SurveyReadError("the depth grid must be north-up with no rotation")
    elevation = _to_array(src.read(1), src.nodatavals[0])
    uncertainty = _to_array(src.read(2), src.nodatavals[1])
    uncertainty[~np.isfinite(elevation)] = np.nan
    return elevation, uncertainty, crs, (float(transform.a), float(-transform.e))


RESAMPLE_POPULATION = "MEAN"


def read_depth_grid(path: str | Path, resolution_m: float | None = None) -> DepthGrid:
    """Read a hydrographic product (or a subset written from one).

    Values come out exactly as the product holds them: elevation in metres,
    positive up, so the seabed is negative.

    Without ``resolution_m`` this is the product's base grid; for a
    variable-resolution product that is its low-resolution layer, and its
    finer grids are not read.

    With ``resolution_m`` the finer grids of a variable-resolution survey file
    (BAG) are read onto a regular grid of that cell size by GDAL's resampled
    mode: each cell holds the mean elevation of the finer-grid nodes that fall
    inside it and the *largest* of their uncertainties, and a cell with no node
    stays empty.  Nothing is interpolated.  Any other kind of file is refused.
    (GDAL's behaviour was checked against the nodes; see
    :func:`verify_resampled`.)
    """

    rasterio = _rasterio()
    import re  # noqa: PLC0415

    options: dict[str, Any] = {}
    if resolution_m is not None:
        if not (math.isfinite(resolution_m) and resolution_m > 0):
            raise SurveyReadError("resolution_m must be a positive number")
        with rasterio.open(path) as probe:
            if probe.driver != "BAG":
                raise SurveyReadError(
                    "only a variable-resolution bathymetric survey file (BAG) has "
                    "finer grids to read at another resolution"
                )
        options = {
            "MODE": "RESAMPLED_GRID",
            "RESX": float(resolution_m),
            "RESY": float(resolution_m),
            "VALUE_POPULATION": RESAMPLE_POPULATION,
        }
    with rasterio.open(path, **options) as src:
        elevation, uncertainty, crs, cell = _two_bands(src)
        tags = src.tags()
        metadata = (
            " ".join(src.tags(ns="xml:BAG").values()) if src.driver == "BAG" else ""
        )
        window = RasterWindow(
            values=elevation,
            crs=crs,
            origin=(float(src.transform.c), float(src.transform.f)),
            cell_size=cell,
            row_off=0,
            col_off=0,
            source_shape=(src.height, src.width),
            source_nodata=src.nodatavals[0],
        )
        facts = {
            "driver": src.driver,
            "band_descriptions": list(src.descriptions),
            "compound_crs_name": (src.crs.to_wkt().split('"')[1] if src.crs else None),
            "vertical_statements_in_metadata": sorted(
                set(re.findall(r'VERT_DATUM\["([^"]+)"', metadata))
            ),
            "format_version": tags.get("BagVersion"),
            "product_datetime": tags.get("BAG_DATETIME"),
            "refinement_resolution_m": (
                [float(tags["MIN_RESOLUTION_X"]), float(tags["MAX_RESOLUTION_X"])]
                if "MIN_RESOLUTION_X" in tags and "MAX_RESOLUTION_X" in tags
                else None
            ),
        }
        if resolution_m is not None:
            facts["grid_read"] = "finer grids, resampled"
            facts["resampled_cell_m"] = float(resolution_m)
            facts["value_population"] = RESAMPLE_POPULATION
            facts["population_meaning"] = (
                "each cell holds the mean elevation of the finer-grid nodes inside "
                "it and the largest of their uncertainties; a cell with no node is "
                "empty; nothing is interpolated"
            )
    return DepthGrid(window, uncertainty, facts)


# -- the finer grids of a variable-resolution survey file -----------------


def _supergrids(path: str | Path) -> list[str]:
    rasterio = _rasterio()
    with rasterio.open(path, MODE="LIST_SUPERGRIDS") as src:
        return sorted(src.subdatasets)


def finer_grid_spacing(path: str | Path) -> RasterWindow:
    """Node spacing of the finer grid under each base cell, as a base-aligned grid.

    A variable-resolution survey file holds, for each covered cell of its base
    grid, one finer grid with its own node spacing.  This returns a grid of
    the base grid's shape whose value is that spacing in metres, and NaN where
    the base cell has no finer grid.
    """

    rasterio = _rasterio()
    with rasterio.open(path) as base:
        if base.driver != "BAG":
            raise SurveyReadError("only a BAG file has finer grids")
        crs = horizontal_crs(base.crs)
        west, north = float(base.transform.c), float(base.transform.f)
        cell = float(base.transform.a)
        shape = (base.height, base.width)
        nodata = base.nodatavals[0]
    spacing = np.full(shape, np.nan)
    for name in _supergrids(path):
        with rasterio.open(name) as sub:
            t = sub.transform
            cx = t.c + sub.width * t.a / 2.0
            cy = t.f + sub.height * t.e / 2.0
            row = int((north - cy) // cell)
            col = int((cx - west) // cell)
            if not (0 <= row < shape[0] and 0 <= col < shape[1]):
                raise SurveyReadError(
                    f"a finer grid lies outside the base grid: {name}"
                )
            if np.isfinite(spacing[row, col]):
                raise SurveyReadError("two finer grids claim one base cell")
            spacing[row, col] = float(t.a)
    return RasterWindow(
        values=spacing,
        crs=crs,
        origin=(west, north),
        cell_size=(cell, cell),
        row_off=0,
        col_off=0,
        source_shape=shape,
        source_nodata=nodata,
    )


def verify_resampled(path: str | Path, grid: DepthGrid) -> dict[str, Any]:
    """Recompute every cell of a resampled grid from the finer-grid nodes.

    Every node of every finer grid is put in the cell its position falls in
    (a finer grid may reach past its own base cell, so a cell can receive
    nodes from two of them).  Each cell's mean elevation and largest
    uncertainty are recomputed and compared with the grid GDAL produced; a
    cell that receives no node must be empty there, and the reverse.

    A node lying exactly on a cell edge may be put on either side by the two
    computations; such cells are counted separately rather than hidden.
    """

    rasterio = _rasterio()
    window = grid.window
    fine = window.cell_size[0]
    west, north = window.origin
    rows_n, cols_n = window.shape
    z_sum = np.zeros(window.shape)
    u_max = np.full(window.shape, -np.inf)
    count = np.zeros(window.shape, dtype=np.int64)
    on_edge = np.zeros(window.shape, dtype=bool)
    nodes = outside = 0
    for name in _supergrids(path):
        with rasterio.open(name) as sub:
            t = sub.transform
            nd = sub.nodatavals[0]
            elevation = sub.read(1).astype(np.float64)
            uncertainty = sub.read(2).astype(np.float64)
        rr, cc = np.nonzero((elevation != nd) & np.isfinite(elevation))
        if not rr.size:
            continue
        x = t.c + (cc + 0.5) * t.a
        y = t.f + (rr + 0.5) * t.e
        fr = (north - y) / fine
        fc = (x - west) / fine
        r = np.floor(fr).astype(np.int64)
        c = np.floor(fc).astype(np.int64)
        inside = (r >= 0) & (r < rows_n) & (c >= 0) & (c < cols_n)
        outside += int((~inside).sum())
        r, c = r[inside], c[inside]
        z = elevation[rr[inside], cc[inside]]
        u = uncertainty[rr[inside], cc[inside]]
        edge = (np.abs(fr[inside] - np.round(fr[inside])) < 1e-6) | (
            np.abs(fc[inside] - np.round(fc[inside])) < 1e-6
        )
        np.add.at(z_sum, (r, c), z)
        np.maximum.at(u_max, (r, c), u)
        np.add.at(count, (r, c), 1)
        on_edge[r[edge], c[edge]] = True
        nodes += int(inside.sum())
    mine = count > 0
    theirs = np.isfinite(window.values)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(mine, z_sum / np.maximum(count, 1), np.nan)
    both = mine & theirs
    differs = both & (
        (np.abs(window.values - mean) > 1e-3)
        | (np.abs(grid.uncertainty - np.where(mine, u_max, np.nan)) > 1e-3)
    )
    presence = mine != theirs
    unexplained = (differs | presence) & ~on_edge
    near_edge = (differs | presence) & on_edge
    return {
        "nodes_placed": nodes,
        "nodes_outside_grid": outside,
        "cells_with_nodes": int(mine.sum()),
        "cells_with_values_in_resampled_grid": int(theirs.sum()),
        "cells_holding_several_nodes": int((count > 1).sum()),
        "cells_agreeing": int((both & ~differs).sum()),
        "cells_disagreeing_with_a_node_on_a_cell_edge": int(near_edge.sum()),
        "cells_disagreeing_otherwise": int(unexplained.sum()),
        "all_agree_except_edge_nodes": int(unexplained.sum()) == 0 and nodes > 0,
        "method": (
            "every node of every finer grid is put in the cell its position falls "
            "in; each cell's mean elevation and largest uncertainty are recomputed "
            "and must match the resampled grid to 1 mm, and a cell with no node "
            "must be empty there; a node exactly on a cell edge may fall on either "
            "side, and such cells are counted apart"
        ),
    }


def _base_cells(
    window: RasterWindow, spacing: RasterWindow, rows: slice, cols: slice
) -> tuple[slice, slice]:
    ratio = spacing.cell_size[0] / window.cell_size[0]
    return (
        slice(int(rows.start // ratio), int((rows.stop - 1) // ratio) + 1),
        slice(int(cols.start // ratio), int((cols.stop - 1) // ratio) + 1),
    )


def check_alignment(window: RasterWindow, spacing: RasterWindow) -> None:
    ratio = spacing.cell_size[0] / window.cell_size[0]
    if (
        window.origin != spacing.origin
        or abs(ratio - round(ratio)) > 1e-9
        or window.shape[0] != spacing.shape[0] * round(ratio)
        or window.shape[1] != spacing.shape[1] * round(ratio)
    ):
        raise SurveyReadError(
            "the resampled grid does not nest exactly inside the base grid"
        )


def empty_within_covered(window: RasterWindow, spacing: RasterWindow) -> dict[str, Any]:
    """How many resampled cells inside covered base cells received no node.

    Such a cell is empty, and an empty cell is an outlet: it can only stop a
    depression from being closed, never make one.
    """

    check_alignment(window, spacing)
    ratio = round(spacing.cell_size[0] / window.cell_size[0])
    covered = np.kron(np.isfinite(spacing.values), np.ones((ratio, ratio), bool))
    inside = int(covered.sum())
    empty = int((covered & ~np.isfinite(window.values)).sum())
    return {
        "cells_inside_covered_base_cells": inside,
        "empty_cells_inside_covered_base_cells": empty,
        "empty_fraction": round(empty / inside, 4) if inside else None,
        "meaning": (
            "an empty cell is an outlet: it can only stop a depression from being "
            "closed, never make one"
        ),
    }


def spacing_summary(spacing: RasterWindow) -> dict[str, Any]:
    values = spacing.values[np.isfinite(spacing.values)]
    bins = [0.0, 4.0, 8.0, 16.0, 32.0, math.inf]
    labels = ["under 4 m", "4 to 8 m", "8 to 16 m", "16 to 32 m", "32 m or more"]
    counts, _ = np.histogram(values, bins=bins)
    return {
        "finer_grids": int(values.size),
        "node_spacing_m": _summary(values),
        "finer_grids_by_node_spacing": dict(zip(labels, (int(c) for c in counts))),
    }


def finer_grid_context(
    rows: list[dict[str, Any]],
    window: RasterWindow,
    spacing: RasterWindow,
) -> list[dict[str, Any]]:
    """For each detection, the finer grids it was read from.

    A depression smaller than one base cell that sits on a single finer grid,
    or on the boundary between two finer grids of different node spacing, is
    where a gridding seam would show.  It is flagged as a possible artefact.
    The flag is informational and lowers no tier.

    Node spacing differs between almost every pair of finer grids, so in
    practice every depression smaller than one base cell is flagged.  The
    region it is read from is its bounding box.
    """

    check_alignment(window, spacing)
    west, north = window.origin
    fine = window.cell_size[0]
    base_area = spacing.cell_size[0] * spacing.cell_size[1]
    out: list[dict[str, Any]] = []
    for row in rows:
        bw, bs, be, bn = row["bbox_xy"]
        r0 = int(round((north - bn) / fine))
        r1 = int(round((north - bs) / fine))
        c0 = int(round((bw - west) / fine))
        c1 = int(round((be - west) / fine))
        rs, cs = _base_cells(window, spacing, slice(r0, r1), slice(c0, c1))
        under = spacing.values[rs, cs]
        found = sorted({round(float(v), 2) for v in under[np.isfinite(under)]})
        spanned = int(np.isfinite(under).sum())
        change = len(found) > 1
        small = row["area_m2"] < base_area
        out.append(
            {
                "finer_grid_node_spacing_m": (
                    {"min": found[0], "max": found[-1]} if found else None
                ),
                "distinct_node_spacings": len(found),
                "base_cells_spanned": spanned,
                "spans_node_spacing_change": change,
                "smaller_than_one_base_cell": small,
                "possible_refinement_artefact": bool(
                    small and (spanned <= 1 or change)
                ),
            }
        )
    return out


def persistence(
    earlier: list[dict[str, Any]],
    later: list[dict[str, Any]],
    *,
    distance_m: float,
) -> dict[str, Any]:
    """Does each earlier depression appear again on a finer reading?

    The rule, fixed before the finer reading was run:

    * SPLIT: two or more later outer depressions have their deepest point
      inside the earlier one's bounding box;
    * PERSISTED: otherwise, a later depression's deepest point lies within
      ``distance_m`` of the earlier one's and their depths agree within the
      combined depth uncertainty;
    * SAME_PLACE_DEPTH_DIFFERS: a later deepest point lies that close, but
      the depths do not agree;
    * NOT_FOUND: no later deepest point lies that close.

    Both readings come from the same soundings, so this is a consistency
    check, not replication.
    """

    def distance(a: list[float], b: list[float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    matched_later: set[str] = set()
    rows = []
    for old in earlier:
        bw, bs, be, bn = old["bbox_xy"]
        inside = [
            new
            for new in later
            if new.get("hierarchy_level", 0) == 0
            and bw <= new["deepest_xy"][0] <= be
            and bs <= new["deepest_xy"][1] <= bn
        ]
        near = [
            new
            for new in later
            if distance(old["deepest_xy"], new["deepest_xy"]) <= distance_m
        ]
        agreeing = []
        for new in near:
            u_old = old.get("depth_uncertainty_m")
            u_new = new.get("depth_uncertainty_m")
            if u_old is None or u_new is None:
                continue
            if abs(new["max_depth_m"] - old["max_depth_m"]) <= math.hypot(u_old, u_new):
                agreeing.append(new)
        if len(inside) >= 2:
            status = "SPLIT"
            linked = inside
        elif agreeing:
            status = "PERSISTED"
            linked = agreeing
        elif near:
            status = "SAME_PLACE_DEPTH_DIFFERS"
            linked = near
        else:
            status = "NOT_FOUND"
            linked = []
        matched_later.update(new["native_record_id"] for new in linked)
        rows.append(
            {
                "earlier": old["native_record_id"],
                "earlier_max_depth_m": old["max_depth_m"],
                "status": status,
                "later": [
                    {
                        "native_record_id": new["native_record_id"],
                        "max_depth_m": new["max_depth_m"],
                        "distance_between_deepest_points_m": round(
                            distance(old["deepest_xy"], new["deepest_xy"]), 1
                        ),
                    }
                    for new in sorted(linked, key=lambda n: -n["max_depth_m"])
                ],
            }
        )
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    new_rows = [new for new in later if new["native_record_id"] not in matched_later]
    return {
        "rule": (
            "SPLIT if two or more later outer depressions have their deepest point "
            "inside the earlier bounding box; else PERSISTED if a later deepest "
            f"point lies within {distance_m:g} m and the depths agree within the "
            "combined depth uncertainty; else SAME_PLACE_DEPTH_DIFFERS if one lies "
            "that close; else NOT_FOUND"
        ),
        "distance_m": distance_m,
        "by_status": dict(sorted(statuses.items())),
        "earlier": rows,
        "later_not_linked_to_any_earlier": len(new_rows),
        "later_not_linked_deepest_m": (
            round(max(n["max_depth_m"] for n in new_rows), 3) if new_rows else None
        ),
        "limit": (
            "both readings come from the same soundings: a consistency check, "
            "not replication"
        ),
    }


def write_depth_subset(grid: DepthGrid, path: str | Path) -> str:
    """Write a depth grid as a lossless two-band GeoTIFF; return its SHA-256."""

    rasterio = _rasterio()
    from rasterio.transform import from_origin  # noqa: PLC0415

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    nodata = 1000000.0
    window = grid.window
    bands = [
        np.where(np.isfinite(band), band, nodata).astype(np.float32)
        for band in (window.values, grid.uncertainty)
    ]
    rows, cols = bands[0].shape
    with rasterio.open(
        target,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=2,
        dtype="float32",
        crs=window.crs,
        transform=from_origin(
            window.origin[0], window.origin[1], window.cell_size[0], window.cell_size[1]
        ),
        nodata=nodata,
        compress="deflate",
        predictor=3,
        zlevel=9,
    ) as dst:
        dst.write(bands[0], 1)
        dst.write(bands[1], 2)
        dst.set_band_description(1, "elevation")
        dst.set_band_description(2, "uncertainty")
    return sha256_file(target)


def to_seabed(
    grid: DepthGrid, *, vertical_reference: VerticalReference, source_id: str
) -> SurfaceGrid:
    """A measured seabed surface with its per-cell uncertainty.

    Fails closed if the values are not overwhelmingly below their datum: a
    grid declared submerged that sits above it has its sign wrong.
    """

    window = grid.window
    return make_grid(
        window.values,
        cell_size_m=window.cell_size,
        origin=window.origin,
        crs=window.crs,
        kind=SurfaceKind.BATHYMETRY,
        vertical_reference=vertical_reference,
        uncertainty_m=np.where(np.isfinite(grid.uncertainty), grid.uncertainty, np.nan),
        source_id=source_id,
        expect="submerged",
    )


def _summary(values: np.ndarray) -> dict[str, Any] | None:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return None
    return {
        "min": round(float(finite.min()), 3),
        "median": round(float(np.median(finite)), 3),
        "p90": round(float(np.percentile(finite, 90)), 3),
        "max": round(float(finite.max()), 3),
    }


def lonlat_extent(grid: DepthGrid) -> dict[str, Any]:
    """Where the grid and its covered cells lie, as longitude/latitude boxes.

    The boxes are envelopes of cell corners.  They describe the *survey*, not
    any feature: they say where the product has data.
    """

    window = grid.window
    west, south, east, north = window.bounds()
    corners = _lonlat(
        window.crs, [west, east, east, west], [south, south, north, north]
    )
    out: dict[str, Any] = {
        "grid_bbox_lonlat": [
            min(c[0] for c in corners),
            min(c[1] for c in corners),
            max(c[0] for c in corners),
            max(c[1] for c in corners),
        ],
        "covered_bbox_lonlat": None,
    }
    rows, cols = np.nonzero(np.isfinite(window.values))
    if rows.size:
        dx, dy = window.cell_size
        x0 = west + float(cols.min()) * dx
        x1 = west + float(cols.max() + 1) * dx
        y1 = north - float(rows.min()) * dy
        y0 = north - float(rows.max() + 1) * dy
        covered = _lonlat(window.crs, [x0, x1, x1, x0], [y0, y0, y1, y1])
        out["covered_bbox_lonlat"] = [
            min(c[0] for c in covered),
            min(c[1] for c in covered),
            max(c[0] for c in covered),
            max(c[1] for c in covered),
        ]
    return out


def process_seabed(
    grid: DepthGrid,
    source: SourceManifestation,
    *,
    vertical_reference: VerticalReference,
    parameters: DetectionParameters,
) -> SurveyResult:
    """Delineate and describe closed depressions in one gridded seabed surface.

    The uncertainty used is the product's own, cell by cell, and it sets what
    can be seen.  A cell counts as part of a depression only where the water
    depth above it exceeds the uncertainty of a difference of two of its
    heights (the square root of two times its own uncertainty), so:

    * a depression that nowhere exceeds that floor is **not reported at all**;
    * one that exceeds it, but by less than the significance floor, is flagged
      and stays a candidate;
    * the reported area is the part above the floor, so it is a lower bound.

    Where the product's uncertainty is large, the absence of a detection is
    therefore not the absence of a depression.  ``sensitivity`` in the report
    says how much of the survey that applies to.
    """

    surface = to_seabed(
        grid, vertical_reference=vertical_reference, source_id=source.source_id
    )
    detections = detect_offshore(surface, source, parameters)
    lonlats = _lonlat(
        surface.crs,
        [d.centroid_xy[0] for d in detections],
        [d.centroid_xy[1] for d in detections],
    )
    cover = coverage(surface)
    tiers: dict[str, int] = {}
    for detection in detections:
        for assertion in detection.assertions:
            tiers[assertion.tier.name] = tiers.get(assertion.tier.name, 0) + 1
    rows = []
    for detection, lonlat in zip(detections, lonlats):
        row = _detection_row(detection, lonlat)
        row["hierarchy_level"] = detection.hierarchy_level
        row["parent_native_record_id"] = detection.parent_native_record_id
        region = detection.region
        assert region is not None
        row["depth_to_diameter"] = round(region.depth_to_diameter, 5)
        row["mean_wall_slope_deg"] = (
            None
            if region.mean_wall_slope_deg is None
            else round(region.mean_wall_slope_deg, 3)
        )
        row["flat_floor_fraction"] = (
            None
            if region.flat_floor_fraction is None
            else round(region.flat_floor_fraction, 3)
        )
        rows.append(row)
    # The same surface with its uncertainty ignored: every closed low of the
    # minimum depth and area, whether or not it can be told apart from noise.
    # It is a check on the detector, not evidence: it shows what the
    # uncertainty rule withheld, and that the reported depressions are not an
    # effect of that rule.
    reported = {
        tuple(round(v, 3) for v in d.region.deepest_xy)
        for d in detections
        if d.region is not None
    }
    unfloored = delineate_depressions(
        surface,
        min_depth_m=parameters.min_depth_m,
        min_area_m2=parameters.min_area_m2,
        max_regions=parameters.max_regions,
        nested=parameters.nested,
        nested_level_step_m=parameters.nested_level_step_m,
        footprint_min_depth_m=0.0,
    )
    withheld = [
        {
            "deepest_xy": [round(v, 3) for v in region.deepest_xy],
            "max_depth_m": round(region.max_depth_m, 3),
            "area_m2": round(region.area_m2, 1),
            "depth_uncertainty_m": (
                None
                if region.depth_uncertainty_m is None
                else round(region.depth_uncertainty_m, 4)
            ),
        }
        for region in unfloored
        if tuple(round(v, 3) for v in region.deepest_xy) not in reported
    ]
    ignoring = {
        "closed_depressions": len(unfloored),
        "also_reported_by_the_detector": len(unfloored) - len(withheld),
        "withheld_by_the_uncertainty_rule": withheld,
        "meaning": (
            "closed lows of the minimum depth and area when the product's "
            "uncertainty is ignored; a check on the detector, not evidence"
        ),
    }
    elevation = _summary(surface.values)
    floor = math.sqrt(2.0) * grid.uncertainty
    known = np.isfinite(floor)
    covered = int(np.isfinite(surface.values).sum())
    sensitivity = {
        "cell_depth_floor_m": _summary(floor),
        "floor_is": (
            "the square root of two times a cell's own uncertainty: the least "
            "water depth at which the cell counts as part of a depression"
        ),
        "covered_cells": covered,
        "cells_with_published_uncertainty": int(known.sum()),
        "cells_where_min_depth_is_resolvable": int(
            (floor[known] <= parameters.min_depth_m).sum()
        ),
        "cells_where_floor_exceeds_min_depth": int(
            (floor[known] > parameters.min_depth_m).sum()
        ),
        "meaning": (
            "where the floor exceeds the minimum depth, a depression of the "
            "minimum depth cannot be reported; absence of a detection there "
            "is not absence of a depression"
        ),
    }
    report = {
        "source_id": source.source_id,
        "surface": {
            "kind": surface.kind.value,
            "crs": surface.crs,
            "shape": list(surface.shape),
            "cell_size_m": list(surface.cell_size_m),
            "origin": [round(v, 6) for v in surface.origin],
            "bounds": [round(v, 6) for v in grid.window.bounds()],
            "valid_cells": cover.valid_cells,
            "nodata_cells": cover.nodata_cells,
            "elevation_min_m": None if elevation is None else elevation["min"],
            "elevation_max_m": None if elevation is None else elevation["max"],
            "elevation_median_m": None if elevation is None else elevation["median"],
            "cell_uncertainty_m": _summary(grid.uncertainty),
            "uncertainty_basis": "the product's own per-cell uncertainty band",
        },
        "parameters": {
            "min_depth_m": parameters.min_depth_m,
            "min_area_m2": parameters.min_area_m2,
            "significance_floor": parameters.significance_floor,
            "nested": parameters.nested,
            "nested_level_step_m": parameters.nested_level_step_m,
        },
        "sensitivity": sensitivity,
        "ignoring_uncertainty": ignoring,
        "detection_count": len(detections),
        "below_uncertainty": sum(
            1 for row in rows if "BELOW_UNCERTAINTY" in row["flags"]
        ),
        "possible_artifacts": sum(1 for d in detections if d.possible_artifact),
        "assertions_by_tier": dict(sorted(tiers.items())),
        "detections": rows,
    }
    return SurveyResult(surface, tuple(detections), report)
