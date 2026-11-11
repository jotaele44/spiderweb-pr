"""Timeline orchestration: from a site and an adapter to a provisional document.

``build_site_timeline`` is the only place that calls the acquisition adapter. The
rest of the package works on records it returns, so replacing acquisition (hub ADR
0006) touches ``adapters.py`` alone.

Nothing is written here and nothing reads a clock: callers pass ``now``.

Every number derived below is an **uncalibrated heuristic**, stated next to the
code that computes it. The document it produces is a set of provisional visible-change
signals between dated epochs. It does not say what changed, why, who did it or what
it is for (``NO_CAUSAL_INFERENCE``).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .adapters import AcquisitionAdapter, AcquisitionUnavailable
from .epoch import classify_epoch, parse_acquired_at
from .metrics import ChangeMetric, MetricMeta
from .models import (
    COARSE_CONFIDENCE_CAP,
    GUARDRAILS,
    PRECISE_CONFIDENCE_CAP,
    PROHIBITED_OUTPUTS,
    PROVIDER_SCENE,
    EpochClass,
    SceneRecord,
    Site,
    TemporalObservation,
)
from .records import (
    ACQUISITION_SCHEMA,
    ARTIFACT_SCHEMA,
    CLASSIFICATION_SYNTHETIC,
    SIGNAL_SCHEMA,
    acquisition_record,
    artifact_ref,
    comparison_id,
    epoch_record,
    operation_id,
    signal_record,
)
from .score import (
    COARSE_CHANGE_TYPES,
    COARSE_ONLY_ABOVE_M,
    restrict_to_resolution,
    score_temporal_change,
)
from .series import DEFAULT_CLOUD_CUTOFF_PCT, Series, build_series, comparison_pairs

DOCUMENT_SCHEMA = "spiderweb.site_imagery_timeline.v1"

DISPOSITION_SCORED = "SCORED"
DISPOSITION_RENDER_ONLY = "RENDER_CONSISTENCY_ONLY"
DISPOSITION_NO_CLAIM = "NO_CLAIM_UNKNOWN_EPOCH"

INTERIM_NOTE = (
    "Acquisition by spiderweb-pr is an interim path pending the hub acquisition "
    "runtime (hub ADR 0006). adapters.py is the single seam to replace. Every "
    "signal here is provisional and is not evidence of record."
)

# The exact keys a change record's ``result`` may carry. A closed set keeps cause,
# owner and purpose fields out by construction.
_RESULT_KEYS = frozenset(
    {
        "comparison_id",
        "pair_kind",
        "site",
        "epoch_class",
        "disposition",
        "before",
        "after",
        "score",
        "dropped_change_types",
        "review_required",
        "review_reasons",
        "synthetic",
    }
)

_NO_MEASUREMENT = MetricMeta("OTHER", "none@1", {"reason": "no_change_claim_possible"})


# --- derived score inputs (uncalibrated heuristics) -----------------------------


def _area(box: tuple[float, float, float, float]) -> float:
    west, south, east, north = box
    return max(0.0, east - west) * max(0.0, north - south)


def _intersect(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def spatial_overlap(site: Site, before: SceneRecord, after: SceneRecord) -> float:
    """Share of the site chip covered by both scenes."""
    chip = site.chip_bbox()
    covered = _intersect(_intersect(chip, before.bbox), after.bbox)
    chip_area = _area(chip)
    return 0.0 if chip_area <= 0 else min(1.0, _area(covered) / chip_area)


def scale_compatibility(before: SceneRecord, after: SceneRecord) -> float:
    """Ratio of the finer to the coarser resolution; 0.5 when either is unknown."""
    a, b = before.resolution_m, after.resolution_m
    if not a or not b:
        return 0.5
    return min(a, b) / max(a, b)


def view_angle_compatibility(before: SceneRecord, after: SceneRecord) -> float:
    """View geometry is not measured. Same platform and instrument counts as 1.0."""
    same = before.platform == after.platform and before.instrument == after.instrument
    return 1.0 if same else 0.7


def artifact_confidence(before: SceneRecord, after: SceneRecord) -> float:
    """Cloud is the dominant artifact source: the cloudier scene sets the level."""
    clouds = [c for c in (before.cloud_cover_pct, after.cloud_cover_pct) if c]
    return max(clouds, default=0.0) / 100.0


def _effective_resolution(
    site: Site, before: SceneRecord, after: SceneRecord
) -> float | None:
    """Coarse geometry or coarse imagery restricts the allowed change classes.

    ``None`` means "treated as coarse" for ``restrict_to_resolution``.
    """
    if site.is_coarse or not before.resolution_m or not after.resolution_m:
        return None
    return max(before.resolution_m, after.resolution_m)


# --- one comparison -------------------------------------------------------------


def compare_pair(
    site: Site,
    before: SceneRecord,
    after: SceneRecord,
    pair_kind: str,
    metric: ChangeMetric,
    payloads: tuple[bytes, bytes],
    now: str,
) -> dict[str, Any]:
    """Compare two admitted scenes. Unknown and same epochs make no change claim."""
    cmp_id = comparison_id(site, before, after, pair_kind)
    epoch = classify_epoch(before, after)

    if epoch in (EpochClass.UNKNOWN_EPOCH, EpochClass.SAME_EPOCH):
        disposition = (
            DISPOSITION_NO_CLAIM
            if epoch is EpochClass.UNKNOWN_EPOCH
            else DISPOSITION_RENDER_ONLY
        )
        signal = signal_record(
            cmp_id=cmp_id,
            site=site,
            before=before,
            after=after,
            pair_kind=pair_kind,
            epoch_class=epoch,
            meta=_NO_MEASUREMENT,
            score=None,
            dropped_change_types=(),
            review_reasons=(),
            disposition=disposition,
            now=now,
        )
        return _comparison(cmp_id, pair_kind, epoch, disposition, signal)

    measurement = metric.measure(before, after, payloads)
    kept, dropped = restrict_to_resolution(
        measurement.signals, _effective_resolution(site, before, after)
    )
    observation = TemporalObservation(
        comparison_id=cmp_id,
        before=epoch_record(before),
        after=epoch_record(after),
        change_signals=kept,
        spatial_overlap=spatial_overlap(site, before, after),
        registration_quality=min(
            before.geometric_confidence, after.geometric_confidence
        ),
        scale_compatibility=scale_compatibility(before, after),
        view_angle_compatibility=view_angle_compatibility(before, after),
        artifact_confidence=artifact_confidence(before, after),
        contradiction_confidence=0.0,  # no contradiction source is wired
    )
    score = score_temporal_change(observation)

    reasons = [f"CHANGE_CLASS_NOT_SUPPORTED:{name}" for name in dropped]
    if epoch is EpochClass.NEAR_EPOCH:
        reasons.append("NEAR_EPOCH")
    signal = signal_record(
        cmp_id=cmp_id,
        site=site,
        before=before,
        after=after,
        pair_kind=pair_kind,
        epoch_class=epoch,
        meta=measurement.meta,
        score=score,
        dropped_change_types=dropped,
        review_reasons=tuple(sorted(set(score.review_reasons) | set(reasons))),
        disposition=DISPOSITION_SCORED,
        now=now,
    )
    return _comparison(cmp_id, pair_kind, epoch, DISPOSITION_SCORED, signal)


def _comparison(
    cmp_id: str,
    pair_kind: str,
    epoch: EpochClass,
    disposition: str,
    signal: dict[str, Any],
) -> dict[str, Any]:
    return {
        "comparison_id": cmp_id,
        "pair_kind": pair_kind,
        "epoch_class": epoch.value,
        "disposition": disposition,
        "signal": signal,
    }


# --- one site -------------------------------------------------------------------


def site_summary(site: Site) -> dict[str, Any]:
    return {
        "external_site_id": site.external_site_id,
        "producer_entity_id": site.producer_entity_id,
        "name": site.name,
        "lat": site.lat,
        "lon": site.lon,
        "geometry_precision_decimals": site.geometry_precision_decimals,
        "geometry_coarse": site.is_coarse,
        "chip_bbox": [round(v, 6) for v in site.chip_bbox()],
        "authority": site.authority,
    }


class ContentMismatch(AcquisitionUnavailable):
    """Fetched bytes do not hash to the scene's declared content hash."""


