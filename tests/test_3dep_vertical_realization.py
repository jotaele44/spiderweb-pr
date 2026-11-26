"""3DEP geoid realizations: statement parsing, sampling helpers, and the receipt."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_3dep_vertical_realization.py"
RECEIPT = REPO_ROOT / "evidence" / "dem_sources" / "3dep_vertical_realization_2026-11-26"


def _load():
    spec = importlib.util.spec_from_file_location("check_3dep_vertical_realization", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()

# Statements as they appear in the surveys' own records.
VENDOR_XML = """<metadata><idinfo><descript><abstract>... a horizontal projection/datum of NAD83 (2011),
Puerto Rico and Virgin Islands, meters and vertical datum of PRVD02 (GEOID12B), meters. Lidar ...</abstract>
<lidar><ldrinfo><ldrgeoid>National Geodetic Survey (NGS) Geoid12B</ldrgeoid></ldrinfo></lidar></descript></idinfo>
<spref><vertdef><altsys><altdatum>Puerto Rico Vertical Datum of 2002, Geoid 12B</altdatum></altsys></vertdef></spref></metadata>"""
LPC_REPORT = 'COMPD_CS["NAD83(2011) / UTM zone 19N + PRVD02 height - Geoid18 (Meters)", VERT_CS["PRVD02 height - Geoid18 (Meters)", VERT_DATUM["Puerto Rico Vertical Datum of 2002",2005]]'


@pytest.mark.parametrize("text, geoid", [
    ("Puerto Rico Vertical Datum of 2002, Geoid 12B", "GEOID12B"),
    ("National Geodetic Survey (NGS) Geoid12B", "GEOID12B"),
    ("vertical datum of PRVD02 (GEOID12B)", "GEOID12B"),
    ("PRVD02 height - Geoid18 (Meters)", "GEOID18"),
    ("realized with the GEOID18 geoid model", "GEOID18"),
    ("referenced to the North American Vertical Datum of 1988 (NAVD88)", None),
    (None, None),
])
def test_normalize_geoid(text, geoid) -> None:
    assert mod.normalize_geoid(text) == geoid


@pytest.mark.parametrize("text, datum", [
    ("Puerto Rico Vertical Datum of 2002, Geoid 12B", "PRVD02"),
    ("PRVD02 height - Geoid18 (Meters)", "PRVD02"),
    ("VIVD09 height - Geoid18 (Meters)", "VIVD09"),
    ("referenced to the North American Vertical Datum of 1988 (NAVD88)", "NAVD88"),
    ("Mean High Water", None),
])
def test_datum_of(text, datum) -> None:
    assert mod.datum_of(text) == datum


def test_fgdc_vertical_reads_altdatum_lidar_geoid_and_sentence() -> None:
    v = mod.fgdc_vertical(VENDOR_XML)
    assert v == {
        "altdatum": "Puerto Rico Vertical Datum of 2002, Geoid 12B",
        "geoid_element": "National Geodetic Survey (NGS) Geoid12B",
        "datum_sentence": "vertical datum of PRVD02 (GEOID12B)",
    }


def test_lpc_vert_cs() -> None:
    assert mod.lpc_vert_cs(LPC_REPORT) == "PRVD02 height - Geoid18 (Meters)"
    assert mod.lpc_vert_cs("no crs here") is None


def test_bilinear_corners_and_centre() -> None:
    w = np.array([[0.0, 1.0], [2.0, 3.0]])
    assert mod.bilinear(w, 0.0, 0.0) == 0.0 and mod.bilinear(w, 1.0, 1.0) == 3.0
    assert mod.bilinear(w, 0.5, 0.5) == pytest.approx(1.5)


def test_summarize_skips_missing_values() -> None:
    s = mod.summarize([0.01, -0.01, 0.03, None, float("nan")])
    assert s["samples"] == 3 and s["median_m"] == 0.01 and s["mean_m"] == 0.01
    assert mod.summarize([]) == {"samples": 0}


def test_update_config_writes_each_parts_geoid() -> None:
    cfg = {"sites": [{"site_id": "s", "lidar_2018": [{"project": "PR_PRVI_F_2018"}], "lidar_d24": {"project": "PR_PuertoRicoUSVI_D24"}}]}
    stated = {"generated": "2026-11-26", "surveys": {
        "2018": {"blocks": [{"project": "PR_PRVI_F_2018", "vertical_datums": ["PRVD02"], "geoid_models": ["GEOID12B"],
                             "files": [{"url": "u", **mod.fgdc_vertical(VENDOR_XML)}]}]},
        "d24": {"parts": [{"part": "PR_PuertoRicoUSVI_1_D24", "vert_cs": "PRVD02 height - Geoid18 (Meters)",
                           "vertical_datums": ["PRVD02"], "geoid_models": ["GEOID18"]}]}}}
    out = mod.update_config(cfg, stated)
    part, d24 = out["sites"][0]["lidar_2018"][0], out["sites"][0]["lidar_d24"]
    assert (part["stated_geoid"], part["project_vertical_datum"]) == ("GEOID12B", "PRVD02")
    assert part["project_datum_text"] == "vertical datum of PRVD02 (GEOID12B)"
    assert (d24["stated_geoid"], d24["project_vertical_datum"]) == ("GEOID18", "PRVD02")


def test_update_config_refuses_a_block_with_two_geoids() -> None:
    cfg = {"sites": [{"site_id": "s", "lidar_2018": [{"project": "B"}], "lidar_d24": {"project": "D"}}]}
    stated = {"generated": "x", "surveys": {
        "2018": {"blocks": [{"project": "B", "vertical_datums": ["PRVD02"], "geoid_models": ["GEOID12B", "GEOID18"], "files": [{"url": "u", "datum_sentence": "s", "altdatum": "a"}]}]},
        "d24": {"parts": [{"vert_cs": "PRVD02 height - Geoid18 (Meters)", "vertical_datums": ["PRVD02"], "geoid_models": ["GEOID18"]}]}}}
    with pytest.raises(RuntimeError):
        mod.update_config(cfg, stated)


@pytest.fixture(scope="module")
def checkpoints() -> dict:
    return json.loads((RECEIPT / "checkpoints.json").read_text())


def test_checkpoint_summary_matches_its_points(checkpoints: dict) -> None:
    pts = [p for p in checkpoints["points"] if None not in (p["dem_2018_m"], p["dem_d24_m"], p["geoid12b_minus_geoid18_m"])]
    s = checkpoints["summary"]
    assert s["points_with_both_surveys"] == len(pts) > 50
    d24 = np.array([p["dem_d24_m"] - p["checkpoint_prvd02_m"] for p in pts])
    assert s["d24_minus_checkpoint"]["median_m"] == pytest.approx(float(np.median(d24)), abs=1e-3)
    on18 = np.array([p["dem_2018_m"] + p["geoid12b_minus_geoid18_m"] - p["checkpoint_prvd02_m"] for p in pts])
    assert s["dem_2018_minus_checkpoint_on_geoid18"]["median_m"] == pytest.approx(float(np.median(on18)), abs=1e-3)
    assert all(p["checkpoint_geoid"].upper() == "GEOID18" for p in checkpoints["points"])


def test_d24_meets_its_own_checkpoints(checkpoints: dict) -> None:
    # USGS reports NVA RMSEz 4.50 cm for D24 at these points.
    s = checkpoints["summary"]["d24_minus_checkpoint"]
    assert abs(s["median_m"]) < 0.02 and s["rmse_m"] < 0.08


def test_receipts_record_no_credentials(checkpoints: dict) -> None:
    text = json.dumps(checkpoints) + (RECEIPT / "geoid_statements.json").read_text()
    for marker in ("API_Key", "Authorization", "Signature", "X-Amz"):
        assert marker not in text
