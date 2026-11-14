"""NOAA Emergency Response Imagery (ERI) tile service.

The public bucket ``noaa-eri-pds`` publishes each flight as a folder of
GeoTIFFs in EPSG:4326 and no pre-rendered tile pyramid, so a web map cannot
point at it directly. This module renders 256 px Web-Mercator tiles on request
from the images that intersect the tile, and exposes the image footprints so
the map can show coverage and identify a single image.

Routes (all read-only):

    GET /imagery/eri/datasets
    GET /imagery/eri/{dataset_id}/footprints.geojson
    GET /imagery/eri/{dataset_id}/tiles/{z}/{x}/{y}.png

Boundaries that are deliberate:

* The registry (``configs/eri_imagery_sources.yaml``) is the allowlist. Only
  objects under ``{bucket_url}/{event}/{flight}/`` of a registered dataset are
  ever requested; nothing in a request can name a host or a key.
* Footprints come from the bucket's own key listing. File names encode the
  north-west corner of each image, and the registry supplies the cell size.
* Rendering needs ``rasterio`` (in the ``server`` extra). Without it the dataset and
  footprint routes still work and the tile route answers 503.
"""

from __future__ import annotations

import json
import logging
import math
import re
import struct
import threading
import zlib
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import yaml
from fastapi import APIRouter, HTTPException, Response

log = logging.getLogger("priis.backend.eri")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "configs" / "eri_imagery_sources.yaml"
CACHE_DIR = ROOT / "cache" / "eri_imagery"
BUCKET_URL = "https://noaa-eri-pds.s3.amazonaws.com"

TILE_SIZE = 256
# Hard ceiling on remote images composited into one tile. min_zoom in the
# registry keeps real requests well under it; this guards a bad registry edit.
MAX_IMAGES_PER_TILE = 24
TILE_CACHE_ENTRIES = 512
LIST_TIMEOUT_S = 30
_WEB_MERCATOR_HALF = 20037508.342789244
_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
# `...C0643345w174500n.tif` -> lon DDDMMSS west, lat DDMMSS north (NW corner).
_CELL_RE = re.compile(r"C(\d{3})(\d{2})(\d{2})w(\d{2})(\d{2})(\d{2})n\.tif$")


@dataclass(frozen=True)
class Dataset:
    id: str
    label: str
    event: str
    flight: str
    kind: str
    acquired: str
    cell_arcsec: float
    bbox: tuple[float, float, float, float]
    min_zoom: int
    max_zoom: int

    @property
    def prefix(self) -> str:
        return f"{self.event}/{self.flight}/"

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "event": self.event,
            "flight": self.flight,
            "kind": self.kind,
            "acquired": self.acquired,
            "bbox": list(self.bbox),
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom,
            "source_url": f"{BUCKET_URL}/index.html#{self.prefix}",
        }


@dataclass(frozen=True)
class Footprint:
    key: str
    size: int
    west: float
    south: float
    east: float
    north: float

    @property
    def url(self) -> str:
        return f"{BUCKET_URL}/{quote(self.key)}"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Read the registry; a missing or malformed file yields an empty registry."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        log.warning("ERI registry not found at %s", path)
        return {}
    except Exception as exc:  # noqa: BLE001 - never take the API offline
        log.warning("failed to load ERI registry %s (%s)", path, exc)
        return {}
    if document.get("bucket_url") != BUCKET_URL:
        log.warning("ERI registry bucket_url is not %s; registry ignored", BUCKET_URL)
        return {}
    return document


def datasets_from_registry(registry: dict[str, Any]) -> dict[str, Dataset]:
    out: dict[str, Dataset] = {}
    for raw in registry.get("datasets", []):
        dataset = Dataset(
            id=raw["id"],
            label=raw["label"],
            event=raw["event"],
            flight=raw["flight"],
            kind=raw["kind"],
            acquired=str(raw["acquired"]),
            cell_arcsec=float(raw["cell_arcsec"]),
            bbox=tuple(float(v) for v in raw["bbox"]),  # type: ignore[arg-type]
            min_zoom=int(raw["min_zoom"]),
            max_zoom=int(raw["max_zoom"]),
        )
        out[dataset.id] = dataset
    return out


# ─── Footprints ────────────────────────────────────────────────────────────────


