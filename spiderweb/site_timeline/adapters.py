"""The single acquisition seam.

Everything that would touch an imagery provider lives behind this protocol, so
replacing spiderweb-side acquisition with hub-brokered artifacts later (hub ADR 0006
moves provider access, credentials and caching into the hub) means replacing this
module and nothing else.

Nothing here imports an HTTP client, an imaging library or a provider.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Protocol

from .epoch import parse_acquired_at
from .models import PROVIDER_SCENE, SceneRecord, Site

LIVE_ACQUISITION_MESSAGE = (
    "live acquisition is not wired. It needs Sentinel-2 credentials supplied "
    "through environment variables, and hub ADR 0006 moves satellite-provider "
    "access into the hub, so this seam is interim. Nothing was fetched."
)


class AcquisitionUnavailable(RuntimeError):
    """Raised instead of returning partial or invented data."""


class AcquisitionAdapter(Protocol):
    name: str

    def search(self, site: Site, start: str, end: str) -> list[SceneRecord]:
        """Return candidate scenes for ``site`` between two ISO dates.

        May include undated captures so that series admission excludes them
        visibly. Raises ``AcquisitionUnavailable`` rather than return partial data.
        """

    def fetch(self, site: Site, scene: SceneRecord) -> bytes:
        """Return the scene bytes, held in memory only.

        The caller verifies them against ``scene.content_sha256``. Implementations
        never write them to disk and never log credentials.
        """


def synthetic_payload(scene_id: str) -> bytes:
    """Deterministic stand-in bytes for a fixture scene. Not an image."""
    return f"SYNTHETIC-SCENE:{scene_id}".encode()


def synthetic_scene(
    site: Site,
    scene_id: str,
    acquired_at: str | None,
    cloud_cover_pct: float | None,
    *,
    provider: str = "sentinelhub",
    resolution_m: float | None = 10.0,
    platform: str = "Sentinel-2",
    instrument: str = "MSI",
    collection: str = "sentinel-2-l2a",
    geometric_confidence: float = 0.6,
    capture_kind: str = PROVIDER_SCENE,
) -> SceneRecord:
    """A fixture scene over the site's chip, marked ``synthetic``."""
    return SceneRecord(
        scene_id=scene_id,
        provider=provider,
        acquired_at=acquired_at,
        cloud_cover_pct=cloud_cover_pct,
        resolution_m=resolution_m,
        bbox=site.chip_bbox(),
        content_sha256=hashlib.sha256(synthetic_payload(scene_id)).hexdigest(),
        platform=platform,
        instrument=instrument,
        collection=collection,
        capture_kind=capture_kind,
        geometric_confidence=geometric_confidence,
        synthetic=True,
    )


class SyntheticAdapter:
    """Offline adapter over a fixed table of scenes. Deterministic, no network."""

    name = "synthetic"

    def __init__(self, scenes_by_site: Mapping[str, Sequence[SceneRecord]]):
        self._scenes = {k: tuple(v) for k, v in scenes_by_site.items()}

    def search(self, site: Site, start: str, end: str) -> list[SceneRecord]:
        low, high = parse_acquired_at(start), parse_acquired_at(end)
        found = []
        for scene in self._scenes.get(site.external_site_id, ()):
            when = parse_acquired_at(scene.acquired_at)
            # An undated scene is returned so the admission rules can exclude it.
            if when is None or (
                low is not None
                and high is not None
                and low.date() <= when.date() <= high.date()
            ):
                found.append(scene)
        return found

    def fetch(self, site: Site, scene: SceneRecord) -> bytes:
        payload = synthetic_payload(scene.scene_id)
        if hashlib.sha256(payload).hexdigest() != scene.content_sha256:
            raise AcquisitionUnavailable(
                f"fixture scene {scene.scene_id} does not match its content hash"
            )
        return payload


class UnavailableAdapter:
    """The live adapter, as a fail-closed stub. It reads no credentials."""

    name = "live-unavailable"

    def search(self, site: Site, start: str, end: str) -> list[SceneRecord]:
        raise AcquisitionUnavailable(LIVE_ACQUISITION_MESSAGE)

    def fetch(self, site: Site, scene: SceneRecord) -> bytes:
        raise AcquisitionUnavailable(LIVE_ACQUISITION_MESSAGE)
