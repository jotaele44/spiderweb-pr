#!/usr/bin/env python3
"""Record the geoid each 3DEP survey used, and test both surveys against D24's checkpoints.

PRVD02 is a leveled datum. A lidar survey reaches it from GNSS ellipsoidal heights
through a geoid model, and the 2018 and D24 surveys used different ones. This
script reads the surveys' own project-level records on USGS's prd-tnm bucket
(``StagedProducts/Elevation/metadata/``):

* 2018 (project PR_PuertoRico_VirginIslands_2018_D18, TNM blocks PR_PRVI_*_2018):
  the vendor FGDC metadata of the DEM and the classified point cloud, in each
  block's ``reports/vendor_provided_xml/``;
* D24 (project PR_PuertoRicoUSVI_D24, parts 1-6): the ``VERT_CS`` of each part's
  final LPC report.

It then samples both surveys' 1 m DEMs at USGS's D24 non-vegetated (NVA)
checkpoints. Those checkpoints were surveyed in 2024 on PRVD02 through GEOID18,
so the 2018 values are also moved to a GEOID18 basis (+ GEOID12B - GEOID18)
before they are compared. The checkpoints are D24's own QA points: they test
2018 independently, D24 only against its own control.

Nothing raster is stored: DEM tiles and the NGS geoid grids are read as
cloud-optimised GeoTIFF windows over HTTP. The receipt is written under
``evidence/dem_sources/3dep_vertical_realization_<date>/``.

    python scripts/check_3dep_vertical_realization.py                 # statements, checkpoints, receipt
    python scripts/check_3dep_vertical_realization.py --update-config # also write stated_geoid into the tile config
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "data_sources" / "elevation" / "lidar_comparison_tiles.json"
DEFAULT_RECEIPT = REPO_ROOT / "evidence" / "dem_sources" / "3dep_vertical_realization_2026-11-26"
BUCKET = "https://prd-tnm.s3.amazonaws.com"
METADATA = "StagedProducts/Elevation/metadata"
PROJECT_2018 = "PR_PuertoRico_VirginIslands_2018_D18"
PROJECT_D24 = "PR_PuertoRicoUSVI_D24"
VENDOR_XML_2018 = ("DEM_1.3v2_PR_USVI_Lidar_2018.xml", "ClassifiedPointCloud_1.3v2_PR_USVI_Lidar_2018.xml")
CHECKPOINTS_URL = f"{BUCKET}/{METADATA}/{PROJECT_D24}/vertical_accuracy/USGS/USGS_standard_PR_PuertoRicoUSVI_D24_PRVD02.gpkg"
CHECKPOINT_CRS = "EPSG:6566"  # NAD83(2011) / Puerto Rico and Virgin Is., metres
GEOID_GRIDS = {"GEOID12B": "https://cdn.proj.org/us_noaa_g2012bp0.tif", "GEOID18": "https://cdn.proj.org/us_noaa_g2018p0.tif"}
TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
USER_AGENT = "spiderweb-pr-3dep-vertical-realization/1.0"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"


# -- pure helpers (unit-tested) ---------------------------------------------------

_GEOID = re.compile(r"(?i)geoid\s*(\d{2})\s*([a-z])?(?![a-z])")


def normalize_geoid(text: str | None) -> str | None:
    """'Geoid 12B', 'NGS Geoid12B', 'Geoid18' -> 'GEOID12B', 'GEOID18'."""
    if not text:
        return None
    m = _GEOID.search(text)
    return f"GEOID{m.group(1)}{(m.group(2) or '').upper()}" if m else None


def datum_of(text: str | None) -> str | None:
    """The vertical datum a statement names, by its usual spellings."""
    if not text:
        return None
    t = text.upper()
    for key, names in (("PRVD02", ("PRVD02", "PRVD 02", "PUERTO RICO VERTICAL DATUM OF 2002")),
                       ("VIVD09", ("VIVD09", "VIVD 09", "VIRGIN ISLANDS VERTICAL DATUM OF 2009")),
                       ("NAVD88", ("NAVD88", "NAVD 88", "NORTH AMERICAN VERTICAL DATUM OF 1988"))):
        if any(n in t for n in names):
            return key
    return None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def fgdc_vertical(xml_text: str) -> dict:
    """The vertical statements of an FGDC record: altdatum, geoid element, abstract sentence.

    The geoid is the lidar extension's ``<ldrgeoid>`` (or a plain ``<geoid>``).
    """
    alt = re.search(r"<altdatum>([^<]+)</altdatum>", xml_text)
    geoid = re.search(r"<(?:ldr)?geoid>([^<]+)</(?:ldr)?geoid>", xml_text)
    sentence = re.search(r"vertical datum of [^,.<]+", xml_text, re.I)
    return {
        "altdatum": _clean(alt.group(1)) if alt else None,
        "geoid_element": _clean(geoid.group(1)) if geoid else None,
        "datum_sentence": _clean(sentence.group(0)) if sentence else None,
    }


def lpc_vert_cs(report_text: str) -> str | None:
    """The VERT_CS name in a USGS LPC report, e.g. 'PRVD02 height - Geoid18 (Meters)'."""
    m = re.search(r'VERT_CS\["([^"]+)"', report_text)
    return m.group(1) if m else None


def bilinear(window: np.ndarray, frac_row: float, frac_col: float) -> float:
    """Bilinear value inside a 2 x 2 window of cell values."""
    a = window
    return float(a[0, 0] * (1 - frac_row) * (1 - frac_col) + a[0, 1] * (1 - frac_row) * frac_col
                 + a[1, 0] * frac_row * (1 - frac_col) + a[1, 1] * frac_row * frac_col)


def summarize(values) -> dict:
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype="float64")
    if v.size == 0:
        return {"samples": 0}
    return {
        "samples": int(v.size),
        "mean_m": round(float(v.mean()), 3),
        "median_m": round(float(np.median(v)), 3),
        "std_m": round(float(v.std(ddof=1)), 3) if v.size > 1 else None,
        "rmse_m": round(float(np.sqrt(np.mean(v ** 2))), 3),
        "min_m": round(float(v.min()), 3),
        "max_m": round(float(v.max()), 3),
    }


# -- I/O ---------------------------------------------------------------------------

def _ssl() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=CA_BUNDLE) if os.path.exists(CA_BUNDLE) else ssl.create_default_context()


def _request(url: str, method: str = "GET", attempts: int = 4):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            return urllib.request.urlopen(req, context=_ssl(), timeout=120)
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(3 * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def get(url: str) -> bytes:
    with _request(url) as r:
        return r.read()


def etag(url: str) -> str | None:
    with _request(url, method="HEAD") as r:
        return (r.headers.get("ETag") or "").strip('"') or None


def list_keys(prefix: str) -> list[str]:
    keys, token = [], None
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            q["continuation-token"] = token
        text = get(f"{BUCKET}/?{urllib.parse.urlencode(q)}").decode()
        keys += re.findall(r"<Key>([^<]+)</Key>", text)
        nxt = re.findall(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", text)
        if not nxt:
            return keys
        token = nxt[0]


def _gdal_env() -> None:
    if os.path.exists(CA_BUNDLE):
        os.environ.setdefault("CURL_CA_BUNDLE", CA_BUNDLE)
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "3")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")


def sample_raster(src, x: float, y: float) -> float | None:
    """Bilinear value of a single-band raster at (x, y) in its own CRS, or None outside/nodata."""
    from rasterio.windows import Window

    b = src.bounds
    if not (b.left <= x <= b.right and b.bottom <= y <= b.top):
        return None
    r, c = src.index(x, y, op=float)
    r0, c0 = int(np.floor(r - 0.5)), int(np.floor(c - 0.5))
    a = src.read(1, window=Window(c0, r0, 2, 2), boundless=True, fill_value=np.nan).astype("float64")
    if src.nodata is not None:
        a[a == src.nodata] = np.nan
    v = bilinear(a, r - 0.5 - r0, c - 0.5 - c0)
    return v if np.isfinite(v) else None


# -- statements ----------------------------------------------------------------------

def statements(config: dict) -> dict:
    projects_2018 = sorted({p["project"] for s in config["sites"] for p in s["lidar_2018"]})
    rows_2018 = []
    for project in projects_2018:
        files = []
        for name in VENDOR_XML_2018:
            url = f"{BUCKET}/{METADATA}/{PROJECT_2018}/{project}/reports/vendor_provided_xml/{name}"
            files.append({"url": url, "etag": etag(url), **fgdc_vertical(get(url).decode("utf-8", "replace"))})
        stated = [f[k] for f in files for k in ("altdatum", "geoid_element", "datum_sentence") if f[k]]
        rows_2018.append({
            "survey": "2018", "project": project, "files": files,
            "vertical_datums": sorted({d for d in map(datum_of, stated) if d}),
            "geoid_models": sorted({g for g in map(normalize_geoid, stated) if g}),
        })
    rows_d24 = []
    for key in sorted(list_keys(f"{METADATA}/{PROJECT_D24}/")):
        if not re.search(r"/PR_PuertoRicoUSVI_\d_D24/reports/USGS_PR_PuertoRicoUSVI_\d_D24_Final_LPC_Report\.txt$", key, re.I):
            continue
        url = f"{BUCKET}/{key}"
        vert = lpc_vert_cs(get(url).decode("utf-8", "replace"))
        rows_d24.append({
            "survey": "d24", "part": re.search(r"PR_PuertoRicoUSVI_(\d)_D24", key).group(0), "url": url, "etag": etag(url),
            "vert_cs": vert, "vertical_datums": [d for d in [datum_of(vert)] if d],
            "geoid_models": [g for g in [normalize_geoid(vert)] if g],
        })
    return {
        "generated": time.strftime("%Y-%m-%d"),
        "source": f"{BUCKET}/{METADATA}/",
        "surveys": {
            "2018": {"project": PROJECT_2018, "blocks": rows_2018,
                     "geoid_models": sorted({g for r in rows_2018 for g in r["geoid_models"]})},
            "d24": {"project": PROJECT_D24, "parts": rows_d24,
                    "geoid_models": sorted({g for r in rows_d24 for g in r["geoid_models"]})},
        },
    }


def update_config(config: dict, stated: dict) -> dict:
    """Write each lidar part's project-level datum and geoid into the tile config."""
    blocks = {b["project"]: b for b in stated["surveys"]["2018"]["blocks"]}
    pr_parts = [p for p in stated["surveys"]["d24"]["parts"] if "PRVD02" in p["vertical_datums"]]
    d24_geoids = sorted({g for p in pr_parts for g in p["geoid_models"]})
    if len(d24_geoids) != 1:
        raise RuntimeError(f"D24 Puerto Rico parts state {d24_geoids or 'no'} geoid models")
    for site in config["sites"]:
        for part in site["lidar_2018"]:
            block = blocks[part["project"]]
            dem = block["files"][0]
            if block["vertical_datums"] != ["PRVD02"] or len(block["geoid_models"]) != 1:
                raise RuntimeError(f"{part['project']}: datums {block['vertical_datums']}, geoids {block['geoid_models']}")
            part.update({"project_vertical_datum": "PRVD02", "stated_geoid": block["geoid_models"][0],
                         "project_datum_text": dem["datum_sentence"] or dem["altdatum"], "project_metadata_url": dem["url"]})
        site["lidar_d24"].update({
            "project_vertical_datum": "PRVD02", "stated_geoid": d24_geoids[0], "project_datum_text": pr_parts[0]["vert_cs"],
            "project_metadata_url": f"{BUCKET}/{METADATA}/{PROJECT_D24}/",
        })
    config["project_datum_source"] = (
        "Project-level records on prd-tnm, read " + stated["generated"] + ": 2018 vendor FGDC XML per block; "
        "D24 VERT_CS of each part's final LPC report (scripts/check_3dep_vertical_realization.py)")
    return config


