"""AOI intake, validation, and deterministic freezing for subsurface analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from shapely import force_2d
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


@dataclass(frozen=True)
class FrozenAOI:
    source_path: str
    source_format: str
    source_sha256: str
    source_size: int
    frozen_at_utc: str
    source_feature_count: int
    source_geometry_type: str
    source_has_z: bool
    analysis_geometry_type: str
    analysis_dimension_loss: tuple[str, ...]
    canonical_geojson: dict
    canonical_sha256: str
    kmz_member: str | None = None
    kmz_member_sha256: str | None = None

    @property
    def geometry(self):
        return shape(self.canonical_geojson)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonicalize_polygonal(geom):
    if geom.is_empty:
        raise ValueError("AOI geometry is empty")
    if not geom.is_valid:
        raise ValueError("AOI geometry is invalid; repair must be explicit upstream")
    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise ValueError(f"AOI must be Polygon or MultiPolygon, got {geom.geom_type}")

    geom2d = force_2d(geom)
    if isinstance(geom2d, Polygon):
        geom2d = orient(geom2d, sign=1.0)
    else:
        geom2d = MultiPolygon([orient(p, sign=1.0) for p in geom2d.geoms])
    normalized = geom2d.normalize()
    obj = mapping(normalized)
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return obj, _sha256(payload), bool(getattr(geom, "has_z", False))


def _extract_geojson(obj: dict):
    obj_type = obj.get("type")
    geometries = []
    feature_count = 0
    if obj_type == "FeatureCollection":
        for feature in obj.get("features", []):
            feature_count += 1
            geometry = feature.get("geometry")
            if geometry is not None:
                geometries.append(shape(geometry))
    elif obj_type == "Feature":
        feature_count = 1
        if obj.get("geometry") is not None:
            geometries.append(shape(obj["geometry"]))
    else:
        feature_count = 1
        geometries.append(shape(obj))

    polygonal = []
    for geom in geometries:
        if isinstance(geom, (Polygon, MultiPolygon)):
            polygonal.append(geom)
        elif isinstance(geom, GeometryCollection):
            polygonal.extend(
                g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))
            )
        else:
            raise ValueError(f"AOI contains non-polygonal geometry: {geom.geom_type}")
    if not polygonal:
        raise ValueError("AOI contains no polygonal geometry")
    return unary_union(polygonal), feature_count


def _coordinates(text: str) -> list[tuple[float, ...]]:
    coords = []
    for token in text.replace("\n", " ").replace("\t", " ").split():
        values = tuple(float(v) for v in token.split(",") if v != "")
        if len(values) < 2:
            raise ValueError("Malformed KML coordinate tuple")
        coords.append(values)
    if len(coords) < 4:
        raise ValueError("KML polygon ring has fewer than four coordinate tuples")
    return coords


def _parse_kml(data: bytes):
    root = ET.fromstring(data)
    polygons = []
    for poly in root.findall(".//{*}Polygon"):
        outer_node = poly.find("./{*}outerBoundaryIs/{*}LinearRing/{*}coordinates")
        if outer_node is None or not (outer_node.text or "").strip():
            raise ValueError("KML Polygon missing outerBoundaryIs coordinates")
        outer = _coordinates(outer_node.text or "")
        holes = []
        for inner in poly.findall("./{*}innerBoundaryIs/{*}LinearRing/{*}coordinates"):
            if (inner.text or "").strip():
                holes.append(_coordinates(inner.text or ""))
        polygons.append(Polygon(outer, holes))
    if not polygons:
        raise ValueError("KML contains no Polygon geometry")
    return unary_union(polygons), len(polygons)


def freeze_aoi(path: str | Path) -> FrozenAOI:
    """Load KML, KMZ, or GeoJSON, validate it, and freeze a canonical 2D AOI.

    Source bytes are hashed separately from canonical geometry. Z is preserved as a
    source fact but intentionally removed from the analysis geometry because AOI
    topological predicates are planar. The loss is declared in the receipt.
    """

    source = Path(path)
    raw = source.read_bytes()
    suffix = source.suffix.lower()
    kmz_member = None
    kmz_member_sha = None

    if suffix in {".geojson", ".json"}:
        geom, feature_count = _extract_geojson(json.loads(raw.decode("utf-8")))
        source_format = "GEOJSON"
    elif suffix == ".kml":
        geom, feature_count = _parse_kml(raw)
        source_format = "KML"
    elif suffix == ".kmz":
        with zipfile.ZipFile(source) as zf:
            names = sorted(n for n in zf.namelist() if n.lower().endswith(".kml"))
            if not names:
                raise ValueError("KMZ contains no KML member")
            kmz_member = "doc.kml" if "doc.kml" in names else names[0]
            kml = zf.read(kmz_member)
        kmz_member_sha = _sha256(kml)
        geom, feature_count = _parse_kml(kml)
        source_format = "KMZ"
    else:
        raise ValueError("AOI format must be .kml, .kmz, .geojson, or .json")

    canonical, canonical_sha, source_has_z = _canonicalize_polygonal(geom)
    return FrozenAOI(
        source_path=str(source),
        source_format=source_format,
        source_sha256=_sha256(raw),
        source_size=len(raw),
        frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        source_feature_count=feature_count,
        source_geometry_type=geom.geom_type,
        source_has_z=source_has_z,
        analysis_geometry_type=shape(canonical).geom_type,
        analysis_dimension_loss=("Z",) if source_has_z else (),
        canonical_geojson=canonical,
        canonical_sha256=canonical_sha,
        kmz_member=kmz_member,
        kmz_member_sha256=kmz_member_sha,
    )
