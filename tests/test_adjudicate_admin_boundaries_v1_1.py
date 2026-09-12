import importlib.util
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "adjudicate_admin_boundaries_v1_1.py"
spec = importlib.util.spec_from_file_location("adjudicate_admin_boundaries", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

TO_LOCAL = Transformer.from_crs("EPSG:4326", "EPSG:32161", always_xy=True).transform


def square(west=-66.10, south=18.20, east=-66.00, north=18.30):
    return Polygon(
        [(west, south), (east, south), (east, north), (west, north), (west, south)]
    )


def census_feature(geoid, name, geometry=None):
    return {
        "type": "Feature",
        "properties": {"GEOID": geoid, "BASENAME": name},
        "geometry": mapping(geometry or square()),
    }


def sige_municipio(name, geometry=None):
    source_geometry = transform(TO_LOCAL, geometry or square())
    return {
        "type": "Feature",
        "properties": {"Nombre": name},
        "geometry": mapping(source_geometry),
    }


def sige_barrio(municipio, barrio, geometry=None):
    source_geometry = transform(TO_LOCAL, geometry or square())
    return {
        "type": "Feature",
        "properties": {"MUNICIPIO": municipio, "BARRIO": barrio},
        "geometry": mapping(source_geometry),
    }


def test_exact_geometry_advances_only_to_provisional_candidate_pass():
    rows, unresolved = module.build_municipio_bindings(
        [census_feature("72001", "Adjuntas")], [sige_municipio("Adjuntas")]
    )
    assert unresolved == []
    assert len(rows) == 1
    assert rows[0]["canonical_id"] == "pr:municipio:72001"
    assert rows[0]["identity_state"] == "PROVISIONAL"
    assert rows[0]["geometry_state"] == "GEOMETRY_CANDIDATE_PASS"
    assert rows[0]["metrics"]["hausdorff_distance_m"] < 1e-6


def test_duplicate_name_candidates_never_promote_name_only_identity():
    rows, unresolved = module.build_municipio_bindings(
        [census_feature("72001", "Adjuntas")],
        [sige_municipio("Adjuntas"), sige_municipio("Adjuntas")],
    )
    assert rows == []
    binding = [row for row in unresolved if row.get("side") == "binding"]
    assert binding[0]["candidate_count"] == 2


def test_barrio_requires_resolved_parent_municipio():
    municipio_rows, _ = module.build_municipio_bindings(
        [census_feature("72001", "Adjuntas")], [sige_municipio("Adjuntas")]
    )
    rows, unresolved = module.build_barrio_bindings(
        [census_feature("7200100001", "Barrio Uno")],
        [sige_barrio("Utuado", "Barrio Uno")],
        municipio_rows,
    )
    assert rows == []
    assert any(row.get("reason") == "unresolved parent municipio" for row in unresolved)


def test_barrio_parent_and_name_binding_preserves_census_geoid():
    municipio_rows, _ = module.build_municipio_bindings(
        [census_feature("72001", "Adjuntas")], [sige_municipio("Adjuntas")]
    )
    rows, unresolved = module.build_barrio_bindings(
        [census_feature("7200100001", "Barrio Uno")],
        [sige_barrio("Adjuntas", "Barrio Uno")],
        municipio_rows,
    )
    assert unresolved == []
    assert rows[0]["canonical_id"] == "pr:barrio:7200100001"
    assert rows[0]["parent_canonical_id"] == "pr:municipio:72001"
    assert rows[0]["identity_state"] == "PROVISIONAL"
    assert rows[0]["geometry_state"] == "GEOMETRY_CANDIDATE_PASS"


def test_large_geometry_disagreement_is_review_not_rejection_or_identity_pass():
    shifted = square(west=-65.80, east=-65.70)
    rows, unresolved = module.build_municipio_bindings(
        [census_feature("72001", "Adjuntas")], [sige_municipio("Adjuntas", shifted)]
    )
    assert unresolved == []
    assert rows[0]["identity_state"] == "PROVISIONAL"
    assert rows[0]["geometry_state"] == "REVIEW"
    assert rows[0]["metrics"]["overlap_ratio"] == 0.0


def test_arithmetic_closure_preserves_unresolved_residue():
    assert module.arithmetic(10, 8) == {
        "source": 10,
        "retained": 8,
        "excluded": 0,
        "unresolved": 2,
    }
