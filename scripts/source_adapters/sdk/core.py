"""Core contracts for source-adapter acquisition workflows.

The SDK provides small, dependency-light primitives that can be reused by portal
specific adapters such as Census, USGS, NOAA, USACE, PR GIS Portal, USFWS, and
USDA. It intentionally avoids storing payloads in git-tracked paths.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence, TypeAlias


class SourceAdapterError(RuntimeError):
    """Raised when a source adapter cannot complete a reproducible step."""


ParamScalar: TypeAlias = str | int | float | bool
ParamValue: TypeAlias = ParamScalar | Sequence[ParamScalar]
ParamInput: TypeAlias = Mapping[str, ParamValue] | Sequence[tuple[str, ParamScalar]]


def normalize_param_pairs(params: ParamInput) -> tuple[tuple[str, str], ...]:
    """Return an ordered, repeat-preserving parameter sequence.

    Mapping inputs remain backward compatible. Sequence values in a mapping are
    expanded in insertion order, while an explicit sequence of ``(key, value)``
    pairs preserves duplicate keys exactly as supplied.
    """

    if isinstance(params, Mapping):
        pairs: Iterable[tuple[str, ParamValue]] = params.items()
        normalized: list[tuple[str, str]] = []
        for key, value in pairs:
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                normalized.extend((str(key), str(item)) for item in value)
            else:
                normalized.append((str(key), str(value)))
        return tuple(normalized)

    return tuple((str(key), str(value)) for key, value in params)


@dataclass(frozen=True)
class SourceEndpoint:
    """Stable description of a source endpoint or portal."""

    source_id: str
    name: str
    url: str
    method: str = "GET"
    authority: str = ""
    evidence_tier: str = "T1"
    notes: str = ""


@dataclass(frozen=True)
class AdapterPolicy:
    """Repository guardrails for a source adapter."""

    raw_payload_root: Path
    manifest_root: Path
    extracted_root: Path | None = None
    cache_root: Path | None = None
    promoted_output_root: Path | None = None
    allow_raw_commit: bool = False
    allow_extracted_commit: bool = False

    def validate_runtime_paths(self) -> None:
        if self.allow_raw_commit or self.allow_extracted_commit:
            raise SourceAdapterError("source-adapter policy must not allow raw or extracted payload commits")


@dataclass(frozen=True)
class PayloadRequest:
    """One deterministic acquisition request."""

    request_id: str
    endpoint: SourceEndpoint
    params: ParamInput = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    expected_content: str = ""
    group_key: str = ""

    def param_pairs(self) -> tuple[tuple[str, str], ...]:
        """Canonical parameters used by both HTTP encoding and manifests."""

        return normalize_param_pairs(self.params)


@dataclass(frozen=True)
class DownloadResult:
    """Normalized result row for a payload request."""

    request_id: str
    source_id: str
    source_url: str
    request_method: str
    request_params: str
    download_timestamp_utc: str
    http_status: int | str
    content_type: str
    filename: str
    sha256: str
    bytes: int
    review_status: str
    error: str = ""


@dataclass(frozen=True)
class CoverageSummary:
    """0-to-100 accounting for a source-adapter run."""

    expected: int
    requested: int
    acquired: int
    failed: int
    hold: int
    skipped: int = 0
    unresolved: int = 0

    @property
    def coverage_pct(self) -> float:
        denominator = self.requested or self.expected
        if denominator <= 0:
            return 0.0
        return round((self.acquired / denominator) * 100, 2)


@dataclass(frozen=True)
class AcquisitionContext:
    """A run context shared by download, manifest, and normalization stages."""

    adapter_id: str
    endpoint: SourceEndpoint
    policy: AdapterPolicy
    expected_universe: Sequence[str]
    requested_universe: Sequence[str]

    def validate(self) -> None:
        self.policy.validate_runtime_paths()
        missing = [item for item in self.requested_universe if item not in set(self.expected_universe)]
        if missing:
            raise SourceAdapterError(f"requested item(s) not found in expected universe: {', '.join(missing)}")
