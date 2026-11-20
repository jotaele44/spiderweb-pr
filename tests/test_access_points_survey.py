"""Fetching a named product inside a byte ceiling, and processing a real survey.

The download tests use a scripted opener and never touch the network.  The
processing tests write synthetic GeoTIFFs with known answers; the last group
re-computes the committed run from the evidence kept in the repository.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from pipeline.marine_sources import BoundingBox
from spiderweb.access_points import acquisition as acq
from spiderweb.access_points import controls, seeding, survey_run
from spiderweb.access_points import detection as det
from spiderweb.access_points import products as prod
from spiderweb.access_points import vertical as vert
from spiderweb.access_points import vocabulary as v
from tests import access_points_support as sup
from tests.test_access_points_integration import FakeNoaa, frozen

REPO = Path(__file__).resolve().parents[1]
INLAND, OFFSHORE = sup.INLAND, sup.OFFSHORE
HOST = "products.example.invalid"
URL = f"https://{HOST}/elevation/tile_a.tif"
BODY = b"elevation-product-bytes " * 4096
PR_POINT = (-66.8893, 18.3687)


def grant(files=2, ceiling=10_000_000):
    return acq.Authorization(
        acq.AuthorizationLevel.PRODUCT_DOWNLOAD, "test-operator", files, ceiling
    )


def request(url=URL, size=len(BODY)):
    return prod.ProductRequest("TEST_PROVIDER", "TEST:1", "tile a", url, size)


class Opener:
    """A scripted stand-in for ``urlopen``."""

    def __init__(self, body=BODY, *, length="auto", status=200, final_url=None):
        self.body, self.status, self.final_url = body, status, final_url
        self.length = len(body) if length == "auto" else length
        self.calls: list[str] = []
        self.bytes_read = 0

    def __call__(self, http_request, timeout):
        self.calls.append(http_request.full_url)
        self.agent = http_request.get_header("User-agent")
        outer = self
        stream = io.BytesIO(self.body)

        class Response:
            status = outer.status
            headers = {
                **(
                    {}
                    if outer.length is None
                    else {"Content-Length": str(outer.length)}
                ),
                "Set-Cookie": "session=abc",
                "ETag": '"e1"',
            }

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def geturl(self):
                return outer.final_url or http_request.full_url

            def read(self, n=-1):
                chunk = stream.read(n)
                outer.bytes_read += len(chunk)
                return chunk

        return Response()


def session(opener, authorization=None):
    return prod.DownloadSession(
        authorization if authorization is not None else grant(),
        allowed_hosts=[HOST],
        opener=opener,
    )


# ── Grants ───────────────────────────────────────────────────────────────────


def test_a_product_grant_is_separate_and_must_bound_bytes():
    with pytest.raises(ValueError, match="bound the number of bytes"):
        acq.Authorization(acq.AuthorizationLevel.PRODUCT_DOWNLOAD, "someone", 1)
    with pytest.raises(ValueError, match="only a product grant"):
        acq.Authorization(acq.AuthorizationLevel.METADATA_DISCOVERY, "someone", 1, 10)
    env = {acq.AUTHORIZATION_ENV: "product:2:800000000:the owner: on 2026-11-17"}
    parsed = acq.Authorization.from_environment(env)
    assert parsed.level is acq.AuthorizationLevel.PRODUCT_DOWNLOAD
    assert (parsed.max_requests, parsed.max_bytes) == (2, 800_000_000)
    assert parsed.granted_by == "the owner: on 2026-11-17"
    for raw in ("product:2:0:x", "product:0:5:x", "product:2:5:", "product:2", "all"):
        assert (
            acq.Authorization.from_environment({acq.AUTHORIZATION_ENV: raw}).level
            is acq.AuthorizationLevel.NONE
        )
    metadata = acq.Authorization.from_environment(
        {acq.AUTHORIZATION_ENV: "metadata:15:the owner"}
    )
    assert metadata.level is acq.AuthorizationLevel.METADATA_DISCOVERY


def test_one_grant_cannot_be_spent_as_the_other(tmp_path):
    opener = Opener()
    metadata = acq.Authorization(acq.AuthorizationLevel.METADATA_DISCOVERY, "x", 5)
    for authorization in (acq.Authorization(), metadata):
        with pytest.raises(acq.AcquisitionNotAuthorized):
            session(opener, authorization).fetch(request(), tmp_path)
    assert opener.calls == [] and list(tmp_path.iterdir()) == []
    fake = FakeNoaa()
    receipt = acq.discover_sources(
        OFFSHORE,
        BoundingBox(-66.3, 17.5, -65.7, 18.1),
        discovered_utc="t",
        transport=fake,
        authorization=grant(),
    )
    assert fake.calls == [] and receipt.state is acq.RunState.NOT_AUTHORIZED


# ── Downloading inside a ceiling ─────────────────────────────────────────────


def test_a_product_is_hashed_as_written_and_reused_without_a_request(tmp_path):
    opener = Opener()
    downloads = session(opener)
    receipt = downloads.fetch(request(), tmp_path)
    assert receipt.sha256 == hashlib.sha256(BODY).hexdigest()
    assert receipt.path.read_bytes() == BODY and receipt.reused is False
    assert (downloads.files_fetched, downloads.bytes_fetched) == (1, len(BODY))
    assert opener.agent == acq.GENERIC_USER_AGENT
    manifest = json.loads((tmp_path / "tile_a.tif.manifest.json").read_text())
    assert manifest["response_sha256"] == receipt.sha256
    assert set(manifest["headers"]) == {"Content-Length", "ETag"}
    again = session(opener).fetch(request(), tmp_path)
    assert again.reused is True and len(opener.calls) == 1
    # Even with no grant at all, a held product that still matches is usable.
    assert session(opener, acq.Authorization()).fetch(request(), tmp_path).reused


def test_a_held_product_that_no_longer_matches_is_an_error_not_a_refetch(tmp_path):
    opener = Opener()
    session(opener).fetch(request(), tmp_path)
    (tmp_path / "tile_a.tif").write_bytes(BODY + b"x")
    with pytest.raises(prod.ProductIntegrityError, match="does not match"):
        session(opener).fetch(request(), tmp_path)
    (tmp_path / "tile_a.tif").unlink()
    with pytest.raises(prod.ProductIntegrityError, match="both be present"):
        session(opener).fetch(request(), tmp_path)
    assert len(opener.calls) == 1


def test_the_ceiling_is_checked_before_a_byte_is_read(tmp_path):
    # Stated size over the ceiling: no request at all.
    opener = Opener()
    with pytest.raises(prod.ByteCeilingExceeded, match="Nothing was requested"):
        session(opener, grant(ceiling=len(BODY) - 1)).fetch(request(), tmp_path)
    assert opener.calls == []
    # Size unknown to the catalogue: the server's declared length decides.
    with pytest.raises(prod.ByteCeilingExceeded, match="not read"):
        session(opener, grant(ceiling=len(BODY) - 1)).fetch(
            request(size=None), tmp_path
        )
    assert opener.bytes_read == 0 and list(tmp_path.iterdir()) == []
    # Two files inside a ceiling that fits one and a half.
    downloads = session(Opener(), grant(ceiling=int(len(BODY) * 1.5)))
    downloads.fetch(request(), tmp_path)
    with pytest.raises(prod.ByteCeilingExceeded):
        downloads.fetch(request(url=f"https://{HOST}/elevation/tile_b.tif"), tmp_path)
    assert downloads.bytes_remaining == int(len(BODY) * 1.5) - len(BODY)


def test_the_number_of_files_and_the_host_are_bounded(tmp_path):
    downloads = session(Opener(), grant(files=1))
    downloads.fetch(request(), tmp_path)
    with pytest.raises(prod.ProductRefused, match="number of files"):
        downloads.fetch(request(url=f"https://{HOST}/elevation/tile_b.tif"), tmp_path)
    opener = Opener()
    with pytest.raises(prod.ProductRefused, match="not an allowed product host"):
        session(opener).fetch(request(url="https://elsewhere.invalid/t.tif"), tmp_path)
    assert opener.calls == []
    with pytest.raises(ValueError, match="at least one allowed host"):
        prod.DownloadSession(grant(), allowed_hosts=[])


@pytest.mark.parametrize(
    "opener, message",
    [
        (Opener(length=None), "declared no length"),
        (Opener(length=len(BODY) + 7), "catalogue stated"),
        (Opener(status=206), "HTTP status 206"),
        (Opener(final_url="https://elsewhere.invalid/tile_a.tif"), "answered from"),
    ],
)
def test_a_response_that_cannot_be_trusted_is_refused(tmp_path, opener, message):
    with pytest.raises((prod.ProductRefused, acq.UnexpectedRedirect), match=message):
        session(opener).fetch(request(), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("delta", [+9, -9])
def test_a_body_that_disagrees_with_its_declared_length_leaves_nothing(tmp_path, delta):
    body = BODY + b"y" * 9 if delta > 0 else BODY[:-9]
    opener = Opener(body, length=len(BODY))
    with pytest.raises(prod.ProductRefused, match="declared"):
        session(opener).fetch(request(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_product_address_must_be_https_and_name_a_file():
    with pytest.raises(ValueError, match="https"):
        request(url="http://products.example.invalid/tile.tif")
    with pytest.raises(ValueError, match="name a file"):
        request(url=f"https://{HOST}/")
    with pytest.raises(ValueError, match="positive"):
        request(size=0)


# ── The product catalogue ────────────────────────────────────────────────────


def _catalogue(items, total=None):
    def transport(url):
        return frozen(
            url, {"items": items, "total": len(items) if total is None else total}
        )

    return transport


def test_a_catalogue_answer_is_complete_or_refused():
    box = BoundingBox(-66.9, 18.36, -66.88, 18.38)
    item = {
        "sourceId": "abc",
        "title": "tile",
        "downloadURL": URL,
        "sizeInBytes": 123,
        "publicationDate": "2020-05-06",
        "metaUrl": "https://example.invalid/item/abc",
    }
    response, listed = prod.tnm_elevation_products(box, transport=_catalogue([item]))
    (only,) = listed
    assert only.native_identifier == "TNM:abc" and only.size_bytes == 123
    assert "bbox=-66.9%2C18.36%2C-66.88%2C18.38" in response.request_url
    with pytest.raises(ValueError, match="truncated"):
        prod.tnm_elevation_products(box, transport=_catalogue([item], total=2))
    with pytest.raises(ValueError, match="repeated"):
        prod.tnm_elevation_products(box, transport=_catalogue([item, item]))
    with pytest.raises(ValueError, match="no identifier or address"):
        prod.tnm_elevation_products(box, transport=_catalogue([{"title": "x"}]))


# ── Stated datums ────────────────────────────────────────────────────────────


def test_a_stated_datum_is_checked_against_where_the_data_lie():
    plausible = vert.RegionalPlausibility.PLAUSIBLE
    implausible = vert.RegionalPlausibility.IMPLAUSIBLE_FOR_REGION
    assert (
        vert.regional_plausibility(vert.VerticalDatum.NAVD88, *PR_POINT)[0]
        is implausible
    )
    assert (
        "PRVD02" in vert.regional_plausibility(vert.VerticalDatum.NAVD88, *PR_POINT)[1]
    )
    assert (
        vert.regional_plausibility(vert.VerticalDatum.PRVD02, *PR_POINT)[0] is plausible
    )
    assert (
        vert.regional_plausibility(vert.VerticalDatum.NAVD88, -98.0, 39.0)[0]
        is plausible
    )
    assert (
        vert.regional_plausibility(vert.VerticalDatum.PRVD02, -98.0, 39.0)[0]
        is implausible
    )
    assert (
        vert.regional_plausibility(vert.VerticalDatum.VIVD09, -64.9, 18.33)[0]
        is plausible
    )
    assert (
        vert.regional_plausibility(vert.VerticalDatum.NAVD88, -64.9, 18.33)[0]
        is implausible
    )
    assert (
        vert.regional_plausibility(vert.VerticalDatum.MLLW, *PR_POINT)[0]
        is vert.RegionalPlausibility.NOT_ASSESSED
    )


# ── Processing a gridded surface ─────────────────────────────────────────────

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from spiderweb.access_points import survey  # noqa: E402

WEST, NORTH = 722515.0, 2032773.0  # UTM 19N, inside Puerto Rico


def write_tif(
    path, values, *, crs="EPSG:26919", nodata=-9999.0, transform=None, count=1
):
    data = np.where(np.isfinite(values), values, nodata).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=count,
        dtype="float32",
        crs=crs,
        transform=transform or from_origin(WEST, NORTH, 1.0, 1.0),
        nodata=nodata,
    ) as dst:
        for band in range(1, count + 1):
            dst.write(data, band)
    return path


def scene(*, noise_seed=1, basins=((60, 70, 4.0, 9.0), (140, 150, 3.0, 8.0))):
    surface = controls.tilted_plane(200, 220, base_m=200.0, slope_x=0.01, slope_y=0.005)
    for row, col, depth, sigma in basins:
        surface = controls.add_gaussian_basin(
            surface, row, col, depth_m=depth, sigma_cells=sigma
        )
    return controls.add_noise(surface, sigma_m=0.02, seed=noise_seed)


def a_source(tag="a"):
    return survey.gridded_source(
        provider="TEST_PROVIDER",
        native_identifier=f"TEST:{tag}",
        title=f"synthetic tile {tag}",
        source_uri=f"https://{HOST}/elevation/tile_{tag}.tif",
        sha256=hashlib.sha256(tag.encode()).hexdigest(),
        retrieved_utc="2026-11-15T00:00:00+00:00",
        published_date=None,
        survey_date=None,
        lineage_root_id=f"TEST:{tag}",
    )


def processed(path, tag="a", uncertainty=0.05, datum="PRVD02"):
    window = survey.read_raster(path)
    reference, _ = survey.stated_vertical(
        window, stated_datum=datum, basis="test", at_lonlat=PR_POINT
    )
    return survey.process_terrain(
        window,
        a_source(tag),
        vertical_reference=reference,
        uncertainty_m=uncertainty,
        parameters=det.DetectionParameters(min_depth_m=1.0, min_area_m2=50.0),
    )


def test_a_window_is_the_products_own_cells_and_a_subset_loses_nothing(tmp_path):
    values = scene()
    values[0:5, 0:5] = np.nan
    path = write_tif(tmp_path / "tile.tif", values)
    centre = survey._lonlat("EPSG:26919", [WEST + 110.5], [NORTH - 100.5])[0]
    window = survey.read_window(path, center_lonlat=centre, half_size_m=40)
    assert window.shape == (80, 80) and (window.row_off, window.col_off) == (60, 70)
    np.testing.assert_array_equal(
        window.values, values[60:140, 70:150].astype("float32").astype("float64")
    )
    whole = survey.read_window(path, center_lonlat=centre, half_size_m=10_000)
    assert whole.shape == values.shape and np.isnan(whole.values[:5, :5]).all()
    digest = survey.write_subset(window, tmp_path / "subset.tif")
    assert digest == survey.sha256_file(tmp_path / "subset.tif")
    again = survey.read_raster(tmp_path / "subset.tif")
    np.testing.assert_array_equal(again.values, window.values)
    assert again.origin == window.origin and again.crs == window.crs
    with pytest.raises(survey.SurveyReadError, match="outside the product"):
        survey.read_window(path, center_lonlat=(-60.0, 10.0), half_size_m=40)


def test_products_that_are_not_a_metre_grid_are_refused(tmp_path):
    values = scene()
    geographic = write_tif(
        tmp_path / "geo.tif",
        values,
        crs="EPSG:4269",
        transform=from_origin(-66.9, 18.4, 0.00001, 0.00001),
    )
    with pytest.raises(survey.SurveyReadError, match="projected CRS in metres"):
        survey.read_raster(geographic)
    two_band = write_tif(tmp_path / "two.tif", values, count=2)
    with pytest.raises(survey.SurveyReadError, match="exactly one band"):
        survey.read_raster(two_band)


def test_a_datum_is_bound_as_stated_and_a_placeholder_is_not_a_datum(tmp_path):
    window = survey.read_raster(write_tif(tmp_path / "tile.tif", scene()))
    _, stated = survey.stated_vertical(
        window, stated_datum="NAVD88", basis="a sentence", at_lonlat=PR_POINT
    )
    assert stated["resolved_datum"] == "NAVD88"
    assert stated["regional_plausibility"] == "IMPLAUSIBLE_FOR_REGION"
    assert stated["joinable_to_other_references"] is False
    assert stated["statement_basis"] == "a sentence"
    _, local = survey.stated_vertical(
        window, stated_datum="PRVD02", basis="an element", at_lonlat=PR_POINT
    )
    assert local["joinable_to_other_references"] is True
    with pytest.raises(vert.UnknownVerticalDatumError):
        survey.stated_vertical(
            window, stated_datum="User Specified", basis="x", at_lonlat=PR_POINT
        )


def test_basins_are_found_and_a_grid_never_earns_more_than_supporting(tmp_path):
    result = processed(write_tif(tmp_path / "tile.tif", scene()))
    assert result.report["detection_count"] == 2
    depths = sorted(d["max_depth_m"] for d in result.report["detections"])
    assert depths[0] == pytest.approx(3.0, abs=0.4) and depths[1] == pytest.approx(
        4.0, abs=0.4
    )
    assert set(result.report["assertions_by_tier"]) == {"SUPPORTING"}
    assert result.report["possible_artifacts"] == 0
    assert not a_source().is_direct_measurement
    allowed = {v.EvidenceTier.CANDIDATE, v.EvidenceTier.SUPPORTING}
    for detection in result.detections:
        assert {a.tier for a in detection.assertions} <= allowed
        dims = {a.dimension for a in detection.assertions}
        assert v.EvidenceDimension.PHYSICAL_OPENING not in dims
        assert v.EvidenceDimension.CONNECTIVITY not in dims
    flat = processed(
        write_tif(tmp_path / "flat.tif", controls.tilted_plane(120, 120)), tag="f"
    )
    assert flat.report["detection_count"] == 0


def test_without_a_published_uncertainty_the_evidence_stays_candidate(tmp_path):
    result = processed(write_tif(tmp_path / "tile.tif", scene()), uncertainty=None)
    assert set(result.report["assertions_by_tier"]) == {"CANDIDATE"}
    for row in result.report["detections"]:
        assert "UNCERTAINTY_UNKNOWN" in row["flags"] and row["significance"] is None
    assert result.report["surface"]["stated_uncertainty_m"] is None


def test_a_second_survey_shows_which_basins_are_landforms(tmp_path):
    earlier = processed(write_tif(tmp_path / "a.tif", scene(noise_seed=1)), tag="a")
    both = processed(write_tif(tmp_path / "b.tif", scene(noise_seed=2)), tag="b")
    same = survey.compare_surveys(earlier, both)
    assert same["replicated"] == 2 and same["only_in_earlier"] == []
    assert abs(same["elevation_difference_later_minus_earlier"]["median_m"]) < 0.01
    one = processed(
        write_tif(
            tmp_path / "c.tif", scene(noise_seed=3, basins=((60, 70, 4.0, 9.0),))
        ),
        tag="c",
    )
    partial = survey.compare_surveys(earlier, one)
    assert partial["replicated"] == 1 and len(partial["only_in_earlier"]) == 1
    assert partial["replicated_fraction_of_earlier"] == 0.5
    assert "not an identity" in partial["meaning"]
    shifted = processed(
        write_tif(
            tmp_path / "d.tif",
            scene(),
            transform=from_origin(WEST + 5, NORTH, 1.0, 1.0),
        ),
        tag="d",
    )
    with pytest.raises(survey.SurveyReadError, match="same cells"):
        survey.compare_surveys(earlier, shifted)


def test_distance_to_a_registered_point_attaches_nothing(tmp_path):
    result = processed(write_tif(tmp_path / "tile.tif", scene()))
    inside = survey._lonlat("EPSG:26919", [WEST + 70.5], [NORTH - 60.5])[0]
    relation = survey.nearest_detections(result, lonlat=inside)
    assert relation["basis"] == "DISTANCE_ONLY_DISCOVERY"
    assert relation["inside_any_basin_bbox"] is True
    assert relation["nearest"][0]["distance_to_deepest_point_m"] < 5
    far = survey.nearest_detections(result, lonlat=(-66.0, 18.0))
    assert far["point_inside_window"] is False and far["inside_any_basin_bbox"] is False
    dry = survey.dry_registration(
        result, a_source(), created_utc="2026-11-15T00:00:00Z"
    )
    assert dry["features_that_would_be_filed"] == 2 and dry["verified"] == 0
    assert dry["by_status"] == {"CANDIDATE": 2}
    assert dry["written_to_committed_registry"] is False
    assert not ({"OPENING", "PASSAGE", "CONNECTION"} & set(dry["by_assertion_rung"]))


# ── The declared run and its committed evidence ──────────────────────────────


def _run_config(tmp_path, mutate):
    import yaml

    data = yaml.safe_load((REPO / survey_run.RUNS_PATH).read_text(encoding="utf-8"))
    mutate(data["runs"][0])
    path = tmp_path / "runs.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_a_run_may_not_state_a_position_or_leave_a_basis_blank(tmp_path):
    run_id = "2026-11-17"
    assert (
        survey_run.load_run(REPO / survey_run.RUNS_PATH, run_id)["half_size_m"] == 500
    )
    with pytest.raises(survey_run.SurveyRunError, match="may not state a position"):
        survey_run.load_run(
            _run_config(tmp_path, lambda r: r.update(lon=-66.9, lat=18.4)), run_id
        )
    with pytest.raises(survey_run.SurveyRunError, match="where the value was read"):
        survey_run.load_run(
            _run_config(
                tmp_path,
                lambda r: r["products"][1].update(vertical_uncertainty_basis=" "),
            ),
            run_id,
        )
    with pytest.raises(survey_run.SurveyRunError, match="positive or null"):
        survey_run.load_run(
            _run_config(
                tmp_path, lambda r: r["products"][1].update(vertical_uncertainty_m=0)
            ),
            run_id,
        )
    with pytest.raises(survey_run.SurveyRunError, match="nested basins are reported"):
        survey_run.load_run(
            _run_config(tmp_path, lambda r: r["parameters"].pop("nested")), run_id
        )
    assert (
        survey_run.load_run(REPO / survey_run.RUNS_PATH, run_id)["parameters"].nested
        is False
    )
    with pytest.raises(survey_run.SurveyRunError, match="no survey run"):
        survey_run.load_run(REPO / survey_run.RUNS_PATH, "1999-01-01")


@pytest.fixture(scope="module")
def committed():
    report = survey_run.current_report(REPO)
    if report is None:
        pytest.skip("no survey run is committed")
    return report


def test_the_committed_report_is_reproduced_from_committed_evidence(committed):
    run = survey_run.load_run(REPO / survey_run.RUNS_PATH, committed["run_id"])
    assert survey_run.check_report(run, repo_root=REPO) == []


def test_the_committed_run_changed_no_record_and_overstates_nothing(committed):
    build = seeding.build_all(REPO)
    registry = build.inland
    assert committed["registry_changes"] == 0
    assert committed["target_point_lonlat"] == list(
        seeding._point_of(registry, committed["target_feature"])
    )
    total = 0
    for product in committed["products"]:
        total += product["download"]["size_bytes"]
        source = registry.sources[product["source"]["source_id"]]
        assert source.provenance_state is v.ProvenanceState.REGISTERED
        assert source.manifestation_sha256 == product["download"]["sha256"]
        assert not source.is_direct_measurement
        assert product["subset"]["parent_sha256"] == product["download"]["sha256"]
        assert set(product["result"]["assertions_by_tier"]) <= {
            "CANDIDATE",
            "SUPPORTING",
        }
        assert product["dry_registration"]["verified"] == 0
        assert product["dry_registration"]["written_to_committed_registry"] is False
        assert product["vertical"]["statement_basis"].strip()
        if product["vertical_uncertainty"]["value_m"] is None:
            assert set(product["result"]["assertions_by_tier"]) == {"CANDIDATE"}
    assert total <= 800_000_000
    assert build.survey["registered"] == len(committed["products"])
    statuses = registry.counts()["features_by_status"]
    assert statuses["CANDIDATE"] == 4 and statuses["VERIFIED"] == 0
    cited = {
        sid
        for f in registry.features.values()
        for a in f.assertions
        for sid in a.source_ids
    }
    assert not cited & {p["source"]["source_id"] for p in committed["products"]}


def test_a_changed_subset_or_manifest_is_detected(committed, tmp_path):
    import yaml

    crosswalk = yaml.safe_load(
        (REPO / seeding.CROSSWALK_PATH).read_text(encoding="utf-8")
    )
    for rel in (
        survey_run.RUNS_PATH,
        "registry/access_points/inland.json",
        seeding.SEEDS_PATH,
        seeding.CROSSWALK_PATH,
        str(crosswalk["legacy_file"]),
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    run_id = committed["run_id"]
    shutil.copytree(
        REPO / survey_run.SURVEY_DIR / run_id, tmp_path / survey_run.SURVEY_DIR / run_id
    )
    run = survey_run.load_run(tmp_path / survey_run.RUNS_PATH, run_id)
    assert survey_run.check_report(run, repo_root=tmp_path) == []

    run_dir = tmp_path / survey_run.SURVEY_DIR / run_id
    subset = run_dir / "subsets" / "window_2018.tif"
    original = subset.read_bytes()
    window = survey.read_raster(subset)
    lowered = window.values.copy()
    lowered[400:420, 400:420] -= 5.0
    survey.write_subset(
        survey.RasterWindow(
            lowered,
            window.crs,
            window.origin,
            window.cell_size,
            0,
            0,
            window.source_shape,
            window.source_nodata,
        ),
        subset,
    )
    assert any(
        "not reproduced" in p for p in survey_run.check_report(run, repo_root=tmp_path)
    )
    subset.write_bytes(original)
    assert survey_run.check_report(run, repo_root=tmp_path) == []

    manifest_path = next((run_dir / "products").glob("*2018*.manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    manifest["response_size"] += 1
    manifest_path.write_text(json.dumps(manifest))
    assert any(
        "disagrees with the catalogue" in p
        for p in survey_run.check_report(run, repo_root=tmp_path)
    )
