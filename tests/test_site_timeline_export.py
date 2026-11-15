"""Site imagery timeline: export lane, offline CLI and manifest compatibility.

The lane mirrors the PPP geometry lane (hub ADR 0008): a spiderweb-owned entity per
registered site plus `observations` rows that point at it and carry the registering
producer's entity id in attributes.producer_entity_id. Equivalence with that
producer's entity is the hub's call (hub ADR 0009), so the lane must never reuse the
producer's id as its own. Synthetic data only.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

import scripts.build_site_imagery_timeline as cli
import scripts.federation_export as fx
from spiderweb.site_timeline.models import (
    COARSE_CONFIDENCE_CAP,
    PRECISE_CONFIDENCE_CAP,
)
from tests.site_timeline_support import (
    ARROYO_ENT,
    NOW,
    PIN_ENT,
    coarse_site,
    document_for,
    make_live,
    precise_site,
    scene,
    set_after_date,
    standard_document,
    timeline_for,
)

REPO = Path(__file__).resolve().parents[1]
VENDORED = REPO / "schemas" / "federation_epistemic_state.v1.schema.json"
SCRIPT = REPO / "scripts" / "federation_export.py"


def _evidence_validator():
    schema = json.loads(VENDORED.read_text())
    wrapper = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/producer_declaration",
    }
    return jsonschema.Draft202012Validator(wrapper)


def _lane(doc=None):
    return fx.build_site_imagery_streams(doc or standard_document(), NOW)


# --- row shapes -----------------------------------------------------------------


def test_lane_row_counts_and_types():
    lane = _lane()
    assert len(lane["sources"]) == 1 and len(lane["entities"]) == 2
    kinds = [o["observation_type"] for o in lane["observations"]]
    # 4 admitted scenes + 2 scored comparisons
    assert kinds.count("satellite_scene") == 4
    assert kinds.count("satellite_visible_change") == 2
    assert {e["entity_type"] for e in lane["entities"]} == {"site_imagery_series"}
    assert lane["sources"][0]["source_type"] == "satellite_imagery_timeline"


def test_ids_follow_the_hub_patterns():
    lane = _lane()
    assert re.fullmatch(r"src_[a-f0-9]{32}", lane["sources"][0]["source_id"])
    for ent in lane["entities"]:
        assert re.fullmatch(r"ent_[a-f0-9]{32}", ent["entity_id"])
    for obs in lane["observations"]:
        assert re.fullmatch(r"obs_[a-f0-9]{32}", obs["observation_id"])
    ids = [o["observation_id"] for o in lane["observations"]]
    assert len(ids) == len(set(ids))


def test_series_entity_is_spiderwebs_own_and_never_reuses_the_producer_id():
    lane = _lane()
    producer_ids = {ARROYO_ENT, PIN_ENT}
    assert {e["entity_id"] for e in lane["entities"]}.isdisjoint(producer_ids)
    by_id = {e["entity_id"] for e in lane["entities"]}
    for obs in lane["observations"]:
        assert obs["entity_id"] in by_id
        assert obs["attributes"]["producer_entity_id"] in producer_ids
        assert obs["entity_id"] != obs["attributes"]["producer_entity_id"]


def test_series_entity_id_is_stable_per_producer_entity():
    first = {e["entity_id"] for e in _lane()["entities"]}
    assert first == {e["entity_id"] for e in _lane()["entities"]}
    assert fx._fid("ent", "site_imagery_series", ARROYO_ENT) in first


def test_every_row_is_provisional_and_synthetic_fixtures_say_so():
    lane = _lane()
    for row in lane["sources"] + lane["entities"] + lane["observations"]:
        assert row["synthetic"] is True
    for obs in lane["observations"]:
        assert obs["attributes"]["provisional"] is True


def test_confidence_is_bounded_by_geometry_precision():
    lane = _lane()
    for obs in lane["observations"]:
        coarse = obs["attributes"]["geometry_coarse"]
        assert (
            0.0
            <= obs["confidence"]
            <= (COARSE_CONFIDENCE_CAP if coarse else PRECISE_CONFIDENCE_CAP)
        )
    for ent in lane["entities"]:
        assert ent["confidence"] in (COARSE_CONFIDENCE_CAP, PRECISE_CONFIDENCE_CAP)


def test_exporter_ceilings_match_the_package_constants():
    assert fx.SITE_IMAGERY_SOURCE_CONFIDENCE == PRECISE_CONFIDENCE_CAP
    assert fx.SITE_IMAGERY_COARSE_CONFIDENCE == COARSE_CONFIDENCE_CAP


def test_evidence_state_validates_against_the_vendored_contract():
    validator = _evidence_validator()
    lane = _lane()
    for row in lane["sources"] + lane["entities"] + lane["observations"]:
        errors = list(validator.iter_errors(row["evidence_state"]))
        assert not errors, errors
    states = {o["observation_type"]: o["evidence_state"] for o in lane["observations"]}
    assert states["satellite_scene"]["epistemic_class"] == "CURATED"
    assert states["satellite_visible_change"]["epistemic_class"] == "COMPUTED"
    for state in states.values():
        assert state["geometry_precision"] == "REPRESENTATIVE_POINT"
        # Absence is never asserted: a change score is not an observation state.
        assert "observation_state" not in state


def test_change_rows_carry_the_provisional_signal_and_the_guardrail():
    lane = _lane()
    change = next(
        o
        for o in lane["observations"]
        if o["observation_type"] == "satellite_visible_change"
    )
    attrs = change["attributes"]
    assert attrs["guardrail"] == "VISIBLE_EPOCH_CHANGE_ONLY"
    assert attrs["signal_id"].startswith("sig_")
    assert attrs["before_artifact_id"] != attrs["after_artifact_id"]
    assert attrs["review_status"] in {"UNREVIEWED", "NEEDS_REVIEW"}
    assert change["observed_at"].endswith("Z")


def test_lineage_is_content_addressed_to_the_document():
    doc = standard_document()
    sha = hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    source = _lane(doc)["sources"][0]
    assert f"site_imagery_timeline:sha256:{sha}" in source["lineage"]["source_inputs"]
    other = copy.deepcopy(doc)
    other["window"]["end"] = "2030-01-01"
    assert _lane(other)["sources"][0]["lineage"]["source_inputs"] != (
        source["lineage"]["source_inputs"]
    )


def test_lane_is_deterministic():
    assert _lane() == _lane()


def test_unknown_and_same_epoch_pairs_are_not_exported_as_changes():
    site = precise_site()
    timeline = timeline_for(
        site,
        [
            scene(site, "a", "2021-03-05T10:00:00Z", 1.0),
            scene(site, "b", "2021-03-05T10:05:00Z", 1.0),
        ],
        {},
    )
    assert timeline["comparisons"][0]["disposition"] == "RENDER_CONSISTENCY_ONLY"
    kinds = [
        o["observation_type"] for o in _lane(document_for(timeline))["observations"]
    ]
    assert kinds == ["satellite_scene", "satellite_scene"]


def test_empty_document_yields_an_empty_lane():
    empty = document_for()
    assert _lane(empty) == {"sources": [], "entities": [], "observations": []}


def test_merge_is_idempotent_and_keeps_existing_rows():
    streams = fx.build_streams(
        [], {"airspace_events": [], "observations": [], "tracks": []}, NOW
    )
    streams["sources"].append({"source_id": "src_" + "e" * 32})
    lane = _lane()
    fx.merge_site_imagery(streams, lane)
    once = {k: len(v) for k, v in streams.items()}
    fx.merge_site_imagery(streams, lane)
    assert {k: len(v) for k, v in streams.items()} == once
    assert once["observations"] == len(lane["observations"])
    assert any(s["source_id"] == "src_" + "e" * 32 for s in streams["sources"])


def test_default_export_has_no_site_imagery_rows():
    streams = fx.build_streams(
        [], {"airspace_events": [], "observations": [], "tracks": []}, NOW
    )
    assert not [
        e for e in streams["entities"] if e["entity_type"] == "site_imagery_series"
    ]
    assert streams.get("observations", []) == []


# --- the exporter command line --------------------------------------------------


def _run_export(tmp_path, *extra):
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    out = tmp_path / "fed"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--package",
            str(empty),
            "--out",
            str(out),
            "--no-ppp-geometry",
            *extra,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return proc, out


def _write_doc(tmp_path, doc=None):
    path = tmp_path / "timeline.json"
    path.write_text(json.dumps(doc or standard_document()))
    return path


def test_flag_adds_the_lane_and_a_manifest_that_counts_it(tmp_path):
    proc, out = _run_export(
        tmp_path, "--site-imagery-timeline", str(_write_doc(tmp_path))
    )
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    streams = {f["stream"]: f["record_count"] for f in manifest["files"]}
    # Every package also carries one source_monitors row per registered source.
    monitors = streams.pop("source_monitors")
    assert monitors == len(fx.build_source_monitors("2026-01-01T00:00:00Z"))
    assert streams == {"sources": 1, "entities": 2, "observations": 6}
    for f in manifest["files"]:
        digest = hashlib.sha256((out / f["filename"]).read_bytes()).hexdigest()
        assert digest == f["sha256"]


def test_without_the_flag_nothing_is_exported(tmp_path):
    proc, out = _run_export(tmp_path)
    assert proc.returncode == 0 and "nothing to export" in proc.stdout
    assert not out.exists()


def test_invalid_document_fails_the_export_and_writes_nothing(tmp_path):
    bad = standard_document()
    bad["provisional"] = False
    proc, out = _run_export(
        tmp_path, "--site-imagery-timeline", str(_write_doc(tmp_path, bad))
    )
    assert proc.returncode == 2 and "must be provisional" in proc.stderr
    assert not out.exists()


def test_unreadable_document_fails_the_export(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    proc, out = _run_export(tmp_path, "--site-imagery-timeline", str(path))
    assert proc.returncode == 2 and not out.exists()
    missing, out2 = _run_export(
        tmp_path, "--site-imagery-timeline", str(tmp_path / "absent.json")
    )
    assert missing.returncode == 2 and not out2.exists()


def test_production_mode_refuses_synthetic_lane_rows(tmp_path):
    proc, out = _run_export(
        tmp_path,
        "--mode",
        "production",
        "--site-imagery-timeline",
        str(_write_doc(tmp_path)),
    )
    assert proc.returncode == 1 and "synthetic" in proc.stdout
    assert not out.exists()


def test_scenes_with_identical_pixels_keep_distinct_observations():
    """Codex finding on #446 (P2): artifact ids may repeat across scenes."""
    from spiderweb.site_timeline.adapters import SyntheticAdapter
    from spiderweb.site_timeline.metrics import FixtureMetric
    from spiderweb.site_timeline.timeline import build_site_timeline, validate_document

    site = precise_site()
    payload = b"identical-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    class Constant(SyntheticAdapter):
        def fetch(self, site, scene):
            return payload

    scenes = [
        dataclasses.replace(scene(site, name, day, 1.0), content_sha256=digest)
        for name, day in (("A", "2017-03-02"), ("B", "2021-03-05"))
    ]
    timeline = build_site_timeline(
        site,
        Constant({site.external_site_id: scenes}),
        FixtureMetric({("A", "B"): {"SURFACE_COVER_CHANGE": 0.5}}),
        start="2015-06-23",
        end="2026-11-07",
        now=NOW,
    )
    doc = document_for(timeline)
    assert validate_document(doc) == []
    lane = fx.build_site_imagery_streams(doc, NOW)
    scene_rows = [
        o for o in lane["observations"] if o["observation_type"] == "satellite_scene"
    ]
    assert len(scene_rows) == 2
    assert len({o["observation_id"] for o in scene_rows}) == 2
    assert len({o["attributes"]["artifact_id"] for o in scene_rows}) == 1
    streams = {"sources": [], "entities": [], "observations": []}
    fx.merge_site_imagery(streams, lane)
    kept = [
        o for o in streams["observations"] if o["observation_type"] == "satellite_scene"
    ]
    assert {o["attributes"]["scene_id"] for o in kept} == {"A", "B"}