def build_site_timeline(
    site: Site,
    adapter: AcquisitionAdapter,
    metric: ChangeMetric,
    *,
    start: str,
    end: str,
    now: str,
    cloud_cutoff_pct: float = DEFAULT_CLOUD_CUTOFF_PCT,
) -> dict[str, Any]:
    """Search, admit, fetch (in memory), compare. Raises rather than guesses."""
    from hashlib import sha256

    series = build_series(
        site, adapter.search(site, start, end), cloud_cutoff_pct=cloud_cutoff_pct
    )
    operation = operation_id(site, start, end, adapter.name)

    payloads: dict[str, bytes] = {}
    for scene in series.admitted:
        data = adapter.fetch(site, scene)
        if sha256(data).hexdigest() != scene.content_sha256:
            raise ContentMismatch(
                f"scene {scene.scene_id}: fetched bytes do not match content_sha256"
            )
        payloads[scene.scene_id] = data

    comparisons = [
        compare_pair(
            site,
            before,
            after,
            kind,
            metric,
            (payloads[before.scene_id], payloads[after.scene_id]),
            now,
        )
        for before, after, kind in comparison_pairs(series)
    ]
    return _site_document(site, series, operation, comparisons, now)


def _site_document(
    site: Site,
    series: Series,
    operation: str,
    comparisons: list[dict[str, Any]],
    now: str,
) -> dict[str, Any]:
    return {
        "site": site_summary(site),
        "ledger": series.ledger(),
        "exclusions": [
            {"scene_id": e.scene_id, "reason": e.reason} for e in series.exclusions
        ],
        "epochs": [asdict(epoch_record(s)) for s in series.admitted],
        "acquisitions": [
            acquisition_record(site, s, operation=operation, now=now)
            for s in series.admitted
        ],
        "artifacts": [artifact_ref(s) for s in series.admitted],
        "comparisons": comparisons,
    }