def footprint_from_key(key: str, size: int, cell_arcsec: float) -> Footprint | None:
    """Decode an image key into its footprint, or None when it is not an image."""
    match = _CELL_RE.search(key)
    if match is None:
        return None
    lon_d, lon_m, lon_s, lat_d, lat_m, lat_s = (int(group) for group in match.groups())
    west = -(lon_d + lon_m / 60 + lon_s / 3600)
    north = lat_d + lat_m / 60 + lat_s / 3600
    cell = cell_arcsec / 3600
    return Footprint(
        key=key, size=size, west=west, south=north - cell, east=west + cell, north=north
    )


def _fetch_listing_page(prefix: str, token: str | None) -> bytes:
    params = {"list-type": "2", "prefix": prefix, "delimiter": "/"}
    if token:
        params["continuation-token"] = token
    request = Request(f"{BUCKET_URL}/?{urlencode(params)}", method="GET")
    with urlopen(
        request, timeout=LIST_TIMEOUT_S
    ) as response:  # noqa: S310 - fixed https host
        return response.read()


def list_footprints(
    dataset: Dataset,
    fetch_page: Callable[[str, str | None], bytes] = _fetch_listing_page,
) -> list[Footprint]:
    """List a flight folder and decode every image key in it."""
    footprints: list[Footprint] = []
    token: str | None = None
    while True:
        root = ElementTree.fromstring(
            fetch_page(dataset.prefix, token)
        )  # noqa: S314 - S3 XML
        for contents in root.iter(f"{_S3_NS}Contents"):
            key = contents.findtext(f"{_S3_NS}Key") or ""
            size = int(contents.findtext(f"{_S3_NS}Size") or 0)
            footprint = footprint_from_key(key, size, dataset.cell_arcsec)
            if footprint is not None:
                footprints.append(footprint)
        token = root.findtext(f"{_S3_NS}NextContinuationToken")
        if root.findtext(f"{_S3_NS}IsTruncated") != "true" or not token:
            break
    return footprints


class FootprintIndex:
    """Per-dataset footprints: memory first, then disk cache, then the bucket."""

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        lister: Callable[[Dataset], list[Footprint]] = list_footprints,
    ) -> None:
        self._cache_dir = cache_dir
        self._lister = lister
        self._memory: dict[str, list[Footprint]] = {}
        self._lock = threading.Lock()

    def get(self, dataset: Dataset) -> list[Footprint]:
        with self._lock:
            cached = self._memory.get(dataset.id)
            if cached is not None:
                return cached
            footprints = self._read_disk(dataset)
            if footprints is None:
                footprints = self._lister(dataset)
                self._write_disk(dataset, footprints)
            self._memory[dataset.id] = footprints
            return footprints

    def _path(self, dataset: Dataset) -> Path:
        return self._cache_dir / f"{dataset.id}.json"

    def _read_disk(self, dataset: Dataset) -> list[Footprint] | None:
        try:
            document = json.loads(self._path(dataset).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        # A registry edit to the folder or cell size invalidates the cache.
        if (
            document.get("prefix") != dataset.prefix
            or document.get("cell_arcsec") != dataset.cell_arcsec
        ):
            return None
        return [
            footprint
            for key, size in document.get("keys", [])
            if (footprint := footprint_from_key(key, size, dataset.cell_arcsec))
            is not None
        ]

    def _write_disk(self, dataset: Dataset, footprints: list[Footprint]) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._path(dataset).write_text(
                json.dumps(
                    {
                        "prefix": dataset.prefix,
                        "cell_arcsec": dataset.cell_arcsec,
                        "keys": [[f.key, f.size] for f in footprints],
                    }
                ),
                encoding="utf-8",
            )
        except OSError as exc:  # a read-only install must still serve
            log.warning("could not cache ERI footprints for %s (%s)", dataset.id, exc)


def footprints_geojson(
    dataset: Dataset, footprints: Iterable[Footprint]
) -> dict[str, Any]:
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [f.west, f.south],
                        [f.east, f.south],
                        [f.east, f.north],
                        [f.west, f.north],
                        [f.west, f.south],
                    ]
                ],
            },
            "properties": {
                "name": f.key.rsplit("/", 1)[-1],
                "dataset_id": dataset.id,
                "dataset_label": dataset.label,
                "acquired": dataset.acquired,
                "size_bytes": f.size,
                "url": f.url,
            },
        }
        for f in footprints
    ]
    return {"type": "FeatureCollection", "features": features}


