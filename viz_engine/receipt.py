"""Machine-readable receipt for every rendered artifact."""

from __future__ import annotations

import platform
from typing import Any

from federation.spatial_core import canonical_json_sha256
from provenance_utils import git_head_or_unknown

from . import EVIDENCE_CLASSES, RENDERER, VERSION
from .snapshot import Snapshot
from .validate import status_of

SCHEMA = "viz_receipt/v1"


def render_id_for(snap: Snapshot, view: str, config: dict[str, Any]) -> str:
    """Identity of the render *inputs* (snapshot + config + software); embeds in the artifact."""
    return canonical_json_sha256(
        {
            "snapshot": snap.manifest_sha256,
            "view": view,
            "config": config,
            "renderer": RENDERER,
            "version": VERSION,
        }
    )


def build_receipt(
    snap: Snapshot,
    view: str,
    config: dict[str, Any],
    render_id: str,
    issues: list[dict[str, Any]],
    drawn: list[dict[str, Any]],
    steps: list[str],
    output_name: str,
    output_sha256: str,
    output_bytes: int,
) -> dict[str, Any]:
    m = snap.manifest
    counts = {c: 0 for c in EVIDENCE_CLASSES}
    for d in drawn:
        counts[d["evidence"]] += 1
    dates = sorted({d["observation_date"] for d in drawn if d.get("observation_date")})
    body = {
        "schema": SCHEMA,
        "render_id": render_id,
        "renderer": {
            "name": RENDERER,
            "version": VERSION,
            "python": platform.python_version(),
            "repo_commit": git_head_or_unknown(),
        },
        "view": view,
        "config": config,
        "inputs": {
            "snapshot_id": m["snapshot_id"],
            "snapshot_version": m["version"],
            "manifest_sha256": snap.manifest_sha256,
            "layers": [
                {
                    "layer_id": e["layer_id"],
                    "kind": e["kind"],
                    "sha256": e["sha256"],
                    "source": e.get("source", {}),
                }
                for e in m["layers"]
            ],
        },
        "reference_frame": {
            "crs": m["crs"],
            "vertical_datum": m["vertical_datum"],
            "units": m["units"],
            "extent": config.get("extent") or m["extent"],
        },
        "features": drawn,
        "evidence_counts": counts,
        "observation_dates": dates,
        "processing_steps": steps,
        "validation": {"status": status_of(issues), "issues": issues},
        "publication_ready": status_of(issues) == "PASS",
        "output": {"file": output_name, "sha256": output_sha256, "bytes": output_bytes},
    }
    return {**body, "receipt_sha256": canonical_json_sha256(body)}
