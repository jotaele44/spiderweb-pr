"""Scientific positive and negative controls for the shared processing core.

Surfaces are built in-test with numpy.  They verify the software; they are not
evidence about real terrain or seabed.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import LineString, Point, Polygon, box

from gebco.marine_evidence import (
    CoverageState,
    EvidenceState,
    MarineObservation,
    ProductStage,
    SensorType,
    VerticalCompatibilityError,
    VerticalReference,
    classify_feature_evidence,
    compare_depths,
)
from spiderweb.access_points import coastal, controls, detection, rules, transects
from spiderweb.access_points import models as m
from spiderweb.access_points import namespaces as ns
from spiderweb.access_points import raster as R
from spiderweb.access_points import vertical as V
from spiderweb.access_points import vocabulary as v
from tests import access_points_support as sup

CRS = "EPSG:32620"
PRVD = VerticalReference(CRS, None, "PRVD02", None, "up")
MLLW_DOWN = VerticalReference(CRS, None, None, "MLLW", "down")
PLACEHOLDERS = [
    "",
    "Unknown",
    "unknown",
    "Not Provided",
    "User Specified",
    "N/A",
    "n/a",
    "source_dependent",
    "Source Dependent",
    "None",
    "TBD",
    "various",
    None,
]


def land(values, **kw):
    kw.setdefault("uncertainty_m", 0.1)
    return R.make_grid(
        values,
        cell_size_m=(1.0, 1.0),
        origin=(0.0, float(values.shape[0])),
        crs=CRS,
        kind=kw.pop("kind", R.SurfaceKind.TERRAIN_BARE_EARTH),
        vertical_reference=kw.pop("vertical_reference", PRVD),
        **kw,
    )


def sea(elevation_up, **kw):
    """Build a bathymetric grid from elevations (positive up) published as depth."""

    kw.setdefault("uncertainty_m", 0.3)
    return R.make_grid(
        -elevation_up,
        cell_size_m=(2.0, 2.0),
        origin=(0.0, 2.0 * elevation_up.shape[0]),
        crs=CRS,
        kind=R.SurfaceKind.BATHYMETRY,
        vertical_reference=MLLW_DOWN,
        **kw,
    )


# ── Vertical datum contract ──────────────────────────────────────────────────


@pytest.mark.parametrize("value", PLACEHOLDERS)
def test_placeholder_datum_fails_closed_everywhere(value):
    assert V.is_placeholder(value)
    with pytest.raises(V.UnknownVerticalDatumError):
        V.normalize_datum(value)
    reference = VerticalReference(CRS, None, value, None, "down")
    with pytest.raises(V.UnknownVerticalDatumError):
        V.bind(reference)
    with pytest.raises(V.UnknownVerticalDatumError):
        R.make_grid(
            np.zeros((4, 4)),
            cell_size_m=(1, 1),
            origin=(0, 4),
            crs=CRS,
            kind=R.SurfaceKind.BATHYMETRY,
            vertical_reference=reference,
        )
    assert V.decide_join(PRVD, reference).state is V.JoinState.BLOCKED_UNKNOWN_DATUM
    assert not V.decide_join(PRVD, reference).may_difference
    with pytest.raises(V.UnknownVerticalDatumError):
        V.to_common_elevation_m(5.0, reference, V.VerticalDatum.PRVD02)


@pytest.mark.parametrize(
    "spelling, datum",
    [
        ("PRVD02", V.VerticalDatum.PRVD02),
        ("Puerto Rico Vertical Datum of 2002", V.VerticalDatum.PRVD02),
        ("MLLW", V.VerticalDatum.MLLW),
        ("Mean Lower Low Water", V.VerticalDatum.MLLW),
        ("Mean High Water", V.VerticalDatum.MHW),
        ("EPSG:5866", V.VerticalDatum.MLLW),
        ("EPSG:5715", V.VerticalDatum.MSL),
        ("EPSG:5703", V.VerticalDatum.NAVD88),
        ("mean_sea_level_assumed", V.VerticalDatum.MSL_ASSUMED),
    ],
)
def test_spellings_found_in_this_repository_resolve(spelling, datum):
    assert V.normalize_datum(spelling) is datum


def test_unrecognised_and_conflicting_references_fail_closed():
    with pytest.raises(V.UnknownVerticalDatumError):
        V.normalize_datum("Bogus Datum 1999")
    with pytest.raises(V.UnknownVerticalDatumError, match="conflicting"):
        V.bind(VerticalReference(CRS, None, "PRVD02", "MLLW", "up"))
    with pytest.raises(V.UnknownVerticalDatumError):
        V.bind(None)
    # An EPSG depth code declared positive-up contradicts itself (and vice versa).
    with pytest.raises(VerticalCompatibilityError):
        V.bind(VerticalReference(CRS, "EPSG:5866", None, None, "up"))
    with pytest.raises(VerticalCompatibilityError):
        V.bind(VerticalReference(CRS, "EPSG:6641", None, None, "down"))
    assert (
        V.bind(VerticalReference(CRS, "EPSG:5866", None, "MLLW", "down")).datum
        is V.VerticalDatum.MLLW
    )


def test_sign_is_normalised_exactly_once():
    assert V.elevation_up_m(12.5, MLLW_DOWN) == -12.5
    assert V.elevation_up_m(12.5, PRVD) == 12.5
    with pytest.raises(ValueError):
        V.elevation_up_m(float("nan"), PRVD)
    grid = sea(np.full((6, 6), -20.0))
    assert np.all(grid.values == -20.0) and grid.vertical.positive == "up"


def test_wrong_depth_sign_is_caught_not_analysed_upside_down():
    # Negative values published under a positive-down depth label: after sign
    # normalisation the "seabed" would sit above the datum.
    negative_values_labelled_depth = np.full((20, 20), -500.0)
    with pytest.raises(R.SignConventionError):
        R.make_grid(
            negative_values_labelled_depth,
            cell_size_m=(64, 64),
            origin=(0, 1280),
            crs=CRS,
            kind=R.SurfaceKind.BATHYMETRY,
            vertical_reference=MLLW_DOWN,
            expect="submerged",
        )
    ok = R.make_grid(
        -negative_values_labelled_depth,
        cell_size_m=(64, 64),
        origin=(0, 1280),
        crs=CRS,
        kind=R.SurfaceKind.BATHYMETRY,
        vertical_reference=MLLW_DOWN,
        expect="submerged",
    )
    assert float(ok.values.max()) == -500.0
    with pytest.raises(R.SignConventionError):
        land(np.full((10, 10), -30.0), expect="emergent")
    with pytest.raises(ValueError):
        land(np.zeros((4, 4)), expect="sideways")


def test_values_on_different_datums_need_a_certified_transform():
    with pytest.raises(VerticalCompatibilityError):
        V.to_common_elevation_m(8.0, MLLW_DOWN, V.VerticalDatum.PRVD02)
    transform = V.CertifiedTransform(
        V.VerticalDatum.MLLW,
        V.VerticalDatum.PRVD02,
        -0.25,
        "synthetic test authority",
        0.04,
    )
    moved = V.to_common_elevation_m(
        8.0,
        MLLW_DOWN,
        V.VerticalDatum.PRVD02,
        transforms=[transform],
        uncertainty_m=0.3,
    )
    assert moved.elevation_m == pytest.approx(-8.25)
    assert moved.uncertainty_m == pytest.approx(math.hypot(0.3, 0.04))
    assert moved.transform_authority == "synthetic test authority"
    unknown_part = V.to_common_elevation_m(
        8.0,
        MLLW_DOWN,
        V.VerticalDatum.PRVD02,
        transforms=[transform],
        uncertainty_m=None,
    )
    assert unknown_part.uncertainty_m is None  # unknown stays unknown, never 0
    assert V.combined_uncertainty_m(0.3, None) is None
    same = V.to_common_elevation_m(3.0, PRVD, V.VerticalDatum.PRVD02, uncertainty_m=0.1)
    assert same.elevation_m == 3.0 and same.transform_authority is None


def test_transform_must_be_real_unambiguous_and_in_range():
    make = lambda **kw: V.CertifiedTransform(  # noqa: E731
        **{
            "source": V.VerticalDatum.MLLW,
            "target": V.VerticalDatum.PRVD02,
            "offset_m": -0.2,
            "authority": "synthetic test authority",
            **kw,
        }
    )
    for bad in (
        {"authority": " "},
        {"authority": "Unknown"},
        {"target": V.VerticalDatum.MLLW},
        {"offset_m": float("inf")},
        {"uncertainty_m": -1.0},
        {"target": V.VerticalDatum.MSL_ASSUMED},
        {"valid_bbox": (1.0, 0.0, 0.0, 1.0)},
    ):
        with pytest.raises(ValueError):
            make(**bad)
    with pytest.raises(VerticalCompatibilityError, match="more than one"):
        V.to_common_elevation_m(
            8.0,
            MLLW_DOWN,
            V.VerticalDatum.PRVD02,
            transforms=[make(), make(offset_m=-0.3)],
        )
    local = make(valid_bbox=(-66.5, 17.8, -66.0, 18.2))
    assert V.to_common_elevation_m(
        8.0, MLLW_DOWN, V.VerticalDatum.PRVD02, transforms=[local], lon=-66.2, lat=18.0
    ).elevation_m == pytest.approx(-8.2)
    for where in ({"lon": -65.0, "lat": 18.0}, {}):
        with pytest.raises(VerticalCompatibilityError):
            V.to_common_elevation_m(
                8.0, MLLW_DOWN, V.VerticalDatum.PRVD02, transforms=[local], **where
            )
    assumed = VerticalReference(CRS, None, "mean_sea_level_assumed", None, "up")
    with pytest.raises(VerticalCompatibilityError):
        V.to_common_elevation_m(-10.0, assumed, V.VerticalDatum.MSL_ASSUMED)
    assert V.decide_join(PRVD, assumed).state is V.JoinState.SEPARATE_SURFACES_ONLY


@pytest.mark.parametrize("src_sign", ["up", "down"])
@pytest.mark.parametrize("dst_sign", ["up", "down"])
def test_transform_agrees_with_the_existing_depth_comparison(src_sign, dst_sign):
    transform = V.CertifiedTransform(
        V.VerticalDatum.MLLW, V.VerticalDatum.PRVD02, -0.25, "synthetic test authority"
    )
    source = V.BoundVertical(V.VerticalDatum.MLLW, src_sign, CRS)
    target = V.BoundVertical(V.VerticalDatum.PRVD02, dst_sign, CRS)
    value_b = 8.0 if src_sign == "down" else -8.0  # eight metres below MLLW
    value_a = 8.25 if dst_sign == "down" else -8.25  # the same point on PRVD02
    obs = lambda oid, val, ref: MarineObservation(  # noqa: E731
        oid,
        SensorType.MULTIBEAM_ECHOSOUNDER,
        ProductStage.PROCESSED_OBSERVATION,
        oid,
        ref,
        CoverageState.DIRECTLY_OBSERVED,
        value_m=val,
    )
    comparison = compare_depths(
        obs("a", value_a, target.to_reference()),
        obs("b", value_b, source.to_reference()),
        transforms=[transform.as_depth_transform(source, target)],
    )
    assert comparison.delta_b_minus_a_m == pytest.approx(0.0, abs=1e-12)


# ── Grid construction ────────────────────────────────────────────────────────


def test_grid_requires_crs_datum_and_sane_shape():
    with pytest.raises(R.MissingCRSError):
        R.make_grid(
            np.zeros((4, 4)),
            cell_size_m=(1, 1),
            origin=(0, 4),
            crs=None,
            kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
            vertical_reference=PRVD,
        )
    with pytest.raises(R.MissingCRSError):
        R.make_grid(
            np.zeros((4, 4)),
            cell_size_m=(1, 1),
            origin=(0, 4),
            crs="  ",
            kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
            vertical_reference=PRVD,
        )
    with pytest.raises(V.UnknownVerticalDatumError):
        R.make_grid(
            np.zeros((4, 4)),
            cell_size_m=(1, 1),
            origin=(0, 4),
            crs=CRS,
            kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
        )
    for bad in ({"cell_size_m": (0, 1)}, {"cell_size_m": (1, float("nan"))}):
        with pytest.raises(ValueError):
            R.make_grid(
                np.zeros((4, 4)),
                origin=(0, 4),
                crs=CRS,
                kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
                vertical_reference=PRVD,
                **bad,
            )
    with pytest.raises(ValueError):
        land(np.zeros(5))
    with pytest.raises(R.GridMismatchError):
        land(np.zeros((4, 4)), interpolated=np.zeros((3, 3), bool))
    grid = land(np.array([[1.0, -9999.0], [np.inf, 4.0]]), nodata=-9999.0)
    assert np.isnan(grid.values[0, 1]) and np.isnan(grid.values[1, 0])
    with pytest.raises(ValueError):
        grid.values[0, 0] = 5.0  # immutable


@pytest.mark.parametrize(
    "kind", [R.SurfaceKind.SIDESCAN_INTENSITY, R.SurfaceKind.BACKSCATTER_INTENSITY]
)
def test_intensity_raster_is_not_a_depth_surface(kind):
    image = R.make_grid(
        np.random.default_rng(1).random((30, 30)),
        cell_size_m=(1, 1),
        origin=(0, 30),
        crs=CRS,
        kind=kind,
    )
    assert not image.is_elevation
    for operation in (
        R.slope_degrees,
        R.fill_depressions,
        R.depression_depth,
        R.detect_seams,
        lambda g: R.position_index(g, 3),
        lambda g: R.local_relief(g, 2),
        R.hillshade,
        lambda g: R.delineate_depressions(g, min_depth_m=1, min_area_m2=1),
    ):
        with pytest.raises(R.NotAnElevationSurfaceError):
            operation(image)
    with pytest.raises(R.NotAnElevationSurfaceError):
        R.make_grid(
            np.zeros((4, 4)),
            cell_size_m=(1, 1),
            origin=(0, 4),
            crs=CRS,
            kind=kind,
            vertical_reference=PRVD,
        )
    with pytest.raises(R.NotAnElevationSurfaceError):
        transects.build_cross_section([image], [(0, 5), (20, 5)], spacing_m=1)


# ── Basin delineation controls ───────────────────────────────────────────────

FIND = dict(min_depth_m=0.5, min_area_m2=20.0)


@pytest.mark.parametrize(
    "surface",
    [
        controls.tilted_plane(120, 120),
        np.full((120, 120), 50.0),
        controls.tilted_plane(120, 120, slope_x=0.5, slope_y=-0.3),
        50.0
        + 10.0
        * np.exp(
            -(
                (
                    (np.mgrid[0:120, 0:120][0] - 60) ** 2
                    + (np.mgrid[0:120, 0:120][1] - 60) ** 2
                )
                / 400.0
            )
        ),
    ],
    ids=["tilted-plane", "flat", "steep-plane", "dome"],
)
def test_surfaces_without_basins_yield_none(surface):
    assert R.delineate_depressions(land(surface), **FIND) == []
    assert float(np.nanmax(R.depression_depth(land(surface)))) == pytest.approx(
        0.0, abs=1e-9
    )


@pytest.mark.parametrize("seed", range(5))
def test_noise_alone_yields_nothing_above_thresholds(seed):
    noisy = controls.add_noise(controls.tilted_plane(150, 150), sigma_m=0.05, seed=seed)
    assert R.delineate_depressions(land(noisy), **FIND) == []
    assert R.detect_seams(land(noisy)) == []


def test_planted_basin_is_found_once_where_it_was_put():
    surface = controls.add_gaussian_basin(
        np.full((200, 200), 100.0), 80.0, 120.0, depth_m=6.0, sigma_cells=9.0
    )
    regions = R.delineate_depressions(land(surface), **FIND)
    assert len(regions) == 1
    basin = regions[0]
    assert basin.max_depth_m == pytest.approx(6.0, abs=0.05)  # flat rim: spill at 100 m
    assert basin.spill_elevation_m == pytest.approx(100.0, abs=0.05)
    assert basin.floor_elevation_m == pytest.approx(94.0, abs=0.05)
    assert basin.deepest_xy == (120.5, 200.0 - 80.5)
    assert (
        abs(basin.centroid_xy[0] - 120.5) < 1.5
        and abs(basin.centroid_xy[1] - 119.5) < 1.5
    )
    analytic_volume = 6.0 * 2.0 * math.pi * 9.0**2
    assert basin.volume_m3 == pytest.approx(analytic_volume, rel=0.05)
    assert basin.circularity > 0.8 and basin.elongation < 1.2
    assert not basin.adjoins_edge and not basin.adjoins_nodata
    assert basin.depth_uncertainty_m == pytest.approx(math.sqrt(2) * 0.1)
    assert basin.significance == pytest.approx(
        basin.max_depth_m / basin.depth_uncertainty_m
    )


@pytest.mark.parametrize(
    "name, analytic_circularity, tolerance, rectangular",
    [
        ("disc", 1.0, 0.04, False),
        ("square", math.pi / 4, 0.13, True),
        ("bar", 0.503, 0.10, True),
    ],
)
def test_shape_measures_against_analytic_shapes(
    name, analytic_circularity, tolerance, rectangular
):
    yy, xx = np.mgrid[0:200, 0:200].astype(float)
    footprint = {
        "disc": (xx - 100) ** 2 + (yy - 100) ** 2 <= 900,
        "square": (abs(xx - 100) <= 30) & (abs(yy - 100) <= 30),
        "bar": (abs(xx - 100) <= 40) & (abs(yy - 100) <= 10),
    }[name]
    surface = np.full((200, 200), 100.0)
    surface[footprint] -= 5.0
    (basin,) = R.delineate_depressions(land(surface), **FIND)
    assert basin.area_m2 == float(footprint.sum())
    assert basin.max_depth_m == pytest.approx(5.0)
    assert basin.volume_m3 == pytest.approx(5.0 * footprint.sum())
    assert basin.circularity == pytest.approx(analytic_circularity, abs=tolerance)
    assert (basin.rectangularity >= detection.RECTANGULARITY_THRESHOLD) is rectangular
    (found,) = detection.detect_inland(land(surface), SOURCE, PARAMS)
    assert (found.proposed_class == "SURFACE_EXCAVATION") is rectangular


def test_tilt_lowers_the_spill_level_but_not_the_location():
    tilted = controls.add_gaussian_basin(
        controls.tilted_plane(200, 200, slope_x=0.03, slope_y=0.0),
        100.0,
        100.0,
        depth_m=6.0,
        sigma_cells=9.0,
    )
    (basin,) = R.delineate_depressions(land(tilted), **FIND)
    assert 2.0 < basin.max_depth_m < 6.0
    assert abs(basin.deepest_xy[0] - 100.5) < 6.0


def test_basin_that_could_drain_into_unmeasured_ground_is_not_reported():
    surface = controls.add_gaussian_basin(
        np.full((160, 160), 100.0), 80.0, 80.0, depth_m=6.0, sigma_cells=9.0
    )
    holed = controls.add_nodata_block(surface, 75, 75, 86, 86)  # floor never measured
    assert R.delineate_depressions(land(holed), **FIND) == []
    edge = controls.add_gaussian_basin(
        np.full((160, 160), 100.0), 80.0, 2.0, depth_m=6.0, sigma_cells=9.0
    )
    assert R.delineate_depressions(land(edge), **FIND) == []  # open to the grid edge
    nodata_far_away = controls.add_nodata_block(surface, 0, 0, 10, 10)
    assert len(R.delineate_depressions(land(nodata_far_away), **FIND)) == 1
    assert R.delineate_depressions(land(np.full((20, 20), np.nan)), **FIND) == []


def test_no_data_survives_every_derivative_and_coverage_closes():
    surface = controls.add_nodata_block(controls.tilted_plane(80, 80), 30, 30, 40, 40)
    mask = controls.interpolation_mask(surface.shape, 0, 0, 20, 80)
    grid = land(surface, interpolated=mask)
    for product in (
        R.slope_degrees(grid),
        R.position_index(grid, 4),
        R.local_relief(grid, 3),
        R.fill_depressions(grid),
        R.depression_depth(grid),
        R.hillshade(grid),
    ):
        assert np.all(np.isnan(product[30:40, 30:40]))
    summary = R.coverage(grid)
    assert summary.closes()
    assert summary.nodata_cells == 100 and summary.valid_cells == 6300
    assert summary.interpolated_cells == 1600 and summary.measured_cells == 4700
    unknown = R.coverage(land(surface))
    assert (
        unknown.measured_cells is None
        and unknown.measured_fraction is None
        and unknown.closes()
    )


def test_seam_is_found_with_its_axis_index_and_step():
    rough = controls.add_noise(controls.tilted_plane(200, 200), sigma_m=0.05, seed=4)
    (column_seam,) = R.detect_seams(
        land(controls.add_column_seam(rough, 130, step_m=0.8))
    )
    assert (column_seam.axis, column_seam.index) == ("column", 129)
    assert column_seam.step_m == pytest.approx(0.8 + 0.02, abs=0.05)
    assert column_seam.sign_consistency > 0.95
    row_step = rough.copy()
    row_step[70:, :] -= 1.5
    (row_seam,) = R.detect_seams(land(row_step))
    assert (row_seam.axis, row_seam.index) == ("row", 69)
    assert row_seam.step_m == pytest.approx(-1.5 + 0.01, abs=0.05)
    mask = R.seam_mask(land(rough), [column_seam])
    assert mask[:, 129:131].all() and not mask[:, :128].any()


def test_tiled_processing_equals_untiled_and_is_deterministic():
    surface = controls.add_noise(
        controls.karst_plateau_scene(noise_m=0.0)[0], sigma_m=0.02, seed=2
    )
    grid = land(surface)
    for operation, halo in (
        (R.slope_degrees, 2),
        (lambda g: R.position_index(g, 6), 7),
    ):
        whole = operation(grid)
        assert np.array_equal(whole, operation(grid), equal_nan=True)
        tiled = R.apply_tiled(grid, operation, tile=64, halo=halo)
        assert np.allclose(whole, tiled, equal_nan=True)
    seamless = R.apply_tiled(grid, lambda g: R.position_index(g, 6), tile=64, halo=0)
    assert not np.allclose(
        R.position_index(grid, 6), seamless, equal_nan=True
    )  # halo matters
    first = R.delineate_depressions(grid, **FIND)
    second = R.delineate_depressions(grid, **FIND)
    assert [(r.label, r.max_depth_m, r.area_m2) for r in first] == [
        (r.label, r.max_depth_m, r.area_m2) for r in second
    ]
    with pytest.raises(ValueError):
        list(R.iter_windows((10, 10), 0))


def test_coarsening_keeps_flags_and_never_reduces_uncertainty():
    values = controls.tilted_plane(64, 64)
    mask = controls.interpolation_mask(values.shape, 0, 0, 1, 1)
    sigma = np.full(values.shape, 0.1)
    sigma[10, 10] = 0.9
    coarse = R.coarsen(land(values, interpolated=mask, uncertainty_m=sigma), 4)
    assert coarse.shape == (16, 16) and coarse.cell_size_m == (4.0, 4.0)
    assert coarse.interpolated[0, 0] and not coarse.interpolated[5, 5]
    assert coarse.uncertainty_m[2, 2] == pytest.approx(0.9)
    assert float(coarse.uncertainty_m.min()) >= 0.1
    with pytest.raises(ValueError):
        R.coarsen(land(values), 1)


# ── Temporal comparison ──────────────────────────────────────────────────────


def test_surface_difference_controls():
    base = controls.tilted_plane(50, 50)
    earlier = land(base, uncertainty_m=0.05)
    same = R.difference(earlier, land(base, uncertainty_m=0.05))
    assert np.allclose(same.delta_m, 0.0) and not same.detectable.any()
    shifted = R.difference(earlier, land(base + 0.5, uncertainty_m=0.05))
    assert np.allclose(shifted.delta_m, 0.5) and shifted.detectable.all()
    assert shifted.uncertainty_m[0, 0] == pytest.approx(math.hypot(0.05, 0.05))
    noisy = R.difference(
        land(base, uncertainty_m=0.4), land(base + 0.5, uncertainty_m=0.4)
    )
    assert not noisy.detectable.any()  # 0.5 m is inside 2 sigma of 0.57 m
    unknown = R.difference(
        land(base, uncertainty_m=None), land(base + 0.5, uncertainty_m=None)
    )
    assert unknown.detectable is None and unknown.uncertainty_m is None
    assert unknown.compared_cells == 2500


def test_surface_difference_refuses_incomparable_grids():
    base = controls.tilted_plane(40, 40)
    a = land(base)
    with pytest.raises(R.GridMismatchError):
        R.difference(a, land(controls.tilted_plane(40, 41)))
    shifted_origin = R.make_grid(
        base,
        cell_size_m=(1, 1),
        origin=(0.5, 40.0),
        crs=CRS,
        kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=PRVD,
    )
    with pytest.raises(R.GridMismatchError):
        R.difference(a, shifted_origin)
    other_crs = R.make_grid(
        base,
        cell_size_m=(1, 1),
        origin=(0.0, 40.0),
        crs="EPSG:32619",
        kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=PRVD,
    )
    with pytest.raises(R.GridMismatchError):
        R.difference(a, other_crs)
    on_msl = land(
        base, vertical_reference=VerticalReference(CRS, None, "MSL", None, "up")
    )
    with pytest.raises(VerticalCompatibilityError):
        R.difference(a, on_msl)
    transform = V.CertifiedTransform(
        V.VerticalDatum.MSL,
        V.VerticalDatum.PRVD02,
        0.1,
        "synthetic test authority",
        0.02,
    )
    moved = R.difference(a, on_msl, transforms=[transform])
    assert (
        np.allclose(moved.delta_m, 0.1)
        and moved.transform_authority == "synthetic test authority"
    )
    assumed = land(
        base,
        vertical_reference=VerticalReference(
            CRS, None, "mean_sea_level_assumed", None, "up"
        ),
    )
    with pytest.raises(VerticalCompatibilityError):
        R.difference(assumed, assumed)


# ── Detection ────────────────────────────────────────────────────────────────

PARAMS = detection.DetectionParameters(min_depth_m=1.0, min_area_m2=30.0)
SOURCE = sup.direct_source("TEST-LIDAR-001", sensor=SensorType.TOPOBATHYMETRIC_LIDAR)
KARST = detection.GeologicalContext(
    "APSRC-" + "7" * 16, "synthetic limestone unit", True, v.SpatialState.FULLY_WITHIN
)


def _flat_scene():
    surface = np.full((260, 260), 120.0)
    surface = controls.add_gaussian_basin(
        surface, 70.0, 70.0, depth_m=6.0, sigma_cells=9.0
    )
    surface = controls.add_steep_pit(
        surface, 180.0, 70.0, depth_m=10.0, radius_cells=8.0
    )
    surface = controls.add_rectangular_cut(surface, 60, 170, 90, 230, floor_m=114.0)
    return controls.add_noise(surface, sigma_m=0.02, seed=6)


def test_inland_detection_finds_each_planted_feature_with_the_right_class():
    found = detection.detect_inland(land(_flat_scene()), SOURCE, PARAMS)
    assert len(found) == 3
    by_class = sorted(d.proposed_class for d in found)
    assert by_class == ["CLOSED_DEPRESSION", "CLOSED_DEPRESSION", "SURFACE_EXCAVATION"]
    cut = next(d for d in found if d.proposed_class == "SURFACE_EXCAVATION")
    assert 170 < cut.centroid_xy[0] < 230 and cut.region.rectangularity > 0.9
    origin = [
        a
        for a in cut.assertions
        if a.dimension is v.EvidenceDimension.NATURAL_OR_ARTIFICIAL_ORIGIN
    ]
    assert origin and origin[0].tier is v.EvidenceTier.CANDIDATE
    assert origin[0].claim_class is v.ClaimClass.HYPOTHESIS
    assert all(d.namespace is sup.INLAND and not d.flags for d in found)


def test_sinkhole_reading_needs_an_evidenced_karst_context():
    grid = land(_flat_scene())
    assert "SINKHOLE" not in {
        d.proposed_class for d in detection.detect_inland(grid, SOURCE, PARAMS)
    }
    with_karst = detection.detect_inland(grid, SOURCE, PARAMS, geology=KARST)
    assert sorted(d.proposed_class for d in with_karst).count("SINKHOLE") == 2
    assert "SURFACE_EXCAVATION" in {
        d.proposed_class for d in with_karst
    }  # the cut is still a cut
    for state in (
        v.SpatialState.PARTIAL,
        v.SpatialState.TOUCH_ONLY,
        v.SpatialState.OUTSIDE,
        v.SpatialState.UNRESOLVED,
        v.SpatialState.NULL_EMPTY,
    ):
        weak = detection.GeologicalContext(KARST.source_id, "unit", True, state)
        assert "SINKHOLE" not in {
            d.proposed_class
            for d in detection.detect_inland(grid, SOURCE, PARAMS, geology=weak)
        }
    not_karst = detection.GeologicalContext(
        KARST.source_id, "volcanic unit", False, v.SpatialState.FULLY_WITHIN
    )
    assert "SINKHOLE" not in {
        d.proposed_class
        for d in detection.detect_inland(grid, SOURCE, PARAMS, geology=not_karst)
    }


def test_offshore_detection_classes():
    surface, _ = controls.shelf_scene()
    found = detection.detect_offshore(
        sea(surface),
        SOURCE,
        detection.DetectionParameters(min_depth_m=1.0, min_area_m2=100.0),
    )
    classes = {d.proposed_class for d in found}
    assert classes == {"BLUE_HOLE_CANDIDATE", "SEAFLOOR_DEPRESSION"}
    pit = next(d for d in found if d.proposed_class == "BLUE_HOLE_CANDIDATE")
    assert "not established by shape" in pit.assertions[1].statement
    assert all(d.namespace is sup.OFFSHORE for d in found)


def test_detection_refuses_the_wrong_kind_of_surface():
    scene = _flat_scene()
    with pytest.raises(ValueError, match="bare-earth"):
        detection.detect_inland(
            land(scene, kind=R.SurfaceKind.TERRAIN_FIRST_RETURN), SOURCE, PARAMS
        )
    with pytest.raises(ValueError):
        detection.detect_inland(sea(-scene), SOURCE, PARAMS)
    with pytest.raises(ValueError):
        detection.detect_offshore(land(scene), SOURCE, PARAMS)
    with pytest.raises(ValueError):
        detection.detect_escarpments(
            land(scene), SOURCE, min_slope_deg=20, min_length_m=50
        )
    with pytest.raises(ValueError):
        detection.DetectionParameters(min_depth_m=0, min_area_m2=1)


def test_detection_never_claims_an_opening_whatever_the_score():
    surface, _ = controls.shelf_scene()
    found = detection.detect_offshore(
        sea(surface),
        SOURCE,
        detection.DetectionParameters(min_depth_m=1.0, min_area_m2=100.0),
    )
    found += detection.detect_inland(land(_flat_scene()), SOURCE, PARAMS, geology=KARST)
    forbidden = {
        v.EvidenceDimension.PHYSICAL_OPENING,
        v.EvidenceDimension.ACCESSIBILITY,
        v.EvidenceDimension.FUNCTION,
        v.EvidenceDimension.CONNECTIVITY,
    }
    assert max(d.discovery_score for d in found) > 90
    held = {SOURCE.source_id: SOURCE}
    for d in found:
        assert not forbidden & {a.dimension for a in d.assertions}
        feature = m.Feature(
            ns.feature_id(d.namespace, 1),
            d.namespace,
            d.proposed_class,
            assertions=tuple(a for a in d.assertions if set(a.source_ids) <= set(held)),
        )
        assert rules.assertion_rung(feature, held) <= v.AssertionRung.FEATURE


def test_artefact_flags_lower_the_tier_and_the_score():
    surface = controls.add_gaussian_basin(
        np.full((160, 160), -30.0), 80.0, 80.0, depth_m=5.0, sigma_cells=8.0
    )
    params = detection.DetectionParameters(min_depth_m=1.0, min_area_m2=40.0)
    (clean,) = detection.detect_offshore(sea(surface), SOURCE, params)
    mask = controls.interpolation_mask(surface.shape, 50, 50, 110, 110)
    (interp,) = detection.detect_offshore(
        sea(surface, interpolated=mask), SOURCE, params
    )
    assert detection.DetectionFlag.MOSTLY_INTERPOLATED in interp.flags
    assert interp.proposed_class == "SURVEY_ARTIFACT" and interp.possible_artifact
    assert all(a.tier is v.EvidenceTier.CANDIDATE for a in interp.assertions)
    assert interp.discovery_score < clean.discovery_score
    assert clean.proposed_class != "SURVEY_ARTIFACT"
    assert all(a.tier is v.EvidenceTier.SUPPORTING for a in clean.assertions)
    (inland_interp,) = detection.detect_inland(
        land(surface + 200.0, interpolated=mask), SOURCE, params
    )
    assert inland_interp.proposed_class == "UNCLASSIFIED_ANOMALY"


def test_depth_must_exceed_its_uncertainty():
    surface = controls.add_gaussian_basin(
        np.full((160, 160), 100.0), 80.0, 80.0, depth_m=1.5, sigma_cells=8.0
    )
    # Depth barely above what the survey can resolve: reported, flagged, capped.
    (weak,) = detection.detect_inland(land(surface, uncertainty_m=0.5), SOURCE, PARAMS)
    assert weak.region.significance < 3.0
    assert detection.DetectionFlag.BELOW_UNCERTAINTY in weak.flags
    # Depth the survey cannot tell from zero over a reportable area: not reported at all.
    assert (
        detection.detect_inland(land(surface, uncertainty_m=1.0), SOURCE, PARAMS) == []
    )
    assert all(a.tier is v.EvidenceTier.CANDIDATE for a in weak.assertions)
    (unknown,) = detection.detect_inland(
        land(surface, uncertainty_m=None), SOURCE, PARAMS
    )
    assert detection.DetectionFlag.UNCERTAINTY_UNKNOWN in unknown.flags
    assert all(a.tier is v.EvidenceTier.CANDIDATE for a in unknown.assertions)
    (strong,) = detection.detect_inland(
        land(surface, uncertainty_m=0.05), SOURCE, PARAMS
    )
    assert not strong.flags and strong.native_record_id == weak.native_record_id


def test_escarpment_detection():
    yy, xx = np.mgrid[0:120, 0:200].astype(float)
    shelf = np.where(xx < 100, -20.0, -20.0 - np.clip(xx - 100, 0, 12) * 5.0)
    (scarp,) = detection.detect_escarpments(
        sea(shelf), SOURCE, min_slope_deg=30, min_length_m=100
    )
    assert scarp.proposed_class == "ESCARPMENT" and scarp.region is None
    assert scarp.measurements["relief_m"] > 40 and scarp.measurements["length_m"] > 200
    assert (
        detection.detect_escarpments(
            sea(np.full((80, 80), -20.0)), SOURCE, min_slope_deg=30, min_length_m=100
        )
        == []
    )


def test_evaluation_is_one_to_one_class_wise_and_honest_about_truth():
    found = detection.detect_inland(land(_flat_scene()), SOURCE, PARAMS)
    label = (
        lambda i, cls, x, y, kind=detection.TruthKind.SYNTHETIC_CONTROL: (  # noqa: E731
            detection.ReferenceLabel(f"L{i}", cls, (x, y), 15.0, kind)
        )
    )
    labels = [
        label(1, "CLOSED_DEPRESSION", 70.5, 189.5),
        label(2, "CLOSED_DEPRESSION", 70.5, 79.5),
        label(3, "SURFACE_EXCAVATION", 200.0, 185.0),
    ]
    report = detection.evaluate(found, labels)
    assert report.state is detection.EvaluationState.SOFTWARE_CONTROL
    assert {
        (s.feature_class, s.true_positives, s.false_positives, s.false_negatives)
        for s in report.scores
    } == {("CLOSED_DEPRESSION", 2, 0, 0), ("SURFACE_EXCAVATION", 1, 0, 0)}
    # Two labels near one detection: one match and one miss, never two matches.
    crowded = detection.evaluate(
        found, labels + [label(4, "SURFACE_EXCAVATION", 201.0, 186.0)]
    )
    cut = next(s for s in crowded.scores if s.feature_class == "SURFACE_EXCAVATION")
    assert (cut.true_positives, cut.false_negatives) == (1, 1) and cut.recall == 0.5
    # A wrong class is a miss and a false alarm, not a hit.
    wrong = detection.evaluate(found, [label(1, "SINKHOLE", 70.5, 189.5)])
    assert (
        next(s for s in wrong.scores if s.feature_class == "SINKHOLE").false_negatives
        == 1
    )
    empty = detection.evaluate(found, [])
    assert empty.state is detection.EvaluationState.EXPLORATORY and empty.scores == ()
    assert "no precision" in empty.statement
    field = [
        label(
            9,
            "CLOSED_DEPRESSION",
            70.5,
            189.5,
            detection.TruthKind.INDEPENDENT_FIELD_TRUTH,
        )
    ]
    assert detection.evaluate(found, field).state is detection.EvaluationState.MEASURED
    with pytest.raises(ValueError, match="separately"):
        detection.evaluate(found, labels + field)
    with pytest.raises(ValueError, match="duplicate"):
        detection.evaluate(found, [labels[0], labels[0]])


# ── Cross-coastal transects ──────────────────────────────────────────────────


def _coast_pair(sea_reference=MLLW_DOWN):
    land_grid = R.make_grid(
        controls.tilted_plane(40, 100, base_m=1.0, slope_x=0.05, slope_y=0.0),
        cell_size_m=(1, 1),
        origin=(0.0, 40.0),
        crs=CRS,
        kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=PRVD,
        uncertainty_m=0.1,
    )
    sea_grid = R.make_grid(
        np.full((40, 100), 8.0),
        cell_size_m=(1, 1),
        origin=(-130.0, 40.0),
        crs=CRS,
        kind=R.SurfaceKind.BATHYMETRY,
        vertical_reference=sea_reference,
        uncertainty_m=0.3,
    )
    return land_grid, sea_grid


def test_cross_section_reports_the_unsurveyed_gap_and_bridges_nothing():
    land_grid, sea_grid = _coast_pair()
    section = transects.build_cross_section(
        [land_grid, sea_grid], [(-120.0, 20.0), (90.0, 20.0)], spacing_m=5.0
    )
    assert section.length_m == pytest.approx(210.0)
    assert not section.is_continuous
    (gap,) = section.gaps
    assert (gap.start_m, gap.end_m, gap.length_m) == (90.0, 115.0, 25.0)
    for profile in section.profiles:
        for sample in profile.samples:
            if gap.start_m <= sample.distance_m <= gap.end_m:
                assert sample.elevation_m is None  # nothing interpolated across the gap
    assert section.join.state is V.JoinState.SEPARATE_SURFACES_ONLY
    assert section.common_profiles == () and section.common_datum is None
    assert [p.datum for p in section.profiles] == [
        V.VerticalDatum.PRVD02,
        V.VerticalDatum.MLLW,
    ]
    sea_profile = section.profiles[1]
    assert (
        sea_profile.samples[0].elevation_m == -8.0
    )  # the cell value, not a smoothed one
    assert 0 < sea_profile.covered_fraction < 1
    document = transects.cross_section_to_dict(section, truth_kind="SYNTHETIC_CONTROL")
    assert (
        document["truth_kind"] == "SYNTHETIC_CONTROL"
        and document["join"]["may_difference"] is False
    )


def test_cross_section_joins_only_with_a_certified_transform():
    land_grid, sea_grid = _coast_pair()
    transform = V.CertifiedTransform(
        V.VerticalDatum.MLLW,
        V.VerticalDatum.PRVD02,
        -0.2,
        "synthetic test authority",
        0.05,
    )
    section = transects.build_cross_section(
        [land_grid, sea_grid],
        [(-120.0, 20.0), (90.0, 20.0)],
        spacing_m=5.0,
        transforms=[transform],
    )
    assert section.join.state is V.JoinState.TRANSFORMED
    assert section.common_datum is V.VerticalDatum.PRVD02
    moved = section.common_profiles[1].samples[0]
    assert moved.elevation_m == pytest.approx(-8.2)
    assert moved.uncertainty_m == pytest.approx(math.hypot(0.3, 0.05))
    assert section.gaps  # a transform does not fill a coverage gap
    same_datum = transects.build_cross_section(
        [
            land_grid,
            _coast_pair(VerticalReference(CRS, None, "PRVD02", None, "down"))[1],
        ],
        [(-120.0, 20.0), (90.0, 20.0)],
        spacing_m=5.0,
    )
    assert (
        same_datum.join.state is V.JoinState.SAME_REFERENCE
        and len(same_datum.common_profiles) == 2
    )


def test_cross_section_input_rules():
    land_grid, sea_grid = _coast_pair()
    other = R.make_grid(
        np.zeros((4, 4)),
        cell_size_m=(1, 1),
        origin=(0, 4),
        crs="EPSG:32619",
        kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=PRVD,
    )
    with pytest.raises(R.GridMismatchError):
        transects.build_cross_section([land_grid, other], [(0, 2), (3, 2)], spacing_m=1)
    for bad in (
        {"surfaces": []},
        {"line": [(0, 0)]},
        {"spacing": 0},
        {"line": [(5, 5), (5, 5)]},
    ):
        with pytest.raises(ValueError):
            transects.build_cross_section(
                bad.get("surfaces", [land_grid]),
                bad.get("line", [(0, 20), (50, 20)]),
                spacing_m=bad.get("spacing", 5),
            )
    bent = transects.build_cross_section(
        [land_grid], [(0.0, 20.0), (30.0, 20.0), (30.0, 5.0)], spacing_m=10.0
    )
    assert bent.length_m == pytest.approx(45.0)
    assert [s.distance_m for s in bent.profiles[0].samples] == [
        0.0,
        10.0,
        20.0,
        30.0,
        40.0,
        45.0,
    ]
    assert (
        bent.is_continuous
        and bent.join is None
        and bent.common_datum is V.VerticalDatum.PRVD02
    )


# ── Coast ────────────────────────────────────────────────────────────────────

MHW = coastal.CoastlineVersion(
    "mhw-2018",
    "APSRC-" + "0" * 16,
    V.VerticalDatum.MHW,
    "2018-01-01",
    box(0, 0, 100, 100),
    CRS,
)
MLLW_COAST = coastal.CoastlineVersion(
    "mllw-2022",
    "APSRC-" + "1" * 16,
    V.VerticalDatum.MLLW,
    "2022-01-01",
    box(-10, 0, 100, 100),
    CRS,
)


@pytest.mark.parametrize(
    "geometry, state, side, registry",
    [
        (
            Point(50, 50),
            v.SpatialState.FULLY_WITHIN,
            coastal.CoastalSide.LAND,
            sup.INLAND,
        ),
        (Point(-50, 50), v.SpatialState.OUTSIDE, coastal.CoastalSide.SEA, sup.OFFSHORE),
        (
            box(-20, 40, 20, 60),
            v.SpatialState.PARTIAL,
            coastal.CoastalSide.STRADDLES_COAST,
            None,
        ),
        (
            LineString([(-5, 50), (0, 50)]),
            v.SpatialState.TOUCH_ONLY,
            coastal.CoastalSide.ON_COASTLINE,
            None,
        ),
        (Point(), v.SpatialState.NULL_EMPTY, coastal.CoastalSide.UNRESOLVED, None),
        (None, v.SpatialState.NULL_EMPTY, coastal.CoastalSide.UNRESOLVED, None),
        (
            Polygon([(10, 10), (30, 30), (30, 10), (10, 30)]),
            v.SpatialState.UNRESOLVED,
            coastal.CoastalSide.UNRESOLVED,
            None,
        ),
    ],
    ids=["land", "sea", "straddles", "touches", "empty", "none", "invalid"],
)
def test_coastal_relation_states(geometry, state, side, registry):
    relation = coastal.classify(geometry, MHW, crs=CRS)
    assert (relation.state, relation.side) == (state, side)
    assert coastal.assess(geometry, [MHW], crs=CRS).registry is registry


def test_coastal_side_is_reported_per_coastline_version():
    assessment = coastal.assess(Point(-5, 50), [MLLW_COAST, MHW], crs=CRS)
    assert [r.version_id for r in assessment.relations] == [
        "mhw-2018",
        "mllw-2022",
    ]  # by date
    assert assessment.sides == {coastal.CoastalSide.SEA, coastal.CoastalSide.LAND}
    assert not assessment.is_stable and assessment.registry is None
    assert coastal.side_changes(assessment) == {"mhw-2018->mllw-2022": ("SEA", "LAND")}
    stable = coastal.assess(Point(50, 50), [MHW, MLLW_COAST], crs=CRS)
    assert stable.is_stable and coastal.side_changes(stable) == {}


def test_coastline_inputs_are_validated():
    with pytest.raises(ValueError, match="reproject"):
        coastal.classify(Point(1, 1), MHW, crs="OGC:CRS84")
    with pytest.raises(ValueError, match="duplicate"):
        coastal.assess(Point(1, 1), [MHW, MHW], crs=CRS)
    with pytest.raises(ValueError):
        coastal.assess(Point(1, 1), [], crs=CRS)
    with pytest.raises(ValueError):
        coastal.CoastlineVersion("x", "s", V.VerticalDatum.MHW, "2020", Polygon(), CRS)
    with pytest.raises(ValueError, match="invalid"):
        coastal.CoastlineVersion(
            "x",
            "s",
            V.VerticalDatum.MHW,
            "2020",
            Polygon([(0, 0), (2, 2), (2, 0), (0, 2)]),
            CRS,
        )


# ── Hardened pre-existing gates ──────────────────────────────────────────────


@pytest.mark.parametrize("value", [p for p in PLACEHOLDERS if p is not None])
def test_placeholder_no_longer_binds_a_vertical_reference(value):
    assert not VerticalReference(CRS, None, value, None).is_fully_bound()
    a = MarineObservation(
        "a",
        SensorType.MULTIBEAM_ECHOSOUNDER,
        ProductStage.PROCESSED_OBSERVATION,
        "r1",
        VerticalReference(CRS, None, value, None),
        CoverageState.DIRECTLY_OBSERVED,
        value_m=10.0,
    )
    b = MarineObservation(
        "b",
        SensorType.BATHYMETRIC_LIDAR,
        ProductStage.PROCESSED_OBSERVATION,
        "r2",
        VerticalReference(CRS, None, value, None),
        CoverageState.DIRECTLY_OBSERVED,
        value_m=11.0,
    )
    with pytest.raises(VerticalCompatibilityError):
        compare_depths(a, b)  # two unknowns that merely share a word are not one datum


def test_real_references_still_bind_and_compare():
    for reference in (
        VerticalReference(CRS, None, "MLLW", None),
        VerticalReference(CRS, "EPSG:5866", None, None),
        VerticalReference(CRS, None, None, "MHW"),
    ):
        assert reference.is_fully_bound()
    ref = VerticalReference(CRS, None, "MLLW", None)
    obs = lambda oid, val: MarineObservation(  # noqa: E731
        oid,
        SensorType.MULTIBEAM_ECHOSOUNDER,
        ProductStage.PROCESSED_OBSERVATION,
        oid,
        ref,
        CoverageState.DIRECTLY_OBSERVED,
        value_m=val,
    )
    assert compare_depths(
        obs("a", 10.0), obs("b", 11.5)
    ).delta_b_minus_a_m == pytest.approx(1.5)


def test_rootless_observation_no_longer_outranks_a_rooted_one():
    ref = VerticalReference(CRS, None, "MLLW", None)
    direct = lambda oid, root, sensor=SensorType.MULTIBEAM_ECHOSOUNDER: MarineObservation(  # noqa: E731
        oid,
        sensor,
        ProductStage.PROCESSED_OBSERVATION,
        root,
        ref,
        CoverageState.DIRECTLY_OBSERVED,
        value_m=10.0,
    )
    assert (
        classify_feature_evidence([direct("a", None)])
        is EvidenceState.SINGLE_SENSOR_SUPPORTED
    )
    assert (
        classify_feature_evidence([direct("a", "r1")])
        is EvidenceState.SINGLE_SENSOR_SUPPORTED
    )
    assert classify_feature_evidence([direct("a", "r1"), direct("b", "r2")]) is (
        EvidenceState.DIRECT_SENSOR_CONFIRMED
    )
    assert (
        classify_feature_evidence(
            [direct("a", "r1"), direct("b", "r2", SensorType.BATHYMETRIC_LIDAR)]
        )
        is EvidenceState.MULTISENSOR_CONFIRMED
    )
    assert classify_feature_evidence([direct("a", None), direct("b", None)]) is (
        EvidenceState.SINGLE_SENSOR_SUPPORTED
    )


def test_undeclared_datum_no_longer_passes_datum_policy():
    from source_adapters.ncei_coastal_dem.datum_policy import evaluate_datum_policy
    from source_adapters.ncei_coastal_dem.registry import load_registry

    records = load_registry()
    undeclared = [
        r for r in records if r.vertical_datum.strip().lower() == "source_dependent"
    ]
    declared = [r for r in records if r.vertical_datum.strip() == "PRVD02"]
    assert undeclared and declared, "registry no longer holds both kinds of row"
    result = evaluate_datum_policy(undeclared)
    assert (
        result.review_status == "review_required"
        and result.requires_vertical_normalization
    )
    assert evaluate_datum_policy(declared[:1]).review_status == "pass"
    assert (
        evaluate_datum_policy(declared[:1] + undeclared[:1]).review_status
        == "review_required"
    )


# ── Basins nested inside a larger closed basin ───────────────────────────────


def _compound(extra=()):
    """A broad shallow bowl with two deep pits in it, on a gentle slope."""

    surface = controls.tilted_plane(400, 400, base_m=200.0, slope_x=0.01, slope_y=0.005)
    surface = controls.add_gaussian_basin(
        surface, 200, 200, depth_m=3.0, sigma_cells=60.0
    )
    for row, col, depth, sigma in ((190, 150, 8.0, 6.0), (210, 250, 8.0, 6.0), *extra):
        surface = controls.add_gaussian_basin(
            surface, row, col, depth_m=depth, sigma_cells=sigma
        )
    return surface


def _nested_regions(surface, **kw):
    grid = _terrain(surface)
    return grid, R.delineate_depressions(
        grid, min_depth_m=1.0, min_area_m2=50.0, nested=True, **kw
    )


def _terrain(surface):
    return R.make_grid(
        surface,
        cell_size_m=(1.0, 1.0),
        origin=(722000.0, 2033000.0),
        crs="EPSG:26919",
        kind=R.SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=VerticalReference("EPSG:26919", None, "PRVD02", None, "up"),
        uncertainty_m=0.05,
    )


def test_pits_sharing_one_rim_are_reported_inside_the_basin_that_holds_them():
    grid, regions = _nested_regions(_compound())
    outer = [r for r in regions if r.hierarchy_level == 0]
    inner = [r for r in regions if r.hierarchy_level == 1]
    assert len(outer) == 1 and len(inner) == 2 and len(regions) == 3
    for region in inner:
        assert region.parent_deepest_xy == outer[0].deepest_xy
        assert region.depth_resolution_m == 0.5
        # Depth is a lower bound: never more than the basin that holds it.
        assert 1.0 <= region.max_depth_m <= outer[0].max_depth_m
        assert region.area_m2 < outer[0].area_m2
        assert region.spill_elevation_m < outer[0].spill_elevation_m
    planted = {(722150.5, 2032809.5), (722250.5, 2032789.5)}
    found = {min(planted, key=lambda p: math.dist(p, r.deepest_xy)) for r in inner}
    assert found == planted
    for region in inner:
        assert min(math.dist(p, region.deepest_xy) for p in planted) <= 3.0


def test_the_outer_basins_are_the_same_with_and_without_nesting():
    grid = _terrain(_compound())
    plain = R.delineate_depressions(grid, min_depth_m=1.0, min_area_m2=50.0)
    _, nested = _nested_regions(_compound())
    assert [r for r in nested if r.hierarchy_level == 0] == plain
    assert all(
        r.depth_resolution_m is None and r.parent_deepest_xy is None for r in plain
    )


def test_a_single_basin_noise_and_small_bumps_make_no_nested_basin():
    lone = controls.add_gaussian_basin(
        controls.tilted_plane(300, 300, base_m=200.0),
        150,
        150,
        depth_m=6.0,
        sigma_cells=20.0,
    )
    _, regions = _nested_regions(controls.add_noise(lone, sigma_m=0.05, seed=3))
    assert [r.hierarchy_level for r in regions] == [0]
    # A second hollow too shallow to be a basin on its own is a bump, not a split.
    _, bumped = _nested_regions(_compound(extra=((230, 200, 0.6, 4.0),)))
    assert sum(1 for r in bumped if r.hierarchy_level > 0) == 2
    # One deep pit in a broad bowl does not separate the water body: the stated limit.
    one_pit = controls.add_gaussian_basin(
        controls.add_gaussian_basin(
            controls.tilted_plane(400, 400, base_m=200.0),
            200,
            200,
            depth_m=3.0,
            sigma_cells=60.0,
        ),
        200,
        200,
        depth_m=9.0,
        sigma_cells=6.0,
    )
    _, single = _nested_regions(one_pit)
    assert [r.hierarchy_level for r in single] == [0]


def test_nesting_goes_as_deep_as_the_ground_does():
    # Two pits inside one of two sub-bowls inside one bowl.
    surface = controls.tilted_plane(
        500, 500, base_m=200.0, slope_x=0.004, slope_y=0.002
    )
    surface = controls.add_gaussian_basin(
        surface, 250, 250, depth_m=3.0, sigma_cells=90.0
    )
    surface = controls.add_gaussian_basin(
        surface, 250, 170, depth_m=4.0, sigma_cells=22.0
    )
    surface = controls.add_gaussian_basin(
        surface, 250, 330, depth_m=4.0, sigma_cells=22.0
    )
    surface = controls.add_gaussian_basin(
        surface, 250, 160, depth_m=6.0, sigma_cells=4.0
    )
    surface = controls.add_gaussian_basin(
        surface, 250, 182, depth_m=6.0, sigma_cells=4.0
    )
    _, regions = _nested_regions(surface)
    levels = sorted(r.hierarchy_level for r in regions)
    assert levels == [0, 1, 1, 2, 2]
    by_level = {
        level: [r for r in regions if r.hierarchy_level == level] for level in (1, 2)
    }
    parents = {r.deepest_xy for r in by_level[1]}
    assert {r.parent_deepest_xy for r in by_level[2]} <= parents
    assert len({r.label for r in regions}) == len(regions)


def test_the_level_step_is_validated_and_never_overstates_depth():
    with pytest.raises(ValueError, match="nested_level_step_m"):
        _nested_regions(_compound(), nested_level_step_m=0)
    _, fine = _nested_regions(_compound(), nested_level_step_m=0.1)
    _, coarse = _nested_regions(_compound(), nested_level_step_m=1.0)
    deep = lambda regions: sorted(  # noqa: E731
        r.max_depth_m for r in regions if r.hierarchy_level == 1
    )
    assert len(deep(fine)) == len(deep(coarse)) == 2
    # A coarser step sees the split later, so it measures a shallower basin.
    assert all(c <= f + 1e-9 for c, f in zip(deep(coarse), deep(fine)))
    assert all(f - c <= 1.0 + 1e-9 for c, f in zip(deep(coarse), deep(fine)))


def test_nested_detections_are_flagged_identified_and_still_only_shapes():
    grid = _terrain(_compound())
    source = sup.direct_source("TEST-NESTED-1")
    plain = detection.detect_inland(
        grid, source, detection.DetectionParameters(min_depth_m=1.0, min_area_m2=50.0)
    )
    nested = detection.detect_inland(
        grid,
        source,
        detection.DetectionParameters(min_depth_m=1.0, min_area_m2=50.0, nested=True),
    )
    assert [d.native_record_id for d in plain] == [
        d.native_record_id for d in nested if d.hierarchy_level == 0
    ]
    ids = [d.native_record_id for d in nested]
    assert len(ids) == len(set(ids)) == 3
    (outer,) = [d for d in nested if d.hierarchy_level == 0]
    inner = [d for d in nested if d.hierarchy_level == 1]
    assert outer.parent_native_record_id is None and "/n" not in outer.native_record_id
    for item in inner:
        assert item.native_record_id.endswith("/n1")
        assert item.parent_native_record_id == outer.native_record_id
        assert detection.DetectionFlag.NESTED in item.flags
        assert not item.possible_artifact
        assert item.measurements["depth_resolution_m"] == 0.5
        # The flag is informational: it lowers nothing and adds no claim.
        assert {a.tier for a in item.assertions} == {v.EvidenceTier.SUPPORTING}
        dims = {a.dimension for a in item.assertions}
        assert v.EvidenceDimension.PHYSICAL_OPENING not in dims
        assert v.EvidenceDimension.CONNECTIVITY not in dims
    with pytest.raises(ValueError, match="nested_level_step_m"):
        detection.DetectionParameters(
            min_depth_m=1.0, min_area_m2=50.0, nested_level_step_m=0
        )


def test_the_seabed_detector_reports_nested_basins_the_same_way():
    depth = -(_compound() - 150.0)  # the same shapes, as depths below a datum
    grid = R.make_grid(
        -depth - 400.0,
        cell_size_m=(1.0, 1.0),
        origin=(722000.0, 2033000.0),
        crs="EPSG:26919",
        kind=R.SurfaceKind.BATHYMETRY,
        vertical_reference=VerticalReference("EPSG:26919", None, "MLLW", None, "up"),
        uncertainty_m=0.05,
    )
    source = sup.direct_source("TEST-NESTED-SEA")
    params = detection.DetectionParameters(min_depth_m=1.0, min_area_m2=50.0)
    plain = detection.detect_offshore(grid, source, params)
    nested = detection.detect_offshore(
        grid,
        source,
        detection.DetectionParameters(min_depth_m=1.0, min_area_m2=50.0, nested=True),
    )
    assert len(plain) == 1 and sorted(d.hierarchy_level for d in nested) == [0, 1, 1]
    assert all(d.namespace is sup.OFFSHORE for d in nested)