# ─── Tile maths ────────────────────────────────────────────────────────────────


def tile_bounds_mercator(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """XYZ tile -> (west, south, east, north) in EPSG:3857 metres."""
    span = 2 * _WEB_MERCATOR_HALF / (1 << z)
    west = -_WEB_MERCATOR_HALF + x * span
    north = _WEB_MERCATOR_HALF - y * span
    return west, north - span, west + span, north


def tile_bounds_lonlat(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """XYZ tile -> (west, south, east, north) in EPSG:4326 degrees."""
    n = 1 << z

    def lat(row: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / n))))

    return x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y)


def footprints_for_tile(
    footprints: Iterable[Footprint], z: int, x: int, y: int
) -> list[Footprint]:
    west, south, east, north = tile_bounds_lonlat(z, x, y)
    return [
        f
        for f in footprints
        if f.east > west and f.west < east and f.north > south and f.south < north
    ]


# ─── Rendering ─────────────────────────────────────────────────────────────────


def encode_png_rgba(rgba: bytes, width: int, height: int) -> bytes:
    """Encode raw RGBA rows as a PNG (stdlib only)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    stride = width * 4
    raw = b"".join(
        b"\x00" + rgba[row * stride : (row + 1) * stride] for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


EMPTY_TILE = encode_png_rgba(bytes(TILE_SIZE * TILE_SIZE * 4), TILE_SIZE, TILE_SIZE)


# Range-read the remote GeoTIFFs: no directory probing, no sidecar lookups.
_GDAL_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": "2",
    "GDAL_HTTP_TIMEOUT": "20",
    "VSI_CACHE": "TRUE",
}


class RendererUnavailable(RuntimeError):
    """rasterio is not installed in this environment."""


def _read_image_tile(url: str, bounds: tuple[float, float, float, float]):
    """Warp one remote image onto the tile grid -> (4, 256, 256) uint8 RGBA."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT

    transform = from_bounds(*bounds, TILE_SIZE, TILE_SIZE)
    with rasterio.open(f"/vsicurl/{url}") as src:
        has_alpha = src.count >= 4
        with WarpedVRT(
            src,
            crs="EPSG:3857",
            transform=transform,
            width=TILE_SIZE,
            height=TILE_SIZE,
            resampling=Resampling.bilinear,
            add_alpha=not has_alpha,
        ) as vrt:
            if src.count >= 3:
                rgb = vrt.read(indexes=[1, 2, 3])
            else:
                rgb = np.repeat(vrt.read(indexes=[1]), 3, axis=0)
            alpha = (
                vrt.read(indexes=[4]) if has_alpha else vrt.dataset_mask()[None, ...]
            )
    out = np.concatenate([rgb, alpha]).astype("uint8", copy=False)
    return out


def render_tile(
    footprints: list[Footprint],
    z: int,
    x: int,
    y: int,
    read_image: Callable[[str, tuple[float, float, float, float]], Any] | None = None,
) -> bytes:
    """Composite the images under a tile into one RGBA PNG."""
    if not footprints:
        return EMPTY_TILE
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - numpy is a base dependency
        raise RendererUnavailable(str(exc)) from exc
    bounds = tile_bounds_mercator(z, x, y)
    if read_image is None:
        try:
            import rasterio
        except ImportError as exc:
            raise RendererUnavailable("rasterio is not installed") from exc

        def reader(url: str, tile_bounds: tuple[float, float, float, float]) -> Any:
            # GDAL configuration is thread-local, so each worker opens its own Env.
            with rasterio.Env(**_GDAL_OPTIONS):
                return _read_image_tile(url, tile_bounds)

    else:
        reader = read_image

    def load(footprint: Footprint):
        try:
            return reader(footprint.url, bounds)
        except Exception as exc:  # noqa: BLE001 - one bad image must not blank the tile
            log.warning("ERI image read failed for %s (%s)", footprint.key, exc)
            return None

    with ThreadPoolExecutor(max_workers=min(8, len(footprints))) as pool:
        layers = [layer for layer in pool.map(load, footprints) if layer is not None]
    if not layers:
        raise RuntimeError("no image under the tile could be read")

    canvas = np.zeros((4, TILE_SIZE, TILE_SIZE), dtype="uint8")
    for layer in layers:
        fill = (canvas[3] == 0) & (layer[3] > 0)
        if fill.any():
            canvas[:, fill] = layer[:, fill]
    if not canvas[3].any():
        return EMPTY_TILE
    return encode_png_rgba(np.moveaxis(canvas, 0, -1).tobytes(), TILE_SIZE, TILE_SIZE)