def test_partially_cleared_synthetic_flags_never_reach_a_production_export(tmp_path):
    """Codex finding on #446 (P1): test data must not pass the production gate."""
    doc = standard_document()
    doc["synthetic"] = False
    for entry in doc["sites"]:
        for art in entry["artifacts"]:
            art["synthetic"] = False
    proc, out = _run_export(
        tmp_path,
        "--mode",
        "production",
        "--site-imagery-timeline",
        str(_write_doc(tmp_path, doc)),
    )
    assert proc.returncode == 2 and "mixes synthetic and live" in proc.stderr
    assert not out.exists()


def test_a_consistently_live_document_passes_the_production_export(tmp_path):
    doc = make_live(standard_document())
    proc, out = _run_export(
        tmp_path,
        "--mode",
        "production",
        "--site-imagery-timeline",
        str(_write_doc(tmp_path, doc)),
    )
    assert proc.returncode == 0, proc.stderr
    rows = [
        json.loads(line)
        for line in (out / "observations.jsonl").read_text().splitlines()
    ]
    assert rows and {r["synthetic"] for r in rows} == {False}


def test_a_stale_epoch_label_fails_the_export(tmp_path):
    """Codex finding on #446 (P2): a same-date pair cannot keep a change claim."""
    doc = standard_document()
    set_after_date(doc, doc["sites"][0]["artifacts"][0]["acquired_at"])
    proc, out = _run_export(
        tmp_path, "--site-imagery-timeline", str(_write_doc(tmp_path, doc))
    )
    assert proc.returncode == 2 and "does not match its scenes" in proc.stderr
    assert not out.exists()


