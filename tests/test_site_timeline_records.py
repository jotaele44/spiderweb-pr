"""Site imagery timeline: records, comparison guardrails and document validation.

Synthetic data only. The guardrails come from the SATIM mixed-epoch spec
(VISIBLE_EPOCH_CHANGE_ONLY, ORIGINAL_EPOCH_RECORD_IMMUTABILITY,
SEPARATE_BEFORE_AFTER_PROVENANCE, NO_CAUSAL_INFERENCE) and
docs/contracts/SITE_IMAGERY_TIMELINE.md.
"""

from __future__ import annotations

import copy
import dataclasses
import io
import json
import re

import pytest

from spiderweb.site_timeline import records as rec
from spiderweb.site_timeline.adapters import SyntheticAdapter, synthetic_payload
from spiderweb.site_timeline.metrics import (
    FixtureMetric,
    MetricMeta,
    MetricUnavailable,
    PixelDifferenceMetric,
)
from spiderweb.site_timeline.models import (
    GUARDRAILS,
    PROHIBITED_OUTPUTS,
    UNDATED_BASEMAP_CAPTURE,
    EpochClass,
)
from spiderweb.site_timeline.timeline import (
    DISPOSITION_NO_CLAIM,
    DISPOSITION_RENDER_ONLY,
    DISPOSITION_SCORED,
    ContentMismatch,
    build_site_timeline,
    compare_pair,
    to_json,
    validate_document,
)
from tests.site_timeline_support import (
    END,
    NOW,
    START,
    coarse_site,
    document_for,
    precise_site,
    scene,
    standard_document,
    timeline_for,
)

# The fields satim_provisional_signal.v1 requires, copied from the thehub-pr contract
# (schemas/contracts/skywatcher_ai). The schema has additionalProperties: false.
SIGNAL_FIELDS = {
    "schema_version",
    "signal_id",
    "source_artifact_ids",
    "method",
    "method_version",
    "parameters",
    "result",
    "confidence",
    "provisional",
    "review_status",
    "created_at",
}
SIGNAL_METHODS = {
    "PIXEL_DIFFERENCE",
    "CALIBRATED_CHANGE_DETECTION",
    "TILE_SEAM_CLASSIFICATION",
    "OTHER",
}
SIGNAL_REVIEW = {"UNREVIEWED", "NEEDS_REVIEW", "APPROVED", "REJECTED", "SUPERSEDED"}
RECEIPT_HUB_ONLY = {"audit_event_id", "egress_decision_id"}


def _all(doc, key):
    return [item for entry in doc["sites"] for item in entry[key]]


# --- the three separate objects -------------------------------------------------


def test_standard_document_validates():
    assert validate_document(standard_document()) == []


def test_each_scene_and_comparison_yields_three_separate_objects():
    doc = standard_document()
    acquisitions, artifacts = _all(doc, "acquisitions"), _all(doc, "artifacts")
    comparisons = _all(doc, "comparisons")
    assert len(acquisitions) == len(artifacts) == 4 and len(comparisons) == 2
    for acq in acquisitions:
        assert acq["schema_version"] == rec.ACQUISITION_SCHEMA
        assert acq["artifact_ids"][0].startswith("sha256:")
        assert "result" not in acq and "content_sha256" not in acq
    for art in artifacts:
        assert art["schema_version"] == rec.ARTIFACT_SCHEMA
        assert "outcome" not in art and "signal_id" not in art
    for cmp in comparisons:
        assert cmp["signal"]["schema_version"] == rec.SIGNAL_SCHEMA


def test_artifact_ref_is_content_addressed_and_holds_no_pixels():
    for art in _all(standard_document(), "artifacts"):
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", art["artifact_id"])
        assert art["artifact_id"] == "sha256:" + art["content_sha256"]
        assert not ({"local_path", "image", "image_bytes", "pixels"} & set(art))


def test_acquisition_record_does_not_pose_as_a_hub_receipt():
    for acq in _all(standard_document(), "acquisitions"):
        assert acq["hub_receipt"] is False
        assert not (RECEIPT_HUB_ONLY & set(acq))
        assert acq["schema_version"] != "acquisition_receipt.v1"
        assert acq["classification"] == "TEST_ONLY" and acq["synthetic"] is True


