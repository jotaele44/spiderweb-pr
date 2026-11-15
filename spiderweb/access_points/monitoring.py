"""Source-aware change detection for the access-point registries.

Two discovery receipts for the same box are compared record by record.  The
result says which sources are new, which changed and which disappeared, and
which registered features lie under a new or changed footprint and should be
looked at again.

What this module will not do
----------------------------
* It does not schedule anything.  It compares receipts it is given; running
  discovery on a timer belongs to whatever already schedules work.
* It never changes a feature.  A new survey over a candidate raises a review
  flag; it does not promote, demote or edit the candidate.
* A provider that failed or was not authorised produces no source-level
  events.  A failed request is not evidence that a survey was withdrawn.

Four dates are kept apart for every event: when the change was *discovered*,
when the source was *published*, when it was *surveyed*, and when the response
that revealed it was *retrieved*.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

from federation.spatial_core import canonical_json_sha256
from pipeline.marine_reference_run import SpatialRelation
from pipeline.marine_sources import BoundingBox

from .acquisition import DiscoveredRow, DiscoveryReceipt, ProviderRun, RunState

MONITORING_VERSION = "access-point-source-monitoring/1.0"


class SourceChange(StrEnum):
    NEW_SOURCE = "NEW_SOURCE"
    REVISED_METADATA = "REVISED_METADATA"
    WITHDRAWN_SOURCE = "WITHDRAWN_SOURCE"
    UNCHANGED = "UNCHANGED"


class ProviderChange(StrEnum):
    """Provider-level outcome.  Values shared with the repository's existing
    remote-change vocabulary are spelled identically."""

    NO_CHANGE = "NO_CHANGE"
    PAYLOAD_CHANGED_SCHEMA_STABLE = "PAYLOAD_CHANGED_SCHEMA_STABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_EMPTY = "SOURCE_EMPTY"
    NOT_COMPARABLE = "NOT_COMPARABLE"  # one side was not run or not authorised
    FIRST_OBSERVATION = "FIRST_OBSERVATION"


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    provider_id: str
    native_identifier: str
    identifier_is_stable: bool
    change: SourceChange
    title: str
    discovered_utc: str
    published: str | None
    surveyed: str | None
    retrieved_utc: str | None
    previous_sha256: str | None
    current_sha256: str | None
    envelope: BoundingBox | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "native_identifier": self.native_identifier,
            "identifier_is_stable": self.identifier_is_stable,
            "change": self.change.value,
            "title": self.title,
            "dates": {
                "discovered_utc": self.discovered_utc,
                "published": self.published,
                "surveyed": self.surveyed,
                "retrieved_utc": self.retrieved_utc,
            },
            "previous_sha256": self.previous_sha256,
            "current_sha256": self.current_sha256,
        }


@dataclass(frozen=True)
class ProviderComparison:
    provider_id: str
    state: ProviderChange
    events: tuple[ChangeEvent, ...]
    detail: str


@dataclass(frozen=True, slots=True)
class ReviewFlag:
    """A feature to look at again.  Carries no status change."""

    feature_id: str
    provider_id: str
    native_identifier: str
    change: SourceChange
    envelope_relation: str
    reason: str


def _row_hash(row: DiscoveredRow) -> str:
    return canonical_json_sha256(
        {
            "title": row.title,
            "attributes": {
                str(k): row.attributes[k] for k in sorted(row.attributes, key=str)
            },
            "metadata_uri": row.metadata_uri,
            "data_access_uri": row.data_access_uri,
            "surveyed": row.surveyed,
            "published": row.published,
        }
    )


def _retrieved(run: ProviderRun) -> str | None:
    return run.responses[-1].retrieved_utc if run.responses else None


def _event(
    run: ProviderRun,
    row: DiscoveredRow,
    change: SourceChange,
    discovered_utc: str,
    previous: str | None,
    current: str | None,
) -> ChangeEvent:
    return ChangeEvent(
        provider_id=run.provider_id,
        native_identifier=row.native_identifier,
        identifier_is_stable=row.identifier_is_stable,
        change=change,
        title=row.title,
        discovered_utc=discovered_utc,
        published=row.published,
        surveyed=row.surveyed,
        retrieved_utc=_retrieved(run),
        previous_sha256=previous,
        current_sha256=current,
        envelope=row.envelope,
    )


_RAN = frozenset({RunState.PASS, RunState.ZERO})


def compare_provider(
    previous: ProviderRun | None, current: ProviderRun, *, discovered_utc: str
) -> ProviderComparison:
    if current.state is RunState.FAIL:
        return ProviderComparison(
            current.provider_id,
            ProviderChange.SOURCE_UNAVAILABLE,
            (),
            f"current run failed ({current.error}); no conclusion about its sources",
        )
    if current.state not in _RAN:
        return ProviderComparison(
            current.provider_id,
            ProviderChange.NOT_COMPARABLE,
            (),
            "current run did not execute",
        )
    now = {row.native_identifier: row for row in current.rows}
    if previous is None or previous.state not in _RAN:
        events = tuple(
            _event(
                current,
                row,
                SourceChange.NEW_SOURCE,
                discovered_utc,
                None,
                _row_hash(row),
            )
            for row in sorted(now.values(), key=lambda r: r.native_identifier)
        )
        return ProviderComparison(
            current.provider_id,
            ProviderChange.FIRST_OBSERVATION,
            events,
            "no comparable earlier run; every source is new to this registry",
        )
    before = {row.native_identifier: row for row in previous.rows}
    events: list[ChangeEvent] = []
    for native in sorted(set(before) | set(now)):
        old, new = before.get(native), now.get(native)
        if old is None and new is not None:
            events.append(
                _event(
                    current,
                    new,
                    SourceChange.NEW_SOURCE,
                    discovered_utc,
                    None,
                    _row_hash(new),
                )
            )
        elif new is None and old is not None:
            events.append(
                _event(
                    current,
                    old,
                    SourceChange.WITHDRAWN_SOURCE,
                    discovered_utc,
                    _row_hash(old),
                    None,
                )
            )
        elif old is not None and new is not None:
            a, b = _row_hash(old), _row_hash(new)
            change = SourceChange.UNCHANGED if a == b else SourceChange.REVISED_METADATA
            events.append(_event(current, new, change, discovered_utc, a, b))
    changed = [e for e in events if e.change is not SourceChange.UNCHANGED]
    if not now and before:
        state = ProviderChange.SOURCE_EMPTY
        detail = "source answered cleanly with no records where it had some; review before trusting"
    elif changed:
        state = ProviderChange.PAYLOAD_CHANGED_SCHEMA_STABLE
        detail = f"{len(changed)} source records changed"
    else:
        state = ProviderChange.NO_CHANGE
        detail = "no source record changed"
    return ProviderComparison(current.provider_id, state, tuple(events), detail)


def compare_receipts(
    previous: DiscoveryReceipt | None, current: DiscoveryReceipt
) -> list[ProviderComparison]:
    """Compare two discovery receipts of the same registry and the same box."""

    if previous is not None:
        if previous.namespace is not current.namespace:
            raise ValueError("receipts belong to different registries")
        if previous.bbox != current.bbox:
            raise ValueError("receipts cover different boxes and cannot be compared")
    earlier = (
        {run.provider_id: run for run in previous.runs} if previous is not None else {}
    )
    return [
        compare_provider(
            earlier.get(run.provider_id), run, discovered_utc=current.discovered_utc
        )
        for run in sorted(current.runs, key=lambda r: r.provider_id)
    ]


def _relation(envelope: BoundingBox | None, lon: float, lat: float) -> SpatialRelation:
    if envelope is None:
        return SpatialRelation.NULL_EMPTY
    inside = (
        envelope.min_lon <= lon <= envelope.max_lon
        and envelope.min_lat <= lat <= envelope.max_lat
    )
    if not inside:
        return SpatialRelation.OUTSIDE
    on_edge = lon in (envelope.min_lon, envelope.max_lon) or lat in (
        envelope.min_lat,
        envelope.max_lat,
    )
    return SpatialRelation.TOUCH_ONLY if on_edge else SpatialRelation.FULLY_WITHIN


def review_flags(
    comparisons: Sequence[ProviderComparison],
    feature_points: Mapping[str, tuple[float, float]],
) -> list[ReviewFlag]:
    """Features under a new or changed source footprint.

    The test is point-in-envelope and is for prioritising review only; an
    envelope is not a survey outline.  Features without coordinates cannot be
    tested and are never flagged by position.
    """

    flags: list[ReviewFlag] = []
    for comparison in comparisons:
        for event in comparison.events:
            if event.change in {SourceChange.UNCHANGED}:
                continue
            for feature_id in sorted(feature_points):
                lon, lat = feature_points[feature_id]
                relation = _relation(event.envelope, lon, lat)
                if relation not in {
                    SpatialRelation.FULLY_WITHIN,
                    SpatialRelation.TOUCH_ONLY,
                }:
                    continue
                flags.append(
                    ReviewFlag(
                        feature_id=feature_id,
                        provider_id=event.provider_id,
                        native_identifier=event.native_identifier,
                        change=event.change,
                        envelope_relation=relation.value,
                        reason=(
                            f"{event.change.value} {event.title!r} has a footprint envelope over "
                            "this feature; review the evidence (no status was changed)"
                        ),
                    )
                )
    return flags


def change_report(
    comparisons: Sequence[ProviderComparison],
    flags: Sequence[ReviewFlag],
    *,
    discovered_utc: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": "access_point_source_change_report/1.0",
        "monitoring_version": MONITORING_VERSION,
        "discovered_utc": discovered_utc,
        "providers": [
            {
                "provider_id": c.provider_id,
                "state": c.state.value,
                "detail": c.detail,
                "events": [
                    e.to_dict()
                    for e in c.events
                    if e.change is not SourceChange.UNCHANGED
                ],
                "unchanged_count": sum(
                    1 for e in c.events if e.change is SourceChange.UNCHANGED
                ),
            }
            for c in comparisons
        ],
        "review_flags": [
            {
                "feature_id": f.feature_id,
                "provider_id": f.provider_id,
                "native_identifier": f.native_identifier,
                "change": f.change.value,
                "envelope_relation": f.envelope_relation,
                "reason": f.reason,
            }
            for f in flags
        ],
        "automatic_promotions": 0,
        "invariants": [
            "a failed or unauthorised provider yields no source-level events",
            "review flags never change a feature's status",
            "envelope relations are planning-only",
        ],
    }
    body["content_sha256"] = canonical_json_sha256(body)
    return body
