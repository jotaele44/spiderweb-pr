"""NOAA ERI imagery tile service (server/backend/eri_imagery.py).

Everything here runs offline: the S3 listing is a canned XML page and image
reads are either stubbed or served from a GeoTIFF written to tmp_path.
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
yaml = pytest.importorskip("yaml")

from server.backend import eri_imagery as eri  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "configs" / "eri_imagery_sources.yaml"
SCHEMA = REPO / "schemas" / "eri_imagery_sources.schema.json"

LISTING_PAGE_1 = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>page-2</NextContinuationToken>
  <Contents><Key>2022_Pre_Event/CB2201a_OB_N_RGB/CB2201a_OB_NC0660700w182800n.tif</Key><Size>100</Size></Contents>
  <Contents><Key>2022_Pre_Event/CB2201a_OB_N_RGB/cogs_CB2201a_OB_N_RGB.vrt</Key><Size>5</Size></Contents>
</ListBucketResult>"""
LISTING_PAGE_2 = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <IsTruncated>false</IsTruncated>
  <Contents><Key>2022_Pre_Event/CB2201a_OB_N_RGB/CB2201a_OB_NC0660615w182800n.tif</Key><Size>200</Size></Contents>
  <Contents><Key>2022_Pre_Event/CB2201a_OB_N_RGB/tile_index_CB2201a_OB_N_RGB.shp</Key><Size>7</Size></Contents>
