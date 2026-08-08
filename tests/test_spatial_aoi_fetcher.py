from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "spatial_aoi_fetcher.py"
spec = importlib.util.spec_from_file_location("spatial_aoi_fetcher", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _write_vrt(path: Path) -> None:
    path.write_text(
        """<VRTDataset rasterXSize=\"200\" rasterYSize=\"100\">\n"
        "<SRS>AUTHORITY[\"EPSG\",\"26920\"]</SRS>\n"
        "<GeoTransform>1000,1,0,2000,0,-1</GeoTransform>\n"
        "<VRTRasterBand dataType=\"Float32\" band=\"1\">\n"
        "<ComplexSource><SourceFilename relativeToVRT=\"1\">./tiles/a.tif</SourceFilename>"
        "<SourceProperties RasterXSize=\"100\" RasterYSize=\"100\" DataType=\"Float32\" BlockXSize=\"16\" BlockYSize=\"16\"/>"
        "<DstRect xOff=\"0\" yOff=\"0\" xSize=\"100\" ySize=\"100\"/></ComplexSource>\n"
        "<ComplexSource><SourceFilename relativeToVRT=\"1\">./tiles/b.tif</SourceFilename>"
        "<SourceProperties RasterXSize=\"100\" RasterYSize=\"100\" DataType=\"Float32\" BlockXSize=\"16\" BlockYSize=\"16\"/>"
        "<DstRect xOff=\"100\" yOff=\"0\" xSize=\"100\" ySize=\"100\"/></ComplexSource>\n"
        "</VRTRasterBand></VRTDataset>""",
        encoding="utf-8",
    )


def test_parse_vrt_catalog_and_native_aoi_selection(tmp_path: Path) -> None:
    vrt = tmp_path / "test.vrt"
    _write_vrt(vrt)
    catalog = mod.parse_vrt_catalog(vrt, dataset_id="demo")
    assert catalog["source_crs"] == "EPSG:26920"
    assert catalog["source_tile_count"] == 2
    assert catalog["tiles"][0].bbox_native == (1000.0, 1900.0, 1100.0, 2000.0)
    assert catalog["tiles"][1].bbox_native == (1100.0, 1900.0, 1200.0, 2000.0)

    plan = mod.plan_for_aoi(
        catalog,
        aoi_bbox=(1010.0, 1910.0, 1090.0, 1990.0),
        aoi_crs="EPSG:26920",
        cache_dir=tmp_path / "cache",
    )
    assert plan["required_tile_count"] == 1
    assert plan["tiles"][0]["tile_id"] == "a.tif"
    assert plan["cell_binding_status"] == "UNAVAILABLE_CANONICAL_GRID_UNGEOREFERENCED"


def test_overlapping_second_task_reuses_cached_bytes(tmp_path: Path, monkeypatch) -> None:
    vrt = tmp_path / "test.vrt"
    _write_vrt(vrt)
    catalog = mod.parse_vrt_catalog(vrt, dataset_id="demo")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "a.tif").write_bytes(b"not-empty")
    monkeypatch.setattr(mod, "rasterio", None)

    first = mod.plan_for_aoi(
        catalog,
        aoi_bbox=(1010.0, 1910.0, 1090.0, 1990.0),
        aoi_crs="EPSG:26920",
        cache_dir=cache,
    )
    second = mod.plan_for_aoi(
        catalog,
        aoi_bbox=(1020.0, 1920.0, 1080.0, 1980.0),
        aoi_crs="EPSG:26920",
        cache_dir=cache,
    )
    assert first["cached_valid_tile_count"] == 1
    assert second["cached_valid_tile_count"] == 1
    assert second["missing_tile_count"] == 0


def test_fetch_fails_closed_without_source_url(tmp_path: Path, monkeypatch) -> None:
    vrt = tmp_path / "test.vrt"
    _write_vrt(vrt)
    catalog = mod.parse_vrt_catalog(vrt, dataset_id="demo")
    monkeypatch.setattr(mod, "rasterio", None)
    plan = mod.plan_for_aoi(
        catalog,
        aoi_bbox=(1010.0, 1910.0, 1090.0, 1990.0),
        aoi_crs="EPSG:26920",
        cache_dir=tmp_path / "cache",
    )
    receipt = mod.fetch_plan(plan, tmp_path / "cache", require_complete=True)
    assert receipt["complete"] is False
    assert receipt["analysis_gate"] == "BLOCKED_INCOMPLETE_SOURCE_BYTES"
    assert receipt["results"][0]["reason"] == "UNRESOLVED_SOURCE_URL"
