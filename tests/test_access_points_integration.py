"""Acquisition, monitoring, cross-repository context, registry builder, service.

All transports are injected; nothing here touches the network.  Payloads are
synthetic and use artificial identifiers.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from pipeline.marine_sources import BoundingBox, FrozenHttpResponse
from spiderweb.access_points import acquisition as acq
from spiderweb.access_points import federation_context as fc
from spiderweb.access_points import models as m
from spiderweb.access_points import monitoring as mon
from spiderweb.access_points import namespaces as ns
from spiderweb.access_points import rules, seeding
from spiderweb.access_points import service as svc
from spiderweb.access_points import vocabulary as v
from spiderweb.access_points.registry import AccessPointRegistry
from tests import access_points_support as sup

REPO = Path(__file__).resolve().parents[1]
BBOX = BoundingBox(-66.3, 17.5, -65.7, 18.1)
GRANT = acq.Authorization(acq.AuthorizationLevel.METADATA_DISCOVERY, "test-operator", 200)
RING = [[-66.2, 17.8], [-65.8, 17.8], [-65.8, 18.0], [-66.2, 18.0], [-66.2, 17.8]]
OFFSHORE, INLAND = sup.OFFSHORE, sup.INLAND


def frozen(url: str, payload, status: int = 200, raw: bytes | None = None) -> FrozenHttpResponse:
    body = raw if raw is not None else json.dumps(payload).encode()
    return FrozenHttpResponse(url, status, "2026-11-15T00:00:00+00:00",
                              hashlib.sha256(body).hexdigest(), len(body),
                              {"Content-Type": "application/json"}, body)


def lidar_row(global_id, name="synthetic project", **attrs):
    return {"attributes": {"GlobalID": global_id, "ProjectName": name, "CollectionDate": "2020",
                           "VerticalDatum": "User Specified", **attrs},
            "geometry": {"rings": [RING]}}


class FakeNoaa:
    """A scriptable stand-in for the catalogue and inventory endpoints."""

    def __init__(self, **overrides):
        self.calls: list[str] = []
        self.tables = {
            "usiei0": [lidar_row("{TEST-TB-1}")],
            "usiei1": [lidar_row("{TEST-TOPO-1}"), lidar_row("{TEST-TOPO-2}")],
            "usiei2": [], "usiei3": [], "usiei4": [],
            "multibeam": [{"surveyId": "TEST-SURVEY-001"}, {"surveyId": "TEST-SURVEY-002"}],
            "sounding": [],
            "bag": [{"attributes": {"SURVEY_ID": "TEST-BAG-001"}, "geometry": {"rings": [RING]}}],
        }
        self.tables.update(overrides)

    def __call__(self, url: str) -> FrozenHttpResponse:
        self.calls.append(url)
        query = parse_qs(urlparse(url).query)
        if "USInteragencyElev" in url:
            key = "usiei" + url.split("/MapServer/")[1].split("/")[0]
            return self._arcgis(url, key, query)
        if "nos_hydro_dynamic" in url:
            return self._arcgis(url, "bag", query)
        key = "multibeam" if "multibeam" in url else "sounding"
        table = self.tables[key]
        if callable(table):
            return table(url, query)
        offset = int(query.get("offset", ["0"])[0])
        size = int(query.get("pageSize", query.get("page_size", ["100"]))[0])
        return frozen(url, {"items": table[offset:offset + size], "count": len(table)})

    def _arcgis(self, url, key, query):
        table = self.tables[key]
        if callable(table):
            return table(url, query)
        offset = int(query.get("resultOffset", ["0"])[0])
        size = int(query.get("resultRecordCount", ["2000"])[0])
        page = table[offset:offset + size]
        return frozen(url, {"features": page, "exceededTransferLimit": offset + size < len(table)})


def discover(namespace=OFFSHORE, transport=None, authorization=GRANT, **kw):
    return acq.discover_sources(namespace, BBOX, discovered_utc="2026-11-15T00:00:00Z",
                                transport=transport if transport is not None else FakeNoaa(),
                                authorization=authorization, **kw)


def run_of(receipt, provider_id):
    return next(r for r in receipt.runs if r.provider_id == provider_id)


# ── Authorisation ────────────────────────────────────────────────────────────


def test_nothing_is_requested_without_an_explicit_grant():
    fake = FakeNoaa()
    receipt = acq.discover_sources(OFFSHORE, BBOX, discovered_utc="t", transport=fake)
    assert fake.calls == []
    assert receipt.state is acq.RunState.NOT_AUTHORIZED
    assert {r.state for r in receipt.runs} == {acq.RunState.NOT_AUTHORIZED}
    assert [(s.state, s.outcome) for s in receipt.lifecycle] == [
        (acq.LifecycleState.DISCOVER, acq.StepOutcome.NOT_AUTHORIZED)]
    assert not receipt.zero_result_claim_permitted and receipt.sources() == []
    with pytest.raises(acq.AcquisitionNotAuthorized):
        acq.denied_transport("https://example.invalid/x")
    with pytest.raises(acq.AcquisitionNotAuthorized):
        acq.discover_sources(OFFSHORE, BBOX, discovered_utc="t", authorization=GRANT).state and \
            acq.budgeted(acq.denied_transport, GRANT)("https://example.invalid/x")


@pytest.mark.parametrize(
    "value, granted",
    [("metadata:20:operator", True), ("", False), ("yes", False), ("true", False),
     ("metadata", False), ("metadata:0:operator", False), ("metadata:-5:operator", False),
     ("metadata:abc:operator", False), ("metadata:20:", False), ("metadata:20:   ", False),
     ("fetch:20:operator", False), ("bulk:999:operator", False)],
)
def test_environment_grant_is_exact_or_nothing(value, granted):
    grant = acq.Authorization.from_environment({acq.AUTHORIZATION_ENV: value} if value else {})
    assert (grant.level is acq.AuthorizationLevel.METADATA_DISCOVERY) is granted
    if granted:
        assert (grant.max_requests, grant.granted_by) == (20, "operator")


def test_grant_must_be_named_and_bounded_and_is_enforced():
    for bad in ({"granted_by": ""}, {"max_requests": 0}):
        with pytest.raises(ValueError):
            acq.Authorization(**{"level": acq.AuthorizationLevel.METADATA_DISCOVERY,
                                 "granted_by": "x", "max_requests": 5, **bad})
    tight = acq.Authorization(acq.AuthorizationLevel.METADATA_DISCOVERY, "test-operator", 2)
    fake = FakeNoaa()
    receipt = discover(transport=fake, authorization=tight)
    assert len(fake.calls) == 2
    states = [r.state for r in receipt.runs]
    assert states[:2] == [acq.RunState.PASS, acq.RunState.ZERO]
    assert set(states[2:]) == {acq.RunState.NOT_AUTHORIZED}
    assert receipt.state is acq.RunState.NOT_AUTHORIZED and not receipt.zero_result_claim_permitted


def test_discovery_downloads_no_data_product():
    fake = FakeNoaa()
    receipt = discover(transport=fake)
    assert receipt.lifecycle[-1].state is acq.LifecycleState.ACQUIRE_IF_AUTHORIZED
    assert receipt.lifecycle[-1].outcome is acq.StepOutcome.NOT_AUTHORIZED
    assert [s.state for s in receipt.lifecycle] == list(acq.LIFECYCLE_ORDER[:7])
    for url in fake.calls:
        assert "/query?" in url or "/catalog" in url or "MapServer" in url, url
        assert not url.lower().endswith((".bag", ".tif", ".laz", ".las", ".xyz", ".zip", ".nc"))
    assert "no data product was downloaded by this run" in receipt.to_document()["invariants"]


# ── Completeness and failure semantics ───────────────────────────────────────


def test_clean_discovery_states_and_sources():
    receipt = discover()
    assert receipt.state is acq.RunState.PASS
    assert run_of(receipt, "NCEI_MULTIBEAM_CATALOG").row_count == 2
    assert run_of(receipt, "NCEI_SOUNDING_CATALOG").state is acq.RunState.ZERO
    assert run_of(receipt, "NCEI_MULTIBEAM_CATALOG").completeness is acq.Completeness.COUNT_CLOSED
    assert not receipt.zero_result_claim_permitted  # some providers returned rows
    sources = receipt.sources()
    assert len(sources) == 4
    for source in sources:
        assert source.provenance_state is v.ProvenanceState.REFERENCED_ONLY
        assert source.coverage_state.value == "UNKNOWN" and not source.is_direct_measurement
    coverage = receipt.coverage()
    assert {row["basis"] for row in coverage} == {"ENVELOPE_ONLY_PLANNING"}
    assert {row["envelope_relation"] for row in coverage} <= {s.value for s in v.SpatialState}
    document = receipt.to_document()
    body = {k: val for k, val in document.items() if k != "content_sha256"}
    from federation.spatial_core import canonical_json_sha256
    assert document["content_sha256"] == canonical_json_sha256(body)


def test_inland_and_offshore_use_their_own_providers():
    inland = discover(INLAND)
    assert {r.provider_id for r in inland.runs} == {"USIEI_TOPOGRAPHIC_LIDAR", "USIEI_TOPOBATHY_LIDAR",
                                                    "USIEI_IFSAR"}
    assert run_of(inland, "USIEI_TOPOGRAPHIC_LIDAR").row_count == 2
    with pytest.raises(ValueError, match="does not serve"):
        discover(INLAND, provider_ids=["NCEI_MULTIBEAM_CATALOG"])


def test_everything_empty_permits_a_zero_claim_and_a_failure_forbids_it():
    empty = FakeNoaa(usiei0=[], usiei1=[], multibeam=[], bag=[])
    assert discover(transport=empty).zero_result_claim_permitted
    assert discover(transport=empty).state is acq.RunState.ZERO
    failing = FakeNoaa(usiei0=[], usiei1=[], multibeam=[],
                       bag=lambda url, q: frozen(url, {"error": {"code": 500}}))
    receipt = discover(transport=failing)
    assert run_of(receipt, "NOS_BAG_INVENTORY").state is acq.RunState.FAIL
    assert receipt.state is acq.RunState.FAIL and not receipt.zero_result_claim_permitted


@pytest.mark.parametrize(
    "name, table",
    [("http 503", lambda url, q: frozen(url, {"items": [], "count": 0}, status=503)),
     ("invalid json", lambda url, q: frozen(url, None, raw=b"<html>busy</html>")),
     ("error object", lambda url, q: frozen(url, {"error": {"message": "x"}})),
     ("count drift", lambda url, q: frozen(
         url, {"items": [{"surveyId": f"TEST-{q.get('offset', ['0'])[0]}"}],
               "count": 2 if q.get("offset", ["0"])[0] == "0" else 3})),
     ("too many rows", lambda url, q: frozen(
         url, {"items": [{"surveyId": f"TEST-{i}"} for i in range(500)], "count": 500})),
     ("no identifier", lambda url, q: frozen(url, {"items": [{"platform": "x"}], "count": 1})),
     ("duplicate identifier", lambda url, q: frozen(
         url, {"items": [{"surveyId": "TEST-A"}, {"surveyId": "TEST-A"}], "count": 2}))],
)
def test_a_failed_source_is_a_failure_not_zero_data(name, table):
    receipt = discover(transport=FakeNoaa(multibeam=table))
    run = run_of(receipt, "NCEI_MULTIBEAM_CATALOG")
    assert run.state is acq.RunState.FAIL, name
    assert run.row_count == 0 and run.error
    assert not receipt.zero_result_claim_permitted
    # The other providers still ran: one failure hides nothing else.
    assert run_of(receipt, "USIEI_TOPOBATHY_LIDAR").state is acq.RunState.PASS


def test_pagination_is_followed_to_completion():
    many = [{"surveyId": f"TEST-SURVEY-{i:03d}"} for i in range(230)]
    lidar = [lidar_row(f"{{TEST-TB-{i}}}") for i in range(4500)]
    fake = FakeNoaa(multibeam=many, usiei0=lidar)
    receipt = discover(transport=fake)
    assert run_of(receipt, "NCEI_MULTIBEAM_CATALOG").row_count == 230
    assert run_of(receipt, "NCEI_MULTIBEAM_CATALOG").request_count == 3
    assert run_of(receipt, "USIEI_TOPOBATHY_LIDAR").row_count == 4500
    assert run_of(receipt, "USIEI_TOPOBATHY_LIDAR").request_count == 3
    stuck = lambda url, q: frozen(url, {"features": [], "exceededTransferLimit": True})  # noqa: E731
    assert run_of(discover(transport=FakeNoaa(usiei0=stuck)), "USIEI_TOPOBATHY_LIDAR").state is (
        acq.RunState.FAIL)


def test_source_identity_uses_stable_identifiers_never_names():
    same_name = [lidar_row("{TEST-A}", "Same Project Name"), lidar_row("{TEST-B}", "Same Project Name")]
    local_only = [{"attributes": {"OBJECTID": 41, "ProjectName": "row without stable id"},
                   "geometry": {"rings": [RING]}}]
    receipt = discover(transport=FakeNoaa(usiei0=same_name, usiei2=local_only))
    rows = run_of(receipt, "USIEI_TOPOBATHY_LIDAR").rows
    assert len({r.native_identifier for r in rows}) == 2
    (local,) = run_of(receipt, "USIEI_BATHYMETRIC_LIDAR").rows
    assert not local.identifier_is_stable and "OBJECTID" in local.native_identifier
    source = acq.to_source_manifestation(acq.PROVIDERS["USIEI_BATHYMETRIC_LIDAR"], local)
    assert source.lineage_root_id is None  # a row number is not a lineage root
    anonymous = [{"attributes": {"ProjectName": "no id at all"}, "geometry": {"rings": [RING]}}]
    assert run_of(discover(transport=FakeNoaa(usiei0=anonymous)), "USIEI_TOPOBATHY_LIDAR").state is (
        acq.RunState.FAIL)


# ── Transport wrappers and offline replay ────────────────────────────────────


def test_retry_surfaces_the_final_failure_and_never_invents_success():
    sleeps, attempts = [], {"n": 0}

    def flaky(url):
        attempts["n"] += 1
        return frozen(url, {}, status=503 if attempts["n"] < 3 else 200)

    assert acq.with_retry(flaky, sleep=sleeps.append)("u").status == 200
    assert attempts["n"] == 3 and sleeps == [1.5, 3.0]
    always = lambda url: frozen(url, {}, status=503)  # noqa: E731
    assert acq.with_retry(always, attempts=2, sleep=lambda s: None)("u").status == 503

    def broken(url):
        raise ConnectionResetError("reset")

    with pytest.raises(ConnectionResetError):
        acq.with_retry(broken, attempts=3, sleep=lambda s: None)("u")
    calls = {"n": 0}

    def denied(url):
        calls["n"] += 1
        raise acq.AcquisitionNotAuthorized("no")

    with pytest.raises(acq.AcquisitionNotAuthorized):
        acq.with_retry(denied, attempts=5, sleep=lambda s: None)("u")
    assert calls["n"] == 1  # an authorisation refusal is not retried
    assert acq.with_retry(lambda url: frozen(url, {}, status=404), sleep=lambda s: None)("u").status == 404
    with pytest.raises(ValueError):
        acq.with_retry(always, attempts=0)


def test_rate_limit_spaces_requests():
    now, slept = {"t": 0.0}, []

    def sleep(seconds):
        slept.append(round(seconds, 6))
        now["t"] += seconds

    limited = acq.with_rate_limit(lambda url: frozen(url, {}), min_interval_s=2.0,
                                  clock=lambda: now["t"], sleep=sleep)
    limited("a")
    now["t"] += 0.5
    limited("b")
    now["t"] += 5.0
    limited("c")
    assert slept == [1.5]


def test_frozen_fixtures_replay_exact_bytes_and_refuse_tampering(tmp_path):
    fake = FakeNoaa()
    recorder = acq.Recorder(fake)
    live = acq.discover_sources(OFFSHORE, BBOX, discovered_utc="t", transport=recorder,
                                authorization=GRANT)
    manifests = recorder.freeze_all(tmp_path, stem_prefix="synthetic")
    assert len(manifests) == len(fake.calls) and all((tmp_path / e["body_file"]).is_file() for e in manifests)
    replayed = acq.discover_sources(OFFSHORE, BBOX, discovered_utc="t",
                                    transport=acq.replay_transport(tmp_path), authorization=GRANT)
    assert [(r.provider_id, r.state, r.row_count) for r in replayed.runs] == [
        (r.provider_id, r.state, r.row_count) for r in live.runs]
    assert [s.source_id for s in replayed.sources()] == [s.source_id for s in live.sources()]
    with pytest.raises(acq.ReplayMiss):
        acq.replay_transport(tmp_path)("https://example.invalid/unknown")
    (tmp_path / manifests[0]["body_file"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="does not match"):
        acq.replay_transport(tmp_path)


def test_lifecycle_log_refuses_skipping_and_continuing_after_a_halt():
    log = acq.LifecycleLog()
    with pytest.raises(acq.LifecycleError):
        log.record(acq.LifecycleState.FREEZE_RAW, acq.StepOutcome.PASS, "skipped ahead")
    log.record(acq.LifecycleState.DISCOVER, acq.StepOutcome.PASS, "ok")
    log.record(acq.LifecycleState.INSPECT_METADATA, acq.StepOutcome.FAIL, "broken")
    assert log.halted
    with pytest.raises(acq.LifecycleError):
        log.record(acq.LifecycleState.IDENTIFY_SOURCE, acq.StepOutcome.PASS, "after a failure")
    assert [s.value for s in acq.LIFECYCLE_ORDER] == [
        "DISCOVER", "INSPECT_METADATA", "IDENTIFY_SOURCE", "VALIDATE_SCOPE", "VERIFY_ACCESS",
        "PLAN_ACQUISITION", "ACQUIRE_IF_AUTHORIZED", "FREEZE_RAW", "VERIFY_SCHEMA",
        "VALIDATE_GEOMETRY", "NORMALIZE", "INDEX", "ANALYZE", "PRESERVE_LINEAGE",
        "REGISTER_EVIDENCE", "VALIDATE_OUTPUT"]


# ── Monitoring ───────────────────────────────────────────────────────────────


def _events(comparisons):
    return {(c.provider_id, e.native_identifier): e.change for c in comparisons for e in c.events}


def test_first_observation_and_no_change():
    first = discover()
    comparisons = mon.compare_receipts(None, first)
    assert {c.state for c in comparisons if c.events} == {mon.ProviderChange.FIRST_OBSERVATION}
    assert set(_events(comparisons).values()) == {mon.SourceChange.NEW_SOURCE}
    again = mon.compare_receipts(first, discover())
    assert {c.state for c in again} == {mon.ProviderChange.NO_CHANGE}
    assert set(_events(again).values()) == {mon.SourceChange.UNCHANGED}


def test_added_revised_and_withdrawn_sources_are_told_apart():
    before = discover()
    changed = FakeNoaa(
        multibeam=[{"surveyId": "TEST-SURVEY-001", "platform": "revised"}, {"surveyId": "TEST-SURVEY-003"}])
    after = discover(transport=changed)
    events = _events(mon.compare_receipts(before, after))
    key = lambda s: ("NCEI_MULTIBEAM_CATALOG", f"NCEI:multibeam:{s}")  # noqa: E731
    assert events[key("TEST-SURVEY-001")] is mon.SourceChange.REVISED_METADATA
    assert events[key("TEST-SURVEY-002")] is mon.SourceChange.WITHDRAWN_SOURCE
    assert events[key("TEST-SURVEY-003")] is mon.SourceChange.NEW_SOURCE
    event = next(e for c in mon.compare_receipts(before, after) for e in c.events
                 if e.change is mon.SourceChange.NEW_SOURCE)
    assert set(event.to_dict()["dates"]) == {"discovered_utc", "published", "surveyed", "retrieved_utc"}
    assert event.to_dict()["dates"]["retrieved_utc"] != event.to_dict()["dates"]["discovered_utc"]


def test_a_failed_or_unauthorised_run_withdraws_nothing():
    before = discover()
    failing = discover(transport=FakeNoaa(multibeam=lambda url, q: frozen(url, {}, status=500)))
    comparison = next(c for c in mon.compare_receipts(before, failing)
                      if c.provider_id == "NCEI_MULTIBEAM_CATALOG")
    assert comparison.state is mon.ProviderChange.SOURCE_UNAVAILABLE and comparison.events == ()
    unauthorised = acq.discover_sources(OFFSHORE, BBOX, discovered_utc="t", transport=FakeNoaa())
    assert {c.state for c in mon.compare_receipts(before, unauthorised)} == {
        mon.ProviderChange.NOT_COMPARABLE}
    emptied = discover(transport=FakeNoaa(multibeam=[]))
    assert next(c for c in mon.compare_receipts(before, emptied)
                if c.provider_id == "NCEI_MULTIBEAM_CATALOG").state is mon.ProviderChange.SOURCE_EMPTY
    with pytest.raises(ValueError, match="different registries"):
        mon.compare_receipts(discover(INLAND), before)
    other_box = acq.discover_sources(OFFSHORE, BoundingBox(-67, 17, -66, 18), discovered_utc="t",
                                     transport=FakeNoaa(), authorization=GRANT)
    with pytest.raises(ValueError, match="different boxes"):
        mon.compare_receipts(other_box, before)


def test_review_flags_never_change_a_feature():
    comparisons = mon.compare_receipts(None, discover())
    points = {"OFAP-PR-000010": (-66.0, 17.9), "OFAP-PR-000011": (-60.0, 10.0)}
    flags = mon.review_flags(comparisons, points)
    assert {f.feature_id for f in flags} == {"OFAP-PR-000010"}
    assert all("no status was changed" in f.reason for f in flags)
    assert mon.review_flags(comparisons, {}) == []  # features without coordinates are never flagged
    report = mon.change_report(comparisons, flags, discovered_utc="2026-11-15T00:00:00Z")
    assert report["automatic_promotions"] == 0 and len(report["content_sha256"]) == 64
    assert mon.review_flags(mon.compare_receipts(discover(), discover()), points) == []


def test_provider_states_match_the_existing_remote_change_vocabulary():
    control_plane = pytest.importorskip("scripts.source_adapters.pr_hydrography.control_plane")
    shared = {"NO_CHANGE", "PAYLOAD_CHANGED_SCHEMA_STABLE", "SOURCE_UNAVAILABLE", "SOURCE_EMPTY"}
    assert shared <= set(control_plane.REMOTE_CHANGE_STATES)
    assert shared <= {member.value for member in mon.ProviderChange}


# ── Cross-repository context ─────────────────────────────────────────────────

CANON = {"entities": "federation_entity.schema.json",
         "relationships": "federation_relationship.schema.json",
         "sources": "federation_source.schema.json"}


def write_package(directory: Path, producer: str, streams: dict[str, list[dict]], **manifest):
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for stream, rows in streams.items():
        text = "".join(json.dumps(row) + "\n" for row in rows)
        (directory / f"{stream}.jsonl").write_text(text, encoding="utf-8")
        files.append({"filename": f"{stream}.jsonl", "stream": stream,
                      "schema_id": CANON.get(stream, f"federation_{stream}.schema.json"),
                      "sha256": hashlib.sha256(text.encode()).hexdigest(), "record_count": len(rows)})
    document = {"producer": producer, "export_contract_version": "1.0.0", "mode": "test",
                "package_id": "pkg_" + "0" * 32,
                "federation": {"hub_parent": "thehub-pr", "producer_repo": producer}, "files": files}
    document.update(manifest)
    (directory / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
    return directory


def entity(eid, kind, **extra):
    return {"entity_id": f"ent_{eid:032x}", "entity_type": kind, "name": f"synthetic {kind} {eid}",
            "source_id": "src_" + "1" * 32, "confidence": 0.8, "synthetic": False, **extra}


MONEY = [
    entity(1, "project", location={"municipality": "Guayama", "attribution_confidence": 0.7},
           attributes={"status": "completed"}),
    entity(2, "contract", location={"latitude": 17.98, "longitude": -66.11},
           attributes={"status": "active"}),
    entity(3, "property", location={"latitude": 18.0, "longitude": -66.2},
           attributes={"grid_v2_coordinate_evidence_state": "VERIFIED_SOURCE_COORDINATE"}),
    entity(4, "person"),
    entity(5, "project", synthetic=True),
]
WATER = [
    entity(11, "utility_asset", location={"lat": 17.97, "lon": -66.10},
           attributes={"asset_subtype": "groundwater_well", "evidence_tier": "T1"}),
    entity(12, "utility_asset", location={"lat": 18.4, "lon": -66.8},
           attributes={"asset_subtype": "wastewater_treatment", "evidence_tier": "T3"}),
    entity(13, "utility_asset", attributes={"asset_subtype": "tide_gauge"}),
    entity(14, "utility_asset", location={"lat": 18.0, "lon": -66.0},
           attributes={"asset_subtype": "substation"}),
    entity(15, "outage"),
]


def test_a_closing_package_loads_and_keeps_foreign_ids_verbatim(tmp_path):
    package = fc.load_package(write_package(tmp_path / "pkg", "moneysweep-pr", {"entities": MONEY}),
                              expected_producer="moneysweep-pr")
    assert package.synthetic_rows_dropped == 1 and len(package.rows("entities")) == 4
    assert package.stream_state("entities") is fc.StreamState.PRESENT
    assert package.stream_state("observations") is fc.StreamState.NOT_EXPORTED
    with pytest.raises(fc.PackageIntegrityError, match="not zero records"):
        package.rows("observations")
    records = fc.moneysweep_context(package)
    assert [r.foreign_id for r in records] == [f"ent_{i:032x}" for i in (1, 2, 3)]
    assert all(r.context_class is fc.ContextClass.DOCUMENTARY and r.diagnostic_only for r in records)


def _break(tmp_path, name, **manifest_edit):
    directory = write_package(tmp_path / name, "moneysweep-pr", {"entities": MONEY})
    path = directory / "manifest.json"
    document = json.loads(path.read_text())
    return directory, path, document


def test_packages_that_do_not_close_are_refused(tmp_path):
    load = lambda d, **kw: fc.load_package(d, expected_producer="moneysweep-pr", **kw)  # noqa: E731
    with pytest.raises(fc.PackageIntegrityError, match="no manifest"):
        load(tmp_path / "absent")  # unavailable producer package
    cases = {
        "wrong producer": lambda doc, d: doc.update(producer="someone-else"),
        "major version": lambda doc, d: doc.update(export_contract_version="2.0.0"),
        "unreadable version": lambda doc, d: doc.update(export_contract_version="latest"),
        "wrong hub": lambda doc, d: doc.update(federation={"hub_parent": "elsewhere"}),
        "no files": lambda doc, d: doc.update(files=[]),
        "foreign schema": lambda doc, d: doc["files"][0].update(schema_id="moneysweep_entity.schema.json"),
        "wrong count": lambda doc, d: doc["files"][0].update(record_count=99),
        "wrong hash": lambda doc, d: doc["files"][0].update(sha256="0" * 64),
        "traversal": lambda doc, d: doc["files"][0].update(filename="../entities.jsonl"),
        "missing file": lambda doc, d: (d / "entities.jsonl").unlink(),
        "edited bytes": lambda doc, d: (d / "entities.jsonl").write_text('{"x": 1}\n'),
        "duplicate stream": lambda doc, d: doc["files"].append(dict(doc["files"][0])),
    }
    for name, edit in cases.items():
        directory, path, document = _break(tmp_path, name.replace(" ", "_"))
        edit(document, directory)
        path.write_text(json.dumps(document))
        with pytest.raises(fc.PackageIntegrityError):
            load(directory)
            pytest.fail(f"accepted a package with: {name}")
    bad_json = write_package(tmp_path / "badjson", "moneysweep-pr", {"entities": MONEY})
    (bad_json / "manifest.json").write_text("{not json")
    with pytest.raises(fc.PackageIntegrityError):
        load(bad_json)


def test_fixture_locations_and_the_other_contract_are_refused(tmp_path):
    fixture = write_package(tmp_path / "exports" / "samples" / "pkg", "moneysweep-pr", {"entities": MONEY})
    with pytest.raises(fc.PackageIntegrityError, match="fixture"):
        fc.load_package(fixture, expected_producer="moneysweep-pr")
    assert fc.load_package(fixture, expected_producer="moneysweep-pr", allow_fixture=True).producer
    legacy_contract = REPO / "tests" / "fixtures" / "moneysweep_v1_2"
    with pytest.raises(fc.PackageIntegrityError):
        fc.load_package(legacy_contract, expected_producer="moneysweep-pr")
    with pytest.raises(fc.PackageIntegrityError):  # even when the fixture location is allowed
        fc.load_package(legacy_contract, expected_producer="moneysweep-pr", allow_fixture=True)


def test_documents_never_become_locations_or_physical_states(tmp_path):
    package = fc.load_package(write_package(tmp_path / "pkg", "moneysweep-pr", {"entities": MONEY}),
                              expected_producer="moneysweep-pr")
    project, contract, verified = fc.moneysweep_context(package)
    assert project.lon_lat is None and project.municipality == "Guayama"
    assert project.coordinate_basis is fc.CoordinateBasis.MUNICIPALITY_LABEL_ONLY
    assert project.producer_status_raw == "completed"  # kept verbatim, never read as "built"
    assert contract.lon_lat is None  # unverified passthrough coordinates are not used
    assert verified.lon_lat == (-66.2, 18.0)
    assert verified.coordinate_basis is fc.CoordinateBasis.VERIFIED_SOURCE_COORDINATE
    physical = fc.PHYSICAL_LIFECYCLE
    for kinds in (["contract"], ["project"], ["funding_award", "transaction", "contract"],
                  ["receives_contract", "funded_by"], ["completed"], []):
        assert fc.lifecycle_from_documents(kinds) not in physical
    assert fc.lifecycle_from_documents(["contract"]) is fc.EngineeredLifecycle.CONTRACTED
    assert fc.lifecycle_from_documents(["transaction"]) is fc.EngineeredLifecycle.FUNDED
    direct, referenced = sup.direct_source(), sup.referenced_source()
    assert fc.lifecycle_from_observation(fc.EngineeredLifecycle.BUILT, [referenced]) is (
        fc.EngineeredLifecycle.UNKNOWN)
    assert fc.lifecycle_from_observation(fc.EngineeredLifecycle.BUILT, [direct]) is (
        fc.EngineeredLifecycle.BUILT)


def test_a_contract_or_funding_record_does_not_prove_a_physical_opening(tmp_path):
    package = fc.load_package(write_package(tmp_path / "pkg", "moneysweep-pr", {"entities": MONEY}),
                              expected_producer="moneysweep-pr")
    registry, source, observation, feature = sup.registry_with_direct_feature(reviewer=None)
    held = registry.sources
    before = (rules.assertion_rung(feature, held), dict(rules.dimension_tiers(feature, held)))
    extra = tuple(fc.context_assertion(record, "an outfall contract names this area")
                  for record in fc.moneysweep_context(package))
    for added in extra:
        assert added.dimension is v.EvidenceDimension.FUNCTION
        assert added.tier is v.EvidenceTier.CANDIDATE and added.claim_class is v.ClaimClass.HYPOTHESIS
    enriched = replace(feature, assertions=feature.assertions + extra)
    after = rules.dimension_tiers(enriched, held)
    assert rules.assertion_rung(enriched, held) is before[0]
    for dimension in (v.EvidenceDimension.EXISTENCE, v.EvidenceDimension.PHYSICAL_OPENING,
                      v.EvidenceDimension.ACCESSIBILITY, v.EvidenceDimension.CONNECTIVITY):
        assert after[dimension] is before[1][dimension]
    assert after[v.EvidenceDimension.FUNCTION] is v.EvidenceTier.CANDIDATE
    # Context alone leaves a feature an anomaly.
    bare = m.Feature(ns.feature_id(OFFSHORE, 9), OFFSHORE, "ENGINEERED_OUTFALL", assertions=extra)
    assert rules.assertion_rung(bare, held) is v.AssertionRung.ANOMALY


def test_water_context_selection_and_nearby_relations(tmp_path):
    package = fc.load_package(write_package(tmp_path / "pkg", "aguayluz-pr", {"entities": WATER}),
                              expected_producer="aguayluz-pr")
    records = fc.aguayluz_context(package)
    assert [r.record_kind for r in records] == ["groundwater_well", "wastewater_treatment", "tide_gauge"]
    assert records[0].context_class is fc.ContextClass.MONITORING_SITE
    assert records[1].context_class is fc.ContextClass.INFRASTRUCTURE_ASSET
    assert records[1].evidence_tier_raw == "T3" and not records[2].placeable
    with pytest.raises(fc.PackageIntegrityError):
        fc.moneysweep_context(package)
    feature = ns.TypedRef(OFFSHORE, "OFAP-PR-000004")
    near = fc.nearby_context(feature, (-66.1, 17.96), records, threshold_m=5000)
    assert [record.record_kind for record, _ in near] == ["groundwater_well"]
    relation = near[0][1]
    assert relation.identity_semantics == "CANDIDATE_NOT_IDENTITY"
    assert relation.relation_type == "WITHIN_DISTANCE" and relation.distance_m < 5000
    assert fc.nearby_context(feature, (-66.1, 17.96), records, threshold_m=10) == []


# ── Registry builder ─────────────────────────────────────────────────────────


def _floats(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _floats(value)
    elif isinstance(node, list):
        for value in node:
            yield from _floats(value)
    elif isinstance(node, float):
        yield node


def test_build_is_deterministic_and_matches_the_committed_documents(tmp_path):
    first, second = seeding.build_all(REPO), seeding.build_all(REPO)
    assert first.inland.to_document() == second.inland.to_document()
    assert first.offshore.to_document() == second.offshore.to_document()
    fresh = seeding.write_documents(first, tmp_path)
    for name, digest in fresh.items():
        committed = REPO / seeding.REGISTRY_DIR / name
        assert hashlib.sha256(committed.read_bytes()).hexdigest() == digest, f"{name} is stale"
    check = subprocess.run([sys.executable, "scripts/build_access_point_registries.py", "--check"],
                           cwd=REPO, capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr


def test_provisional_seeds_carry_no_coordinate_depth_or_claim():
    build = seeding.build_all(REPO)
    seeds = [build.offshore.features[i] for i in build.seeded]
    assert len(seeds) == 5
    assert [f.provisional_labels for f in seeds] == [(f"OSAP-SEED-00{i}",) for i in range(1, 6)]
    for feature in seeds:
        assert feature.status is v.RegistryStatus.PROVISIONAL_DISCOVERY
        assert build.offshore.rung(feature.feature_id) is v.AssertionRung.ANOMALY
        assert not ns.is_feature_id(feature.provisional_labels[0], OFFSHORE)
        assert list(_floats(feature.to_dict())) == []
        for oid in feature.observation_ids:
            observation = build.offshore.observations[oid]
            assert observation.geometry is None and observation.value_m is None
            assert observation.geometry_basis is v.GeometryBasis.LOCALITY_LABEL_ONLY
            assert list(_floats(observation.to_dict())) == []
            assert build.offshore.sources[observation.source_id].provenance_state is (
                v.ProvenanceState.UNREGISTERED)
        assert {a.dimension for a in feature.assertions} == {v.EvidenceDimension.EXISTENCE}
    assert build.offshore.counts()["features_by_status"]["VERIFIED"] == 0
    assert build.inland.counts()["features_by_status"]["VERIFIED"] == 0


@pytest.mark.parametrize("extra", [{"lat": 18.5}, {"lon": -67.2}, {"depth_m": 40}, {"geometry": {}},
                                   {"connected_to": "x"}])
def test_seed_file_cannot_smuggle_in_geography(extra):
    config = yaml.safe_load((REPO / seeding.SEEDS_PATH).read_text())
    config["seeds"][0].update(extra)
    registry = AccessPointRegistry(OFFSHORE, producer_identity="t")
    with pytest.raises(seeding.SeedingError):
        seeding.seed_offshore(registry, config)
    assert registry.counts()["features"] == 0


def test_seed_file_rules():
    config = yaml.safe_load((REPO / seeding.SEEDS_PATH).read_text())
    wrong_label = json.loads(json.dumps(config))
    wrong_label["seeds"][0]["label"] = "INAP-PR-000001"
    with pytest.raises(seeding.SeedingError):
        seeding.seed_offshore(AccessPointRegistry(OFFSHORE, producer_identity="t"), wrong_label)
    with pytest.raises(seeding.SeedingError):
        seeding.seed_offshore(AccessPointRegistry(INLAND, producer_identity="t"), config)
    claims_registered = json.loads(json.dumps(config))
    claims_registered["source"]["provenance_state"] = "REFERENCED_ONLY"
    with pytest.raises(seeding.SeedingError):
        seeding.seed_offshore(AccessPointRegistry(OFFSHORE, producer_identity="t"), claims_registered)


def test_legacy_crosswalk_is_exact_closed_and_read_only():
    legacy = REPO / "configs" / "ilap_registry.yaml"
    before = hashlib.sha256(legacy.read_bytes()).hexdigest()
    build = seeding.build_all(REPO)
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == before
    result = build.crosswalk
    assert result.closes() and result.legacy_nodes_read == 103
    assert result.matched == len(result.feature_ids) == 5
    nodes = {str(n["node_id"]): n for n in yaml.safe_load(legacy.read_text())["ilap_nodes"]}
    rules_cfg = yaml.safe_load((REPO / seeding.CROSSWALK_PATH).read_text())["rules"]
    allowed = {(r["legacy_type"], r["legacy_subtype"]): (r["registry"], r["feature_class"])
               for r in rules_cfg}
    for registry in (build.inland, build.offshore):
        for feature in registry.features.values():
            if feature.provisional_labels:
                continue
            assert feature.status is v.RegistryStatus.CANDIDATE
            (observation,) = (registry.observations[o] for o in feature.observation_ids)
            node = nodes[observation.native_record_id]
            key = (node["ilap_type"], node["ilap_subtype"])
            assert allowed[key] == (registry.namespace.value, feature.feature_class)
            assert observation.raw_attributes["node_id"] == node["node_id"]
            assert observation.raw_attributes["name"] == node["name"] == feature.raw_names[0]
            assert observation.geometry["coordinates"] == [node["lon"], node["lat"]]
            assert observation.raw_attributes["horizontal_crs_basis"] == (
                "ASSUMED_WGS84_UNDECLARED_IN_SOURCE")
            assert observation.horizontal_uncertainty_m is None
            assert registry.rung(feature.feature_id) is v.AssertionRung.ANOMALY
    # Nothing is matched by name: a legacy node whose name mentions a cave but
    # whose type pair is not listed is not crosswalked.
    matched_ids = {registry.observations[o].native_record_id
                   for registry in (build.inland, build.offshore)
                   for f in registry.features.values() if not f.provisional_labels
                   for o in f.observation_ids}
    for node_id, node in nodes.items():
        if (node.get("ilap_type"), node.get("ilap_subtype")) not in allowed:
            assert node_id not in matched_ids


def test_guayama_reference_sources_match_the_receipt_and_are_not_measurements():
    build = seeding.build_all(REPO)
    assert build.guayama == {"multibeam": 13, "sounding": 29, "bag": 1, "topobathy_lidar": 4,
                             "datum_placeholders": 4}
    referenced = [s for s in build.offshore.sources.values()
                  if s.provenance_state is v.ProvenanceState.REFERENCED_ONLY]
    assert len(referenced) == 47
    assert not any(s.is_direct_measurement for s in build.offshore.sources.values())
    assert len(build.ledger.relationships) == 0


# ── Service ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def service():
    return svc.AccessPointService(REPO)


def test_service_summary_and_blocks(service):
    summary = service.registries()
    assert [(r["registry"], r["code"], r["available"]) for r in summary["registries"]] == [
        ("inland", "INAP", True), ("offshore", "OFAP", True)]
    for entry in summary["registries"]:
        assert len(entry["provenance"]["sha256"]) == 64 and entry["provenance"]["counts_close"]
    for response in (service.feature_collection("inland"), service.feature("inland", "INAP-PR-000001"),
                     service.evidence("offshore", "OFAP-PR-000004"), service.source_coverage("offshore"),
                     service.relationships()):
        assert response["scope"]["identity_effect"] == "NONE"
        assert response["provenance"]["path"].startswith("registry/access_points/")


@pytest.mark.parametrize("limit", [1, 2, 4, 500])
def test_pagination_visits_every_feature_exactly_once(service, limit):
    seen, cursor = [], None
    while True:
        page = service.feature_collection("offshore", limit=limit, cursor=cursor)
        seen += [f["id"] for f in page["features"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(seen) and len(seen) == len(set(seen)) == 6 == page["number_matched"]


def test_unlocated_records_are_counted_never_placed(service):
    everything = service.feature_collection("offshore")
    assert everything["unlocated_count"] == 5
    unlocated = [f for f in everything["features"] if f["geometry"] is None]
    assert len(unlocated) == 5
    for feature in unlocated:
        assert feature["properties"]["has_geometry"] is False
        assert feature["properties"]["geometry_basis"] == "LOCALITY_LABEL_ONLY"
        assert feature["properties"]["horizontal_uncertainty_state"] == "UNKNOWN"
        assert list(_floats(feature)) == []
    boxed = service.feature_collection("offshore", bbox=svc.parse_bbox("-68,17,-65,19"))
    assert [f["id"] for f in boxed["features"]] == ["OFAP-PR-000006"]
    assert boxed["unlocated_count"] == 5
    assert service.feature_collection("offshore", status=["CANDIDATE"])["number_matched"] == 1
    assert service.feature_collection("inland", feature_class=["SINKHOLE"])["number_matched"] == 1
    for bad in ({"status": ["NOPE"]}, {"limit": 0}, {"limit": 501}, {"cursor": "OFAP-PR-000999"}):
        with pytest.raises(svc.InvalidQuery):
            service.feature_collection("offshore", **bad)


@pytest.mark.parametrize("text", ["1,2,3", "a,b,c,d", "-66,18,-67,19", "-66,19,-65,18", "-200,17,-65,19",
                                  "170,10,-170,20", "-66,-95,-65,19", ""])
def test_bbox_parsing_fails_closed(text):
    with pytest.raises(svc.InvalidQuery):
        svc.parse_bbox(text)


def test_identifiers_of_other_registries_and_meanings_are_refused(service):
    with pytest.raises(ns.NamespaceCollisionError):
        service.feature("inland", "OFAP-PR-000001")
    with pytest.raises(ns.NamespaceCollisionError):
        service.evidence("offshore", "INAP-PR-000001")
    with pytest.raises(ns.NamespaceCollisionError):
        service.feature("inland", "ILAP_AREA_NORTH_001")
    with pytest.raises(KeyError):
        service.feature("inland", "INAP-PR-000999")
    for slug in ("ilap", "osap", "access_point.inland", ""):
        with pytest.raises(svc.UnknownRegistry):
            service.feature_collection(slug)


def test_evidence_shows_what_each_assertion_is_worth(service):
    evidence = service.evidence("offshore", "OFAP-PR-000004")
    assert evidence["assertion_rung"] == "ANOMALY" and evidence["status"] == "PROVISIONAL_DISCOVERY"
    assert any("physical opening" in b for b in evidence["promotion_blockers"])
    assert any("coordinates" in b for b in evidence["promotion_blockers"])
    (assertion,) = evidence["assertions"]
    assert assertion["effective_tier"] == "CANDIDATE" and assertion["claim_class"] == "HYPOTHESIS"
    assert evidence["sources"][0]["provenance_state"] == "UNREGISTERED"
    coverage = service.source_coverage("offshore")
    assert coverage["direct_measurement_sources"] == 0
    assert coverage["by_provider"]["NCEI_SOUNDING_CATALOG"] == {"REFERENCED_ONLY": 29}


def test_one_registry_failing_does_not_hide_the_other(tmp_path):
    scratch = tmp_path / "registry" / "access_points"
    shutil.copytree(REPO / seeding.REGISTRY_DIR, scratch)
    document = json.loads((scratch / "inland.json").read_text())
    document["features"][0]["status"] = "VERIFIED"  # edited without re-hashing
    (scratch / "inland.json").write_text(json.dumps(document))
    broken = svc.AccessPointService(tmp_path)
    with pytest.raises(svc.RegistryUnavailable, match="verification"):
        broken.feature_collection("inland")
    assert broken.feature_collection("offshore")["number_matched"] == 6
    summary = {r["registry"]: r["available"] for r in broken.registries()["registries"]}
    assert summary == {"inland": False, "offshore": True}
    (scratch / "offshore.json").unlink()
    missing = svc.AccessPointService(tmp_path)
    with pytest.raises(svc.RegistryUnavailable, match="not been built"):
        missing.feature_collection("offshore")


def test_control_cross_section_is_labelled_synthetic():
    section = svc.control_cross_section()
    assert section["truth_kind"] == "SYNTHETIC_CONTROL" and "not a survey" in section["statement"]
    assert not section["is_continuous"] and section["gaps"]
    assert section["join"]["state"] == "SEPARATE_SURFACES_ONLY" and section["common_profiles"] == []


def test_registry_work_needs_no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    build = seeding.build_all(REPO)
    offline = svc.AccessPointService(REPO)
    assert offline.feature_collection("inland")["number_matched"] == build.inland.counts()["features"]
    assert svc.control_cross_section()["truth_kind"] == "SYNTHETIC_CONTROL"
    assert acq.discover_sources(OFFSHORE, BBOX, discovered_utc="t").state is acq.RunState.NOT_AUTHORIZED