def test_signal_matches_the_hub_provisional_signal_shape():
    for cmp in _all(standard_document(), "comparisons"):
        signal = cmp["signal"]
        assert set(signal) == SIGNAL_FIELDS
        assert signal["schema_version"] == "satim_provisional_signal.v1"
        assert signal["provisional"] is True
        assert signal["method"] in SIGNAL_METHODS
        assert signal["review_status"] in SIGNAL_REVIEW - {
            "APPROVED",
            "REJECTED",
            "SUPERSEDED",
        }
        assert signal["source_artifact_ids"] and len(
            set(signal["source_artifact_ids"])
        ) == len(signal["source_artifact_ids"])


def test_ids_are_deterministic_prefixed_digests():
    doc = standard_document()
    assert to_json(doc) == to_json(standard_document())
    for acq in _all(doc, "acquisitions"):
        assert re.fullmatch(r"acq_[0-9a-f]{32}", acq["receipt_id"])
        assert re.fullmatch(r"op_[0-9a-f]{32}", acq["operation_id"])
        assert re.fullmatch(r"[0-9a-f]{64}", acq["request_digest"])
    for cmp in _all(doc, "comparisons"):
        assert re.fullmatch(r"cmp_[0-9a-f]{32}", cmp["comparison_id"])
        assert re.fullmatch(r"sig_[0-9a-f]{32}", cmp["signal"]["signal_id"])


def test_ids_change_when_content_changes():
    site = precise_site()
    a = scene(site, "a", "2017-03-02", 1.0)
    b = scene(site, "b", "2021-03-05", 1.0)
    changed = dataclasses.replace(b, content_sha256="1" * 64)
    assert rec.comparison_id(site, a, b, "consecutive") != rec.comparison_id(
        site, a, changed, "consecutive"
    )
    assert rec.comparison_id(site, a, b, "consecutive") != rec.comparison_id(
        site, a, b, "baseline_latest"
    )


def test_identical_content_yields_one_unique_source_artifact():
    site = precise_site()
    a = scene(site, "a", "2017-03-02", 1.0)
    b = dataclasses.replace(
        scene(site, "b", "2021-03-05", 1.0), content_sha256=a.content_sha256
    )
    signal = rec.signal_record(
        cmp_id="cmp_x",
        site=site,
        before=a,
        after=b,
        pair_kind="consecutive",
        epoch_class=EpochClass.CROSS_EPOCH,
        meta=MetricMeta("OTHER", "t@1", {}),
        score=None,
        dropped_change_types=(),
        review_reasons=(),
        disposition=DISPOSITION_SCORED,
        now=NOW,
    )
    assert signal["source_artifact_ids"] == [rec.artifact_id(a.content_sha256)]


