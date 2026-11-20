"""A gridded seabed survey, from a held product to a sealed report.

Synthetic two-band grids with planted depressions exercise the reader, the
per-cell uncertainty rule and both halves of a declared run without any
network or any held product.  The last section checks the committed run of
2026-11-18 against what is committed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from spiderweb.access_points import bathymetry_run as bath
from spiderweb.access_points import controls, raster, seeding
from spiderweb.access_points import detection as det
from spiderweb.access_points import products as prod
from spiderweb.access_points import vocabulary as v
from spiderweb.access_points.namespaces import Namespace
from spiderweb.access_points.survey_run import RUNS_PATH, SURVEY_DIR

rasterio = pytest.importorskip("rasterio")

from spiderweb.access_points import survey  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RUN_ID = "2026-11-18-offshore"
CELL = 64.0
WEST, NORTH = 186000.0, 1976000.0  # UTM 20N, off south-eastern Puerto Rico
CENTRE = (-65.93, 17.82)
PARAMETERS = det.DetectionParameters(min_depth_m=2.0, min_area_m2=4 * CELL * CELL)
COMPOUND_WKT = (
    'COMPD_CS["NAD83 / UTM zone 20N + MLLW depth",'
    + rasterio.crs.CRS.from_epsg(26920).to_wkt()
    + ',VERT_CS["MLLW depth",VERT_DATUM["MLLW",2005],UNIT["metre",1],'
    'AXIS["Depth",DOWN]]]'
)


def seabed(*, second_uncertainty=2.0):
    """A gently sloping seabed near -100 m with two planted depressions.

    The first lies where the cell uncertainty is small; the second where it is
    ``second_uncertainty``.  A corner has no data, as a real survey's grid
    does.
    """

    surface = controls.tilted_plane(80, 90, base_m=-100.0, slope_x=-0.05, slope_y=-0.03)
    surface = controls.add_gaussian_basin(surface, 25, 25, depth_m=9.0, sigma_cells=4)
    surface = controls.add_gaussian_basin(surface, 55, 60, depth_m=7.0, sigma_cells=4)
    surface = controls.add_noise(surface, sigma_m=0.02, seed=3)
    uncertainty = np.full(surface.shape, 0.3)
    uncertainty[40:70, 45:75] = second_uncertainty
    surface[:10, 70:] = np.nan
    uncertainty[:10, 70:] = np.nan
    return surface, uncertainty


def depth_grid(values, uncertainty, crs="EPSG:26920"):
    return survey.DepthGrid(
        survey.RasterWindow(
            values, crs, (WEST, NORTH), (CELL, CELL), 0, 0, values.shape, None
        ),
        uncertainty,
        {},
    )


def a_source(tag="s"):
    from gebco.marine_evidence import SensorType

    return survey.gridded_source(
        provider="TEST_PROVIDER",
        native_identifier=f"TEST:{tag}",
        title=f"synthetic seabed {tag}",
        source_uri=f"https://products.example.invalid/seabed/{tag}.bag",
        sha256=hashlib.sha256(tag.encode()).hexdigest(),
        retrieved_utc="2026-11-18T00:00:00+00:00",
        published_date=None,
        survey_date=None,
        lineage_root_id=f"TEST:{tag}",
        sensor_type=SensorType.MULTIBEAM_ECHOSOUNDER,
    )


def processed(grid, parameters=PARAMETERS):
    reference, vertical = survey.stated_vertical(
        grid.window, stated_datum="MLLW", basis="test", at_lonlat=CENTRE
    )
    result = survey.process_seabed(
        grid, a_source(), vertical_reference=reference, parameters=parameters
    )
    return result, vertical


# ── Reading ──────────────────────────────────────────────────────────────────


def test_only_the_horizontal_part_of_a_compound_crs_places_cells():
    compound = rasterio.crs.CRS.from_wkt(COMPOUND_WKT)
    assert survey.horizontal_crs(compound) == "EPSG:26920"
    assert survey.horizontal_crs(rasterio.crs.CRS.from_epsg(26920)) == "EPSG:26920"


def test_a_subset_holds_both_bands_and_loses_nothing(tmp_path):
    values, uncertainty = seabed()
    values = values.astype("float32").astype("float64")
    uncertainty = uncertainty.astype("float32").astype("float64")
    path = tmp_path / "base.tif"
    digest = survey.write_depth_subset(depth_grid(values, uncertainty), path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    back = survey.read_depth_grid(path)
    assert np.array_equal(back.window.values, values, equal_nan=True)
    assert np.array_equal(back.uncertainty, uncertainty, equal_nan=True)
    assert back.window.crs == "EPSG:26920"
    assert back.window.cell_size == (CELL, CELL)
    assert back.window.origin == (WEST, NORTH)
    assert back.facts["driver"] == "GTiff"
    assert back.facts["refinement_resolution_m"] is None
    # Writing the same grid again gives the same bytes.
    again = tmp_path / "again.tif"
    assert survey.write_depth_subset(back, again) == digest


def test_a_grid_that_is_not_a_two_band_metre_grid_is_refused(tmp_path):
    from rasterio.transform import from_origin

    values, _ = seabed()

    def write(path, *, count, crs, transform):
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=values.shape[0],
            width=values.shape[1],
            count=count,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=1000000.0,
        ) as dst:
            for band in range(1, count + 1):
                dst.write(np.nan_to_num(values, nan=1000000.0).astype("float32"), band)
        return path

    metres = from_origin(WEST, NORTH, CELL, CELL)
    with pytest.raises(survey.SurveyReadError, match="uncertainty band"):
        survey.read_depth_grid(
            write(tmp_path / "one.tif", count=1, crs="EPSG:26920", transform=metres)
        )
    with pytest.raises(survey.SurveyReadError, match="projected CRS in metres"):
        survey.read_depth_grid(
            write(
                tmp_path / "degrees.tif",
                count=2,
                crs="EPSG:4326",
                transform=from_origin(-66.0, 17.9, 0.001, 0.001),
            )
        )


def test_a_surface_above_its_datum_is_not_a_seabed():
    values, uncertainty = seabed()
    reference, _ = survey.stated_vertical(
        depth_grid(values, uncertainty).window,
        stated_datum="MLLW",
        basis="test",
        at_lonlat=CENTRE,
    )
    with pytest.raises(raster.SignConventionError):
        survey.to_seabed(
            depth_grid(-values, uncertainty),
            vertical_reference=reference,
            source_id="APSRC-test",
        )


# ── Processing ───────────────────────────────────────────────────────────────


def test_depressions_are_found_and_judged_by_the_uncertainty_of_their_own_cells():
    result, vertical = processed(depth_grid(*seabed()))
    rows = result.report["detections"]
    assert len(rows) == 2
    assert {row["proposed_class"] for row in rows} == {"SEAFLOOR_DEPRESSION"}
    by_depth = sorted(rows, key=lambda row: -row["max_depth_m"])
    sure, unsure = by_depth
    assert sure["flags"] == [] and sure["depth_uncertainty_m"] < 1.0
    assert {a["tier"] for a in sure["assertions"]} == {"SUPPORTING"}
    assert "BELOW_UNCERTAINTY" in unsure["flags"]
    assert {a["tier"] for a in unsure["assertions"]} == {"CANDIDATE"}
    assert result.report["below_uncertainty"] == 1
    assert set(result.report["assertions_by_tier"]) == {"CANDIDATE", "SUPPORTING"}
    assert result.grid.kind is raster.SurfaceKind.BATHYMETRY
    assert result.report["surface"]["cell_uncertainty_m"]["max"] == 2.0
    assert unsure["significance"] < PARAMETERS.significance_floor
    assert result.report["surface"]["nodata_cells"] == 200
    # A tidal datum has no regional extent to check against: not assessed,
    # never called plausible, and so never joinable to a land surface.
    assert vertical["resolved_datum"] == "MLLW"
    assert vertical["regional_plausibility"] == "NOT_ASSESSED"
    assert vertical["joinable_to_other_references"] is False


def test_with_small_uncertainty_everywhere_both_are_supporting_and_no_more():
    result, _ = processed(depth_grid(*seabed(second_uncertainty=0.3)))
    assert result.report["detection_count"] == 2
    assert result.report["assertions_by_tier"] == {"SUPPORTING": 4}
    assert result.report["below_uncertainty"] == 0
    sensitivity = result.report["sensitivity"]
    assert sensitivity["cells_where_floor_exceeds_min_depth"] == 0
    assert sensitivity["cells_where_min_depth_is_resolvable"] == 80 * 90 - 200
    ignoring = result.report["ignoring_uncertainty"]
    assert ignoring["closed_depressions"] == 2
    assert ignoring["withheld_by_the_uncertainty_rule"] == []


def test_a_depression_below_its_cells_uncertainty_is_not_reported_and_that_is_said():
    """Large uncertainty hides a real depression; the report must say where."""

    result, _ = processed(depth_grid(*seabed(second_uncertainty=6.0)))
    rows = result.report["detections"]
    assert len(rows) == 1 and rows[0]["flags"] == []
    sensitivity = result.report["sensitivity"]
    assert sensitivity["cells_where_floor_exceeds_min_depth"] == 30 * 30
    assert sensitivity["cell_depth_floor_m"]["max"] == pytest.approx(8.485, abs=1e-3)
    assert "not absence of a depression" in sensitivity["meaning"]
    # The check that ignores uncertainty still sees it, and says it was withheld.
    ignoring = result.report["ignoring_uncertainty"]
    assert ignoring["closed_depressions"] == 2
    assert ignoring["also_reported_by_the_detector"] == 1
    (withheld,) = ignoring["withheld_by_the_uncertainty_rule"]
    assert withheld["max_depth_m"] == pytest.approx(6.18, abs=0.05)
    assert withheld["depth_uncertainty_m"] > withheld["max_depth_m"]
    assert "not evidence" in ignoring["meaning"]


def test_a_flat_seabed_and_a_shallow_dimple_report_nothing():
    plane = controls.tilted_plane(60, 60, base_m=-80.0, slope_x=-0.05, slope_y=-0.02)
    result, _ = processed(depth_grid(plane, np.full(plane.shape, 0.3)))
    assert result.report["detection_count"] == 0
    dimple = controls.add_gaussian_basin(plane, 30, 30, depth_m=1.0, sigma_cells=4)
    result, _ = processed(depth_grid(dimple, np.full(plane.shape, 0.3)))
    assert result.report["detection_count"] == 0


def test_the_extent_describes_the_survey_and_a_dry_run_files_nothing():
    grid = depth_grid(*seabed())
    extent = survey.lonlat_extent(grid)
    box, covered = extent["grid_bbox_lonlat"], extent["covered_bbox_lonlat"]
    assert box[0] < CENTRE[0] < box[2] or box[1] < CENTRE[1] < box[3]
    assert box[0] <= covered[0] and covered[2] <= box[2]
    empty = depth_grid(np.full((4, 4), np.nan), np.full((4, 4), np.nan))
    assert survey.lonlat_extent(empty)["covered_bbox_lonlat"] is None

    result, _ = processed(grid)
    dry = survey.dry_registration(
        result,
        a_source(),
        created_utc="2026-11-18T00:00:00+00:00",
        namespace=Namespace.ACCESS_POINT_OFFSHORE,
    )
    assert dry["features_that_would_be_filed"] == 2
    assert dry["by_status"] == {"CANDIDATE": 2}
    assert dry["verified"] == 0 and dry["written_to_committed_registry"] is False
    assert not ({"OPENING", "PASSAGE", "CONNECTION"} & set(dry["by_assertion_rung"]))


# ── The declared run ─────────────────────────────────────────────────────────


def _config(tmp_path, mutate):
    data = yaml.safe_load((REPO / RUNS_PATH).read_text(encoding="utf-8"))
    mutate(data[bath.RUNS_KEY][0])
    path = tmp_path / "runs.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r.update(lon=-65.9, lat=17.8), "may not state a position"),
        (lambda r: r.update(bbox=[-66, 17, -65, 18]), "may not state a position"),
        (lambda r: r.update(target_feature="OFAP-PR-000001"), "target record"),
        (lambda r: r.update(registry="access_point.inland"), "off-shore registry"),
        (lambda r: r.pop("search_area"), "search area"),
        (lambda r: r["parameters"].pop("nested"), "nested basins are reported"),
        (lambda r: r["product"].update(sha256="abc"), "64-digit hash"),
        (
            lambda r: r["product"].update(vertical_statement_basis="  "),
            "where the value was read",
        ),
        (lambda r: r["product"].pop("lineage_root_id"), "lineage_root_id is required"),
        (lambda r: r.pop("product"), "exactly one product"),
    ],
)
def test_a_seabed_run_states_no_position_and_leaves_no_basis_blank(
    tmp_path, mutate, message
):
    with pytest.raises(bath.SeabedRunError, match=message):
        bath.load_run(_config(tmp_path, mutate), RUN_ID)


def test_the_declared_run_reads_as_declared():
    run = bath.load_run(REPO / RUNS_PATH, RUN_ID)
    assert run["registry"] is Namespace.ACCESS_POINT_OFFSHORE
    assert run["parameters"].nested is True
    assert run["parameters"].min_area_m2 == 4 * CELL * CELL
    with pytest.raises(bath.SeabedRunError, match="no seabed run"):
        bath.load_run(REPO / RUNS_PATH, "1999-01-01")
    # An inland run is not a seabed run, and the reverse.
    with pytest.raises(bath.SeabedRunError, match="no seabed run"):
        bath.load_run(REPO / RUNS_PATH, "2026-11-17")


# A whole run on a synthetic product: landing page, held file, both halves.

HOST = "products.example.invalid"
LANDING = f"https://{HOST}/nos/T00001.html"
PRODUCT_URL = f"https://{HOST}/nos/T00001/BAG/T00001_MB_64m_MLLW_1of1.tif"
SYNTH_ID = "synthetic-seabed"


def synthetic_run(tmp_path, *, declared_sha256=None):
    """A repository-shaped folder holding one declared synthetic seabed run."""

    root = tmp_path / "repo"
    held = tmp_path / "held"
    held.mkdir(parents=True)
    filename = PRODUCT_URL.rsplit("/", 1)[-1]
    product = held / filename
    survey.write_depth_subset(depth_grid(*seabed()), product)
    digest = hashlib.sha256(product.read_bytes()).hexdigest()
    (held / (filename + ".manifest.json")).write_text(
        json.dumps(
            {
                "schema": prod.MANIFEST_SCHEMA,
                "products_version": prod.PRODUCTS_VERSION,
                "request": {"url": PRODUCT_URL},
                "filename": filename,
                "response_size": product.stat().st_size,
                "response_sha256": digest,
                "retrieved_utc": "2026-11-18T00:00:00+00:00",
                "headers": {},
            }
        ),
        encoding="utf-8",
    )
    catalogue = root / SURVEY_DIR / SYNTH_ID / "catalogue"
    catalogue.mkdir(parents=True)
    page = (
        f'<html><a href="{PRODUCT_URL}">grid</a>'
        f'<a href="https://{HOST}/nos/T00001/other.pdf">report</a></html>'
    ).encode()
    (catalogue / "landing.bin").write_bytes(page)
    (catalogue / "landing.manifest.json").write_text(
        json.dumps(
            {
                "request_url": LANDING,
                "status": 200,
                "retrieved_utc": "2026-11-18T00:00:00+00:00",
                "response_sha256": hashlib.sha256(page).hexdigest(),
                "response_size": len(page),
                "headers": {},
            }
        ),
        encoding="utf-8",
    )
    (root / "configs").mkdir()
    shutil.copy(REPO / bath.CORRIDORS_PATH, root / bath.CORRIDORS_PATH)
    (root / RUNS_PATH).write_text(
        yaml.safe_dump(
            {
                "version": bath.RUNS_VERSION,
                "runs": [],
                bath.RUNS_KEY: [
                    {
                        "run_id": SYNTH_ID,
                        "registry": "access_point.offshore",
                        "search_area": "guayama_punta_tuna_discovery_v0_1",
                        "parameters": {
                            "min_depth_m": 2.0,
                            "min_area_m2": 4 * CELL * CELL,
                            "nested": True,
                        },
                        "product": {
                            "filename": filename,
                            "native_identifier": "TEST:BAG:T00001:1of1",
                            "landing_page": LANDING,
                            "sha256": declared_sha256 or digest,
                            "stated_vertical_datum": "MLLW",
                            "vertical_statement_basis": "synthetic",
                            "vertical_uncertainty_basis": "synthetic band",
                            "lineage_root_id": "TEST:BAG:T00001",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return root, held, bath.load_run(root / RUNS_PATH, SYNTH_ID)


def test_both_halves_of_a_run_and_the_report_needs_no_held_product(tmp_path):
    root, held, run = synthetic_run(tmp_path)
    extracted = bath.extract(run, repo_root=root, product_dir=held)
    run_dir = root / SURVEY_DIR / SYNTH_ID
    assert (run_dir / bath.SUBSET_NAME).is_file()
    assert extracted["facts"]["parent_sha256"] == run["product"]["sha256"]

    shutil.rmtree(held)  # the report half must not need the product
    report = bath.build_report(run, repo_root=root)
    bath.write_report(report, repo_root=root)
    assert bath.check_report(run, repo_root=root) == []
    assert bath.current_report(root) == report

    product = report["products"][0]
    assert report["target_feature"] is None and report["registry_changes"] == 0
    assert report["evaluation_state"] == "EXPLORATORY"
    assert product["result"]["detection_count"] == 2
    assert product["subset"]["parent_sha256"] == product["download"]["sha256"]
    assert product["search_area"]["relation"] == "FULLY_WITHIN"
    assert "not the position" in product["search_area"]["search_area_is"]
    assert product["prior_receipt"] is None
    assert product["vertical"]["cells_at_or_above_datum"] == 0
    assert product["vertical"]["converted_to_another_datum"] is False
    assert product["source"]["product_stage"] == "GRID"
    assert product["source"]["sensor_type"] == "MULTIBEAM_ECHOSOUNDER"

    # The report can be registered as a held, hashed source; a registry that
    # is not the report's own refuses it.
    from spiderweb.access_points.registry import AccessPointRegistry

    registry = AccessPointRegistry(
        Namespace.ACCESS_POINT_OFFSHORE, producer_identity="test"
    )
    summary = seeding.register_survey_sources(
        {Namespace.ACCESS_POINT_OFFSHORE: registry}, report
    )
    assert summary["registered"] == 1 and not registry.features
    source = registry.sources[product["source"]["source_id"]]
    assert not source.is_direct_measurement
    inland = AccessPointRegistry(Namespace.ACCESS_POINT_INLAND, producer_identity="t")
    with pytest.raises(seeding.SeedingError, match="not being built"):
        seeding.register_survey_sources({Namespace.ACCESS_POINT_INLAND: inland}, report)


def test_a_product_that_is_not_the_declared_one_is_refused(tmp_path):
    root, held, run = synthetic_run(tmp_path, declared_sha256="0" * 64)
    with pytest.raises(bath.SeabedRunError, match="not the one the run declares"):
        bath.extract(run, repo_root=root, product_dir=held)

    root, held, run = synthetic_run(tmp_path / "second")
    with pytest.raises(bath.SeabedRunError, match="is not held"):
        bath.extract(run, repo_root=root, product_dir=tmp_path / "nowhere")
    run["product"]["filename"] = "T00001_other.tif"
    with pytest.raises(bath.SeabedRunError, match="not listed on the frozen"):
        bath.extract(run, repo_root=root, product_dir=held)


def test_changed_evidence_is_detected(tmp_path):
    root, held, run = synthetic_run(tmp_path)
    bath.extract(run, repo_root=root, product_dir=held)
    bath.write_report(bath.build_report(run, repo_root=root), repo_root=root)
    run_dir = root / SURVEY_DIR / SYNTH_ID
    assert bath.check_report(run, repo_root=root) == []

    def problems():
        return " ".join(bath.check_report(run, repo_root=root))

    # The subset: a deeper hole dug into it.
    subset = run_dir / bath.SUBSET_NAME
    original = subset.read_bytes()
    grid = survey.read_depth_grid(subset)
    dug = grid.window.values.copy()
    dug[30:36, 30:36] -= 20.0
    survey.write_depth_subset(depth_grid(dug, grid.uncertainty), subset)
    assert "does not match the hash recorded" in problems()
    subset.write_bytes(original)
    assert problems() == ""

    # The product facts.
    facts_path = run_dir / bath.FACTS_NAME
    kept = facts_path.read_text()
    facts = json.loads(kept)
    facts["facts"]["driver"] = "BAG"
    facts_path.write_text(json.dumps(facts))
    assert "does not match its content hash" in problems()
    facts_path.write_text(kept)

    # The download manifest.
    manifest_path = next((run_dir / "products").glob("*.manifest.json"))
    kept = manifest_path.read_text()
    manifest = json.loads(kept)
    manifest["response_sha256"] = "1" * 64
    manifest_path.write_text(json.dumps(manifest))
    assert "not the one the run declares" in problems()
    manifest_path.write_text(kept)

    # The frozen landing page.
    page = run_dir / "catalogue" / "landing.bin"
    kept_bytes = page.read_bytes()
    page.write_bytes(kept_bytes + b" ")
    assert "does not match its manifest" in problems()
    page.write_bytes(kept_bytes)

    # The report itself, and the pointer to it.
    assert problems() == ""
    report_path = run_dir / bath.REPORT_NAME
    report = json.loads(report_path.read_text())
    report["products"][0]["result"]["detection_count"] = 99
    report_path.write_text(json.dumps(report))
    assert "not reproduced" in problems()
    with pytest.raises(bath.SeabedRunError, match="pointer's hash"):
        bath.current_report(root)

    # A search area that is not declared, or belongs to the other registry.
    run["search_area"] = "nowhere_v1"
    assert "is not declared" in problems()
    assert bath.current_report(tmp_path / "empty") is None


# ── The committed run of 2026-11-18 ──────────────────────────────────────────


@pytest.fixture(scope="module")
def committed():
    report = bath.current_report(REPO)
    if report is None:
        pytest.skip("no seabed run is committed")
    return report


def test_the_committed_seabed_report_is_reproduced_from_committed_evidence(committed):
    run = bath.load_run(REPO / RUNS_PATH, committed["run_id"])
    assert bath.check_report(run, repo_root=REPO) == []


def test_the_committed_seabed_run_overstates_nothing(committed):
    product = committed["products"][0]
    result = product["result"]
    assert committed["registry"] == "access_point.offshore"
    assert committed["target_feature"] is None
    assert committed["registry_changes"] == 0
    assert committed["evaluation_state"] == "EXPLORATORY"
    assert committed["replication"] is None
    assert product["download"]["size_bytes"] <= 8_000_000
    assert product["subset"]["parent_sha256"] == product["download"]["sha256"]
    assert product["layers_read"].startswith("the base grid only")
    assert product["product_facts"]["refinement_resolution_m"] is not None
    assert set(result["assertions_by_tier"]) <= {"CANDIDATE", "SUPPORTING"}
    for row in result["detections"]:
        assert row["proposed_class"] == "SEAFLOOR_DEPRESSION"
        tiers = {a["tier"] for a in row["assertions"]}
        if "BELOW_UNCERTAINTY" in row["flags"]:
            assert tiers == {"CANDIDATE"}
        assert row["depth_uncertainty_m"] is not None
    dry = product["dry_registration"]
    assert dry["verified"] == 0 and dry["written_to_committed_registry"] is False
    assert not ({"OPENING", "PASSAGE", "CONNECTION"} & set(dry["by_assertion_rung"]))
    vertical = product["vertical"]
    assert vertical["stated_datum"] == "MLLW"
    assert vertical["regional_plausibility"] == "NOT_ASSESSED"
    assert vertical["joinable_to_other_references"] is False
    assert vertical["cells_at_or_above_datum"] == 0
    assert product["search_area"]["relation"] == "FULLY_WITHIN"
    # The report says how much of the survey cannot show a depression of the
    # minimum depth, rather than leaving silence to read as absence.
    sensitivity = result["sensitivity"]
    assert (
        sensitivity["cells_where_floor_exceeds_min_depth"]
        + sensitivity["cells_where_min_depth_is_resolvable"]
        == sensitivity["covered_cells"]
        == result["surface"]["valid_cells"]
    )
    assert sensitivity["cells_where_floor_exceeds_min_depth"] > 0
    # The earlier, independently made receipt describes the same bytes.
    prior = product["prior_receipt"]
    assert prior["all_agree"] is True and prior["agrees"]["sha256"] is True


def test_the_committed_seabed_run_changed_no_record(committed):
    build = seeding.build_all(REPO)
    registry = build.offshore
    product = committed["products"][0]
    source = registry.sources[product["source"]["source_id"]]
    assert source.provenance_state is v.ProvenanceState.REGISTERED
    assert source.manifestation_sha256 == product["download"]["sha256"]
    assert not source.is_direct_measurement
    assert build.seabed["registered"] == 1
    assert build.seabed["report_content_sha256"] == committed["content_sha256"]
    # It is the only survey grid in the registry whose bytes are held.
    held = [
        s
        for s in registry.sources.values()
        if s.manifestation_sha256 and s.product_stage.value == "GRID"
    ]
    assert [s.source_id for s in held] == [source.source_id]
    assert registry.counts()["features_by_status"].get("VERIFIED", 0) == 0
    cited = {
        sid
        for feature in registry.features.values()
        for assertion in feature.assertions
        for sid in assertion.source_ids
    }
    assert source.source_id not in cited
    # No seed gained a position from a survey lying inside its search area.
    for feature_id in build.seeded:
        assert seeding._point_of(registry, feature_id) is None
    # The inland pointer and report are untouched by the off-shore run.
    assert build.survey["registry"] == "access_point.inland"


# ── Reading the finer grids (V10) ────────────────────────────────────────────

FINE = 8.0
RATIO = int(CELL / FINE)


def test_only_a_variable_resolution_file_can_be_read_at_another_resolution(tmp_path):
    path = tmp_path / "base.tif"
    survey.write_depth_subset(depth_grid(*seabed()), path)
    assert survey.read_depth_grid(path).facts["driver"] == "GTiff"
    with pytest.raises(survey.SurveyReadError, match="variable-resolution"):
        survey.read_depth_grid(path, 8.0)
    for bad in (0.0, -8.0, float("nan")):
        with pytest.raises(survey.SurveyReadError, match="positive"):
            survey.read_depth_grid(path, bad)


def a_row(rid, deepest, depth, unc, *, bbox=None, level=0, area=20000.0):
    x, y = deepest
    return {
        "native_record_id": rid,
        "deepest_xy": [x, y],
        "bbox_xy": bbox or [x - 100, y - 100, x + 100, y + 100],
        "max_depth_m": depth,
        "depth_uncertainty_m": unc,
        "hierarchy_level": level,
        "area_m2": area,
    }


def test_persistence_is_judged_by_a_rule_fixed_in_advance():
    earlier = [
        a_row("same", (1000, 1000), 5.0, 1.0),
        a_row("deeper", (3000, 1000), 3.0, 0.2),
        a_row("gone", (5000, 1000), 4.0, 1.0),
        a_row("split", (7000, 1000), 4.0, 1.0, bbox=[6800, 900, 7200, 1100]),
    ]
    later = [
        a_row("same'", (1030, 1020), 5.8, 1.0),  # 36 m away, depths agree
        a_row("deeper'", (3010, 1000), 6.0, 0.2),  # close, depths disagree
        a_row("far", (5200, 1000), 4.0, 1.0),  # more than one base cell away
        a_row("split-a", (6850, 1000), 3.0, 1.0),
        a_row("split-b", (7150, 1000), 3.5, 1.0),
        a_row("nested", (6990, 1000), 2.5, 1.0, level=1),  # not counted for a split
        a_row("new", (9000, 1000), 2.5, 1.0),
    ]
    result = survey.persistence(earlier, later, distance_m=CELL)
    status = {row["earlier"]: row["status"] for row in result["earlier"]}
    assert status == {
        "same": "PERSISTED",
        "deeper": "SAME_PLACE_DEPTH_DIFFERS",
        "gone": "NOT_FOUND",
        "split": "SPLIT",
    }
    assert result["by_status"] == {
        "NOT_FOUND": 1,
        "PERSISTED": 1,
        "SAME_PLACE_DEPTH_DIFFERS": 1,
        "SPLIT": 1,
    }
    split = next(row for row in result["earlier"] if row["earlier"] == "split")
    assert [n["native_record_id"] for n in split["later"]] == ["split-b", "split-a"]
    # "far", "nested" and "new" belong to no earlier depression.
    assert result["later_not_linked_to_any_earlier"] == 3
    assert "not replication" in result["limit"]


def fine_seabed():
    """The synthetic seabed at 8 m, with a base-aligned spacing grid at 64 m."""

    values, uncertainty = seabed()
    fine_values = np.kron(values, np.ones((RATIO, RATIO)))
    fine_unc = np.kron(uncertainty, np.ones((RATIO, RATIO)))
    window = survey.RasterWindow(
        fine_values,
        "EPSG:26920",
        (WEST, NORTH),
        (FINE, FINE),
        0,
        0,
        fine_values.shape,
        None,
    )
    spacing_values = np.where(np.isfinite(values), 4.0, np.nan)
    spacing_values[:, 45:] = 6.0  # a change of node spacing half way across
    spacing_values[np.isnan(values)] = np.nan
    spacing = survey.RasterWindow(
        spacing_values,
        "EPSG:26920",
        (WEST, NORTH),
        (CELL, CELL),
        0,
        0,
        values.shape,
        None,
    )
    return survey.DepthGrid(window, fine_unc, {}), spacing


def test_empty_cells_are_counted_and_can_only_remove_a_depression():
    grid, spacing = fine_seabed()
    full, _ = processed(grid)
    assert full.report["detection_count"] >= 1
    deepest = max(full.report["detections"], key=lambda r: r["max_depth_m"])
    empty = survey.empty_within_covered(grid.window, spacing)
    assert empty["empty_cells_inside_covered_base_cells"] == 0

    # A one-cell-wide gap cut from the deepest point out through the rim is
    # an outlet: that depression can no longer be closed.
    holed = grid.window.values.copy()
    west, north = grid.window.origin
    r = int((north - deepest["deepest_xy"][1]) // FINE)
    c = int((deepest["deepest_xy"][0] - west) // FINE)
    holed[r, c:] = np.nan
    holed_grid = survey.DepthGrid(
        survey.RasterWindow(
            holed,
            grid.window.crs,
            grid.window.origin,
            grid.window.cell_size,
            0,
            0,
            holed.shape,
            None,
        ),
        np.where(np.isfinite(holed), grid.uncertainty, np.nan),
        {},
    )
    cut, _ = processed(holed_grid)
    assert deepest["deepest_xy"] not in [
        d["deepest_xy"] for d in cut.report["detections"]
    ]
    assert cut.report["detection_count"] < full.report["detection_count"] + 1
    counted = survey.empty_within_covered(holed_grid.window, spacing)
    assert counted["empty_cells_inside_covered_base_cells"] == int(
        np.isnan(holed[r, c:]).sum()
    )
    assert "never make one" in counted["meaning"]

    # Holes in flat ground create nothing.
    plane = controls.tilted_plane(160, 160, base_m=-80.0, slope_x=-0.05, slope_y=-0.02)
    plane[40:42, :] = np.nan
    plane[:, 90:92] = np.nan
    flat, _ = processed(depth_grid(plane, np.full(plane.shape, 0.3)))
    assert flat.report["detection_count"] == 0


def test_a_small_depression_on_one_finer_grid_is_flagged_and_a_broad_one_is_not():
    grid, spacing = fine_seabed()
    west, north = grid.window.origin
    broad = {
        "bbox_xy": [west + 64, north - 640, west + 640, north - 64],
        "area_m2": 200000.0,
    }
    # Inside one base cell (row 2, column 2): smaller than a base cell.
    one_cell = {
        "bbox_xy": [west + 136, north - 184, west + 176, north - 144],
        "area_m2": 1600.0,
    }
    # Small, across the change of node spacing at base column 45.
    seam = {
        "bbox_xy": [
            west + 44 * CELL + 40,
            north - 640,
            west + 45 * CELL + 24,
            north - 600,
        ],
        "area_m2": 1600.0,
    }
    flat_area = {
        "bbox_xy": [west + 64, north - 640, west + 256, north - 576],
        "area_m2": 12000.0,
    }
    rows = survey.finer_grid_context(
        [broad, one_cell, seam, flat_area], grid.window, spacing
    )
    assert [r["possible_refinement_artefact"] for r in rows] == [
        False,
        True,
        True,
        False,
    ]
    assert rows[1]["base_cells_spanned"] == 1
    assert rows[2]["spans_node_spacing_change"] is True
    assert rows[2]["finer_grid_node_spacing_m"] == {"min": 4.0, "max": 6.0}
    assert rows[0]["smaller_than_one_base_cell"] is False


def test_a_grid_that_does_not_nest_in_the_base_grid_is_refused():
    grid, spacing = fine_seabed()
    shifted = survey.RasterWindow(
        spacing.values,
        spacing.crs,
        (WEST + 4.0, NORTH),
        spacing.cell_size,
        0,
        0,
        spacing.shape,
        None,
    )
    with pytest.raises(survey.SurveyReadError, match="nest exactly"):
        survey.empty_within_covered(grid.window, shifted)
    with pytest.raises(survey.SurveyReadError, match="nest exactly"):
        survey.finer_grid_context([], grid.window, shifted)
    summary = survey.spacing_summary(spacing)
    assert summary["finer_grids"] == int(np.isfinite(spacing.values).sum())
    assert summary["finer_grids_by_node_spacing"]["4 to 8 m"] == summary["finer_grids"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r.update(resolution_m=0), "resolution_m must be a positive"),
        (lambda r: r.update(resolution_m="8"), "resolution_m must be a positive"),
        (lambda r: r.update(compare_with=r["run_id"]), "compared with itself"),
        (lambda r: r.update(evidence_run="../elsewhere"), "must name a declared run"),
        (
            lambda r: r.update(resolution_m=8),
            "prior receipt describes the base grid",
        ),
    ],
)
def test_a_run_at_another_resolution_is_declared_properly(tmp_path, mutate, message):
    with pytest.raises(bath.SeabedRunError, match=message):
        bath.load_run(_config(tmp_path, mutate), RUN_ID)


FINE_ID = "synthetic-seabed-8m"
SMALL_ID = "synthetic-seabed-8m-small"


def resampled_runs(tmp_path):
    """The synthetic base run, reported, plus two resampled runs written by hand.

    CI holds no BAG file, so the resampled subset is written from a synthetic
    grid through the same function extract uses.
    """

    root, held, base = synthetic_run(tmp_path)
    bath.extract(base, repo_root=root, product_dir=held)
    bath.write_report(bath.build_report(base, repo_root=root), repo_root=root)
    data = yaml.safe_load((root / RUNS_PATH).read_text())
    product = dict(data[bath.RUNS_KEY][0]["product"])
    common = {
        "registry": "access_point.offshore",
        "search_area": "guayama_punta_tuna_discovery_v0_1",
        "resolution_m": FINE,
        "evidence_run": SYNTH_ID,
        "compare_with": SYNTH_ID,
        "product": product,
    }
    data[bath.RUNS_KEY] += [
        {
            "run_id": FINE_ID,
            **common,
            "parameters": {
                "min_depth_m": 2.0,
                "min_area_m2": 4 * CELL * CELL,
                "nested": True,
            },
        },
        {
            "run_id": SMALL_ID,
            **common,
            "subset_run": FINE_ID,
            "parameters": {"min_depth_m": 2.0, "min_area_m2": 1024.0, "nested": True},
        },
    ]
    (root / RUNS_PATH).write_text(yaml.safe_dump(data))
    fine = bath.load_run(root / RUNS_PATH, FINE_ID)
    small = bath.load_run(root / RUNS_PATH, SMALL_ID)
    grid, spacing = fine_seabed()
    run_dir = root / SURVEY_DIR / FINE_ID
    check = {"all_agree_except_edge_nodes": True, "cells_disagreeing_otherwise": 0}
    bath.write_extracted(
        fine,
        run_dir=run_dir,
        parent_sha256=product["sha256"],
        grid=grid,
        extra={
            "resolution_m": FINE,
            "resampling_check": check,
            "spacing_file": bath.SPACING_NAME,
            "spacing_sha256": survey.write_subset(spacing, run_dir / bath.SPACING_NAME),
        },
    )
    return root, held, base, fine, small


def test_a_resampled_run_reports_from_committed_evidence_and_compares(tmp_path):
    root, held, base, fine, small = resampled_runs(tmp_path)
    pointer = (root / SURVEY_DIR / bath.POINTER_NAME).read_bytes()
    for run in (fine, small):
        report = bath.build_report(run, repo_root=root)
        bath.write_report(report, repo_root=root, set_current=False)
        assert bath.check_report(run, repo_root=root) == []
        product = report["products"][0]
        finer = product["finer_grids"]
        assert finer["resampling"]["cell_m"] == FINE
        assert finer["empty_cells"]["empty_cells_inside_covered_base_cells"] == 0
        assert all("finer_grid" in row for row in product["result"]["detections"])
        assert product["prior_receipt"] is None
        assert product["layers_read"].startswith("the finer grids, resampled to 8 m")
        assert any("not replication" in limit for limit in report["limits"])
        assert not any(
            "only the product's base grid" in limit for limit in report["limits"]
        )
        comparison = report["comparison_with_earlier_run"]
        assert comparison["earlier_run"] == SYNTH_ID
        # The same synthetic seabed read finer: both depressions persist.
        assert comparison["by_status"] == {"PERSISTED": 2}
    small_report = bath.build_report(small, repo_root=root)
    assert small_report["products"][0]["subset"]["file"] == (
        f"../{FINE_ID}/{bath._subset_name(fine)}"
    )
    # The registry pointer still names the base run.
    assert (root / SURVEY_DIR / bath.POINTER_NAME).read_bytes() == pointer

    # Extract is refused for a run that reads another run's subset, and for a
    # resolution on a file that has no finer grids.
    with pytest.raises(bath.SeabedRunError, match="extract that run instead"):
        bath.extract(small, repo_root=root, product_dir=held)
    with pytest.raises(survey.SurveyReadError, match="variable-resolution"):
        bath.extract(fine, repo_root=root, product_dir=held)


def test_a_resampled_run_detects_changed_evidence(tmp_path):
    root, _, _, fine, small = resampled_runs(tmp_path)
    for run in (fine, small):
        bath.write_report(
            bath.build_report(run, repo_root=root), repo_root=root, set_current=False
        )

    def problems(run):
        return " ".join(bath.check_report(run, repo_root=root))

    run_dir = root / SURVEY_DIR / FINE_ID
    spacing_path = run_dir / bath.SPACING_NAME
    kept = spacing_path.read_bytes()
    spacing = survey.read_raster(spacing_path)
    changed = spacing.values.copy()
    changed[0, 0] = 32.0
    survey.write_subset(
        survey.RasterWindow(
            changed,
            spacing.crs,
            spacing.origin,
            spacing.cell_size,
            0,
            0,
            spacing.shape,
            None,
        ),
        spacing_path,
    )
    assert "spacing grid is missing or does not match" in problems(fine)
    assert "spacing grid is missing or does not match" in problems(small)
    spacing_path.write_bytes(kept)
    assert problems(fine) == "" and problems(small) == ""

    # Facts read at another resolution are refused.
    facts_path = run_dir / bath.FACTS_NAME
    kept_facts = facts_path.read_text()
    facts = json.loads(kept_facts)
    facts["resolution_m"] = 16.0
    del facts["content_sha256"]
    from federation.spatial_core import canonical_json_sha256

    facts["content_sha256"] = canonical_json_sha256(facts)
    facts_path.write_text(json.dumps(facts))
    assert "different resolution" in problems(fine)
    facts_path.write_text(kept_facts)
    assert problems(fine) == "" and problems(small) == ""

    # An earlier report that no longer matches its seal stops the comparison.
    earlier = root / SURVEY_DIR / SYNTH_ID / bath.REPORT_NAME
    report = json.loads(earlier.read_text())
    report["products"][0]["result"]["detection_count"] = 99
    earlier.write_text(json.dumps(report))
    assert "does not match its content hash" in problems(small)


# ── The committed 8 m runs of 2026-11-19 ─────────────────────────────────────

FINE_RUNS = ("2026-11-19-offshore-8m", "2026-11-19-offshore-8m-small")


@pytest.mark.parametrize("run_id", FINE_RUNS)
def test_the_committed_8m_reports_are_reproduced(run_id):
    if not (REPO / SURVEY_DIR / run_id / bath.REPORT_NAME).is_file():
        pytest.skip("no 8 m run is committed")
    run = bath.load_run(REPO / RUNS_PATH, run_id)
    assert bath.check_report(run, repo_root=REPO) == []


@pytest.mark.parametrize("run_id", FINE_RUNS)
def test_the_committed_8m_runs_overstate_nothing(run_id):
    path = REPO / SURVEY_DIR / run_id / bath.REPORT_NAME
    if not path.is_file():
        pytest.skip("no 8 m run is committed")
    report = json.loads(path.read_text())
    product = report["products"][0]
    result = product["result"]
    finer = product["finer_grids"]
    assert report["registry_changes"] == 0 and report["target_feature"] is None
    assert report["evaluation_state"] == "EXPLORATORY"
    assert (
        product["download"]["sha256"]
        == bath.load_run(REPO / RUNS_PATH, run_id)["product"]["sha256"]
    )
    check = finer["resampling"]["check_against_nodes"]
    assert check["all_agree_except_edge_nodes"] is True
    assert check["cells_disagreeing_otherwise"] == 0
    assert check["cells_with_nodes"] == result["surface"]["valid_cells"]
    assert set(result["assertions_by_tier"]) <= {"CANDIDATE", "SUPPORTING"}
    for row in result["detections"]:
        if "BELOW_UNCERTAINTY" in row["flags"]:
            assert {a["tier"] for a in row["assertions"]} == {"CANDIDATE"}
        if row["finer_grid"]["smaller_than_one_base_cell"]:
            assert row["finer_grid"]["possible_refinement_artefact"] is True
    comparison = report["comparison_with_earlier_run"]
    assert comparison["earlier_run"] == RUN_ID
    assert sum(comparison["by_status"].values()) == 3
    assert "not replication" in comparison["limit"]
    # The registry still points at the base-grid run.
    pointer = json.loads((REPO / SURVEY_DIR / bath.POINTER_NAME).read_text())
    assert pointer["run_id"] == RUN_ID


# ── The seam test (V11) ──────────────────────────────────────────────────────


def seam_surface(*, step=True, local_step=False, trough=True):
    """A seabed sloping down to the north with a narrow west-east trough.

    ``step``: everything north of row 50 is 8 m lower, across the whole grid,
    as where two finer grids meet at different levels.  ``local_step``: the
    same step only in columns 35 to 65, open to the north edge.  The trough is
    two cells wide (rows 49 and 50) from column 40 to 60.
    """

    values = controls.tilted_plane(100, 100, base_m=-80.0, slope_x=0.0, slope_y=0.05)
    values = values - 0.05 * 100  # stay well below the datum
    if step:
        values[:50, :] -= 8.0
    if local_step:
        values[:50, 35:66] -= 8.0
    if trough:
        values[49:51, 40:61] = values[49:51, 40:61].min() - 12.0
    values = controls.add_noise(values, sigma_m=0.02, seed=7)
    return depth_grid(values, np.full(values.shape, 0.3))


def outer_rows(grid):
    result, _ = processed(
        grid, det.DetectionParameters(min_depth_m=2.0, min_area_m2=1.0)
    )
    return result, [r for r in result.report["detections"] if r["hierarchy_level"] == 0]


def test_a_planted_seam_is_seam_likely():
    result, rows = outer_rows(seam_surface())
    trough = max(rows, key=lambda r: r["max_depth_m"])
    (seam,) = survey.seam_tests(result.grid, [trough])
    assert seam["classification"] == "SEAM_LIKELY", seam
    assert seam["narrow_and_grid_aligned"] is True
    assert seam["median_width_cells"] <= survey.SEAM_MAX_WIDTH_CELLS
    assert seam["median_step_m"] == pytest.approx(-8.0, abs=0.5)
    assert seam["step_significant_fraction"] >= survey.SEAM_ALONG_FRACTION
    assert (
        seam["continuation_significant_fraction"] >= survey.SEAM_CONTINUATION_FRACTION
    )


def test_a_narrow_trough_on_smooth_ground_is_not_seam_like():
    result, rows = outer_rows(seam_surface(step=False))
    trough = max(rows, key=lambda r: r["max_depth_m"])
    (seam,) = survey.seam_tests(result.grid, [trough])
    assert seam["narrow_and_grid_aligned"] is True
    assert seam["classification"] == "NOT_SEAM_LIKE"
    assert abs(seam["median_step_m"]) < 1.0


def test_a_step_that_stops_at_the_trough_is_indeterminate():
    result, rows = outer_rows(seam_surface(step=False, local_step=True))
    trough = max(rows, key=lambda r: r["max_depth_m"])
    (seam,) = survey.seam_tests(result.grid, [trough])
    assert seam["classification"] == "STEP_WITHOUT_CONTINUATION", seam
    assert seam["continuation_significant_fraction"] < survey.SEAM_CONTINUATION_FRACTION


def test_a_broad_bowl_and_a_nested_basin_are_not_called_seams():
    result, _ = processed(depth_grid(*seabed(second_uncertainty=0.3)))
    rows = result.report["detections"]
    tests = survey.seam_tests(result.grid, rows)
    for row, seam in zip(rows, tests):
        if row["hierarchy_level"] == 0:
            assert seam["classification"] == "NOT_SEAM_LIKE"
            assert seam["narrow_and_grid_aligned"] is False
    nested = dict(rows[0], hierarchy_level=1)
    (skipped,) = survey.seam_tests(result.grid, [nested])
    assert skipped["tested"] is False and "nested" in skipped["reason"]
    assert "written before it was applied" not in survey.SEAM_RULE  # the rule only


def test_a_column_with_too_few_cells_beside_it_is_not_measured():
    grid = seam_surface()
    values = grid.window.values.copy()
    values[44:49, :] = np.nan  # no north band anywhere
    values[51:56, :] = np.nan
    holed = depth_grid(values, np.where(np.isfinite(values), 0.3, np.nan))
    result, rows = outer_rows(holed)
    if not rows:
        pytest.skip("the trough is no longer closed once its banks are removed")
    (seam,) = survey.seam_tests(
        result.grid, [max(rows, key=lambda r: r["max_depth_m"])]
    )
    assert seam["classification"] == "INSUFFICIENT_DATA"
