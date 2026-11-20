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

``rasterio`` is needed to read and write GeoTIFFs (the ``dem`` extra).  It is
imported lazily so the rest of the package does not depend on it.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from gebco.marine_evidence import VerticalReference

from .detection import Detection, DetectionParameters, detect_inland
from .models import HORIZONTAL_INTERCHANGE_CRS, SourceManifestation
from .raster import SurfaceGrid, SurfaceKind, coverage, make_grid
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
    result: SurveyResult, source: SourceManifestation, *, created_utc: str
) -> dict[str, Any]:
    """What a scratch inland registry would hold if these detections were filed.

    Nothing is written anywhere.  The point is to show that a real survey's
    detections pass the registry's own rules and where its ladder puts them.
    """

    from .models import Observation  # noqa: PLC0415
    from .namespaces import Namespace, observation_id  # noqa: PLC0415
    from .registry import AccessPointRegistry  # noqa: PLC0415
    from .rules import assertion_rung  # noqa: PLC0415
    from .vocabulary import GeometryBasis  # noqa: PLC0415

    registry = AccessPointRegistry(
        Namespace.ACCESS_POINT_INLAND, producer_identity="dry-run:survey"
    )
    registry.add_source(source)
    rungs: dict[str, int] = {}
    statuses: dict[str, int] = {}
    lonlats = _lonlat(
        result.grid.crs,
        [d.centroid_xy[0] for d in result.detections],
        [d.centroid_xy[1] for d in result.detections],
    )
    for detection, (lon, lat) in zip(result.detections, lonlats):
        oid = observation_id(
            Namespace.ACCESS_POINT_INLAND, source.source_id, detection.native_record_id
        )
        registry.add_observation(
            Observation(
                observation_id=oid,
                namespace=Namespace.ACCESS_POINT_INLAND,
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
        sensor_type=None,
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
