"""DEM vs 3DEP lidar comparison: grid helpers, statistics, datum chain, and the receipt."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_dem_vs_3dep_lidar.py"
CONFIG = REPO_ROOT / "data_sources" / "elevation" / "lidar_comparison_tiles.json"
RECEIPT = REPO_ROOT / "evidence" / "dem_sources" / "lidar_comparison_2026-11-24"
SPACEBORNE = ("nasa_srtmgl1_v003", "nasa_nasadem_hgt_v001", "copernicus_glo30_dem", "jaxa_aw3d30")


def _load():
    spec = importlib.util.spec_from_file_location("run_dem_vs_3dep_lidar", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()
ARCSEC = 1 / 3600


def test_point_grid_centres_sit_on_whole_arcseconds() -> None:
    t, w, h = mod.point_grid(-66.50043, 18.00021, -66.49957, 18.00101)
    lons, lats = mod.cell_centres(t, w, h)
    assert np.allclose(lons / ARCSEC, np.rint(lons / ARCSEC), atol=1e-6)
    assert np.allclose(lats / ARCSEC, np.rint(lats / ARCSEC), atol=1e-6)
    assert lons.min() >= -66.50043 and lons.max() <= -66.49957
    assert lats.min() >= 18.00021 and lats.max() <= 18.00101
    assert lats[0] > lats[-1]  # north first


def test_area_grid_edges_sit_on_whole_arcseconds() -> None:
    t, w, h = mod.area_grid(-66.50043, 18.00021, -66.49957, 18.00101)
    a, _, c, _, e, f = t
    assert c / ARCSEC == pytest.approx(round(c / ARCSEC), abs=1e-6)
    assert f / ARCSEC == pytest.approx(round(f / ARCSEC), abs=1e-6)
    lons, _ = mod.cell_centres(t, w, h)
    # Centres are half an arc-second off the whole-arc-second lines.
    frac = (lons / ARCSEC) % 1.0
    assert np.allclose(frac, 0.5, atol=1e-6)


def test_tiny_box_is_refused() -> None:
    with pytest.raises(ValueError):
        mod.area_grid(-66.5, 18.0, -66.5 + ARCSEC / 3, 18.0 + ARCSEC / 3)


def test_summarize_known_values() -> None:
    s = mod.summarize(np.array([-1.0, 0.0, 1.0, 2.0, np.nan]))
    assert s["samples"] == 4
    assert s["mean_m"] == 0.5 and s["median_m"] == 0.5
    assert s["rmse_m"] == pytest.approx(math.sqrt(1.5), abs=1e-3)
    assert s["within_1m_percent"] == 75.0 and s["within_5m_percent"] == 100.0
    assert mod.summarize(np.array([np.nan])) == {"samples": 0}


def test_slope_of_a_plane() -> None:
    step = ARCSEC
    lats = np.full(5, 18.0)
    dy = mod.EARTH_RADIUS_M * math.radians(step)
    z = np.arange(5, dtype=float)[:, None] * dy * np.ones((5, 5))  # rises 1 m per metre southward
    slope = mod.slope_degrees(z, lats, step)
    assert np.allclose(slope, 45.0, atol=1e-6)


def test_slope_classes_partition_the_samples() -> None:
    diff = np.arange(8, dtype=float)
    slope = np.array([0, 4, 5, 14, 15, 29, 30, 60], dtype=float)
    classes = mod.by_slope_class(diff, slope)
    assert [c["samples"] for c in classes.values()] == [2, 2, 2, 2]


def test_chain_offset_composes_the_three_shifts() -> None:
    seen = {}

    def to_nad83(lons, lats, h):
        return h - 38.75

    def to_itrf(lons, lats, h, epoch):
        seen["epoch"] = epoch
        return h - 1.88

    def to_geoid(lons, lats, h):
        return h + 41.84

    off = mod.chain_offset(np.array([-66.59]), np.array([18.17]), to_nad83_ellipsoid=to_nad83,
                           nad83_to_itrf=to_itrf, to_geoid_height=to_geoid, epoch=2018.79)
    assert off[0] == pytest.approx(1.21)
    assert seen["epoch"] == 2018.79


def test_config_sites_and_tiles() -> None:
    cfg = json.loads(CONFIG.read_text())
    assert len(cfg["sites"]) == 8
    for site in cfg["sites"]:
        assert site["lidar_2018"] and all("/PR_PRVI_" in p["url"] for p in site["lidar_2018"])
        assert "/PR_PuertoRicoUSVI_D24/" in site["lidar_d24"]["url"]
        assert site["tile"] in site["lidar_d24"]["url"]
        assert all(p["head"]["content_length"] == p["size_bytes"] for p in site["lidar_2018"])


@pytest.fixture(scope="module")
def receipt() -> dict:
    path = RECEIPT / "comparison.json"
    if not path.exists():
        pytest.skip("comparison receipt not written yet")
    return json.loads(path.read_text())


def test_receipt_covers_every_site_and_spaceborne_dem(receipt: dict) -> None:
    cfg = json.loads(CONFIG.read_text())
    assert [s["site_id"] for s in receipt["sites"]] == [s["site_id"] for s in cfg["sites"]]
    for name in SPACEBORNE + ("ncei_puerto_rico_cudem_ninth_9525", "lidar_d24_minus_2018_1arcsec"):
        assert name in receipt["overall"], name
    for site in receipt["sites"]:
        for name in SPACEBORNE:
            assert site["results"][name]["overall"]["samples"] > 0, (site["site_id"], name)


def test_receipt_overall_counts_close(receipt: dict) -> None:
    for name, block in receipt["overall"].items():
        per_site = sum(s["results"][name]["overall"].get("samples", 0) for s in receipt["sites"] if name in s["results"])
        assert block["overall"]["samples"] == per_site, name
        assert sum(c.get("samples", 0) for c in block["by_slope_class_deg"].values()) <= per_site


def test_datum_chain_offsets_are_plausible(receipt: dict) -> None:
    chain = json.loads((RECEIPT / "datum_chain.json").read_text())
    assert "PRVD02 height (2)" in chain["operations"]["prvd02_to_nad83_ellipsoid"]  # the GEOID18 grid operation
    for row in chain["site_centres"]:
        # PRVD02 is local mean sea level (San Juan tide gauge), which EGM2008 models to a few
        # decimetres, so its zero sits within a metre of EGM2008's. PROJ's null NAD83 to WGS 84
        # step would drop the ~1.9 m Helmert shift and put it near +2.2 m instead. EGM96 is
        # coarser over the island and is not bounded here.
        assert 0.0 < row["offset_prvd02_to_egm2008_m_2018"] < 1.0, row
        for model in ("egm96", "egm2008"):
            assert abs(row[f"offset_prvd02_to_{model}_m_2018"] - row[f"offset_prvd02_to_{model}_m_d24"]) < 0.1, row


def test_lidar_heights_behave_as_prvd02(receipt: dict) -> None:
    for site, test in receipt["datum_test_lidar_2018_minus_cudem_ninth_low_slope"].items():
        assert test and abs(test["median_m"]) <= 0.15, site


def test_receipt_records_no_credentials_or_signed_urls(receipt: dict) -> None:
    text = (RECEIPT / "tiles_provenance.json").read_text() + json.dumps(receipt)
    for marker in ("API_Key", "Authorization", "Signature", "X-Amz"):
        assert marker not in text
