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
