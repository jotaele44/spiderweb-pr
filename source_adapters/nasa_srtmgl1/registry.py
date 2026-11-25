"""Load the SRTMGL1 source manifest (``data_sources/nasa/srtmgl1.yml``).

The manifest is JSON-compatible YAML, like the NOAA/NCEI manifest, so it is read
with :func:`json.loads` and needs no YAML parser. It holds metadata only; raw
tiles stay in an operator-local cache and are never committed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data_sources" / "nasa" / "srtmgl1.yml"
DATASET_KEY = "srtmgl1_v003_pr"


@dataclass(frozen=True)
class SrtmTile:
    tile_id: str
    granule_ur: str
    https_url: str
    s3_url: str
    num_granule_ur: str
    num_https_url: str
    cmr_footprint_wsen: tuple[float, float, float, float]
    grid_extent_wsen: tuple[float, float, float, float]

    @property
    def hgt_zip_name(self) -> str:
        return f"{self.granule_ur}.zip"

    @property
    def num_zip_name(self) -> str:
        return f"{self.num_granule_ur}.zip"


def load_manifest(path: Path | str = DEFAULT_MANIFEST_PATH) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("source_family") != "NASA_LPDAAC_SRTMGL1":
        raise ValueError("not an SRTMGL1 manifest")
    return manifest


def _dataset(manifest: dict) -> dict:
    matches = [d for d in manifest["datasets"] if d["dataset_key"] == DATASET_KEY]
    if len(matches) != 1:
        raise ValueError(f"manifest must hold exactly one {DATASET_KEY} dataset")
    return matches[0]


def load_tiles(path: Path | str = DEFAULT_MANIFEST_PATH) -> tuple[SrtmTile, ...]:
    manifest = load_manifest(path)
    do_not_commit = set(manifest["repo_policy"]["do_not_commit"])
    for pattern in ("*.hgt.zip", "*.num.zip"):
        if pattern not in do_not_commit:
            raise ValueError(f"repo_policy.do_not_commit must list {pattern}")
    tiles = []
    for row in _dataset(manifest)["tiles"]:
        tiles.append(
            SrtmTile(
                tile_id=row["tile_id"],
                granule_ur=row["granule_ur"],
                https_url=row["https_url"],
                s3_url=row["s3_url"],
                num_granule_ur=row["num"]["granule_ur"],
                num_https_url=row["num"]["https_url"],
                cmr_footprint_wsen=tuple(row["cmr_footprint_wsen"]),
                grid_extent_wsen=tuple(row["grid_extent_wsen"]),
            )
        )
    ids = [tile.tile_id for tile in tiles]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate tile ids in manifest")
    return tuple(tiles)


def require_tile(tiles: tuple[SrtmTile, ...], tile_id: str) -> SrtmTile:
    for tile in tiles:
        if tile.tile_id == tile_id:
            return tile
    raise ValueError(f"tile {tile_id} is not registered in the SRTMGL1 manifest")