def test_original_epoch_records_are_immutable():
    site = precise_site()
    epoch = rec.epoch_record(scene(site, "a", "2017-03-02T14:50:00Z", 1.0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        epoch.capture_time = "2030-01-01T00:00:00Z"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        scene(site, "a", "2017-03-02", 1.0).acquired_at = "x"  # type: ignore[misc]


def test_before_and_after_provenance_stay_separate():
    for cmp in _all(standard_document(), "comparisons"):
        result = cmp["signal"]["result"]
        assert result["before"]["scene_id"] != result["after"]["scene_id"]
        assert result["before"]["artifact_id"] != result["after"]["artifact_id"]


def test_no_causal_ownership_or_purpose_content_exists_in_the_data():
    # The guardrails and prohibited_outputs lists name these notions on purpose, so
    # the scan covers the data the pipeline produced: every site block and the note.
    doc = standard_document()
    text = (json.dumps(doc["sites"]) + doc["interim_acquisition_note"]).lower()
    for word in ("cause", "owner", "purpose", "illegal", "dumping", "certified"):
        assert word not in text


def test_guardrails_and_prohibited_outputs_travel_with_the_document():
    doc = standard_document()
    assert tuple(doc["guardrails"]) == GUARDRAILS
    assert tuple(doc["prohibited_outputs"]) == PROHIBITED_OUTPUTS
    assert doc["provisional"] is True
    assert "ADR 0006" in doc["interim_acquisition_note"]


# --- guardrails on a single comparison -----------------------------------------


class _NeverCalled:
    def measure(self, before, after, payloads):
        raise AssertionError("no change metric may run for this pair")


def _payloads(a, b):
    return synthetic_payload(a.scene_id), synthetic_payload(b.scene_id)


def test_unknown_epoch_makes_no_change_claim():
    site = precise_site()
    dated = scene(site, "d", "2021-03-05T00:00:00Z", 1.0)
    shot = scene(
        site,
        "shot",
        None,
        None,
        capture_kind=UNDATED_BASEMAP_CAPTURE,
        provider="unknown",
    )
    out = compare_pair(
        site, dated, shot, "consecutive", _NeverCalled(), _payloads(dated, shot), NOW
    )
    assert out["disposition"] == DISPOSITION_NO_CLAIM
    assert out["epoch_class"] == "unknown_epoch"
    assert out["signal"]["result"]["score"] is None
    assert out["signal"]["confidence"] is None


def test_same_epoch_is_render_consistency_only():
    site = precise_site()
    a = scene(site, "a", "2021-03-05T10:00:00Z", 1.0)
    b = scene(site, "b", "2021-03-05T10:05:00Z", 1.0)
    out = compare_pair(site, a, b, "consecutive", _NeverCalled(), _payloads(a, b), NOW)
    assert out["disposition"] == DISPOSITION_RENDER_ONLY
    assert out["signal"]["result"]["score"] is None


def test_near_epoch_is_scored_but_always_needs_review():
    site = precise_site()
    a = scene(site, "a", "2021-03-05", 1.0)
    b = scene(site, "b", "2021-03-20", 1.0)
    metric = FixtureMetric({("a", "b"): {"SURFACE_COVER_CHANGE": 0.95}})
    out = compare_pair(site, a, b, "consecutive", metric, _payloads(a, b), NOW)
    result = out["signal"]["result"]
    assert out["epoch_class"] == "near_epoch" and result["score"] is not None
    assert result["review_required"] and "NEAR_EPOCH" in result["review_reasons"]
    assert out["signal"]["review_status"] == "NEEDS_REVIEW"


def test_fine_classes_are_dropped_at_ten_metres_with_a_review_reason():
    site = precise_site()
    a, b = scene(site, "a", "2017-03-02", 1.0), scene(site, "b", "2021-03-05", 1.0)
    metric = FixtureMetric(
        {("a", "b"): {"SURFACE_COVER_CHANGE": 0.8, "NEW_FEATURE": 0.9}}
    )
    result = compare_pair(site, a, b, "consecutive", metric, _payloads(a, b), NOW)[
        "signal"
    ]["result"]
    assert result["score"]["change_types"] == ["SURFACE_COVER_CHANGE"]
    assert result["dropped_change_types"] == ["NEW_FEATURE"]
    assert "CHANGE_CLASS_NOT_SUPPORTED:NEW_FEATURE" in result["review_reasons"]


def test_coarse_site_geometry_drops_fine_classes_even_with_fine_imagery():
    signals = {"EXPANSION": 0.8, "ACCESS_CHANGE": 0.9}

    def run(site):
        a = scene(site, "a", "2017-03-02", 1.0, resolution_m=1.0)
        b = scene(site, "b", "2021-03-05", 1.0, resolution_m=1.0)
        out = compare_pair(
            site,
            a,
            b,
            "consecutive",
            FixtureMetric({("a", "b"): signals}),
            _payloads(a, b),
            NOW,
        )
        return out["signal"]["result"]["score"]["change_types"]

    assert run(coarse_site()) == ["EXPANSION"]
    assert run(precise_site()) == ["ACCESS_CHANGE", "EXPANSION"]


@pytest.mark.parametrize("site_factory, cap", [(coarse_site, 0.3), (precise_site, 0.6)])
def test_confidence_never_exceeds_the_geometry_ceiling(site_factory, cap):
    site = site_factory()
    a, b = scene(site, "a", "2017-03-02", 0.0), scene(site, "b", "2021-03-05", 0.0)
    metric = FixtureMetric({("a", "b"): {"SURFACE_COVER_CHANGE": 1.0}})
    out = compare_pair(site, a, b, "consecutive", metric, _payloads(a, b), NOW)
    adjusted = out["signal"]["result"]["score"]["adjusted_change_score"]
    # Default registration is 0.6, so alignment is (1 + 0.6 + 1 + 1) / 4 = 0.9.
    assert adjusted == 0.9
    assert adjusted > cap  # the ceiling, not the score, is what binds
    assert out["signal"]["confidence"] == cap


def test_heavy_cloud_makes_a_change_artifact_driven():
    site = precise_site()
    timeline = timeline_for(
        site,
        [scene(site, "a", "2017-03-02", 80.0), scene(site, "b", "2021-03-05", 80.0)],
        {("a", "b"): {"SURFACE_COVER_CHANGE": 0.9}},
        cloud_cutoff_pct=100.0,
    )
    signal = timeline["comparisons"][0]["signal"]
    assert signal["result"]["score"]["classification"] == "ARTIFACT_DRIVEN_CHANGE"
    assert "HIGH_ARTIFACT_CONFIDENCE" in signal["result"]["review_reasons"]
    assert signal["review_status"] == "NEEDS_REVIEW"


def test_poor_registration_and_overlap_is_insufficient_alignment():
    site = precise_site()
    west, south, east, north = (
        site.lon - 1e-4,
        site.lat - 1e-4,
        site.lon + 1e-4,
        site.lat + 1e-4,
    )
    tiny = {"bbox": (west, south, east, north), "geometric_confidence": 0.0}
    a = dataclasses.replace(scene(site, "a", "2017-03-02", 1.0), **tiny)
    b = dataclasses.replace(scene(site, "b", "2021-03-05", 1.0), **tiny)
    out = compare_pair(
        site,
        a,
        b,
        "consecutive",
        FixtureMetric({("a", "b"): {"SURFACE_COVER_CHANGE": 0.9}}),
        _payloads(a, b),
        NOW,
    )
    assert out["signal"]["result"]["score"]["classification"] == (
        "INSUFFICIENT_EPOCH_ALIGNMENT"
    )


def test_an_unlisted_fixture_pair_is_an_error_not_stable():
    site = precise_site()
    with pytest.raises(MetricUnavailable):
        timeline_for(
            site,
            [scene(site, "a", "2017-03-02", 1.0), scene(site, "b", "2021-03-05", 1.0)],
            {},
        )


def test_bytes_that_do_not_match_the_declared_hash_are_rejected():
    site = precise_site()
    a = scene(site, "a", "2017-03-02", 1.0)

    class Lying(SyntheticAdapter):
        def fetch(self, site, scene):  # noqa: ANN001
            return b"different bytes"

    with pytest.raises(ContentMismatch):
        build_site_timeline(
            site,
            Lying({site.external_site_id: [a]}),
            FixtureMetric(),
            start=START,
            end=END,
            now=NOW,
        )


def test_series_with_fewer_than_two_scenes_has_no_comparisons():
    site = precise_site()
    timeline = timeline_for(site, [scene(site, "a", "2017-03-02", 1.0)], {})
    assert timeline["comparisons"] == [] and timeline["ledger"]["admitted"] == 1


def test_the_arroyo_screenshot_case_is_excluded_not_compared():
    """The undated basemap screenshot never enters the series or a change claim."""
    site = precise_site()
    timeline = timeline_for(
        site,
        [
            scene(site, "a", "2017-03-02", 1.0),
            scene(site, "b", "2021-03-05", 1.0),
            scene(
                site,
                "shot",
                None,
                None,
                capture_kind=UNDATED_BASEMAP_CAPTURE,
                provider="unknown",
            ),
        ],
        {("a", "b"): {"SURFACE_COVER_CHANGE": 0.5}},
    )
    assert timeline["ledger"]["by_reason"] == {"UNDATED_BASEMAP_CAPTURE": 1}
    ids = {a["scene_id"] for a in timeline["artifacts"]}
    assert "shot" not in ids
    assert all("shot" not in json.dumps(c) for c in timeline["comparisons"])


# --- tampering is caught --------------------------------------------------------


def _first_signal(doc):
    return doc["sites"][0]["comparisons"][0]["signal"]


def _set(path_fn, value):
    def mutate(doc):
        path_fn(doc, value)

    return mutate


def _same_epoch_with_score(doc):
    cmp = doc["sites"][0]["comparisons"][0]
    cmp["epoch_class"] = "same_epoch"
    cmp["signal"]["result"]["epoch_class"] = "same_epoch"


MUTATIONS = {
    "not provisional": lambda d: d.__setitem__("provisional", False),
    "guardrail removed": lambda d: d["guardrails"].pop(),
    "prohibited outputs removed": lambda d: d.__setitem__("prohibited_outputs", []),
    "wrong schema": lambda d: d.__setitem__("schema_version", "x"),
    "signal not provisional": lambda d: _first_signal(d).__setitem__(
        "provisional", False
    ),
    "signal approved": lambda d: _first_signal(d).__setitem__(
        "review_status", "APPROVED"
    ),
    "extra result key": lambda d: _first_signal(d)["result"].__setitem__("cause", "x"),
    "same epoch carries a score": _same_epoch_with_score,
    "confidence above cap": lambda d: _first_signal(d).__setitem__("confidence", 0.99),
    "ledger broken": lambda d: d["sites"][0]["ledger"].__setitem__("considered", 99),
    "exclusion without reason": lambda d: d["sites"][0]["exclusions"][0].__setitem__(
        "reason", ""
    ),
    "acquisition posing as hub receipt": lambda d: d["sites"][0]["acquisitions"][
        0
    ].__setitem__("hub_receipt", True),
    "synthetic not test-only": lambda d: d["sites"][0]["acquisitions"][0].__setitem__(
        "classification", "PUBLIC"
    ),
    "artifact not content addressed": lambda d: d["sites"][0]["artifacts"][
        0
    ].__setitem__("artifact_id", "x"),
    "undated artifact": lambda d: d["sites"][0]["artifacts"][0].__setitem__(
        "acquired_at", None
    ),
    "basemap artifact": lambda d: d["sites"][0]["artifacts"][0].__setitem__(
        "capture_kind", UNDATED_BASEMAP_CAPTURE
    ),
    "epochs out of order": lambda d: _first_signal(d)["result"]["before"].__setitem__(
        "acquired_at", "2099-01-01T00:00:00Z"
    ),
    "unknown artifact": lambda d: _first_signal(d).__setitem__(
        "source_artifact_ids", ["sha256:" + "0" * 64]
    ),
    "duplicate site": lambda d: d["sites"].append(copy.deepcopy(d["sites"][0])),
    "synthetic flag wrong": lambda d: d.__setitem__("synthetic", False),
    "coarse site, fine class": lambda d: d["sites"][1]["comparisons"][0]["signal"][
        "result"
    ]["score"].__setitem__("change_types", ["ACCESS_CHANGE"]),
    "coarse imagery, fine class": lambda d: d["sites"][0]["comparisons"][0]["signal"][
        "result"
    ]["score"].__setitem__("change_types", ["NEW_FEATURE"]),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_validator_catches_tampering(name):
    doc = copy.deepcopy(standard_document())
    MUTATIONS[name](doc)
    assert validate_document(doc), f"{name} slipped through"


def test_validator_rejects_non_documents():
    for bad in (None, [], "x", 3):
        assert validate_document(bad)
    assert validate_document({"sites": "nope"})


def test_a_document_mixing_synthetic_and_live_scenes_is_rejected():
    doc = copy.deepcopy(standard_document())
    doc["sites"][1]["artifacts"][0]["synthetic"] = False
    assert any("mixes" in p for p in validate_document(doc))


def test_document_for_two_sites_keeps_ledgers_per_site():
    doc = standard_document()
    assert [e["ledger"]["considered"] for e in doc["sites"]] == [3, 2]
    assert doc == document_for(*doc["sites"]) | {"generated_at": doc["generated_at"]}


# --- the pixel difference metric (needs Pillow and numpy) -----------------------


def test_pixel_metric_is_a_labelled_uncalibrated_first_pass():
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    from PIL import Image

    def png(color):
        buf = io.BytesIO()
        Image.new("L", (16, 16), color).save(buf, format="PNG")
        return buf.getvalue()

    site = precise_site()
    black, white = png(0), png(255)
    import hashlib

    def real_scene(sid, date, data):
        return dataclasses.replace(
            scene(site, sid, date, 1.0), content_sha256=hashlib.sha256(data).hexdigest()
        )

    a, b = real_scene("a", "2017-03-02", black), real_scene("b", "2021-03-05", white)
    measurement = PixelDifferenceMetric().measure(a, b, (black, white))
    assert measurement.signals == {"SURFACE_COVER_CHANGE": 1.0}
    assert measurement.meta.method == "PIXEL_DIFFERENCE"
    assert measurement.meta.parameters["calibrated"] is False
    same = PixelDifferenceMetric().measure(a, a, (black, black))
    assert same.signals == {"SURFACE_COVER_CHANGE": 0.0}


def test_pixel_metric_only_ever_speaks_to_surface_cover():
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (4, 4), 10).save(buf, format="PNG")
    data = buf.getvalue()
    site = precise_site()
    a = scene(site, "a", "2017-03-02", 1.0)
    out = PixelDifferenceMetric().measure(a, a, (data, data))
    assert set(out.signals) == {"SURFACE_COVER_CHANGE"}