</ListBucketResult>"""


def _dataset(dataset_id: str = "pre_event_2022_cb2201a") -> eri.Dataset:
    return eri.datasets_from_registry(eri.load_registry(REGISTRY))[dataset_id]


def _fake_pages(prefix: str, token: str | None) -> bytes:
    assert prefix == "2022_Pre_Event/CB2201a_OB_N_RGB/"
    return (LISTING_PAGE_2 if token == "page-2" else LISTING_PAGE_1).encode()


def _png_size(png: bytes) -> tuple[int, int]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", png[16:24])


def _png_pixels(png: bytes) -> bytes:
    """Decode the single IDAT chunk written by encode_png_rgba (filter 0 rows)."""
    width, height = _png_size(png)
    idat_at = png.index(b"IDAT")
    length = struct.unpack(">I", png[idat_at - 4 : idat_at])[0]
    raw = zlib.decompress(png[idat_at + 4 : idat_at + 4 + length])
    stride = width * 4 + 1
    return b"".join(raw[row * stride + 1 : (row + 1) * stride] for row in range(height))


# ─── Registry ──────────────────────────────────────────────────────────────────


def test_registry_validates_against_schema():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(
        instance=yaml.safe_load(REGISTRY.read_text(encoding="utf-8")),
        schema=json.loads(SCHEMA.read_text(encoding="utf-8")),
    )


def test_registry_ids_are_unique_and_include_the_reference_flight():
    raw = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["datasets"]
    ids = [entry["id"] for entry in raw]
    assert len(ids) == len(set(ids))
    flights = {(entry["event"], entry["flight"]) for entry in raw}
    assert ("2022_Pre_Event", "CB2201a_OB_N_RGB") in flights


def test_registry_with_foreign_bucket_is_ignored(tmp_path):
    document = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    document["bucket_url"] = "https://example.com"
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    assert eri.load_registry(path) == {}


def test_missing_registry_is_empty(tmp_path):
    assert eri.load_registry(tmp_path / "absent.yaml") == {}


# ─── Footprints ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        "2022_Pre_Event/CB2201a_OB_N_RGB/CB2201a_OB_NC0643345w174500n.tif",
        "2024_Pre_Event/CB2401a_OB_N_RGB/CB2401a_OB_N_C0643345w174500n.tif",
        "2017_Hurricane_Maria/20170922a_RGB/20170922aC0643345w174500n.tif",
    ],
)
def test_footprint_decodes_the_north_west_corner(key):
    footprint = eri.footprint_from_key(key, 10, 45)
    assert footprint is not None
    assert footprint.west == pytest.approx(-(64 + 33 / 60 + 45 / 3600))
    assert footprint.north == pytest.approx(17.75)
    assert footprint.east - footprint.west == pytest.approx(0.0125)
    assert footprint.north - footprint.south == pytest.approx(0.0125)
    assert footprint.url == f"{eri.BUCKET_URL}/{key}"


@pytest.mark.parametrize(
    "key",
    [
        "2022_Pre_Event/CB2201a_OB_N_RGB/cogs_CB2201a_OB_N_RGB.vrt",
        "2022_Pre_Event/CB2201a_OB_N_RGB/tile_index_CB2201a_OB_N_RGB.shp",
        "2022_Pre_Event/CB2201a_OB_N_RGB/raw/044496_0331221338352_000_RGB2.jpg",
    ],
)
def test_non_image_keys_have_no_footprint(key):
    assert eri.footprint_from_key(key, 10, 45) is None


def test_listing_follows_continuation_and_keeps_only_images():
    footprints = eri.list_footprints(_dataset(), fetch_page=_fake_pages)
    assert [f.key.rsplit("/", 1)[-1] for f in footprints] == [
        "CB2201a_OB_NC0660700w182800n.tif",
        "CB2201a_OB_NC0660615w182800n.tif",
    ]
    assert [f.size for f in footprints] == [100, 200]


def test_footprint_index_lists_once_then_reads_the_disk_cache(tmp_path):
    calls = []

    def lister(dataset):
        calls.append(dataset.id)
        return eri.list_footprints(dataset, fetch_page=_fake_pages)

    dataset = _dataset()
    first = eri.FootprintIndex(cache_dir=tmp_path, lister=lister)
    assert len(first.get(dataset)) == 2
    assert len(first.get(dataset)) == 2
    assert calls == [dataset.id]

    def unreachable(_dataset):
        raise AssertionError("the disk cache should have been used")

    second = eri.FootprintIndex(cache_dir=tmp_path, lister=unreachable)
    assert [f.key for f in second.get(dataset)] == [f.key for f in first.get(dataset)]


def test_footprints_geojson_is_closed_polygons_with_source_links():
    dataset = _dataset()
    footprints = eri.list_footprints(dataset, fetch_page=_fake_pages)
    document = eri.footprints_geojson(dataset, footprints)
    assert document["type"] == "FeatureCollection"
    feature = document["features"][0]
    ring = feature["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert feature["properties"]["name"] == "CB2201a_OB_NC0660700w182800n.tif"
    assert feature["properties"]["url"].startswith(eri.BUCKET_URL + "/2022_Pre_Event/")
    assert feature["properties"]["dataset_id"] == dataset.id


# ─── Tile maths ────────────────────────────────────────────────────────────────


def test_tile_bounds_agree_between_projections():
    west, south, east, north = eri.tile_bounds_lonlat(0, 0, 0)
    assert (west, east) == (-180, 180)
    assert north == pytest.approx(85.0511, abs=1e-3) and south == pytest.approx(
        -85.0511, abs=1e-3
    )
    mercator = eri.tile_bounds_mercator(0, 0, 0)
    assert mercator == pytest.approx(
        (-20037508.34, -20037508.34, 20037508.34, 20037508.34)
    )
    # Old San Juan, zoom 16.
    west, south, east, north = eri.tile_bounds_lonlat(16, 20731, 29346)
    assert west < -66.1167 < east and south < 18.4655 < north


def test_only_footprints_under_the_tile_are_selected():
    footprints = eri.list_footprints(_dataset(), fetch_page=_fake_pages)
    # Zoom-16 tile inside the first image (W 66°07'00" N 18°28'00", 45" cell).
    hits = eri.footprints_for_tile(footprints, 16, 20731, 29346)
    assert [f.key.rsplit("/", 1)[-1] for f in hits] == [
        "CB2201a_OB_NC0660700w182800n.tif"
    ]
    assert eri.footprints_for_tile(footprints, 16, 0, 0) == []


# ─── Rendering ─────────────────────────────────────────────────────────────────


def test_png_encoder_round_trips_pixels():
    pixels = bytes(range(16))
    png = eri.encode_png_rgba(pixels, 2, 2)
    assert _png_size(png) == (2, 2)
    assert _png_pixels(png) == pixels


def test_no_footprints_renders_the_transparent_tile():
    assert eri.render_tile([], 16, 0, 0) == eri.EMPTY_TILE
    assert _png_size(eri.EMPTY_TILE) == (eri.TILE_SIZE, eri.TILE_SIZE)
    assert set(_png_pixels(eri.EMPTY_TILE)) == {0}


def test_composite_fills_gaps_and_survives_one_failed_image():
    np = pytest.importorskip("numpy")
    size = eri.TILE_SIZE
    footprints = [
        eri.Footprint(key=f"e/f/{name}.tif", size=1, west=0, south=0, east=1, north=1)
        for name in ("left", "broken", "all")
    ]

    def read(url, _bounds):
        layer = np.zeros((4, size, size), dtype="uint8")
        if url.endswith("left.tif"):
            layer[0, :, : size // 2] = 200
            layer[3, :, : size // 2] = 255
        elif url.endswith("broken.tif"):
            raise OSError("range request failed")
        else:
            layer[1] = 90
            layer[3] = 255
        return layer

    pixels = _png_pixels(eri.render_tile(footprints, 16, 0, 0, read_image=read))
    assert pixels[0:4] == bytes([200, 0, 0, 255])  # first image wins where it has data
    last = (size - 1) * 4
    assert pixels[last : last + 4] == bytes([0, 90, 0, 255])  # the gap is filled


def test_all_images_failing_is_an_error():
    footprint = eri.Footprint(key="e/f/x.tif", size=1, west=0, south=0, east=1, north=1)

    def read(_url, _bounds):
        raise OSError("down")

    with pytest.raises(RuntimeError):
        eri.render_tile([footprint], 16, 0, 0, read_image=read)


def test_real_geotiff_is_warped_onto_the_tile(tmp_path, monkeypatch):
    """End to end through rasterio with a local EPSG:4326 RGBA GeoTIFF."""
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_bounds

    z, x, y = 16, 20731, 29346
    west, south, east, north = eri.tile_bounds_lonlat(z, x, y)
    # Image covers the western half of the tile only.
    middle = (west + east) / 2
    path = tmp_path / "half.tif"
    data = np.zeros((4, 64, 64), dtype="uint8")
    data[0] = 250
    data[3] = 255
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=64,
        height=64,
        count=4,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_bounds(west, south, middle, north, 64, 64),
    ) as dst:
        dst.write(data)

    def read_local(_url, bounds):
        real_open = rasterio.open
        monkeypatch.setattr(rasterio, "open", lambda *_a, **_k: real_open(path))
        try:
            return eri._read_image_tile("https://unused.invalid/half.tif", bounds)
        finally:
            monkeypatch.setattr(rasterio, "open", real_open)

    footprint = eri.Footprint(
        key="e/f/half.tif", size=1, west=west, south=south, east=middle, north=north
    )
    pixels = _png_pixels(eri.render_tile([footprint], z, x, y, read_image=read_local))
    row = (eri.TILE_SIZE // 2) * eri.TILE_SIZE * 4
    left = pixels[row + 40 : row + 44]
    right = pixels[row + (eri.TILE_SIZE - 10) * 4 : row + (eri.TILE_SIZE - 10) * 4 + 4]
    assert left == bytes([250, 0, 0, 255])
    assert right == bytes([0, 0, 0, 0])


# ─── HTTP ──────────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    rendered = []

    def render(hits, z, x, y):
        rendered.append((len(hits), z, x, y))
        return eri.EMPTY_TILE

    index = eri.FootprintIndex(
        cache_dir=tmp_path,
        lister=lambda dataset: eri.list_footprints(dataset, fetch_page=_fake_pages),
    )
    app = FastAPI()
    app.include_router(eri.create_router(index=index, render=render))
    test_client = TestClient(app)
    test_client.rendered = rendered  # type: ignore[attr-defined]
    return test_client


def test_datasets_route_lists_the_registry(client):
    body = client.get("/imagery/eri/datasets").json()
    assert body["tile_size"] == 256
    assert "NOAA" in body["attribution"]
    entry = next(d for d in body["datasets"] if d["id"] == "pre_event_2022_cb2201a")
    assert entry["source_url"] == (
        "https://noaa-eri-pds.s3.amazonaws.com/index.html#2022_Pre_Event/CB2201a_OB_N_RGB/"
    )
    assert entry["min_zoom"] <= entry["max_zoom"]


def test_footprints_route_serves_geojson(client):
    response = client.get("/imagery/eri/pre_event_2022_cb2201a/footprints.geojson")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    assert len(response.json()["features"]) == 2


def test_tile_route_renders_once_then_serves_from_cache(client):
    url = "/imagery/eri/pre_event_2022_cb2201a/tiles/16/20731/29346.png"
    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert "max-age" in first.headers["cache-control"]
    assert client.get(url).content == first.content
    assert client.rendered == [(1, 16, 20731, 29346)]


@pytest.mark.parametrize(
    "path",
    [
        "/imagery/eri/not_a_dataset/tiles/16/20731/29346.png",
        "/imagery/eri/not_a_dataset/footprints.geojson",
        "/imagery/eri/pre_event_2022_cb2201a/tiles/9/161/229.png",  # below min_zoom
        "/imagery/eri/pre_event_2022_cb2201a/tiles/16/70000/29346.png",  # off the grid
    ],
)
def test_out_of_contract_requests_are_404(client, path):
    assert client.get(path).status_code == 404
    assert client.rendered == []


def test_missing_renderer_is_503(tmp_path):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    def render(*_args):
        raise eri.RendererUnavailable("rasterio is not installed")

    index = eri.FootprintIndex(
        cache_dir=tmp_path,
        lister=lambda dataset: eri.list_footprints(dataset, fetch_page=_fake_pages),
    )
    app = FastAPI()
    app.include_router(eri.create_router(index=index, render=render))
    response = TestClient(app).get(
        "/imagery/eri/pre_event_2022_cb2201a/tiles/16/20731/29346.png"
    )
    assert response.status_code == 503


def test_listing_failure_is_502(tmp_path):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    def lister(_dataset):
        raise OSError("bucket unreachable")

    app = FastAPI()
    app.include_router(
        eri.create_router(index=eri.FootprintIndex(cache_dir=tmp_path, lister=lister))
    )
    response = TestClient(app).get(
        "/imagery/eri/pre_event_2022_cb2201a/footprints.geojson"
    )
    assert response.status_code == 502


def test_backend_app_mounts_the_imagery_routes():
    import server.backend.main as backend

    # The OpenAPI document, not app.routes: recent FastAPI keeps an included
    # router as one nested entry instead of flattening its routes.
    paths = set(backend.app.openapi()["paths"])
    assert "/imagery/eri/datasets" in paths
    assert "/imagery/eri/{dataset_id}/tiles/{z}/{x}/{y}.png" in paths


def test_frozen_bundle_includes_the_registry():
    spec = (REPO / "desktop" / "pyinstaller.spec").read_text(encoding="utf-8")
    assert 'REPO_ROOT / "configs" / "eri_imagery_sources.yaml"' in spec