# --- the offline timeline command line ------------------------------------------

SITES = [
    {
        "external_site_id": "LMOP-ARROYO-TEST",
        "producer_entity_id": ARROYO_ENT,
        "name": "Arroyo Landfill (fixture)",
        "lat": 18.004595,
        "lon": -66.04773,
        "geometry_precision_decimals": 6,
    },
]
FIXTURE = {
    "scenes": {
        "LMOP-ARROYO-TEST": [
            {
                "scene_id": "S2-2017",
                "acquired_at": "2017-03-02T14:50:00Z",
                "cloud_cover_pct": 4.0,
            },
            {
                "scene_id": "S2-2021",
                "acquired_at": "2021-03-05T14:50:00Z",
                "cloud_cover_pct": 6.0,
            },
            {
                "scene_id": "SHOT",
                "acquired_at": None,
                "cloud_cover_pct": None,
                "capture_kind": "UNDATED_BASEMAP_CAPTURE",
                "provider": "unknown",
            },
        ]
    },
    "change_signals": [
        {
            "before": "S2-2017",
            "after": "S2-2021",
            "signals": {"SURFACE_COVER_CHANGE": 0.85},
        }
    ],
}


def _inputs(tmp_path, sites=None, fixture=None):
    sites_path = tmp_path / "sites.json"
    fixture_path = tmp_path / "scenes.json"
    sites_path.write_text(json.dumps(sites if sites is not None else SITES))
    fixture_path.write_text(json.dumps(fixture if fixture is not None else FIXTURE))
    return sites_path, fixture_path


