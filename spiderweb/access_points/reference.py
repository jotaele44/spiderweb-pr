"""Published reference datasets: held by hash, read only with a bound CRS.

A reference set is somebody else's map -- a sinkhole inventory, a lithology
map, a planning boundary.  It is useful in two ways and dangerous in one:

* as **labels** to compare a method with, or as **context** (is this ground
  mapped as karst?);
* but a file that reaches the repository as an export may have lost its
  coordinate reference system on the way.  Coordinates in projected metres
  read as longitude and latitude put everything in the wrong ocean, silently.

So a reference set is declared in ``configs/access_point_reference_sets.yaml``
with the SHA-256 of its exact bytes, the CRS **bound** to it and *where that
binding was read*, and the publisher's own statement of positional accuracy.
The loader refuses a file whose bytes differ from the declaration, refuses
coordinates that cannot belong to the bound CRS, and for a shapefile refuses a
projection file that names a different system.

A reference set is a published interpretation.  It is registered as a held,
hashed source, and it is never a direct measurement.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

import yaml
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from gebco.marine_evidence import CoverageState, ProductStage

from .models import HORIZONTAL_INTERCHANGE_CRS, SourceManifestation
from .namespaces import source_id
from .vocabulary import ProvenanceState

REFERENCE_VERSION = "access_point_reference_sets_v1"
REFERENCE_PATH = "configs/access_point_reference_sets.yaml"
_GEOGRAPHIC = frozenset({"OGC:CRS84", "EPSG:4326", "EPSG:4269"})


class ReferenceSetError(ValueError):
    """A reference set is not usable as declared."""


class ReferenceRole(StrEnum):
    LABELS = "LABELS"  # individual mapped features to compare detections with
    CONTEXT_AREA = "CONTEXT_AREA"  # areas with a stated property; not labels
    KARST_LIMIT = "KARST_LIMIT"  # the mapped extent of karst-prone ground
    LITHOLOGY = "LITHOLOGY"  # mapped rock units
    LINEAGE_ONLY = "LINEAGE_ONLY"  # a parent or pointer recorded by hash


class ReferenceFormat(StrEnum):
    GEOJSON = "geojson"
    SHAPEFILE_ZIP = "shapefile_zip"
    OPAQUE = "opaque"  # recorded by hash; never parsed


@dataclass(frozen=True, slots=True)
class ReferenceSet:
    set_id: str
    role: ReferenceRole
    format: ReferenceFormat
    sha256: str
    provider: str
    title: str
    held: bool
    path: str | None = None
    bound_crs: str | None = None
    crs_basis: str | None = None
    positional_offset_m: float | None = None
    positional_basis: str | None = None
    publisher_statement: str | None = None
    label_class: str | None = None
    stated_min_depth_m: float | None = None
    parent_sha256: str | None = None
    published: str | None = None
    received_utc: str | None = None
    note: str | None = None

    @property
    def readable(self) -> bool:
        return self.held and self.format is not ReferenceFormat.OPAQUE


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def load_sets(config_path: str | Path) -> dict[str, ReferenceSet]:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("version") != REFERENCE_VERSION:
        raise ReferenceSetError(f"{config_path}: unsupported reference-set file")
    out: dict[str, ReferenceSet] = {}
    for entry in data.get("sets") or []:
        set_id = _text(entry.get("set_id"))
        if not set_id or set_id in out:
            raise ReferenceSetError(f"reference set id missing or repeated: {set_id!r}")
        sha = _text(entry.get("sha256")) or ""
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ReferenceSetError(f"{set_id}: sha256 must be 64 lowercase hex digits")
        try:
            role = ReferenceRole(entry.get("role"))
            fmt = ReferenceFormat(entry.get("format"))
        except ValueError as exc:
            raise ReferenceSetError(f"{set_id}: unknown role or format") from exc
        held = bool(entry.get("held"))
        ref = ReferenceSet(
            set_id=set_id,
            role=role,
            format=fmt,
            sha256=sha,
            provider=_text(entry.get("provider")) or "",
            title=_text(entry.get("title")) or "",
            held=held,
            path=_text(entry.get("path")),
            bound_crs=_text(entry.get("bound_crs")),
            crs_basis=_text(entry.get("crs_basis")),
            positional_offset_m=entry.get("positional_offset_m"),
            positional_basis=_text(entry.get("positional_basis")),
            publisher_statement=_text(entry.get("publisher_statement")),
            label_class=_text(entry.get("label_class")),
            stated_min_depth_m=entry.get("stated_min_depth_m"),
            parent_sha256=_text(entry.get("parent_sha256")),
            published=_text(entry.get("published")),
            received_utc=_text(entry.get("received_utc")),
            note=_text(entry.get("note")),
        )
        if not ref.provider or not ref.title:
            raise ReferenceSetError(f"{set_id}: provider and title are required")
        if ref.held and not ref.received_utc:
            raise ReferenceSetError(
                f"{set_id}: a held set must say when its bytes were received"
            )
        if ref.readable:
            if not ref.path:
                raise ReferenceSetError(f"{set_id}: a held set must name its file")
            if not ref.bound_crs or not ref.crs_basis:
                raise ReferenceSetError(
                    f"{set_id}: a readable set must bind a CRS and say where the "
                    "binding was read"
                )
        if ref.role is ReferenceRole.LABELS:
            if not ref.label_class:
                raise ReferenceSetError(f"{set_id}: labels must name their class")
            if ref.positional_offset_m is None or not ref.positional_basis:
                raise ReferenceSetError(
                    f"{set_id}: labels must state the publisher's positional "
                    "accuracy and where it was read"
                )
            if ref.positional_offset_m < 0:
                raise ReferenceSetError(f"{set_id}: positional_offset_m is negative")
        out[set_id] = ref
    return out


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bytes(ref: ReferenceSet, repo_root: str | Path) -> bytes:
    if not ref.readable or ref.path is None:
        raise ReferenceSetError(
            f"{ref.set_id} is recorded by hash only and is not read"
        )
    relative = Path(ref.path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReferenceSetError(f"{ref.set_id}: path must stay inside the repository")
    data = (Path(repo_root) / relative).read_bytes()
    if sha256_bytes(data) != ref.sha256:
        raise ReferenceSetError(
            f"{ref.set_id}: the file's bytes do not match the declared hash"
        )
    return data


def _coordinates(geometry: BaseGeometry) -> tuple[float, float, float, float]:
    return geometry.bounds  # type: ignore[return-value]


def _check_extent(ref: ReferenceSet, bounds: tuple[float, float, float, float]) -> None:
    """Coordinates must be possible in the bound CRS."""

    looks_geographic = (
        -180.0 <= bounds[0] <= 180.0
        and -180.0 <= bounds[2] <= 180.0
        and -90.0 <= bounds[1] <= 90.0
        and -90.0 <= bounds[3] <= 90.0
    )
    bound_geographic = ref.bound_crs in _GEOGRAPHIC
    if bound_geographic and not looks_geographic:
        raise ReferenceSetError(
            f"{ref.set_id}: coordinates are not longitude and latitude, yet the set "
            f"is bound to {ref.bound_crs}"
        )
    if not bound_geographic and looks_geographic:
        raise ReferenceSetError(
            f"{ref.set_id}: coordinates look like longitude and latitude, yet the "
            f"set is bound to the projected system {ref.bound_crs}"
        )


@dataclass(frozen=True)
class ReferenceFeature:
    feature_id: str
    properties: Mapping[str, Any]
    geometry: BaseGeometry  # in the set's bound CRS
    repaired: bool


@dataclass(frozen=True)
class ReferenceLayer:
    ref: ReferenceSet
    features: tuple[ReferenceFeature, ...]
    read: int
    dropped_empty: int
    repaired: int
    file_declares_crs: bool

    def summary(self) -> dict[str, Any]:
        return {
            "set_id": self.ref.set_id,
            "role": self.ref.role.value,
            "sha256": self.ref.sha256,
            "bound_crs": self.ref.bound_crs,
            "crs_basis": self.ref.crs_basis,
            "file_declares_crs": self.file_declares_crs,
            "features_read": self.read,
            "features_usable": len(self.features),
            "dropped_empty": self.dropped_empty,
            "repaired_invalid": self.repaired,
            "positional_offset_m": self.ref.positional_offset_m,
            "positional_basis": self.ref.positional_basis,
            "publisher_statement": self.ref.publisher_statement,
        }


def _clean(geometry: BaseGeometry) -> tuple[BaseGeometry | None, bool]:
    if geometry.is_empty or geometry.area <= 0:
        return None, False
    if geometry.is_valid:
        return geometry, False
    fixed = geometry.buffer(0)
    if fixed.is_empty or fixed.area <= 0:
        return None, True
    return fixed, True


def _read_geojson(ref: ReferenceSet, data: bytes) -> ReferenceLayer:
    document = json.loads(data)
    if document.get("type") != "FeatureCollection":
        raise ReferenceSetError(f"{ref.set_id}: not a GeoJSON FeatureCollection")
    features: list[ReferenceFeature] = []
    dropped = repaired = 0
    raw = document.get("features") or []
    for index, feature in enumerate(raw):
        geometry_json = feature.get("geometry")
        if not geometry_json or geometry_json.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ReferenceSetError(f"{ref.set_id}: feature {index} is not a polygon")
        geometry, was_repaired = _clean(shape(geometry_json))
        if geometry is None:
            dropped += 1
            continue
        repaired += was_repaired
        properties = dict(feature.get("properties") or {})
        native = properties.get("OBJECTID", index + 1)
        features.append(
            ReferenceFeature(
                f"{ref.set_id}:{native}", properties, geometry, was_repaired
            )
        )
    ids = [f.feature_id for f in features]
    if len(ids) != len(set(ids)):
        raise ReferenceSetError(f"{ref.set_id}: feature identifiers are not unique")
    if features:
        boxes = [_coordinates(f.geometry) for f in features]
        _check_extent(
            ref,
            (
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            ),
        )
    return ReferenceLayer(
        ref,
        tuple(features),
        len(raw),
        dropped,
        repaired,
        document.get("crs") is not None,
    )


def _signed_area(ring: list[tuple[float, float]]) -> float:
    return 0.5 * sum(
        x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])
    )


def _read_shapefile_zip(ref: ReferenceSet, data: bytes) -> ReferenceLayer:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        shp_names = [n for n in names if n.lower().endswith(".shp")]
        prj_names = [n for n in names if n.lower().endswith(".prj")]
        if len(shp_names) != 1 or len(prj_names) != 1:
            raise ReferenceSetError(
                f"{ref.set_id}: the archive must hold exactly one .shp and one .prj"
            )
        shp = archive.read(shp_names[0])
        prj = archive.read(prj_names[0]).decode("latin-1")
    code = (ref.bound_crs or "").split(":")[-1]
    if f'"EPSG","{code}"' not in prj.replace(" ", ""):
        raise ReferenceSetError(
            f"{ref.set_id}: the projection file does not name {ref.bound_crs}"
        )
    if len(shp) < 100 or struct.unpack(">i", shp[0:4])[0] != 9994:
        raise ReferenceSetError(f"{ref.set_id}: not a shapefile")
    if struct.unpack("<i", shp[32:36])[0] != 5:
        raise ReferenceSetError(f"{ref.set_id}: only polygon shapefiles are read")
    features: list[ReferenceFeature] = []
    dropped = repaired = read = 0
    offset = 100
    while offset < len(shp):
        number, words = struct.unpack(">ii", shp[offset : offset + 8])
        body = shp[offset + 8 : offset + 8 + words * 2]
        offset += 8 + words * 2
        read += 1
        if struct.unpack("<i", body[0:4])[0] != 5:
            dropped += 1
            continue
        parts, count = struct.unpack("<ii", body[36:44])
        starts = list(struct.unpack(f"<{parts}i", body[44 : 44 + 4 * parts])) + [count]
        base = 44 + 4 * parts
        points = [
            struct.unpack("<2d", body[base + 16 * i : base + 16 * (i + 1)])
            for i in range(count)
        ]
        rings = [points[starts[i] : starts[i + 1]] for i in range(parts)]
        # Shapefile outer rings run clockwise (negative signed area).
        outers = [r for r in rings if _signed_area(r) < 0] or rings[:1]
        holes = [r for r in rings if r not in outers]
        polygons = []
        for outer in outers:
            shell = Polygon(outer)
            inside = [
                h for h in holes if shell.contains(Polygon(h).representative_point())
            ]
            polygons.append(Polygon(outer, inside))
        merged: BaseGeometry = (
            polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        )
        geometry, was_repaired = _clean(merged)
        if geometry is None:
            dropped += 1
            continue
        repaired += was_repaired
        features.append(
            ReferenceFeature(f"{ref.set_id}:{number}", {}, geometry, was_repaired)
        )
    if features:
        _check_extent(ref, _coordinates(features[0].geometry))
    return ReferenceLayer(ref, tuple(features), read, dropped, repaired, True)


def read_layer(ref: ReferenceSet, repo_root: str | Path) -> ReferenceLayer:
    """Read a held polygon set in its bound CRS, after checking its bytes."""

    data = _bytes(ref, repo_root)
    if ref.format is ReferenceFormat.GEOJSON:
        return _read_geojson(ref, data)
    if ref.format is ReferenceFormat.SHAPEFILE_ZIP:
        return _read_shapefile_zip(ref, data)
    raise ReferenceSetError(f"{ref.set_id}: format {ref.format.value} is not read")


def reproject(geometry: BaseGeometry, source_crs: str, target_crs: str) -> BaseGeometry:
    """A geometry in another CRS.  Uses the projection library rasterio ships."""

    if source_crs == target_crs:
        return geometry
    from rasterio.warp import transform as warp_transform  # noqa: PLC0415

    def convert(xs: Any, ys: Any, zs: Any = None) -> tuple[Any, Any]:
        out_x, out_y = warp_transform(source_crs, target_crs, list(xs), list(ys))
        return out_x, out_y

    return shapely_transform(convert, geometry)


def to_lonlat(point_xy: tuple[float, float], source_crs: str) -> tuple[float, float]:
    from rasterio.warp import transform as warp_transform  # noqa: PLC0415

    lon, lat = warp_transform(
        source_crs, HORIZONTAL_INTERCHANGE_CRS, [point_xy[0]], [point_xy[1]]
    )
    return round(float(lon[0]), 7), round(float(lat[0]), 7)


def equivalent_radius_m(geometry: BaseGeometry) -> float:
    return math.sqrt(geometry.area / math.pi)


def to_source(ref: ReferenceSet) -> SourceManifestation:
    """A held reference set as a registered source.  Never a direct measurement."""

    if not ref.held:
        raise ReferenceSetError(f"{ref.set_id} is not held and cannot be registered")
    return SourceManifestation(
        source_id=source_id(ref.provider, ref.set_id, None, ref.sha256),
        provider=ref.provider,
        title=ref.title,
        native_identifier=ref.set_id,
        manifestation_sha256=ref.sha256,
        retrieved_utc=ref.received_utc,
        published_date=ref.published,
        lineage_root_id=ref.set_id,
        product_stage=ProductStage.DERIVED_PRODUCT,
        sensor_type=None,
        coverage_state=CoverageState.GENERALIZED,
        provenance_state=ProvenanceState.REGISTERED,
        license_note=ref.note,
    )
