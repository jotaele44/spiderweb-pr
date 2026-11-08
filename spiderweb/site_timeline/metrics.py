"""Change metrics: how two dated scenes are compared.

A metric returns *signals* keyed by SATIM change class plus the method metadata that
travels with the provisional record. The pixel metric reuses ``imagery.compare`` and
imports it lazily, so this package stays importable without Pillow or numpy.

The pixel difference is a first-pass, **uncalibrated** measurement. It can only speak
to ``SURFACE_COVER_CHANGE``: telling ``EXPANSION`` from ``CONTRACTION`` needs a
footprint segmentation that does not exist yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import ChangeType, SceneRecord


class MetricUnavailable(RuntimeError):
    """The metric cannot run here (a dependency is missing). Fail closed."""


@dataclass(frozen=True)
class MetricMeta:
    method: str
    method_version: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Measurement:
    signals: dict[str, float]
    meta: MetricMeta


class ChangeMetric(Protocol):
    def measure(
        self,
        before: SceneRecord,
        after: SceneRecord,
        payloads: tuple[bytes, bytes],
    ) -> Measurement:
        """Return change signals keyed by SATIM change class plus method metadata.

        Raises ``MetricUnavailable`` when the metric cannot run; it never reports
        "no change" for a pair it could not measure.
        """


class FixtureMetric:
    """Signals looked up by ``(before_scene_id, after_scene_id)``. For offline tests.

    A pair that is not in the table raises ``MetricUnavailable``.
    """

    def __init__(
        self, signals: Mapping[tuple[str, str], Mapping[str, float]] | None = None
    ):
        self._signals = {k: dict(v) for k, v in (signals or {}).items()}

    def measure(
        self,
        before: SceneRecord,
        after: SceneRecord,
        payloads: tuple[bytes, bytes],
    ) -> Measurement:
        key = (before.scene_id, after.scene_id)
        if key not in self._signals:
            # An unlisted pair is a fixture gap, not "no change": a typo must not
            # read as STABLE.
            raise MetricUnavailable(f"no fixture signals for pair {key}")
        return Measurement(
            dict(self._signals[key]),
            MetricMeta("OTHER", "fixture@1", {"fixture": True}),
        )


class PixelDifferenceMetric:
    """Grayscale pixel difference through ``imagery.compare`` (needs Pillow, numpy)."""

    def __init__(self, threshold: float | None = None):
        self.threshold = threshold

    def measure(
        self,
        before: SceneRecord,
        after: SceneRecord,
        payloads: tuple[bytes, bytes],
    ) -> Measurement:
        try:
            from imagery.compare import changed_fraction
            from imagery.models import ImageryResult
        except ImportError as exc:  # pragma: no cover - exercised by import-hygiene
            raise MetricUnavailable(f"pixel metric unavailable: {exc}") from exc

        def result(scene: SceneRecord, data: bytes) -> ImageryResult:
            return ImageryResult(
                provider=scene.provider,
                image_bytes=data,
                media_type=scene.media_type,
                bbox=list(scene.bbox),
                acquired_at=scene.acquired_at,
                resolution_m=scene.resolution_m,
                scene_id=scene.scene_id,
            )

        try:
            change = changed_fraction(
                result(before, payloads[0]),
                result(after, payloads[1]),
                self.threshold,
            )
        except ImportError as exc:
            raise MetricUnavailable(f"pixel metric unavailable: {exc}") from exc
        meta = MetricMeta(
            "PIXEL_DIFFERENCE",
            "imagery.changed_fraction@1",
            {
                "threshold": change.threshold,
                "measure": "grayscale_absolute_difference",
                "calibrated": False,
            },
        )
        signals = {ChangeType.SURFACE_COVER_CHANGE.value: change.changed_fraction}
        return Measurement(signals, meta)
