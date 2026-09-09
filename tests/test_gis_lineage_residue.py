"""Synthetic count/geometry controls; not real layer observations."""
import pytest
from tools.gis_evidence.core import id_index
from tools.gis_evidence.cousub import compare_rows, EXPECTED_LSADC


@pytest.fixture
def geo():
    pytest.importorskip("shapely", reason="optional geospatial test dependency")
    pytest.importorskip("pyproj", reason="optional geospatial test dependency")
    from tools.gis_evidence import simplification
    from shapely.geometry import Polygon
    return simplification, Polygon


def test_expected_count_arithmetic_is_not_an_observation():
    assert sum(EXPECTED_LSADC.values())==939


def test_cousub_comparison_exact_and_per_id():
    a=[{"GEOID":"7200100001","LSADC":"20"},{"GEOID":"7200100002","LSADC":"41"}]
    assert compare_rows(a,list(reversed(a)),2)["state"]=="PASS"
    b=[{"GEOID":"7200100001","LSADC":"41"},{"GEOID":"7200100002","LSADC":"20"}]
    r=compare_rows(a,b,2)
    assert r["sets"]["counts"]["symmetric_difference"]==0
    assert len(r["lsadc_mismatches"])==2 and r["state"]=="FAIL"


def test_same_count_different_ids_fails():
    r=compare_rows([{"GEOID":"A","LSADC":"20"}],[{"GEOID":"B","LSADC":"20"}],1)
    assert r["state"]=="FAIL" and r["sets"]["counts"]["symmetric_difference"]==2


def test_duplicate_ids_fail_before_set_comparison():
    with pytest.raises(ValueError,match="DUPLICATE"):
        id_index([{"id":"a"},{"id":"a"}],"id")


@pytest.mark.parametrize("crs",["EPSG:4326","EPSG:2263"])
def test_angular_and_foot_crs_rejected(crs, geo):
    module, _ = geo
    with pytest.raises(ValueError,match="PROJECTED_METRE"):
        module.metric_crs(crs)


def test_geometry_identity_has_zero_error(geo):
    module, Polygon = geo
    g=Polygon([(0,0),(10,0),(10,10),(0,10)])
    r=module.polygon_metrics(g,g)
    assert r["hausdorff_discrete_m"]==r["symmetric_difference_m2"]==0
    assert r["topology_preserved"] is None


def test_small_boundary_move_changes_point_classification(geo):
    module, Polygon = geo
    a=Polygon([(0,0),(10,0),(10,10),(0,10)])
    b=Polygon([(0,0),(9.9,0),(9.9,10),(0,10)])
    r=module.polygon_metrics(a,b)
    assert r["hausdorff_discrete_m"]==pytest.approx(.1)
    assert r["symmetric_difference_m2"]==pytest.approx(1)
    p=module.pip_stability({"one":a},{"one":b},[{"probe_id":"near","x":9.95,"y":5}])
    assert p["mismatch_count"]==1


def test_touching_candidates_preserved(geo):
    module, Polygon = geo
    a=Polygon([(0,0),(10,0),(10,10),(0,10)])
    b=Polygon([(10,0),(20,0),(20,10),(10,10)])
    p=module.pip_stability({"a":a,"b":b},{"a":a,"b":b},[{"probe_id":"edge","x":10,"y":5}])
    assert p["rows"][0]["before"]["touching_ids"]==["a","b"]
