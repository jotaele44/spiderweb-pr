"""
Imagery — persistence sink (spiderweb-pr).

Routes fetched-imagery metadata into the repository's existing satellite-ingest
pipeline: build a satellite_source_manifest, then hand it to
``readiness.satellite_ingest.SatelliteIngest`` which validates it against the
contract schema and writes accepted manifests to ``data/satellite_manifests/``.

This is the *only* module that differs between spiderweb-pr and skywatcher-pr.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from . import manifest as manifest_mod
from .models import ImageryResult


def persist(result: ImageryResult, synthetic: bool = False) -> dict[str, Any]:
    """Build a manifest from ``result`` and ingest it via SatelliteIngest.

    Returns a result dict: ``persisted`` (bool), ``status`` ("accepted" |
    "rejected" | "unavailable"), ``output_path``, and ``errors``. Never raises —
    a persistence failure must not fail the fetch itself.
    """
    doc = manifest_mod.build_manifest(result, synthetic=synthetic)

    try:
        from readiness.satellite_ingest import SatelliteIngest
    except Exception as exc:  # pragma: no cover - only when run outside the repo
        return {
            "persisted": False,
            "status": "unavailable",
            "output_path": None,
            "errors": [f"satellite ingest unavailable: {exc}"],
            "manifest": doc,
        }

    tmp_path: Path | None = None
    try:
        fd = tempfile.NamedTemporaryFile(
            mode="w", suffix=".imagery.json", delete=False, encoding="utf-8"
        )
        with fd as fh:
            json.dump(doc, fh, indent=2)
            tmp_path = Path(fh.name)

        ingest_result = SatelliteIngest().ingest(str(tmp_path))
        return {
            "persisted": ingest_result.get("status") == "accepted",
            "status": ingest_result.get("status"),
            "output_path": ingest_result.get("output_path"),
            "errors": ingest_result.get("errors", []),
            "manifest": doc,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "persisted": False,
            "status": "rejected",
            "output_path": None,
            "errors": [f"ingest error: {exc}"],
            "manifest": doc,
        }
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