# --- the document ---------------------------------------------------------------


def build_document(
    site_timelines: list[dict[str, Any]],
    *,
    now: str,
    adapter_name: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    synthetic = any(a["synthetic"] for t in site_timelines for a in t["artifacts"])
    return {
        "schema_version": DOCUMENT_SCHEMA,
        "generated_at": now,
        "adapter": adapter_name,
        "window": {"start": start, "end": end},
        "synthetic": synthetic,
        "provisional": True,
        "guardrails": list(GUARDRAILS),
        "prohibited_outputs": list(PROHIBITED_OUTPUTS),
        "interim_acquisition_note": INTERIM_NOTE,
        "sites": site_timelines,
    }


def to_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


# --- validation -----------------------------------------------------------------


def validate_document(doc: Any) -> list[str]:
    """Return every problem found; an empty list means the document is sound."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["document is not an object"]
    if doc.get("schema_version") != DOCUMENT_SCHEMA:
        problems.append(f"schema_version must be {DOCUMENT_SCHEMA}")
    if doc.get("provisional") is not True:
        problems.append("document must be provisional")
    if list(doc.get("guardrails", [])) != list(GUARDRAILS):
        problems.append("guardrails are missing or altered")
    if list(doc.get("prohibited_outputs", [])) != list(PROHIBITED_OUTPUTS):
        problems.append("prohibited_outputs are missing or altered")
    if parse_acquired_at(doc.get("generated_at")) is None:
        problems.append("generated_at is not a timestamp")
    sites = doc.get("sites")
    if not isinstance(sites, list):
        return problems + ["sites must be a list"]

    flags: set[bool] = set()
    seen_sites: set[str] = set()
    for entry in sites:
        site_id = (entry.get("site") or {}).get("external_site_id", "?")
        if site_id in seen_sites:
            problems.append(f"{site_id}: duplicate site")
        seen_sites.add(site_id)
        flags |= _synthetic_flags(entry)
        problems += _validate_site(site_id, entry)
    if len(flags) > 1:
        problems.append(
            "document mixes synthetic and live records "
            "(artifacts, acquisitions and change records must agree)"
        )
    if bool(doc.get("synthetic")) != (True in flags):
        problems.append("document synthetic flag does not match its records")
    return problems


def _synthetic_flags(entry: dict[str, Any]) -> set[bool]:
    """The synthetic flag of every record type a site carries.

    The export stamps every row from the document flag, and production mode relies
    on it, so a flag cleared on some records but not others must not pass.
    """
    flags = {bool(a.get("synthetic")) for a in entry.get("artifacts", [])}
    flags |= {bool(a.get("synthetic")) for a in entry.get("acquisitions", [])}
    for cmp in entry.get("comparisons", []):
        result = (cmp.get("signal") or {}).get("result") or {}
        flags.add(bool(result.get("synthetic")))
    return flags


def _validate_site(site_id: str, entry: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    ledger = entry.get("ledger", {})
    artifacts = entry.get("artifacts", [])
    exclusions = entry.get("exclusions", [])
    if ledger.get("considered") != ledger.get("admitted", 0) + ledger.get(
        "excluded", 0
    ):
        problems.append(f"{site_id}: ledger does not close")
    if ledger.get("admitted") != len(artifacts):
        problems.append(f"{site_id}: admitted count does not match artifacts")
    if ledger.get("excluded") != len(exclusions):
        problems.append(f"{site_id}: excluded count does not match exclusions")
    if any(not e.get("reason") for e in exclusions):
        problems.append(f"{site_id}: an exclusion has no reason")
    for key in ("epochs", "acquisitions"):
        if len(entry.get(key, [])) != len(artifacts):
            problems.append(f"{site_id}: {key} do not match artifacts")

    by_artifact: dict[str, dict[str, Any]] = {}
    for art in artifacts:
        aid = art.get("artifact_id", "")
        if art.get("schema_version") != ARTIFACT_SCHEMA:
            problems.append(f"{site_id}: artifact has a wrong schema_version")
        if not (aid.startswith("sha256:") and len(aid) == 71):
            problems.append(f"{site_id}: artifact id is not content-addressed")
        if art.get("capture_kind") != PROVIDER_SCENE:
            problems.append(f"{site_id}: {aid} is not a provider scene")
        if parse_acquired_at(art.get("acquired_at")) is None:
            problems.append(f"{site_id}: {aid} has no acquisition date")
        by_artifact[aid] = art
    # Artifact ids are content hashes, so two scenes with identical pixels share one.
    # Scene ids are unique per site (checked below), so resolve scenes by that.
    by_scene = {str(art.get("scene_id")): art for art in artifacts}

    scene_ids = [art.get("scene_id") for art in artifacts]
    if len(scene_ids) != len(set(scene_ids)):
        problems.append(f"{site_id}: scene ids are not unique")
    # The export reads observed_at from the epoch records and the receipt id from the
    # acquisitions, so each must describe the artifact at the same position.
    for art, epoch_rec in zip(artifacts, entry.get("epochs", []), strict=False):
        provenance = epoch_rec.get("provenance") or {}
        when = parse_acquired_at(art.get("acquired_at"))
        if provenance.get("scene_id") != art.get("scene_id") or (
            when is None or when != parse_acquired_at(epoch_rec.get("capture_time"))
        ):
            problems.append(
                f"{site_id}: epoch record does not match artifact {art.get('scene_id')}"
            )
    for art, acq in zip(artifacts, entry.get("acquisitions", []), strict=False):
        if acq.get("artifact_ids") != [art.get("artifact_id")]:
            problems.append(
                f"{site_id}: acquisition does not match artifact {art.get('scene_id')}"
            )

    for acq in entry.get("acquisitions", []):
        if acq.get("schema_version") != ACQUISITION_SCHEMA:
            problems.append(f"{site_id}: acquisition has a wrong schema_version")
        if acq.get("hub_receipt") is not False:
            problems.append(
                f"{site_id}: acquisition must not claim to be a hub receipt"
            )
        if not set(acq.get("artifact_ids", [])) <= set(by_artifact):
            problems.append(f"{site_id}: acquisition names an unknown artifact")
        if bool(acq.get("synthetic")) != (
            acq.get("classification") == CLASSIFICATION_SYNTHETIC
        ):
            problems.append(
                f"{site_id}: acquisition classification does not match its "
                "synthetic flag (TEST_ONLY exactly when synthetic)"
            )

    site = entry.get("site", {})
    for cmp in entry.get("comparisons", []):
        problems += _validate_comparison(site_id, site, cmp, by_artifact, by_scene)
    return problems


def _validate_comparison(
    site_id: str,
    site: dict[str, Any],
    cmp: dict[str, Any],
    by_artifact: dict[str, dict[str, Any]],
    by_scene: dict[str, dict[str, Any]],
) -> list[str]:
    problems: list[str] = []
    label = f"{site_id}:{cmp.get('comparison_id', '?')}"
    signal = cmp.get("signal", {})
    result = signal.get("result", {})
    epoch = cmp.get("epoch_class")
    score = result.get("score")

    if signal.get("schema_version") != SIGNAL_SCHEMA:
        problems.append(f"{label}: signal has a wrong schema_version")
    if signal.get("provisional") is not True:
        problems.append(f"{label}: signal must be provisional")
    if signal.get("review_status") not in {"UNREVIEWED", "NEEDS_REVIEW"}:
        problems.append(f"{label}: signal review_status is not a pipeline state")
    if set(result) != _RESULT_KEYS:
        problems.append(f"{label}: result keys are not the permitted set")
    if epoch not in {item.value for item in EpochClass}:
        problems.append(f"{label}: unknown epoch class")
    if not set(signal.get("source_artifact_ids", [])) <= set(by_artifact):
        problems.append(f"{label}: signal names an unknown artifact")

    before = result.get("before", {}).get("acquired_at")
    after = result.get("after", {}).get("acquired_at")
    t_before, t_after = parse_acquired_at(before), parse_acquired_at(after)
    if t_before is None or t_after is None or t_after < t_before:
        problems.append(f"{label}: epochs are undated or out of order")

    problems += _epoch_problems(label, epoch, signal, result, by_scene)

    if epoch in ("unknown_epoch", "same_epoch"):
        if score is not None or signal.get("confidence") is not None:
            problems.append(f"{label}: {epoch} must not carry a change claim")
        return problems

    if score is None:
        problems.append(f"{label}: {epoch} comparison has no score")
        return problems
    confidence = signal.get("confidence")
    cap = (
        COARSE_CONFIDENCE_CAP if site.get("geometry_coarse") else PRECISE_CONFIDENCE_CAP
    )
    if confidence is None or not (0.0 <= confidence <= cap):
        problems.append(f"{label}: confidence is outside [0, {cap}]")
    if epoch == "near_epoch" and not result.get("review_required"):
        problems.append(f"{label}: near_epoch must require review")
    if site.get("geometry_coarse") and not set(score.get("change_types", [])) <= (
        COARSE_CHANGE_TYPES
    ):
        problems.append(f"{label}: coarse geometry carries a fine change class")
    resolutions = [
        by_scene[sid].get("resolution_m")
        for sid in (
            str((result.get(side) or {}).get("scene_id"))
            for side in ("before", "after")
        )
        if sid in by_scene
    ]
    coarse_imagery = any(r is None or r > COARSE_ONLY_ABOVE_M for r in resolutions)
    if coarse_imagery and not set(score.get("change_types", [])) <= (
        COARSE_CHANGE_TYPES
    ):
        problems.append(f"{label}: coarse imagery carries a fine change class")
    return problems


def _scene_from_artifact(art: dict[str, Any]) -> SceneRecord | None:
    """Rebuild the fields epoch classification reads. Missing data fails closed."""
    try:
        west, south, east, north = art["bbox"]
        return SceneRecord(
            scene_id=art["scene_id"],
            provider=art["provider"],
            acquired_at=art.get("acquired_at"),
            cloud_cover_pct=art.get("cloud_cover_pct"),
            resolution_m=art.get("resolution_m"),
            bbox=(west, south, east, north),
            content_sha256=art["content_sha256"],
            capture_kind=art.get("capture_kind") or "",
        )
    except (KeyError, TypeError, ValueError):
        return None


def _epoch_problems(
    label: str,
    epoch: Any,
    signal: dict[str, Any],
    result: dict[str, Any],
    by_scene: dict[str, dict[str, Any]],
) -> list[str]:
    """Derive the epoch class from the referenced scenes; do not trust the label.

    A label that disagrees with the scenes would let a same-date pair keep a change
    claim, or a near-epoch pair skip review.
    """
    problems: list[str] = []
    scenes: dict[str, SceneRecord | None] = {}
    for side in ("before", "after"):
        ref = result.get(side) or {}
        art = by_scene.get(str(ref.get("scene_id")))
        if art is None:
            problems.append(f"{label}: {side} names an unknown scene")
            continue
        for key in ("artifact_id", "provider", "acquired_at"):
            if ref.get(key) != art.get(key):
                problems.append(f"{label}: {side} {key} does not match its artifact")
        scenes[side] = _scene_from_artifact(art)

    declared = {
        (result.get("before") or {}).get("artifact_id"),
        (result.get("after") or {}).get("artifact_id"),
    }
    if set(signal.get("source_artifact_ids", [])) != declared:
        problems.append(f"{label}: signal artifacts differ from its before and after")

    before, after = scenes.get("before"), scenes.get("after")
    if before is None or after is None:
        return problems
    try:
        expected = classify_epoch(before, after).value
    except ValueError:
        return problems  # after precedes before: reported by the date check
    if expected != epoch:
        problems.append(
            f"{label}: epoch_class {epoch} does not match its scenes ({expected})"
        )
    return problems
