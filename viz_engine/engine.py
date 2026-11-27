"""Orchestration: snapshot -> validate -> render -> receipt -> files."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import RENDERER, VERSION
from .frame import footer, watermark
from .receipt import build_receipt, render_id_for
from .render_3d import render_3d
from .render_section import render_section
from .render_xy import render_xy
from .snapshot import load_snapshot
from .validate import status_of, validate_snapshot

VIEWS = {
    "xy": ("svg", render_xy),
    "section": ("svg", render_section),
    "3d": ("gltf", render_3d),
}


class PublicationBlocked(RuntimeError):
    """Raised when a FAIL artifact is exported as a publication."""


@dataclass
class RenderResult:
    artifact: Path
    receipt_path: Path
    receipt: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.receipt["validation"]["status"])


def render(
    snapshot_dir: str | Path, view: str, config: dict[str, Any], out_dir: str | Path
) -> RenderResult:
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}; expected one of {sorted(VIEWS)}")
    ext, renderer = VIEWS[view]
    snap = load_snapshot(snapshot_dir)  # raises SnapshotIntegrityError on changed bytes
    render_id = render_id_for(snap, view, config)
    issues = validate_snapshot(snap)
    product, drawn, steps, extra = renderer(snap, config, render_id, issues)
    seen = {(i["code"], i["message"]) for i in issues}
    issues += [i for i in extra if (i["code"], i["message"]) not in seen]
    status = status_of(issues)
    if ext == "svg":
        footer(product, product.footer_y, render_id, status, issues, product.title)
        if status == "FAIL":
            watermark(product, issues)
        content = product.render(
            f"{RENDERER} {VERSION} render_id={render_id} view={view} snapshot={snap.manifest_sha256}"
        )
    else:
        doc = json.loads(product)
        doc["asset"]["extras"]["validation_status"] = status
        content = json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n"
    data = content.encode("utf-8")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = f"{snap.manifest['snapshot_id']}_{view}.{ext}"
    (out / name).write_bytes(data)
    receipt = build_receipt(
        snap,
        view,
        config,
        render_id,
        issues,
        drawn,
        steps,
        name,
        hashlib.sha256(data).hexdigest(),
        len(data),
    )
    receipt_path = out / f"{name}.receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return RenderResult(out / name, receipt_path, receipt)


def export_publication(result: RenderResult, dest_dir: str | Path) -> Path:
    """Copy artifact + receipt to *dest_dir*; refuses anything that failed validation."""
    if result.status != "PASS" or not result.receipt.get("publication_ready"):
        codes = sorted(
            {
                i["code"]
                for i in result.receipt["validation"]["issues"]
                if i["severity"] == "error"
            }
        )
        raise PublicationBlocked(
            f"validation FAIL ({', '.join(codes)}); not exportable as publication"
        )
    on_disk = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    artifact_sha = hashlib.sha256(result.artifact.read_bytes()).hexdigest()
    if (
        on_disk.get("receipt_sha256") != result.receipt["receipt_sha256"]
        or artifact_sha != result.receipt["output"]["sha256"]
    ):
        raise PublicationBlocked(
            "artifact or receipt on disk no longer matches the validated render "
            "(overwritten by a later render?); not exportable as publication"
        )
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(result.artifact, dest / result.artifact.name)
    shutil.copy2(result.receipt_path, dest / result.receipt_path.name)
    return dest / result.artifact.name


def verify_artifact(artifact: str | Path, receipt_path: str | Path) -> bool:
    """True if the artifact bytes still match the receipt's recorded hash."""
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    return (
        hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        == receipt["output"]["sha256"]
    )