def _args(tmp_path, *extra, fixture=True):
    sites_path, fixture_path = tmp_path / "sites.json", tmp_path / "scenes.json"
    args = ["--site-list", str(sites_path), "--now", NOW, *extra]
    if fixture:
        args += ["--scenes-fixture", str(fixture_path)]
    return args


def _inputs_only(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir())


def test_cli_prints_a_summary_and_writes_nothing_by_default(tmp_path, capsys):
    _inputs(tmp_path)
    assert cli.main(_args(tmp_path)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["wrote"] is None and summary["synthetic"] is True
    assert summary["sites"][0]["ledger"]["by_reason"] == {"UNDATED_BASEMAP_CAPTURE": 1}
    assert _inputs_only(tmp_path) == ["scenes.json", "sites.json"]


def test_cli_writes_only_with_out_and_never_overwrites_silently(tmp_path, capsys):
    _inputs(tmp_path)
    out = tmp_path / "out" / "timeline.json"
    assert cli.main(_args(tmp_path, "--out", str(out))) == 0
    first = out.read_text()
    assert json.loads(first)["provisional"] is True
    capsys.readouterr()
    out.write_text("keep me")
    assert cli.main(_args(tmp_path, "--out", str(out))) == 2
    assert "--overwrite" in capsys.readouterr().err
    assert out.read_text() == "keep me"
    assert cli.main(_args(tmp_path, "--out", str(out), "--overwrite")) == 0
    assert out.read_text() == first  # deterministic


def test_cli_output_is_exactly_what_the_exporter_consumes(tmp_path):
    _inputs(tmp_path)
    out = tmp_path / "timeline.json"
    assert cli.main(_args(tmp_path, "--out", str(out))) == 0
    proc, fed = _run_export(tmp_path, "--site-imagery-timeline", str(out))
    assert proc.returncode == 0, proc.stderr
    rows = [
        json.loads(line)
        for line in (fed / "observations.jsonl").read_text().splitlines()
    ]
    assert {r["observation_type"] for r in rows} == {
        "satellite_scene",
        "satellite_visible_change",
    }


def test_live_acquisition_fails_closed_and_writes_nothing(
    tmp_path, capsys, monkeypatch
):
    _inputs(tmp_path)
    monkeypatch.setenv("SENTINELHUB_CLIENT_SECRET", "do-not-leak-me")
    out = tmp_path / "timeline.json"
    assert cli.main(_args(tmp_path, "--out", str(out), fixture=False)) == 3
    err = capsys.readouterr().err
    assert "acquisition unavailable" in err and "do-not-leak-me" not in err
    assert not out.exists()


def test_cli_rejects_bad_inputs_without_writing(tmp_path, capsys):
    out = tmp_path / "timeline.json"
    cases = {
        "unknown site key": ([{**SITES[0], "owner": "x"}], FIXTURE),
        "missing site key": (
            [{k: v for k, v in SITES[0].items() if k != "lat"}],
            FIXTURE,
        ),
        "duplicate site": ([SITES[0], SITES[0]], FIXTURE),
        "bad entity id": ([{**SITES[0], "producer_entity_id": "nope"}], FIXTURE),
        "empty site list": ([], FIXTURE),
        "scenes for an unknown site": (SITES, {"scenes": {"GHOST": []}}),
        "unknown scene key": (
            SITES,
            {"scenes": {"LMOP-ARROYO-TEST": [{"scene_id": "x", "owner": "y"}]}},
        ),
        "malformed change row": (
            SITES,
            {**FIXTURE, "change_signals": [{"before": "a"}]},
        ),
    }
    for name, (sites, fixture) in cases.items():
        _inputs(tmp_path, sites, fixture)
        assert cli.main(_args(tmp_path, "--out", str(out))) == 2, name
        capsys.readouterr()
        assert not out.exists(), name


def test_cli_reports_a_fixture_gap_instead_of_calling_it_stable(tmp_path, capsys):
    fixture = {**FIXTURE, "change_signals": []}
    _inputs(tmp_path, fixture=fixture)
    out = tmp_path / "timeline.json"
    assert cli.main(_args(tmp_path, "--out", str(out))) == 4
    assert "no fixture signals" in capsys.readouterr().err
    assert not out.exists()


def test_cli_missing_input_file_is_an_input_error(tmp_path, capsys):
    assert cli.main(["--site-list", str(tmp_path / "absent.json")]) == 2
    assert "input rejected" in capsys.readouterr().err


# --- compatibility with the existing satellite manifest pipeline ----------------


def test_synthetic_scenes_make_manifests_the_existing_ingest_accepts(tmp_path):
    pytest.importorskip("jsonschema")
    from imagery.manifest import build_manifest
    from imagery.models import ImageryResult
    from readiness.satellite_ingest import SatelliteIngest
    from spiderweb.site_timeline.adapters import synthetic_payload

    site = coarse_site()
    for sc in (
        scene(site, "T-2018", "2018-01-10T14:50:00Z", 2.0),
        scene(site, "T-2022", "2022-01-12T14:50:00Z", 2.0),
    ):
        result = ImageryResult(
            provider=sc.provider,
            image_bytes=synthetic_payload(sc.scene_id),
            media_type=sc.media_type,
            bbox=list(sc.bbox),
            acquired_at=sc.acquired_at,
            collection=sc.collection,
            platform=sc.platform,
            instrument=sc.instrument,
            cloud_cover_pct=sc.cloud_cover_pct,
            resolution_m=sc.resolution_m,
            scene_id=sc.scene_id,
        )
        manifest = build_manifest(result, synthetic=True)
        assert manifest["synthetic"] is True
        assert manifest["acquisition"]["acquired_at"] == sc.acquired_at
        path = tmp_path / f"{sc.scene_id}.json"
        path.write_text(json.dumps(manifest))
        outcome = SatelliteIngest(dry_run=True).ingest(path)
        assert outcome["status"] == "accepted", outcome["errors"]
        # Dry run: ingest wrote no output file.
        assert outcome["output_path"] is None


def test_only_dated_scenes_can_reach_the_manifest_builder():
    """imagery.manifest stamps *now* on a missing date and reports a missing cloud
    cover as 0.0, so an undated or cloud-unknown capture reaching it would acquire a
    false date and a false clear sky. The series is what keeps those out."""
    from spiderweb.site_timeline.series import build_series

    site = precise_site()
    shot = scene(
        site,
        "shot",
        None,
        None,
        capture_kind="UNDATED_BASEMAP_CAPTURE",
        provider="unknown",
    )
    unknown_cloud = scene(site, "nc", "2020-01-01T00:00:00Z", None)
    assert build_series(site, [shot, unknown_cloud]).admitted == ()
