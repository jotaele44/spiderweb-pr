"""Epoch classification for a before/after pair of dated scenes.

Re-implemented from skywatcher-pr's SATIM mixed-epoch validation spec (this
repository forbids cross-repo imports). The classes and their dispositions:

* ``same_epoch``    same provider and acquisition date: render consistency only
* ``near_epoch``    same provider, too close in time to separate seasons: review
* ``cross_epoch``   meaningfully different date, provider or capture cycle: valid
* ``unknown_epoch`` a date or provider is missing: never promoted
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import PROVIDER_SCENE, EpochClass, SceneRecord

# UNCALIBRATED HEURISTIC, chosen here and not taken from the SATIM spec: two scenes
# from one provider closer than this many days are not treated as separated by a
# season. Tune it against real imagery before relying on the near/cross boundary.
NEAR_EPOCH_DAYS = 30

_UNKNOWN_PROVIDERS = frozenset({"", "unknown"})


def parse_acquired_at(value: str | None) -> datetime | None:
    """Parse an ISO-8601 date or date-time into an aware UTC datetime, else None."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_dated_provider_scene(scene: SceneRecord) -> bool:
    return (
        scene.capture_kind == PROVIDER_SCENE
        and parse_acquired_at(scene.acquired_at) is not None
        and scene.provider.strip().lower() not in _UNKNOWN_PROVIDERS
    )


def classify_epoch(before: SceneRecord, after: SceneRecord) -> EpochClass:
    """Classify the pair. ``after`` must not precede ``before``."""
    if not (is_dated_provider_scene(before) and is_dated_provider_scene(after)):
        return EpochClass.UNKNOWN_EPOCH
    t_before = parse_acquired_at(before.acquired_at)
    t_after = parse_acquired_at(after.acquired_at)
    assert t_before is not None and t_after is not None  # narrowed above
    if t_after < t_before:
        raise ValueError("after must not precede before")
    if before.provider != after.provider:
        return EpochClass.CROSS_EPOCH
    if t_before.date() == t_after.date():
        return EpochClass.SAME_EPOCH
    if (t_after - t_before).days < NEAR_EPOCH_DAYS:
        return EpochClass.NEAR_EPOCH
    return EpochClass.CROSS_EPOCH
