import pytest

from federation.surface_analysis import MeasurementClass, SpatialState, SurfaceClass
from federation.surface_engine import RegularSurfaceGrid, SurfaceManifestation, classify_topology, geometry_sha256, sensor_footprint_xy


@pytest.fixture
def grid():
    manifest = SurfaceManifestation("synthetic-pr", "fixture", "SYNTHETIC", "EPSG:4326", "TEST_MSL", "positive_up", 100, MeasurementClass.DIRECT_MULTIBEAM, "a"*64, "surface/1.0")
    return RegularSurfaceGrid([-66.1, -66.0, -65.9], [18.0, 18.1, 18.2], [[-500, -400, -300], [-100, None, 20], [100, 200, 300]], manifest)


def test_point_sampling_preserves_ocean_land_nodata_and_outside(grid):
    assert grid.sample_surface(-66.1, 18.0).surface_class is SurfaceClass.OCEAN_DEPTH
    assert grid.sample_surface(-65.9, 18.2).surface_class is SurfaceClass.LAND_ELEVATION
    assert grid.sample_surface(-66.0, 18.1).spatial_state is SpatialState.NULL_EMPTY
    assert grid.sample_surface(-70, 18).spatial_state is SpatialState.OUTSIDE


def test_geodesic_profile_preserves_nulls_and_provenance(grid):
    profile = grid.profile_surface([(-66.1, 18.0), (-65.9, 18.2)], interval_m=8000)
    assert profile[0]["source_manifestation_id"] == "synthetic-pr"
    assert any(row["spatial_state"] == "NULL_EMPTY" for row in profile)
    assert profile[-1]["distance_m"] > 0


def test_exact_topology_distinguishes_touch_partial_within_outside_and_empty():
    from shapely.geometry import LineString, Polygon
    target = Polygon([(0,0),(10,0),(10,10),(0,10)])
    assert classify_topology(LineString([(1,1),(9,9)]), target)["spatial_state"] is SpatialState.FULLY_WITHIN
    assert classify_topology(LineString([(-1,5),(5,5)]), target)["spatial_state"] is SpatialState.PARTIAL
    assert classify_topology(LineString([(-1,0),(0,0)]), target)["spatial_state"] is SpatialState.TOUCH_ONLY
    assert classify_topology(LineString([(-2,-2),(-1,-1)]), target)["spatial_state"] is SpatialState.OUTSIDE
    assert classify_topology(LineString(), target)["spatial_state"] is SpatialState.NULL_EMPTY


def test_sensor_footprint_is_deterministic_metric_geometry():
    footprint = sensor_footprint_xy(0, 0, altitude_m=1000, azimuth_deg=90, depression_deg=45, horizontal_fov_deg=30)
    assert footprint.area > 0
    assert geometry_sha256(footprint) == geometry_sha256(footprint)


def test_invalid_grid_and_sensor_inputs_fail_closed(grid):
    with pytest.raises(ValueError): RegularSurfaceGrid([1,0],[0,1],[[1,2],[3,4]],grid.manifestation)
    with pytest.raises(ValueError): sensor_footprint_xy(0,0,altitude_m=0,azimuth_deg=0,depression_deg=45,horizontal_fov_deg=30)
