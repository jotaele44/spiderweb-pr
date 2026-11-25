"""Frozen, hash-pinned input snapshots.

A snapshot is a directory holding ``snapshot.json`` (the manifest) plus layer
files.  The manifest pins every layer by SHA-256, so changed input bytes are
detected before anything is rendered.  Snapshots are read-only to the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from federation.spatial_core import canonical_json_sha256
from provenance_utils import compute_sha256

MANIFEST_NAME = "snapshot.json"
SCHEMA = "viz_snapshot/v1"
UNLIMITED = 1 << 40


class SnapshotIntegrityError(ValueError):
    """Raised when a layer file does not match the hash pinned in the manifest."""


@dataclass
class Snapshot:
    root: Path
    manifest: dict[str, Any]
    layers: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def manifest_sha256(self) -> str:
        return canonical_json_sha256(self.manifest)

    def layer(self, kind: str) -> dict[str, Any] | None:
        for data in self.layers.values():
            if data.get("kind") == kind:
                return data
        return None

    def feature_layers(self) -> list[dict[str, Any]]:
        return [d for _, d in sorted(self.layers.items()) if "features" in d]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_snapshot(root: str | Path) -> Snapshot:
    """Load a snapshot and verify every layer hash against the manifest."""
    root = Path(root)
    manifest = _read_json(root / MANIFEST_NAME)
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"unsupported snapshot schema: {manifest.get('schema')!r}")
    layers: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("layers", []):
        path = root / entry["path"]
        actual = compute_sha256(str(path), max_bytes=UNLIMITED)
        if actual != entry["sha256"]:
            raise SnapshotIntegrityError(
                f"layer {entry['layer_id']}: sha256 {actual} != pinned {entry['sha256']}"
            )
        layers[entry["layer_id"]] = _read_json(path)
    return Snapshot(root=root, manifest=manifest, layers=layers)


def freeze_snapshot(
    root: str | Path,
    *,
    snapshot_id: str,
    version: str,
    crs: str,
    vertical_datum: str,
    extent: list[float],
    horizontal_unit: str = "degree",
    vertical_unit: str = "m",
) -> dict[str, Any]:
    """Pin every ``layers/*.json`` file under *root* and write ``snapshot.json``."""
    root = Path(root)
    entries = []
    for path in sorted((root / "layers").glob("*.json")):
        layer = _read_json(path)
        entries.append(
            {
                "layer_id": layer["layer_id"],
                "kind": layer["kind"],
                "path": path.relative_to(root).as_posix(),
                "sha256": compute_sha256(str(path), max_bytes=UNLIMITED),
                "bytes": path.stat().st_size,
                "crs": layer.get("crs"),
                "vertical_datum": layer.get("vertical_datum"),
                "source": layer.get("source", {}),
            }
        )
    manifest = {
        "schema": SCHEMA,
        "snapshot_id": snapshot_id,
        "version": version,
        "crs": crs,
        "vertical_datum": vertical_datum,
        "units": {"horizontal": horizontal_unit, "vertical": vertical_unit},
        "extent": extent,
        "layers": entries,
    }
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
