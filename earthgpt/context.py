"""
EarthGPT iOS — Tile context metadata.

Stores per-tile contextual metadata (land/water, coast, etc.)
that seam and corridor stages can use for penalization.
"""

from typing import Optional


class TileContext:
    """Lightweight context record for a single tile."""

    __slots__ = ("x", "y", "zoom", "tile_type", "coast_weight", "water_weight")

    def __init__(
        self,
        x: int,
        y: int,
        zoom: int,
        tile_type: str = "land",
        coast_weight: float = 1.0,
        water_weight: float = 1.0,
    ) -> None:
        self.x = x
        self.y = y
        self.zoom = zoom
        self.tile_type = tile_type  # "land", "water", "coast"
        self.coast_weight = coast_weight
        self.water_weight = water_weight

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "zoom": self.zoom,
            "tile_type": self.tile_type,
            "coast_weight": self.coast_weight,
            "water_weight": self.water_weight,
        }

    @classmethod
    def from_row(cls, row: dict) -> "TileContext":
        return cls(
            x=int(row.get("x", 0)),
            y=int(row.get("y", 0)),
            zoom=int(row.get("zoom", 15)),
            tile_type=row.get("tile_type", "land"),
            coast_weight=float(row.get("coast_weight", 1.0)),
            water_weight=float(row.get("water_weight", 1.0)),
        )
