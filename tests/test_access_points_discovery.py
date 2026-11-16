"""Planned, bounded discovery runs: search areas, ceilings, replay and registration.

Everything here runs offline against a scripted stand-in for the catalogues.
No test makes a network request, and one test proves the planner cannot.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

from pipeline.marine_reference_run import GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1
from pipeline.marine_sources import BoundingBox
from spiderweb.access_points import acquisition as acq
from spiderweb.access_points import discovery as disc
from spiderweb.access_points import seeding
from spiderweb.access_points import vocabulary as v
from tests import access_points_support as sup
from tests.test_access_points_integration import FakeNoaa, lidar_row

REPO = Path(__file__).resolve().parents[1]
OFFSHORE, INLAND = sup.OFFSHORE, sup.INLAND
GRANT = acq.Authorization(
    acq.AuthorizationLevel.METADATA_DISCOVERY, "test-operator", 20
)
WHEN = "2026-11-15T00:00:00+00:00"
ALLOWED_HOSTS = {"coast.noaa.gov", "www.ngdc.noaa.gov", "gis.ngdc.noaa.gov"}


@pytest.fixture(scope="module")
def build():
    return seeding.build_all(REPO)


@pytest.fixture(scope="module")
def config():
    return disc.load_corridor_config(REPO / disc.CORRIDORS_PATH)


@pytest.fixture(scope="module")
def targets(build, config):
    return disc.build_targets(config, [build.inland, build.offshore])


def run(targets, transport=None, authorization=GRANT, ceiling=500, run_id="test-run"):
    return disc.run_discovery(
        targets,
        run_id=run_id,
        discovered_utc=WHEN,
        transport=transport if transport is not None else FakeNoaa(),
        authorization=authorization,
        max_total_requests=ceiling,
    )


def points_of(build):
    return {
        registry.namespace: disc.registered_points(registry)
        for registry in (build.inland, build.offshore)
    }


# ── Search areas are not positions ───────────────────────────────────────────


def test_committed_corridors_follow_the_seeds_and_state_no_position(config):
    corridors = disc.corridor_targets(config)
    seeds = yaml.safe_load((REPO / seeding.SEEDS_PATH).read_text(encoding="utf-8"))
    assert {(c.seed_label, c.locality) for c in corridors} == {
        (s["label"], s["locality"]) for s in seeds["seeds"]
    }
    for corridor in corridors:
        assert corridor.namespace is OFFSHORE
        assert corridor.basis is disc.TargetBasis.ANALYST_CORRIDOR
        assert corridor.feature_id is None
        described = corridor.to_dict()
        assert described["certified"] is False
        assert described["role"] == "discovery_corridor"
        assert "not a seed position" in corridor.provenance
    raw = yaml.safe_load((REPO / disc.CORRIDORS_PATH).read_text(encoding="utf-8"))
    for entry in raw["corridors"]:
        assert set(entry) <= {
            "corridor_id",
            "registry",
            "locality",
            "seed_label",
            "bbox",
            "provenance",
        }


def test_the_guayama_corridor_is_the_existing_one_unchanged(config):
    corridor = next(
        c
        for c in disc.corridor_targets(config)
        if c.target_id == GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1.aoi_id
    )
    assert corridor.bbox == GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1.bbox


@pytest.mark.parametrize(
    "extra",
    [
        {"coordinates": [-67.2, 18.5]},
        {"lat": 18.5},
        {"depth_m": 400},
        {"geometry": {"type": "Point", "coordinates": [-67.2, 18.5]}},
        {"feature_id": "OFAP-PR-000001"},
    ],
)
def test_a_corridor_that_states_a_position_or_a_feature_is_refused(config, extra):
    bad = dict(config)
    bad["corridors"] = [{**dict(config["corridors"][0]), **extra}]
    with pytest.raises(disc.DiscoveryConfigError, match="search area"):
        disc.corridor_targets(bad)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"bbox": [-67.0, 18.0, -67.5, 18.5]}, "minimums"),
        ({"bbox": [-67.0, 18.0, -66.5]}, "four numbers"),
        ({"provenance": "  "}, "provenance"),
        ({"registry": "access_point.orbital"}, "unknown registry"),
        ({"corridor_id": ""}, "missing or repeated"),
        ({"reviewer": "someone"}, "unknown keys"),
    ],
)
def test_malformed_corridors_fail_closed(config, change, message):
    bad = dict(config)
    bad["corridors"] = [{**dict(config["corridors"][0]), **change}]
    with pytest.raises(disc.DiscoveryConfigError, match=message):
        disc.corridor_targets(bad)


def test_repeated_corridor_ids_and_bad_files_are_refused(config, tmp_path):
    bad = dict(config)
    bad["corridors"] = [config["corridors"][0], config["corridors"][0]]
    with pytest.raises(disc.DiscoveryConfigError, match="repeated"):
        disc.corridor_targets(bad)
    path = tmp_path / "corridors.yaml"
    path.write_text("version: something_else\ncorridors: []\n", encoding="utf-8")
    with pytest.raises(disc.DiscoveryConfigError, match="version"):
        disc.load_corridor_config(path)
    path.write_text(
        f"version: {disc.CORRIDORS_VERSION}\npoint_buffer_half_width_deg: 3\ncorridors: []\n",
        encoding="utf-8",
    )
    with pytest.raises(disc.DiscoveryConfigError, match="half_width"):
        disc.load_corridor_config(path)


def test_point_boxes_exist_only_for_features_that_hold_a_point(build, config):
    half = float(config["point_buffer_half_width_deg"])
    inland = disc.point_targets(build.inland, half_width_deg=half)
    offshore = disc.point_targets(build.offshore, half_width_deg=half)
    assert len(inland) == 4 and len(offshore) == 1
    # The five provisional seeds hold no geometry, so nothing is computed for them.
    seeded = {
        f.feature_id for f in build.offshore.features.values() if f.provisional_labels
    }
    assert len(seeded) == 5 and not seeded & {t.feature_id for t in offshore}
    for registry, made in ((build.inland, inland), (build.offshore, offshore)):
        points = disc.registered_points(registry)
        for target in made:
            lon, lat = points[target.feature_id]
            assert target.basis is disc.TargetBasis.REGISTERED_POINT_BUFFER
            assert target.bbox.min_lon < lon < target.bbox.max_lon
            assert target.bbox.min_lat < lat < target.bbox.max_lat
            assert target.bbox.max_lon - target.bbox.min_lon == pytest.approx(2 * half)


def test_a_target_cannot_mix_the_two_bases():
    box = BoundingBox(-67.0, 18.0, -66.9, 18.1)
    with pytest.raises(disc.DiscoveryConfigError, match="must name its feature"):
        disc.DiscoveryTarget(
            "t", OFFSHORE, box, disc.TargetBasis.REGISTERED_POINT_BUFFER, "computed"
        )
    with pytest.raises(disc.DiscoveryConfigError, match="must not be tied"):
        disc.DiscoveryTarget(
            "t",
            OFFSHORE,
            box,
            disc.TargetBasis.ANALYST_CORRIDOR,
            "drawn",
            feature_id="OFAP-PR-000001",
        )
    with pytest.raises(ValueError, match="provenance"):
        disc.DiscoveryTarget("t", OFFSHORE, box, disc.TargetBasis.ANALYST_CORRIDOR, " ")


def test_running_discovery_gives_no_seed_a_geometry(build, targets):
    before = build.offshore.to_document()
    catalogue = disc.build_catalogue(run(targets), feature_points=points_of(build))
    assert build.offshore.to_document() == before
    assert catalogue["automatic_promotions"] == 0
    assert catalogue["data_products_downloaded"] == 0
    for entry in catalogue["targets"]:
        if entry["basis"] == "ANALYST_CORRIDOR":
            assert entry["feature_id"] is None and entry["certified"] is False


# ── The plan touches nothing ─────────────────────────────────────────────────


def test_the_plan_is_computed_without_a_socket(targets, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the planner opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    plan = disc.plan(targets)
    assert plan["network_used"] is False
    assert len(plan["targets"]) == 10
    # 6 off-shore targets x 6 providers + 4 inland targets x 3 providers
    assert plan["first_requests"] == 6 * 6 + 4 * 3
    for entry in plan["targets"]:
        for provider in entry["providers"]:
            url = urlparse(provider["first_request_url"])
            assert url.scheme == "https" and url.hostname in ALLOWED_HOSTS


# ── Grants and ceilings ──────────────────────────────────────────────────────


def test_without_a_grant_nothing_is_requested_anywhere(targets):
    fake = FakeNoaa()
    done = run(targets, transport=fake, authorization=acq.Authorization())
    assert fake.calls == []
    assert done.state is acq.RunState.NOT_AUTHORIZED and done.total_requests == 0
    catalogue = disc.build_catalogue(done)
    assert catalogue["sources"] == [] and catalogue["state"] == "NOT_AUTHORIZED"
    assert catalogue["totals"]["provider_runs_by_state"] == {"NOT_AUTHORIZED": 48}
    assert not any(t["zero_result_claim_permitted"] for t in catalogue["targets"])


def test_the_run_wide_ceiling_stops_requests_and_is_not_read_as_empty(targets):
    fake = FakeNoaa()
    done = run(targets, transport=fake, ceiling=7)
    assert len(fake.calls) == 7 and done.total_requests == 7
    assert done.state is acq.RunState.NOT_AUTHORIZED
    catalogue = disc.build_catalogue(done)
    states = catalogue["totals"]["provider_runs_by_state"]
    assert states["NOT_AUTHORIZED"] == 48 - 7
    blocked = [t for t in catalogue["targets"] if t["state"] == "NOT_AUTHORIZED"]
    assert blocked and not any(t["zero_result_claim_permitted"] for t in blocked)


def test_the_per_target_ceiling_is_the_grant(targets):
    small = acq.Authorization(acq.AuthorizationLevel.METADATA_DISCOVERY, "tester", 2)
    fake = FakeNoaa()
    done = run(targets, transport=fake, authorization=small)
    for result in done.results:
        assert sum(r.request_count for r in result.receipt.runs) <= 2
    assert done.state is acq.RunState.NOT_AUTHORIZED


def test_run_arguments_are_validated(targets):
    with pytest.raises(ValueError, match="run_id"):
        run(targets, run_id="../elsewhere")
    with pytest.raises(ValueError, match="max_total_requests"):
        run(targets, ceiling=0)
    with pytest.raises(disc.DiscoveryConfigError, match="unique"):
        run([targets[0], targets[0]])


def test_a_failing_provider_is_reported_and_the_rest_still_run(targets):
    def broken(url, query):
        raise OSError("connection reset by peer")

    done = run(targets, transport=FakeNoaa(multibeam=broken))
    assert done.state is acq.RunState.FAIL
    catalogue = disc.build_catalogue(done)
    states = catalogue["totals"]["provider_runs_by_state"]
    assert states["FAIL"] == 6 and states["PASS"] + states["ZERO"] == 42
    assert "NCEI_MULTIBEAM_CATALOG" not in catalogue["totals"]["sources_by_provider"]
    failed = [
        p for t in catalogue["targets"] for p in t["providers"] if p["state"] == "FAIL"
    ]
    assert all("connection reset" in p["error"] for p in failed)


# ── The catalogue closes ─────────────────────────────────────────────────────


def test_a_source_listed_by_several_boxes_is_recorded_once(build, targets):
    catalogue = disc.build_catalogue(run(targets), feature_points=points_of(build))
    disc.verify_sealed(catalogue, what="catalogue")
    keys = [(s["provider_id"], s["native_identifier"]) for s in catalogue["sources"]]
    assert len(keys) == len(set(keys)) == catalogue["totals"]["sources"] == 6
    assert sum(catalogue["totals"]["sources_by_provider"].values()) == 6
    by_native = {s["native_identifier"]: s for s in catalogue["sources"]}
    topobathy = by_native["USIEI:GlobalID:{TEST-TB-1}"]
    assert len(topobathy["targets"]) == 10
    assert topobathy["namespaces"] == [INLAND.value, OFFSHORE.value]
    topo = by_native["USIEI:GlobalID:{TEST-TOPO-1}"]
    assert topo["namespaces"] == [INLAND.value] and len(topo["targets"]) == 4
    bag = by_native["NOS:BAG:TEST-BAG-001"]
    assert bag["namespaces"] == [OFFSHORE.value] and len(bag["targets"]) == 6
    assert catalogue["totals"]["sources_by_namespace"] == {
        INLAND.value: 3,
        OFFSHORE.value: 4,
    }
    assert catalogue["totals"]["requests"] == 48
    assert catalogue["totals"]["inconsistent_rows_within_run"] == 0


def test_placeholder_datums_are_counted_not_accepted(targets):
    totals = disc.build_catalogue(run(targets))["totals"]
    # The three inventory rows publish "User Specified"; none names a datum.
    assert totals["sources_stating_a_vertical_datum_field"] == 3
    assert totals["vertical_datum_placeholders"] == 3


def test_a_row_that_differs_between_boxes_is_reported(targets):
    seen = {"n": 0}

    def shifting(url, query):
        seen["n"] += 1
        rows = [lidar_row("{TEST-TB-1}", name=f"project as seen in call {seen['n']}")]
        from tests.test_access_points_integration import frozen

        return frozen(url, {"features": rows, "exceededTransferLimit": False})

    catalogue = disc.build_catalogue(run(targets, transport=FakeNoaa(usiei0=shifting)))
    assert catalogue["totals"]["inconsistent_rows_within_run"] == 9
    assert {r["native_identifier"] for r in catalogue["inconsistent_rows"]} == {
        "USIEI:GlobalID:{TEST-TB-1}"
    }


def test_review_flags_point_at_features_and_change_nothing(build, targets):
    inside = {OFFSHORE: {"OFAP-PR-000006": (-66.0, 17.9)}}
    catalogue = disc.build_catalogue(run(targets), feature_points=inside)
    flags = catalogue["review_flags"]
    assert flags and {f["feature_id"] for f in flags} == {"OFAP-PR-000006"}
    assert {f["basis"] for f in flags} == {"POINT_IN_ENVELOPE_PLANNING"}
    # Catalogue rows without a footprint can never be placed over a feature.
    assert not any(f["provider_id"].startswith("NCEI") for f in flags)
    outside = {OFFSHORE: {"OFAP-PR-000006": (-60.0, 10.0)}}
    assert (
        disc.build_catalogue(run(targets), feature_points=outside)["review_flags"] == []
    )
    assert catalogue["automatic_promotions"] == 0


# ── Kept bytes reproduce the record ──────────────────────────────────────────


def test_a_written_run_replays_to_identical_receipts(build, targets, tmp_path):
    done = run(targets)
    catalogue = disc.write_run(done, tmp_path, feature_points=points_of(build))
    run_dir = tmp_path / "test-run"
    assert disc.verify_run(run_dir) == []
    replayed = disc.replay_run(run_dir)
    for original, again in zip(done.results, replayed.results):
        assert again.receipt.to_document() == original.receipt.to_document()
    pointer = json.loads((tmp_path / disc.POINTER_NAME).read_text(encoding="utf-8"))
    assert pointer["run_id"] == "test-run" and pointer["raw_bytes_kept"] is True
    path = disc.current_catalogue_path(tmp_path)
    assert disc.load_catalogue(path) == catalogue
    with pytest.raises(FileExistsError, match="never overwritten"):
        disc.write_run(done, tmp_path)


def test_tampered_bytes_and_records_are_detected(build, targets, tmp_path):
    disc.write_run(run(targets), tmp_path, feature_points=points_of(build))
    run_dir = tmp_path / "test-run"
    target = targets[0].target_id

    body = next((run_dir / disc.RAW_DIR / target).glob("*.bin"))
    original = body.read_bytes()
    body.write_bytes(original + b" ")
    assert any("does not match" in p for p in disc.verify_run(run_dir))
    body.write_bytes(original)
    assert disc.verify_run(run_dir) == []

    receipt = run_dir / f"{target}.receipt.json"
    document = json.loads(receipt.read_text(encoding="utf-8"))
    document["providers"][0]["row_count"] += 1
    receipt.write_text(json.dumps(document), encoding="utf-8")
    assert any("does not reproduce" in p for p in disc.verify_run(run_dir))

    catalogue = run_dir / disc.CATALOGUE_NAME
    text = catalogue.read_text(encoding="utf-8").replace("TEST-BAG-001", "TEST-BAG-999")
    catalogue.write_text(text, encoding="utf-8")
    assert any("content hash" in p for p in disc.verify_run(run_dir))
    with pytest.raises(disc.DiscoveryEvidenceError, match="pointer's hash"):
        disc.current_catalogue_path(tmp_path)


def test_the_pointer_cannot_leave_its_folder(tmp_path):
    assert disc.current_catalogue_path(tmp_path) is None
    pointer = tmp_path / disc.POINTER_NAME
    pointer.write_text(
        json.dumps(
            {
                "schema": disc.POINTER_SCHEMA,
                "run_id": "x",
                "catalogue": "../../etc/passwd",
                "catalogue_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(disc.DiscoveryEvidenceError, match="inside the run folder"):
        disc.current_catalogue_path(tmp_path)
    pointer.write_text(json.dumps({"schema": "something"}), encoding="utf-8")
    with pytest.raises(disc.DiscoveryEvidenceError, match="not a discovery pointer"):
        disc.current_catalogue_path(tmp_path)


def test_a_run_kept_without_bytes_cannot_be_replayed(targets, tmp_path):
    disc.write_run(run(targets), tmp_path, keep_raw=False)
    problems = disc.verify_run(tmp_path / "test-run")
    assert problems and "no kept bytes" in problems[0]


# ── Comparison with an earlier listing ───────────────────────────────────────


def test_comparison_with_an_earlier_listing_is_set_arithmetic(targets):
    guayama = next(t for t in targets if t.target_id.startswith("guayama"))
    box = [
        guayama.bbox.min_lon,
        guayama.bbox.min_lat,
        guayama.bbox.max_lon,
        guayama.bbox.max_lat,
    ]

    def broken(url, query):
        raise OSError("timed out")

    done = run(targets, transport=FakeNoaa(sounding=broken))
    result = disc.compare_with_listing(
        done,
        target_id=guayama.target_id,
        bbox=box,
        listed={
            "NCEI_MULTIBEAM_CATALOG": [
                "NCEI:multibeam:TEST-SURVEY-001",
                "NCEI:multibeam:TEST-SURVEY-OLD",
            ],
            "NCEI_SOUNDING_CATALOG": ["NCEI:sounding:H00001"],
        },
    )
    multibeam = result["providers"]["NCEI_MULTIBEAM_CATALOG"]
    assert multibeam["in_both"] == 1
    assert multibeam["only_before"] == ["NCEI:multibeam:TEST-SURVEY-OLD"]
    assert multibeam["only_now"] == ["NCEI:multibeam:TEST-SURVEY-002"]
    # A provider that failed is not comparable; its silence is not a withdrawal.
    assert result["providers"]["NCEI_SOUNDING_CATALOG"]["comparable"] is False
    with pytest.raises(ValueError, match="different box"):
        disc.compare_with_listing(
            done, target_id=guayama.target_id, bbox=[0, 0, 1, 1], listed={}
        )


# ── Registration into the registries ─────────────────────────────────────────


def _temp_repo(tmp_path: Path) -> Path:
    crosswalk = yaml.safe_load(
        (REPO / seeding.CROSSWALK_PATH).read_text(encoding="utf-8")
    )
    for rel in (
        seeding.SEEDS_PATH,
        seeding.CROSSWALK_PATH,
        str(crosswalk["legacy_file"]),
        seeding.GUAYAMA_RECEIPT_PATH,
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def test_without_a_committed_run_the_build_registers_no_discovered_source(tmp_path):
    built = seeding.build_all(_temp_repo(tmp_path))
    assert built.discovery is None
    assert built.guayama["added"] == 47 and built.guayama["already_registered"] == 0


def test_discovered_sources_are_registered_as_references_only(build, targets, tmp_path):
    root = _temp_repo(tmp_path)
    plain = seeding.build_all(root)
    disc.write_run(
        run(targets), root / disc.DISCOVERY_DIR, feature_points=points_of(build)
    )
    built = seeding.build_all(root)
    assert built.discovery["registered"] == {INLAND.value: 3, OFFSHORE.value: 4}
    assert len(built.inland.sources) == len(plain.inland.sources) + 3
    assert len(built.offshore.sources) == len(plain.offshore.sources) + 4
    for registry in (built.inland, built.offshore):
        assert not any(s.is_direct_measurement for s in registry.sources.values())
    added = set(built.offshore.sources) - set(plain.offshore.sources)
    for source_id in added:
        source = built.offshore.sources[source_id]
        assert source.provenance_state is v.ProvenanceState.REFERENCED_ONLY
        assert source.manifestation_sha256 is None and source.retrieved_utc is None
    # No feature, observation, geometry or status moved.
    for before, after in (
        (plain.inland, built.inland),
        (plain.offshore, built.offshore),
    ):
        a, b = before.to_document(), after.to_document()
        for key in ("features", "observations", "derived_geometries"):
            assert a[key] == b[key]
        assert a["counts"]["features_by_status"] == b["counts"]["features_by_status"]
    # The build is still deterministic and names its new inputs.
    again = seeding.build_all(root)
    assert again.offshore.to_document() == built.offshore.to_document()
    assert f"{disc.DISCOVERY_DIR}/{disc.POINTER_NAME}" in built.input_hashes
    manifest_dir = tmp_path / "out"
    seeding.write_documents(built, manifest_dir)
    manifest = json.loads(
        (manifest_dir / seeding.REGISTRY_DIR / "build_manifest.json").read_text()
    )
    assert manifest["counts"]["live_discovery"]["run_id"] == "test-run"


def test_a_survey_already_listed_by_discovery_is_not_registered_twice(
    build, targets, tmp_path
):
    root = _temp_repo(tmp_path)
    listed = FakeNoaa(multibeam=[{"surveyId": "AT20"}, {"surveyId": "EX1811"}])
    disc.write_run(run(targets, transport=listed), root / disc.DISCOVERY_DIR)
    built = seeding.build_all(root)
    assert built.guayama["multibeam"] == 13  # the receipt still closes
    assert built.guayama["already_registered"] == 2 and built.guayama["added"] == 45
    natives = [
        s.native_identifier
        for s in built.offshore.sources.values()
        if s.provider == "NCEI_MULTIBEAM_CATALOG"
    ]
    assert len(natives) == len(set(natives)) == 13


def test_a_catalogue_whose_totals_do_not_close_is_refused(build, targets):
    catalogue = disc.build_catalogue(run(targets))
    catalogue["totals"]["sources_by_namespace"][OFFSHORE.value] += 1
    fresh = seeding.build_all(REPO)
    with pytest.raises(seeding.SeedingError, match="totals do not match"):
        seeding.register_discovered_sources(
            {INLAND: fresh.inland, OFFSHORE: fresh.offshore}, catalogue
        )


def test_a_catalogue_that_misplaces_a_provider_is_refused(build, targets):
    catalogue = disc.build_catalogue(run(targets))
    for entry in catalogue["sources"]:
        if entry["provider_id"] == "NOS_BAG_INVENTORY":
            entry["namespaces"] = [INLAND.value]
    fresh = seeding.build_all(REPO)
    with pytest.raises(seeding.SeedingError, match="does not serve"):
        seeding.register_discovered_sources(
            {INLAND: fresh.inland, OFFSHORE: fresh.offshore}, catalogue
        )


# ── The live transport and the command ───────────────────────────────────────


class _Response:
    def __init__(self, url, body=b"{}", headers=None, status=200):
        self._url, self._body, self.status = url, body, status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body

    def geturl(self):
        return self._url


def test_the_live_transport_sends_a_generic_agent_and_keeps_safe_headers(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["agent"] = request.get_header("User-agent")
        return _Response(
            request.full_url,
            headers={
                "Content-Type": "application/json",
                "Set-Cookie": "session=abc",
                "Server": "example",
                "ETag": "x1",
            },
        )

    monkeypatch.setattr(acq, "urlopen", fake_urlopen)
    response = acq.live_transport()("https://example.invalid/catalogue?a=1")
    assert sent["agent"] == acq.GENERIC_USER_AGENT
    assert "spiderweb" not in sent["agent"].lower()
    assert response.request_url == "https://example.invalid/catalogue?a=1"
    assert set(response.headers) == {"Content-Type", "ETag"}


def test_the_live_transport_refuses_plain_http_and_redirects(monkeypatch):
    monkeypatch.setattr(
        acq, "urlopen", lambda request, timeout: _Response("https://elsewhere.invalid/")
    )
    transport = acq.live_transport()
    with pytest.raises(ValueError, match="only https"):
        transport("http://example.invalid/catalogue")
    with pytest.raises(acq.UnexpectedRedirect):
        transport("https://example.invalid/catalogue")
    with pytest.raises(ValueError, match="user agent"):
        acq.live_transport(user_agent=" ")


def _command():
    spec = importlib.util.spec_from_file_location(
        "discover_access_point_sources",
        REPO / "scripts" / "discover_access_point_sources.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_command_plans_by_default_and_refuses_to_run_without_a_grant(
    monkeypatch, capsys
):
    command = _command()

    def refuse(**kwargs):
        raise AssertionError("a live transport was built")

    monkeypatch.setattr(acq, "live_transport", refuse)
    monkeypatch.delenv(acq.AUTHORIZATION_ENV, raising=False)
    assert command.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["network_used"] is False and plan["first_requests"] == 48
    assert command.main(["--execute", "--run-id", "never-written"]) == 2
    assert "NOT AUTHORISED" in capsys.readouterr().err
    assert not (REPO / disc.DISCOVERY_DIR / "never-written").exists()
    monkeypatch.setenv(acq.AUTHORIZATION_ENV, "everything:please")
    assert command.main(["--execute", "--run-id", "never-written"]) == 2


def test_the_command_reports_evidence_that_does_not_reproduce(capsys):
    command = _command()
    assert command.main(["--verify", "no-such-run"]) == 1
    assert "DOES NOT REPRODUCE" in capsys.readouterr().out
