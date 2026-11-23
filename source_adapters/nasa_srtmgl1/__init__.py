"""NASA SRTMGL1 v003 source adapter (LP DAAC), with per-pixel source composition."""

from .registry import SrtmTile, load_manifest, load_tiles

__all__ = ["SrtmTile", "load_manifest", "load_tiles"]