class TileCache:
    """Small thread-safe LRU of rendered tiles."""

    def __init__(self, capacity: int = TILE_CACHE_ENTRIES) -> None:
        self._capacity = capacity
        self._entries: OrderedDict[tuple[str, int, int, int], bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, int, int, int]) -> bytes | None:
        with self._lock:
            value = self._entries.get(key)
            if value is not None:
                self._entries.move_to_end(key)
            return value

    def put(self, key: tuple[str, int, int, int], value: bytes) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)


# ─── Router ────────────────────────────────────────────────────────────────────


def create_router(
    registry_path: Path = REGISTRY_PATH,
    index: FootprintIndex | None = None,
    render: Callable[[list[Footprint], int, int, int], bytes] = render_tile,
) -> APIRouter:
    registry = load_registry(registry_path)
    datasets = datasets_from_registry(registry)
    footprint_index = index or FootprintIndex()
    tile_cache = TileCache()
    router = APIRouter(prefix="/imagery/eri", tags=["imagery"])

    def dataset_or_404(dataset_id: str) -> Dataset:
        dataset = datasets.get(dataset_id)
        if dataset is None:
            raise HTTPException(404, f"unknown ERI dataset '{dataset_id}'")
        return dataset

    def footprints_or_502(dataset: Dataset) -> list[Footprint]:
        try:
            return footprint_index.get(dataset)
        except Exception as exc:  # noqa: BLE001 - upstream listing failure
            log.warning("ERI listing failed for %s (%s)", dataset.id, exc)
            raise HTTPException(502, "NOAA ERI bucket listing is unavailable") from exc

    @router.get("/datasets")
    def eri_datasets():
        """Registered ERI flights. Source: configs/eri_imagery_sources.yaml."""
        if not datasets:
            raise HTTPException(503, "ERI imagery registry unavailable")
        return {
            "attribution": registry.get("attribution", ""),
            "tile_size": TILE_SIZE,
            "datasets": [dataset.public() for dataset in datasets.values()],
        }

    @router.get("/{dataset_id}/footprints.geojson")
    def eri_footprints(dataset_id: str):
        """One polygon per image in the flight, with its name and source URL."""
        dataset = dataset_or_404(dataset_id)
        body = json.dumps(footprints_geojson(dataset, footprints_or_502(dataset)))
        return Response(
            body,
            media_type="application/geo+json",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @router.get("/{dataset_id}/tiles/{z}/{x}/{y}.png")
    def eri_tile(dataset_id: str, z: int, x: int, y: int):
        """A 256 px Web-Mercator tile composited from the images under it."""
        dataset = dataset_or_404(dataset_id)
        if not dataset.min_zoom <= z <= dataset.max_zoom:
            raise HTTPException(
                404,
                f"zoom {z} is outside {dataset.min_zoom}-{dataset.max_zoom}"
                " for this dataset",
            )
        if not (0 <= x < (1 << z) and 0 <= y < (1 << z)):
            raise HTTPException(404, "tile is outside the tile grid")
        headers = {"Cache-Control": "public, max-age=86400"}
        cache_key = (dataset.id, z, x, y)
        cached = tile_cache.get(cache_key)
        if cached is not None:
            return Response(cached, media_type="image/png", headers=headers)

        hits = footprints_for_tile(footprints_or_502(dataset), z, x, y)
        if len(hits) > MAX_IMAGES_PER_TILE:
            raise HTTPException(422, "tile covers too many source images; zoom in")
        try:
            png = render(hits, z, x, y)
        except RendererUnavailable as exc:
            raise HTTPException(
                503, "ERI tile rendering needs rasterio (install the 'server' extra)"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - upstream read failure
            # dataset.id is the registry's own value and z/x/y are validated
            # integers, so nothing request-controlled can add a line to the log.
            log.warning("ERI tile %s/%d/%d/%d failed (%s)", dataset.id, z, x, y, exc)
            raise HTTPException(502, "NOAA ERI imagery could not be read") from exc
        tile_cache.put(cache_key, png)
        return Response(png, media_type="image/png", headers=headers)

    return router


router = create_router()