# -- checkpoints ---------------------------------------------------------------------

def _tnm_tiles(lon: float, lat: float) -> tuple[list[str], list[str]]:
    q = urllib.parse.urlencode({"datasets": "Digital Elevation Model (DEM) 1 meter", "prodFormats": "GeoTIFF", "max": "50",
                                "bbox": f"{lon - 0.0003},{lat - 0.0003},{lon + 0.0003},{lat + 0.0003}"})
    items = json.loads(get(f"{TNM_API}?{q}")).get("items", [])
    urls = sorted({it["downloadURL"] for it in items if str(it.get("downloadURL", "")).endswith(".tif")})
    return [u for u in urls if "_PR_PRVI_" in u and u.endswith("_2018.tif")], [u for u in urls if PROJECT_D24 in u]


def _dem_value(urls: list[str], lon: float, lat: float) -> tuple[float | None, int]:
    import rasterio
    from pyproj import Transformer

    vals = []
    for u in urls:
        with rasterio.open("/vsicurl/" + u) as src:
            x, y = Transformer.from_crs("EPSG:6318", src.crs, always_xy=True).transform(lon, lat)
            v = sample_raster(src, x, y)
            if v is not None:
                vals.append(v)
    return (float(np.median(vals)) if vals else None), len(vals)


def checkpoints() -> dict:
    import rasterio
    from pyproj import Transformer

    _gdal_env()
    con = sqlite3.connect(":memory:")
    con.deserialize(get(CHECKPOINTS_URL))
    rows = con.execute("select unique_identifier, point_type, collection_date, source_easting, source_northing, "
                       "source_elevation, source_geoid from standard where point_type = 'NVA' order by unique_identifier").fetchall()
    to_ll = Transformer.from_crs(CHECKPOINT_CRS, "EPSG:6318", always_xy=True)
    grids = {k: rasterio.open("/vsicurl/" + u) for k, u in GEOID_GRIDS.items()}

    def one(row):
        pid, _, date, e, n, z, geoid = row
        lon, lat = to_ll.transform(e, n)
        u18, u24 = _tnm_tiles(lon, lat)
        h18, k18 = _dem_value(u18, lon, lat)
        h24, k24 = _dem_value(u24, lon, lat)
        n12 = sample_raster(grids["GEOID12B"], lon % 360, lat)
        n18 = sample_raster(grids["GEOID18"], lon % 360, lat)
        return {"id": pid, "collected": date[:10], "lon": round(lon, 6), "lat": round(lat, 6), "checkpoint_prvd02_m": z,
                "checkpoint_geoid": geoid, "dem_2018_m": None if h18 is None else round(h18, 3),
                "dem_d24_m": None if h24 is None else round(h24, 3), "tiles_2018": k18, "tiles_d24": k24,
                "geoid12b_minus_geoid18_m": None if None in (n12, n18) else round(n12 - n18, 4)}

    with ThreadPoolExecutor(6) as pool:
        points = list(pool.map(one, rows))
    both = [p for p in points if p["dem_2018_m"] is not None and p["dem_d24_m"] is not None and p["geoid12b_minus_geoid18_m"] is not None]
    on18 = {p["id"]: p["dem_2018_m"] + p["geoid12b_minus_geoid18_m"] for p in both}
    return {
        "generated": time.strftime("%Y-%m-%d"),
        "checkpoints": CHECKPOINTS_URL,
        "checkpoints_etag": etag(CHECKPOINTS_URL),
        "geoid_grids": GEOID_GRIDS,
        "note": ("NVA checkpoints surveyed for D24 in 2024 on PRVD02 through GEOID18. The 2018 DEM is on PRVD02 through "
                 "GEOID12B, so it is moved to a GEOID18 basis by adding GEOID12B - GEOID18 (same ellipsoidal height). "
                 "The checkpoints test 2018 independently and D24 only against its own QA points."),
        "summary": {
            "points": len(points), "points_with_both_surveys": len(both),
            "d24_minus_checkpoint": summarize(p["dem_d24_m"] - p["checkpoint_prvd02_m"] for p in both),
            "dem_2018_minus_checkpoint_as_published": summarize(p["dem_2018_m"] - p["checkpoint_prvd02_m"] for p in both),
            "dem_2018_minus_checkpoint_on_geoid18": summarize(on18[p["id"]] - p["checkpoint_prvd02_m"] for p in both),
            "d24_minus_2018_on_geoid18": summarize(p["dem_d24_m"] - on18[p["id"]] for p in both),
            "geoid12b_minus_geoid18": summarize(p["geoid12b_minus_geoid18_m"] for p in both),
        },
        "points": points,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--receipt-dir", default=str(DEFAULT_RECEIPT))
    p.add_argument("--update-config", action="store_true", help="write stated_geoid and the project datum into the tile config")
    p.add_argument("--skip-checkpoints", action="store_true")
    args = p.parse_args(argv)
    out = Path(args.receipt_dir)
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG_PATH.read_text())
    stated = statements(config)
    (out / "geoid_statements.json").write_text(json.dumps(stated, indent=2) + "\n")
    for survey, block in stated["surveys"].items():
        print(f"{survey}: geoid models {block['geoid_models']}", flush=True)
    if args.update_config:
        CONFIG_PATH.write_text(json.dumps(update_config(config, stated), indent=2, ensure_ascii=False) + "\n")
        print(f"tile config updated -> {CONFIG_PATH.relative_to(REPO_ROOT)}", flush=True)
    if not args.skip_checkpoints:
        result = checkpoints()
        (out / "checkpoints.json").write_text(json.dumps(result, indent=2) + "\n")
        for name, s in result["summary"].items():
            print(f"{name}: {s}", flush=True)
    print(f"receipt -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
