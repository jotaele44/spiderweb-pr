"""Record builders: three separate objects, never one mutable manifest.

For every scene and comparison the timeline keeps apart:

* an **acquisition record** (what was requested, from whom, with what outcome);
* a content-addressed **artifact reference** (``sha256:<hex>`` of the pixels, which
  live only in a git-ignored cache);
* a **provisional change record** (the derived signal, never certified evidence).

This mirrors the object separation in hub ADR 0006. Hub contracts are matched as
follows:

* The change record conforms to ``satim_provisional_signal.v1``: every field the
  schema allows is used and nothing else, so spiderweb context rides inside
  ``result``.
* The acquisition record carries the facts of ``acquisition_receipt.v1`` but is
  **not** a hub receipt and does not claim that schema version: the hub schema
  requires an ``audit_event_id`` (and optionally an egress decision) that only a hub
  acquisition runtime can issue, and spiderweb has none. When acquisition moves to
  the hub (ADR 0006) these records are replaced by hub receipts, not reshaped.

Ids are deterministic digests of their inputs. No clock is read here: callers pass
``now``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .epoch import parse_acquired_at
from .metrics import MetricMeta
from .models import EpochClass, EpochRecord, SceneRecord, Site, TemporalScore

ACQUISITION_SCHEMA = "spiderweb.site_timeline.acquisition_record.v1"
ARTIFACT_SCHEMA = "spiderweb.site_timeline.artifact_ref.v1"
SIGNAL_SCHEMA = "satim_provisional_signal.v1"

# Every change record starts unreviewed. Nothing here is ever "approved": approval is
# a reviewer's act, not a pipeline's.
REVIEW_STATUS = "UNREVIEWED"
REVIEW_STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"

CLASSIFICATION_SYNTHETIC = "TEST_ONLY"
CLASSIFICATION_LIVE = "INTERNAL"


def digest(*parts: Any) -> str:
    """Deterministic SHA-256 hex of the parts, joined with a separator."""
    text = "|".join(
        (
            json.dumps(p, sort_keys=True, separators=(",", ":"))
            if isinstance(p, (dict, list, tuple))
            else str(p)
        )
        for p in parts
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def artifact_id(content_sha256: str) -> str:
    return f"sha256:{content_sha256}"


def operation_id(site: Site, start: str, end: str, adapter: str) -> str:
    return "op_" + digest(site.external_site_id, start, end, adapter)[:32]


def request_digest(site: Site, scene: SceneRecord) -> str:
    return digest(
        site.external_site_id,
        scene.provider,
        scene.scene_id,
        [round(v, 6) for v in scene.bbox],
    )


def acquisition_record(
    site: Site,
    scene: SceneRecord,
    *,
    operation: str,
    now: str,
    outcome: str = "SUCCEEDED",
) -> dict[str, Any]:
    req = request_digest(site, scene)
    return {
        "schema_version": ACQUISITION_SCHEMA,
        "receipt_id": "acq_" + digest(req, scene.content_sha256)[:32],
        "operation_id": operation,
        "provider": scene.provider,
        "requested_at": now,
        "completed_at": now,
        "outcome": outcome,
        "request_digest": req,
        "artifact_ids": [artifact_id(scene.content_sha256)],
        "classification": (
            CLASSIFICATION_SYNTHETIC if scene.synthetic else CLASSIFICATION_LIVE
        ),
        "synthetic": scene.synthetic,
        "hub_receipt": False,
    }


def artifact_ref(scene: SceneRecord) -> dict[str, Any]:
    """Content-addressed reference. No pixels, no local path."""
    return {
        "schema_version": ARTIFACT_SCHEMA,
        "artifact_id": artifact_id(scene.content_sha256),
        "content_sha256": scene.content_sha256,
        "media_type": scene.media_type,
        "scene_id": scene.scene_id,
        "provider": scene.provider,
        "collection": scene.collection,
        "platform": scene.platform,
        "instrument": scene.instrument,
        "acquired_at": scene.acquired_at,
        "cloud_cover_pct": scene.cloud_cover_pct,
        "resolution_m": scene.resolution_m,
        "bbox": [round(v, 6) for v in scene.bbox],
        "geometric_confidence": scene.geometric_confidence,
        "capture_kind": scene.capture_kind,
        "synthetic": scene.synthetic,
    }


def epoch_record(scene: SceneRecord) -> EpochRecord:
    when = parse_acquired_at(scene.acquired_at)
    capture = when.isoformat().replace("+00:00", "Z") if when else ""
    return EpochRecord(
        record_id="epr_" + digest(scene.scene_id, scene.content_sha256)[:32],
        epoch_id=f"{scene.provider}:{capture[:10]}",
        capture_time=capture,
        provider=scene.provider,
        resolution_m=scene.resolution_m,
        geometry_id="geo_" + digest([round(v, 6) for v in scene.bbox])[:32],
        provenance={
            "scene_id": scene.scene_id,
            "provider": scene.provider,
            "collection": scene.collection,
            "content_sha256": scene.content_sha256,
            "acquired_at": scene.acquired_at,
        },
    )


def comparison_id(
    site: Site, before: SceneRecord, after: SceneRecord, pair_kind: str
) -> str:
    return (
        "cmp_"
        + digest(
            site.external_site_id,
            pair_kind,
            before.scene_id,
            before.content_sha256,
            after.scene_id,
            after.content_sha256,
        )[:32]
    )


def signal_record(
    *,
    cmp_id: str,
    site: Site,
    before: SceneRecord,
    after: SceneRecord,
    pair_kind: str,
    epoch_class: EpochClass,
    meta: MetricMeta,
    score: TemporalScore | None,
    dropped_change_types: tuple[str, ...],
    review_reasons: tuple[str, ...],
    disposition: str,
    now: str,
) -> dict[str, Any]:
    """A ``satim_provisional_signal.v1`` record. Provisional, never certified."""
    artifacts = [artifact_id(before.content_sha256), artifact_id(after.content_sha256)]
    unique_artifacts = list(dict.fromkeys(artifacts))
    confidence: float | None = None
    if score is not None:
        confidence = round(min(score.adjusted_change_score, site.confidence_cap), 4)
    result: dict[str, Any] = {
        "comparison_id": cmp_id,
        "pair_kind": pair_kind,
        "site": {
            "external_site_id": site.external_site_id,
            "producer_entity_id": site.producer_entity_id,
            "geometry_coarse": site.is_coarse,
        },
        "epoch_class": epoch_class.value,
        "disposition": disposition,
        "before": {
            "artifact_id": artifacts[0],
            "scene_id": before.scene_id,
            "acquired_at": before.acquired_at,
            "provider": before.provider,
        },
        "after": {
            "artifact_id": artifacts[1],
            "scene_id": after.scene_id,
            "acquired_at": after.acquired_at,
            "provider": after.provider,
        },
        "score": (
            None
            if score is None
            else {
                "classification": score.classification,
                "change_score": score.change_score,
                "alignment_score": score.alignment_score,
                "artifact_confidence": score.artifact_confidence,
                "contradiction_confidence": score.contradiction_confidence,
                "adjusted_change_score": score.adjusted_change_score,
                "change_types": list(score.change_types),
            }
        ),
        "dropped_change_types": list(dropped_change_types),
        "review_required": bool(review_reasons)
        or (score is not None and score.review_required),
        "review_reasons": list(review_reasons),
        "synthetic": before.synthetic or after.synthetic,
    }
    parameters = dict(meta.parameters)
    return {
        "schema_version": SIGNAL_SCHEMA,
        "signal_id": "sig_"
        + digest(cmp_id, meta.method, meta.method_version, parameters)[:32],
        "source_artifact_ids": unique_artifacts,
        "method": meta.method,
        "method_version": meta.method_version,
        "parameters": parameters,
        "result": result,
        "confidence": confidence,
        "provisional": True,
        "review_status": (
            REVIEW_STATUS_NEEDS_REVIEW if result["review_required"] else REVIEW_STATUS
        ),
        "created_at": now,
    }
