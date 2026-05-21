"""
EarthGPT iOS — Tile context metadata.

Stores per-tile contextual metadata (land/water, coast, etc.)
that seam and corridor stages can use for penalization.
"""

from typing import Any, Dict, Optional


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

    @classmethod
    def from_flight_event(cls, flight_event_dict: Dict) -> "TileContext":
        """Construct TileContext from a flight_event schema dict."""
        import math
        lat = float(flight_event_dict.get("origin_lat", 18.44))
        lon = float(flight_event_dict.get("origin_lon", -66.0))
        zoom = int(flight_event_dict.get("zoom", 15))
        n = 2 ** zoom
        x = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        return cls(x=x, y=y, zoom=zoom)

    def to_schema_dict(self) -> Dict:
        """Return dict with standard tile context keys."""
        return {
            "tile_x": self.x,
            "tile_y": self.y,
            "zoom": self.zoom,
            "tile_type": self.tile_type,
            "coast_weight": self.coast_weight,
            "water_weight": self.water_weight,
        }


class Context:
    """General context object for flight/pipeline events."""

    def __init__(self) -> None:
        self.flight_id: str = ""
        self.callsign: str = ""
        self.timestamp: str = ""

    @classmethod
    def from_flight_event(cls, flight_event_dict: Dict) -> "Context":
        """Construct Context from a flight_event schema dict."""
        ctx = cls()
        ctx.flight_id = flight_event_dict.get("flight_id", "")
        ctx.callsign = flight_event_dict.get("callsign", "")
        ctx.timestamp = flight_event_dict.get("takeoff_time", "")
        return ctx

    def to_schema_dict(self) -> Dict:
        """Return dict matching flight_event.schema.json."""
        return {
            "flight_id": getattr(self, "flight_id", ""),
            "callsign": getattr(self, "callsign", ""),
            "takeoff_time": getattr(self, "timestamp", ""),
        }
