"""Credential-free unified land/coastal/ocean surface analysis engine.

The grid primitive preserves source manifestation and vertical semantics.  It
uses geodesic densification for WGS84 profiles and requires caller-supplied
metric computation CRS geometries for exact corridor topology.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Sequence

from .surface_analysis import MeasurementClass, SpatialState, SurfaceClass

EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True, slots=True)
class SurfaceManifestation:
    manifestation_id: str
    source_id: str
    source_family: str
    native_crs: str
    vertical_datum: str | None
    depth_sign_convention: str
    horizontal_resolution_m: float
    measurement_class: MeasurementClass
    byte_sha256: str
    processing_version: str

    def __post_init__(self) -> None:
        if not all((self.manifestation_id, self.source_id, self.source_family, self.native_crs, self.processing_version)):
            raise ValueError("manifestation identity fields must not be empty")
        if self.depth_sign_convention not in {"positive_up", "positive_down"}:
            raise ValueError("depth sign convention must be explicit")
        if self.horizontal_resolution_m <= 0 or not math.isfinite(self.horizontal_resolution_m):
            raise ValueError("horizontal resolution must be positive and finite")
        if len(self.byte_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.byte_sha256):
            raise ValueError("byte_sha256 must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class SurfaceSample:
    lon: float
    lat: float
    value_m: float | None
    surface_class: SurfaceClass | None
    slope_deg: float | None
    aspect_deg: float | None
    source_manifestation_id: str
    measurement_class: MeasurementClass
    vertical_datum: str | None
    spatial_state: SpatialState


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a); lon2, lat2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


class RegularSurfaceGrid:
    """Ascending WGS84 regular grid retaining native manifestation semantics."""

    def __init__(self, lons: Sequence[float], lats: Sequence[float], values: Sequence[Sequence[float | None]], manifestation: SurfaceManifestation, *, nodata_value: float | None = None):
        self.lons = tuple(float(v) for v in lons); self.lats = tuple(float(v) for v in lats)
        self.values = tuple(tuple(None if v is None else float(v) for v in row) for row in values)
        self.manifestation = manifestation; self.nodata_value = nodata_value
        if len(self.lons) < 2 or len(self.lats) < 2 or any(a >= b for a, b in zip(self.lons, self.lons[1:])) or any(a >= b for a, b in zip(self.lats, self.lats[1:])):
            raise ValueError("longitude and latitude axes must be strictly ascending with at least two cells")
        if len(self.values) != len(self.lats) or any(len(row) != len(self.lons) for row in self.values):
            raise ValueError("grid dimensions do not match coordinate axes")

    def _index(self, axis: Sequence[float], value: float) -> int | None:
        if value < axis[0] or value > axis[-1]: return None
        return min(range(len(axis)), key=lambda i: abs(axis[i] - value))

    def _value(self, iy: int, ix: int) -> float | None:
        value = self.values[iy][ix]
        if value is None or not math.isfinite(value) or (self.nodata_value is not None and value == self.nodata_value): return None
        return value

    @staticmethod
    def _surface_class(value: float) -> SurfaceClass:
        if value < -10: return SurfaceClass.OCEAN_DEPTH
        if value < 10: return SurfaceClass.COASTAL_TOPOBATHY
        return SurfaceClass.LAND_ELEVATION

    def sample_surface(self, lon: float, lat: float) -> SurfaceSample:
        ix, iy = self._index(self.lons, lon), self._index(self.lats, lat)
        common = dict(lon=float(lon), lat=float(lat), source_manifestation_id=self.manifestation.manifestation_id, measurement_class=self.manifestation.measurement_class, vertical_datum=self.manifestation.vertical_datum)
        if ix is None or iy is None:
            return SurfaceSample(value_m=None, surface_class=None, slope_deg=None, aspect_deg=None, spatial_state=SpatialState.OUTSIDE, **common)
        value = self._value(iy, ix)
        if value is None:
            return SurfaceSample(value_m=None, surface_class=None, slope_deg=None, aspect_deg=None, spatial_state=SpatialState.NULL_EMPTY, **common)
        slope = aspect = None
        if 0 < ix < len(self.lons)-1 and 0 < iy < len(self.lats)-1:
            west, east, south, north = self._value(iy, ix-1), self._value(iy, ix+1), self._value(iy-1, ix), self._value(iy+1, ix)
            if None not in (west, east, south, north):
                dx = _haversine_m((self.lons[ix-1], self.lats[iy]), (self.lons[ix+1], self.lats[iy]))
                dy = _haversine_m((self.lons[ix], self.lats[iy-1]), (self.lons[ix], self.lats[iy+1]))
                dzdx, dzdy = (east-west)/dx, (north-south)/dy
                slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
                aspect = (math.degrees(math.atan2(dzdx, dzdy)) + 360) % 360
        return SurfaceSample(value_m=value, surface_class=self._surface_class(value), slope_deg=slope, aspect_deg=aspect, spatial_state=SpatialState.FULLY_WITHIN, **common)

    def profile_surface(self, coordinates: Sequence[tuple[float, float]], *, interval_m: float) -> tuple[dict[str, Any], ...]:
        if len(coordinates) < 2 or interval_m <= 0: raise ValueError("profile needs at least two points and a positive interval")
        output: list[dict[str, Any]] = []; cumulative = 0.0
        for segment_index, (start, end) in enumerate(zip(coordinates, coordinates[1:])):
            length = _haversine_m(start, end); steps = max(1, math.ceil(length / interval_m))
            for step in range(steps + 1):
                if segment_index and step == 0: continue
                f = step / steps; point = (start[0] + (end[0]-start[0])*f, start[1] + (end[1]-start[1])*f)
                distance = cumulative + length * f; sample = self.sample_surface(*point)
                output.append({"distance_m": distance, "lon": point[0], "lat": point[1], "value_m": sample.value_m, "surface_class": sample.surface_class.value if sample.surface_class else None, "slope_deg": sample.slope_deg, "spatial_state": sample.spatial_state.value, "source_manifestation_id": sample.source_manifestation_id, "measurement_class": sample.measurement_class.value})
            cumulative += length
        return tuple(output)


def classify_topology(subject: Any, target: Any) -> dict[str, Any]:
    """Classify exact Shapely topology in an already-selected computation CRS."""
    if subject is None or target is None or subject.is_empty or target.is_empty:
        return {"spatial_state": SpatialState.NULL_EMPTY, "intersection_geometry": None, "overlap_length_m": None, "overlap_area_m2": None, "distance_m": None}
    intersection = subject.intersection(target)
    if subject.within(target): state = SpatialState.FULLY_WITHIN
    elif subject.touches(target): state = SpatialState.TOUCH_ONLY
    elif subject.intersects(target): state = SpatialState.PARTIAL
    else: state = SpatialState.OUTSIDE
    return {"spatial_state": state, "intersection_geometry": intersection, "overlap_length_m": float(intersection.length), "overlap_area_m2": float(intersection.area), "distance_m": float(subject.distance(target))}


def sensor_footprint_xy(origin_x: float, origin_y: float, *, altitude_m: float, azimuth_deg: float, depression_deg: float, horizontal_fov_deg: float) -> Any:
    """Construct a triangular planar footprint in a caller-declared metric CRS."""
    if altitude_m <= 0 or not 0 < depression_deg < 90 or not 0 < horizontal_fov_deg < 180:
        raise ValueError("altitude, depression and FOV must define a downward finite cone")
    from shapely.geometry import Polygon
    center_range = altitude_m / math.tan(math.radians(depression_deg))
    points = [(origin_x, origin_y)]
    for bearing in (azimuth_deg-horizontal_fov_deg/2, azimuth_deg+horizontal_fov_deg/2):
        angle = math.radians(90-bearing)
        points.append((origin_x+center_range*math.cos(angle), origin_y+center_range*math.sin(angle)))
    return Polygon(points)


def geometry_sha256(geometry: Any) -> str:
    """Hash canonical little-endian WKB; this is geometric-input identity only."""
    from shapely import to_wkb
    return hashlib.sha256(to_wkb(geometry, byte_order=1, include_srid=True)).hexdigest()
