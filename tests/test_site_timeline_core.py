"""Site imagery timeline: epochs, series admission, adapters and import hygiene.

All data is synthetic. Nothing here touches a network, an image library or a
provider. The guardrails under test come from the SATIM mixed-epoch spec and
docs/contracts/SITE_IMAGERY_TIMELINE.md.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from spiderweb.site_timeline import adapters as ad
from spiderweb.site_timeline.epoch import (
    NEAR_EPOCH_DAYS,
    classify_epoch,
    parse_acquired_at,
)
from spiderweb.site_timeline.models import (
    UNDATED_BASEMAP_CAPTURE,
    EpochClass,
    Site,
)
from spiderweb.site_timeline.series import (
    DEFAULT_CLOUD_CUTOFF_PCT,
    build_series,
    comparison_pairs,
)
from tests.site_timeline_support import (
    ARROYO_ENT,
    coarse_site,
    precise_site,
    scene,
)

REPO = Path(__file__).resolve().parents[1]


# --- site -----------------------------------------------------------------------


def test_site_requires_an_opaque_entity_id_shape():
    for bad in ("", "ent_short", "ENT_" + "a" * 32, "landfill:Arroyo"):
        with pytest.raises(ValueError):
            Site("X", bad, "n", 18.0, -66.0)


def test_site_rejects_out_of_range_coordinates():
    with pytest.raises(ValueError):
        Site("X", ARROYO_ENT, "n", 91.0, -66.0)


def test_coarse_geometry_gets_a_wide_chip_and_a_low_ceiling():
    precise, coarse = precise_site(), coarse_site()
    assert coarse.is_coarse and not precise.is_coarse
    assert coarse.confidence_cap < precise.confidence_cap
    width = lambda s: s.chip_bbox()[2] - s.chip_bbox()[0]  # noqa: E731
    assert width(coarse) > width(precise)


def test_unknown_precision_is_treated_as_coarse():
    assert Site("X", ARROYO_ENT, "n", 18.0, -66.0).is_coarse


# --- epoch classes --------------------------------------------------------------


def _pair(d1, d2, p1="sentinelhub", p2="sentinelhub"):
    site = precise_site()
    return (
        scene(site, "a", d1, 1.0, provider=p1),
        scene(site, "b", d2, 1.0, provider=p2),
    )


@pytest.mark.parametrize(
    "d1, d2, p1, p2, expected",
    [
        ("2020-03-01T10:00:00Z", "2020-03-01T11:30:00Z", "x", "x", "same_epoch"),
        ("2020-03-01", "2020-03-11", "x", "x", "near_epoch"),
        ("2020-03-01", "2020-03-30", "x", "x", "near_epoch"),
        ("2020-03-01", "2020-03-31", "x", "x", "cross_epoch"),
        ("2020-03-01", "2020-03-01", "x", "y", "cross_epoch"),
        ("2017-03-02", "2021-03-05", "x", "x", "cross_epoch"),
        (None, "2021-03-05", "x", "x", "unknown_epoch"),
        ("2017-03-02", None, "x", "x", "unknown_epoch"),
        ("not a date", "2021-03-05", "x", "x", "unknown_epoch"),
        ("2017-03-02", "2021-03-05", "unknown", "x", "unknown_epoch"),
        ("2017-03-02", "2021-03-05", "", "x", "unknown_epoch"),
    ],
)
def test_epoch_classification_table(d1, d2, p1, p2, expected):
    before, after = _pair(d1, d2, p1, p2)
    assert classify_epoch(before, after).value == expected


def test_near_epoch_boundary_is_the_documented_constant():
    assert NEAR_EPOCH_DAYS == 30  # uncalibrated heuristic, see epoch.py


def test_undated_basemap_capture_is_always_unknown_epoch():
    site = precise_site()
    shot = scene(site, "shot", None, None, capture_kind=UNDATED_BASEMAP_CAPTURE)
    dated = scene(site, "d", "2021-03-05T00:00:00Z", 1.0)
    assert classify_epoch(dated, shot) is EpochClass.UNKNOWN_EPOCH
    # Even if a capture claims a date, its kind keeps it out of the dated classes.
    dated_shot = replace(shot, acquired_at="2021-03-05T00:00:00Z")
    assert classify_epoch(dated, dated_shot) is EpochClass.UNKNOWN_EPOCH


def test_after_before_before_is_an_error_not_a_silent_swap():
    before, after = _pair("2021-03-05", "2017-03-02")
    with pytest.raises(ValueError):
        classify_epoch(before, after)


def test_timestamps_parse_to_utc_and_garbage_does_not():
    assert parse_acquired_at("2020-01-01T00:00:00Z").utcoffset().total_seconds() == 0
    assert parse_acquired_at("2020-01-01T02:00:00+02:00").hour == 0
    assert parse_acquired_at("2020-01-01").hour == 0
    for bad in (None, "", "  ", "yesterday", "2020-13-45"):
        assert parse_acquired_at(bad) is None


# --- series admission -----------------------------------------------------------


def _series(site, scenes, **kw):
    return build_series(site, scenes, **kw)


def test_only_provider_dated_scenes_enter_the_series_and_the_ledger_closes():
    site = precise_site()
    scenes = [
        scene(site, "ok1", "2017-03-02T14:50:00Z", 4.0),
        scene(site, "ok2", "2021-03-05T14:50:00Z", 6.0),
        scene(
            site,
            "shot",
            None,
            None,
            capture_kind=UNDATED_BASEMAP_CAPTURE,
            provider="unknown",
        ),
        scene(site, "cloudy", "2019-01-01T00:00:00Z", 55.0),
        scene(site, "nocloud", "2019-02-01T00:00:00Z", None),
        scene(site, "ok1", "2018-01-01T00:00:00Z", 1.0),
        scene(site, "undated", None, 1.0),
        scene(site, "noprov", "2018-06-01T00:00:00Z", 1.0, provider="unknown"),
    ]
    series = _series(site, scenes)
    reasons = {e.scene_id + ":" + e.reason for e in series.exclusions}
    assert [s.scene_id for s in series.admitted] == ["ok1", "ok2"]
    assert reasons == {
        "shot:UNDATED_BASEMAP_CAPTURE",
        "cloudy:CLOUD_COVER_ABOVE_CUTOFF",
        "nocloud:CLOUD_COVER_UNKNOWN",
        "ok1:DUPLICATE_SCENE_ID",
        "undated:UNDATED",
        "noprov:UNKNOWN_PROVIDER",
    }
    ledger = series.ledger()
    assert ledger["considered"] == 8 == ledger["admitted"] + ledger["excluded"]
    assert sum(ledger["by_reason"].values()) == ledger["excluded"]


def test_unknown_cloud_cover_is_never_treated_as_clear():
    site = precise_site()
    series = _series(site, [scene(site, "x", "2020-01-01T00:00:00Z", None)])
    assert series.admitted == ()


def test_scene_that_does_not_cover_the_site_is_excluded():
    site = precise_site()
    far = replace(
        scene(site, "far", "2020-01-01T00:00:00Z", 1.0), bbox=(-67.0, 17.0, -66.9, 17.1)
    )
    series = _series(site, [far])
    assert [e.reason for e in series.exclusions] == ["SITE_OUTSIDE_SCENE_BBOX"]


def test_series_is_ordered_by_date_whatever_the_input_order():
    site = precise_site()
    scenes = [
        scene(site, n, d, 1.0)
        for n, d in [("c", "2022-01-01"), ("a", "2018-01-01"), ("b", "2020-01-01")]
    ]
    assert [s.scene_id for s in _series(site, scenes).admitted] == ["a", "b", "c"]


def test_cloud_cutoff_is_configurable_and_defaults_to_twenty_percent():
    site = precise_site()
    cloudy = scene(site, "x", "2020-01-01T00:00:00Z", 55.0)
    assert DEFAULT_CLOUD_CUTOFF_PCT == 20.0
    assert _series(site, [cloudy]).admitted == ()
    assert len(_series(site, [cloudy], cloud_cutoff_pct=60.0).admitted) == 1
    boundary = scene(site, "y", "2020-01-01T00:00:00Z", 20.0)
    assert len(_series(site, [boundary]).admitted) == 1  # cutoff is inclusive


def test_comparison_pairs():
    site = precise_site()

    def pairs(n):
        scenes = [scene(site, f"s{i}", f"20{10 + i}-01-01", 1.0) for i in range(n)]
        return [
            (a.scene_id, b.scene_id, k)
            for a, b, k in comparison_pairs(_series(site, scenes))
        ]

    assert pairs(0) == [] and pairs(1) == []
    assert pairs(2) == [("s0", "s1", "consecutive")]
    assert pairs(3) == [
        ("s0", "s1", "consecutive"),
        ("s1", "s2", "consecutive"),
        ("s0", "s2", "baseline_latest"),
    ]


# --- adapters -------------------------------------------------------------------


def test_synthetic_adapter_is_deterministic_and_content_addressed():
    import hashlib

    site = precise_site()
    scenes = [scene(site, "a", "2020-01-01T00:00:00Z", 1.0)]
    adapter = ad.SyntheticAdapter({site.external_site_id: scenes})
    assert adapter.search(site, "2015-01-01", "2026-01-01") == adapter.search(
        site, "2015-01-01", "2026-01-01"
    )
    data = adapter.fetch(site, scenes[0])
    assert data == adapter.fetch(site, scenes[0])
    assert hashlib.sha256(data).hexdigest() == scenes[0].content_sha256
    assert all(s.synthetic for s in scenes)


def test_synthetic_adapter_filters_by_window_but_keeps_undated_for_exclusion():
    site = precise_site()
    scenes = [
        scene(site, "in", "2020-06-01T00:00:00Z", 1.0),
        scene(site, "out", "2012-06-01T00:00:00Z", 1.0),
        scene(site, "shot", None, None, capture_kind=UNDATED_BASEMAP_CAPTURE),
    ]
    adapter = ad.SyntheticAdapter({site.external_site_id: scenes})
    found = {s.scene_id for s in adapter.search(site, "2015-01-01", "2026-01-01")}
    assert found == {"in", "shot"}


def test_synthetic_fetch_rejects_a_scene_whose_hash_was_tampered():
    site = precise_site()
    good = scene(site, "a", "2020-01-01T00:00:00Z", 1.0)
    adapter = ad.SyntheticAdapter({site.external_site_id: [good]})
    with pytest.raises(ad.AcquisitionUnavailable):
        adapter.fetch(site, replace(good, content_sha256="0" * 64))


def test_live_adapter_is_a_fail_closed_stub(monkeypatch):
    monkeypatch.setenv("SENTINELHUB_CLIENT_SECRET", "do-not-leak-me")
    site = precise_site()
    live = ad.UnavailableAdapter()
    for call in (
        lambda: live.search(site, "2015-01-01", "2026-01-01"),
        lambda: live.fetch(site, scene(site, "a", "2020-01-01", 1.0)),
    ):
        with pytest.raises(ad.AcquisitionUnavailable) as err:
            call()
        message = str(err.value)
        assert "environment variables" in message
        assert "ADR 0006" in message
        assert "do-not-leak-me" not in message


def test_adapter_module_reads_no_environment_and_makes_no_requests():
    source = (REPO / "spiderweb/site_timeline/adapters.py").read_text()
    for forbidden in (
        "os.environ",
        "getenv",
        "import requests",
        "urllib",
        "http.client",
        "socket",
    ):
        assert forbidden not in source


def test_package_imports_without_network_or_imaging_libraries():
    code = (
        "import sys\n"
        "import spiderweb.site_timeline.timeline, spiderweb.site_timeline.fixtures\n"
        "import spiderweb.site_timeline.adapters, spiderweb.site_timeline.metrics\n"
        "bad = [m for m in ('requests', 'PIL', 'numpy', 'httpx', 'urllib3',\n"
        "                   'imagery', 'imagery.providers') if m in sys.modules]\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert out == ""


def test_no_data_files_are_written_by_importing_or_building(tmp_path, monkeypatch):
    from tests.site_timeline_support import standard_document

    monkeypatch.chdir(tmp_path)
    standard_document()
    assert list(tmp_path.iterdir()) == []
