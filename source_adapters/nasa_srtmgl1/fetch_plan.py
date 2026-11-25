"""Metadata-only fetch plans for SRTMGL1 tiles."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from .registry import SrtmTile
from .tiles import tiles_for_bbox

DEFAULT_CACHE_DIR = Path("data/nasa_srtmgl1/cache")
CATALOG_SOURCE_ID = "nasa_srtmgl1_v003"


def select_tiles(
    tiles: Sequence[SrtmTile],
    *,
    tile_ids: Iterable[str] | None = None,
    bbox_wsen: Sequence[float] | None = None,
) -> tuple[SrtmTile, ...]:
    by_id = {tile.tile_id: tile for tile in tiles}
    if tile_ids:
        wanted = list(dict.fromkeys(tile_ids))
        unknown = [t for t in wanted if t not in by_id]
        if unknown:
            raise ValueError(f"tiles not registered in the manifest: {', '.join(unknown)}")
        return tuple(by_id[t] for t in sorted(wanted))
    if bbox_wsen is not None:
        return tuple(by_id[t] for t in tiles_for_bbox(bbox_wsen, by_id))
    return tuple(sorted(tiles, key=lambda t: t.tile_id))


def build_fetch_plan(
    tiles: Sequence[SrtmTile],
    *,
    include_hgt: bool = True,
    include_num: bool = True,
    metadata_only: bool = True,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> dict[str, object]:
    cache = Path(cache_dir)
    tasks = []
    for tile in tiles:
        if include_hgt:
            tasks.append(("SRTMGL1", tile.tile_id, tile.https_url, tile.hgt_zip_name))
        if include_num:
            tasks.append(("SRTMGL1N", tile.tile_id, tile.num_https_url, tile.num_zip_name))
    platform_policy = _platform_policy()
    return {
        "adapter": "nasa_srtmgl1",
        "catalog_source_id": CATALOG_SOURCE_ID,
        "metadata_only": metadata_only,
        "selected_tiles": [tile.tile_id for tile in tiles],
        "tasks": [
            {
                "product": product,
                "tile_id": tile_id,
                "source_url": url,
                "local_cache_path": None if metadata_only else str(cache / name),
                "raw_commit_allowed": False,
                "review_status": "planned_metadata_only" if metadata_only else "planned_raw_cache_fetch",
            }
            for product, tile_id, url, name in tasks
        ],
        "platform_policy": platform_policy,
    }


def _platform_policy() -> dict[str, object]:
    from source_adapters.dem_platform.catalog import load_catalog, products_by_id
    from source_adapters.dem_platform.policy import evaluate_platform_mix

    products = products_by_id(load_catalog())
    return evaluate_platform_mix([products[CATALOG_SOURCE_ID]]).as_dict()
