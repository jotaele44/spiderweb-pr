#!/usr/bin/env python3
"""Compare every gridded DEM in the platform catalog against 3DEP 1 m lidar.

Sites and tiles come from ``data_sources/elevation/lidar_comparison_tiles.json``.
For each site the 2018 lidar (the reference) and the 2024 D24 lidar are averaged
from their 1 m pixels onto each DEM's own grid, so every DEM is compared at its
own sample positions:

* SRTMGL1, NASADEM and COP30: 1 arc-second cells centred on whole arc-seconds;
* AW3D30: 1 arc-second cells with edges on whole arc-seconds (pixel-is-area);
* CUDEM 1/9" and 1/3": the CUDEM tile lattice;
* NCEI San Juan 2015 and the 2006-2007 regional DEMs: their own lat/lon grids.

Vertical datum. The lidar metadata says NAVD88, USGS's programme-wide wording;
NAVD88 is not defined in Puerto Rico and the heights are taken as PRVD02 (the
CUDEM comparison tests this). For DEMs on a global geoid the lidar is moved with
an explicit chain: PRVD02 -> NAD83(2011) ellipsoid (GEOID18), NAD83(2011) ->
ITRF2014 (Helmert, at the survey epoch), ITRF2014 taken as WGS 84, then the
EGM96 or EGM2008 geoid. PROJ's default NAD83(2011) -> WGS 84 step is a null
transform and is deliberately not used.

Each site is processed independently and saved under ``outputs/lidar_comparison``
(git-ignored); a re-run skips finished sites. Lidar tiles are downloaded to a
temporary file, hashed, used and deleted. Nothing raster is committed. The final
step writes the receipt under ``evidence/dem_sources/lidar_comparison_<date>/``.

    python scripts/run_dem_vs_3dep_lidar.py              # all sites, then the receipt
    python scripts/run_dem_vs_3dep_lidar.py --site el_yunque
    python scripts/run_dem_vs_3dep_lidar.py --receipt-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import ssl
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "data_sources" / "elevation" / "lidar_comparison_tiles.json"
NCEI_MANIFEST = REPO_ROOT / "data_sources" / "noaa" / "ncei_coastal_dems.yml"
WORK_DIR = REPO_ROOT / "outputs" / "lidar_comparison"
SRTM_CACHE = REPO_ROOT / "data" / "nasa_srtmgl1" / "cache"
OT_CACHE = REPO_ROOT / "data" / "opentopography" / "cache"
OT_AOI = "-67.95_17.85_-65.2_18.55"
CUDEM_LISTS = {
    "ncei_puerto_rico_cudem_ninth_9525": "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_ninth_Topobathy_PuertoRico_9525/urllist9525.txt",
    "ncei_puerto_rico_cudem_third_9524": "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_third_Topobathy_PuertoRico_9524/urllist9524.txt",
}
ARCSEC = 1.0 / 3600.0
MIN_VALID_FRACTION = 0.9
SLOPE_CLASSES = ((0.0, 5.0), (5.0, 15.0), (15.0, 30.0), (30.0, 90.0))
EARTH_RADIUS_M = 6371008.8
EPOCH = {"2018": 2018.79, "d24": 2024.6}  # mid-collection, decimal years
USER_AGENT = "spiderweb-pr-dem-lidar-comparison/1.0"


# -- pure helpers (unit-tested) ---------------------------------------------------

def point_grid(west: float, south: float, east: float, north: float, step: float = ARCSEC):
    """Cells centred on whole multiples of ``step`` whose centres fall inside the box.

    Returns ``(transform, width, height)`` with ``transform`` as a GDAL-style
    6-tuple ``(a, b, c, d, e, f)`` whose origin is the north-west cell corner.
    """
    c0 = math.ceil(round(west / step, 6))
    c1 = math.floor(round(east / step, 6))
    r_top = math.floor(round(north / step, 6))
    r_bot = math.ceil(round(south / step, 6))
    width, height = c1 - c0 + 1, r_top - r_bot + 1
    if width <= 0 or height <= 0:
        raise ValueError("box too small for one cell")
    return (step, 0.0, c0 * step - step / 2, 0.0, -step, r_top * step + step / 2), width, height


def area_grid(west: float, south: float, east: float, north: float, step: float = ARCSEC):
    """Cells whose edges sit on whole multiples of ``step``, wholly inside the box."""
    e0 = math.ceil(round(west / step, 6))
    e1 = math.floor(round(east / step, 6))
    n0 = math.floor(round(north / step, 6))
    s0 = math.ceil(round(south / step, 6))
    width, height = e1 - e0, n0 - s0
    if width <= 0 or height <= 0:
        raise ValueError("box too small for one cell")
    return (step, 0.0, e0 * step, 0.0, -step, n0 * step), width, height


def cell_centres(transform: Sequence[float], width: int, height: int):
    a, _, c, _, e, f = transform
    return c + a * (np.arange(width) + 0.5), f + e * (np.arange(height) + 0.5)


def summarize(diff: np.ndarray) -> dict:
    d = np.asarray(diff, dtype="float64")
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {"samples": 0}
    med = float(np.median(d))
    return {
        "samples": int(d.size),
        "mean_m": round(float(d.mean()), 3),
        "median_m": round(med, 3),
        "std_m": round(float(d.std()), 3),
        "nmad_m": round(1.4826 * float(np.median(np.abs(d - med))), 3),
        "rmse_m": round(float(np.sqrt(np.mean(d * d))), 3),
        "p95_abs_m": round(float(np.percentile(np.abs(d), 95)), 3),
        "within_1m_percent": round(100.0 * float((np.abs(d) <= 1.0).mean()), 2),
        "within_5m_percent": round(100.0 * float((np.abs(d) <= 5.0).mean()), 2),
    }


def slope_degrees(z: np.ndarray, lat_centres: np.ndarray, step_deg: float) -> np.ndarray:
    """Slope of a geographic grid, in degrees, from central differences in metres."""
    dy = EARTH_RADIUS_M * math.radians(step_deg)
    dx = dy * np.cos(np.radians(lat_centres))[:, None]
    gy, gx = np.gradient(z.astype("float64"))
    return np.degrees(np.arctan(np.hypot(gx / dx, gy / dy)))


def by_slope_class(diff: np.ndarray, slope: np.ndarray) -> dict:
    out = {}
    for lo, hi in SLOPE_CLASSES:
        m = (slope >= lo) & (slope < hi) & np.isfinite(diff)
        out[f"{lo:g}-{hi:g}"] = summarize(diff[m])
    return out


def chain_offset(lons, lats, *, to_nad83_ellipsoid: Callable, nad83_to_itrf: Callable,
                 to_geoid_height: Callable, epoch: float) -> np.ndarray:
    """Height that PRVD02 zero has on the target geoid, per point.

    The chain is a sum of shifts, so lidar_on_target = lidar_prvd02 + offset.
    """
    zeros = np.zeros_like(np.asarray(lons, dtype="float64"))
    h_nad83 = to_nad83_ellipsoid(lons, lats, zeros)
    h_itrf = nad83_to_itrf(lons, lats, h_nad83, epoch)
    return np.asarray(to_geoid_height(lons, lats, h_itrf), dtype="float64")


# -- datum chain (PROJ) ------------------------------------------------------------

def _pick(group_src: str, group_dst: str, must_contain: str):
    from pyproj.transformer import TransformerGroup

    group = TransformerGroup(group_src, group_dst, always_xy=True)
    for t in group.transformers:
        if must_contain in t.description and "ballpark" not in t.description:
            return t
    raise RuntimeError(f"no PROJ operation {group_src} -> {group_dst} containing {must_contain!r}: "
                       f"{[t.description for t in group.transformers]}; unavailable "
                       f"{[op.name for op in group.unavailable_operations]}")


def datum_chain():
    import pyproj

    pyproj.network.set_network_enabled(True)
    ca = "/root/.ccr/ca-bundle.crt"
    if os.path.exists(ca):
        pyproj.network.set_ca_bundle_path(ca)
    geoid18 = _pick("EPSG:6318+6641", "EPSG:6319", "NAD83(2011) to PRVD02 height (2)")
    helmert = _pick("EPSG:6319", "EPSG:7912", "ITRF2014 to NAD83(2011)")
    egm96 = _pick("EPSG:4979", "EPSG:4326+5773", "WGS 84 to EGM96 height (1)")
    egm08 = _pick("EPSG:4979", "EPSG:4326+3855", "WGS 84 to EGM2008 height (1)")
    ops = {
        "prvd02_to_nad83_ellipsoid": geoid18.description,
        "nad83_2011_to_itrf2014": helmert.description,
        "wgs84_to_egm96": egm96.description,
        "wgs84_to_egm2008": egm08.description,
        "itrf2014_as_wgs84": "ITRF2014 ellipsoidal heights are used as WGS 84 (G2139); the two agree at centimetre level",
    }

    def to_nad83(lons, lats, h):
        return geoid18.transform(lons, lats, h)[2]

    def to_itrf(lons, lats, h, epoch):
        t = np.full_like(np.asarray(lons, dtype="float64"), epoch)
        return helmert.transform(lons, lats, h, t)[2]

    def target(model):
        tr = egm96 if model == "EGM96" else egm08
        return lambda lons, lats, h: tr.transform(lons, lats, h)[2]

    def offset(lons, lats, model, epoch):
        lon2, lat2 = np.meshgrid(lons, lats)
        off = chain_offset(lon2.ravel(), lat2.ravel(), to_nad83_ellipsoid=to_nad83,
                           nad83_to_itrf=to_itrf, to_geoid_height=target(model), epoch=epoch)
        off = off.reshape(lat2.shape)
        if not np.isfinite(off).all():
            raise RuntimeError(f"datum chain to {model} returned non-finite values (missing grid?)")
        return off

    return offset, ops


# -- I/O helpers -------------------------------------------------------------------

def _ssl():
    ca = "/root/.ccr/ca-bundle.crt"
    return ssl.create_default_context(cafile=ca) if os.path.exists(ca) else ssl.create_default_context()


def download(url: str, dest: Path) -> dict:
    digest, size, t0 = hashlib.sha256(), 0, time.time()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, context=_ssl(), timeout=300) as r, dest.open("wb") as out:
        etag = (r.headers.get("ETag") or "").strip('"')
        while True:
            chunk = r.read(1 << 22)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return {"url": url, "bytes": size, "sha256": digest.hexdigest(), "etag": etag, "seconds": round(time.time() - t0, 1)}


def lidar_geographic_box(path: Path, margin_deg: float = 2 * ARCSEC):
    """Inner geographic (NAD83) box of a UTM lidar tile."""
    import rasterio
    from rasterio.warp import transform as warp_xy

    with rasterio.open(path) as src:
        b = src.bounds
        xs, ys = warp_xy(src.crs, "EPSG:4269", [b.left, b.right, b.right, b.left], [b.bottom, b.bottom, b.top, b.top])
    return (max(xs[0], xs[3]) + margin_deg, max(ys[0], ys[1]) + margin_deg,
            min(xs[1], xs[2]) - margin_deg, min(ys[2], ys[3]) - margin_deg)


def aggregate_lidar(paths: Iterable[Path], transform, width: int, height: int, crs: str = "EPSG:4269"):
    """Mean of valid 1 m lidar pixels per destination cell, and the valid fraction."""
    import rasterio
    from affine import Affine
    from rasterio.warp import Resampling, reproject

    dst_t = Affine(*transform)
    acc = np.zeros((height, width), "float64")
    wsum = np.zeros((height, width), "float64")
    for p in paths:
        with rasterio.open(p) as src:
            z = src.read(1)
            nod = src.nodata
            valid = (np.isfinite(z) & (z != nod)).astype("uint8") if nod is not None else np.isfinite(z).astype("uint8")
            mean = np.full((height, width), np.nan, "float32")
            reproject(z, mean, src_transform=src.transform, src_crs=src.crs, src_nodata=nod,
                      dst_transform=dst_t, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average, num_threads=4)
            frac = np.zeros((height, width), "float32")
            reproject(valid, frac, src_transform=src.transform, src_crs=src.crs,
                      dst_transform=dst_t, dst_crs=crs, resampling=Resampling.average, num_threads=4)
            del z, valid
        ok = np.isfinite(mean) & (frac > 0)
        acc[ok] += mean[ok] * frac[ok]
        wsum[ok] += frac[ok]
    out = np.full((height, width), np.nan)
    has = wsum > 0
    out[has] = acc[has] / wsum[has]
    return out, np.minimum(wsum, 1.0)


def sample_on_grid(path: Path, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Values of a regular raster at the given cell centres; they must coincide with its samples."""
    import rasterio

    with rasterio.open(path) as src:
        t = src.transform
        cx = (lons - (t.c + t.a / 2)) / t.a
        cy = (lats - (t.f + t.e / 2)) / t.e
        if np.abs(cx - np.rint(cx)).max() > 1e-3 or np.abs(cy - np.rint(cy)).max() > 1e-3:
            raise ValueError(f"{path.name}: grid does not coincide with the requested cell centres")
        cols, rows = np.rint(cx).astype(int), np.rint(cy).astype(int)
        r0, r1, c0, c1 = rows.min(), rows.max(), cols.min(), cols.max()
        win = src.read(1, window=((r0, r1 + 1), (c0, c1 + 1))).astype("float64")
        if src.nodata is not None:
            win[win == src.nodata] = np.nan
    return win[np.ix_(rows - r0, cols - c0)]


def srtm_on_grid(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    sys.path.insert(0, str(REPO_ROOT))
    from source_adapters.nasa_srtmgl1.hgt import VOID, read_hgt_zip

    out = np.full((lats.size, lons.size), np.nan)
    for tlat in range(int(math.floor(lats.min())), int(math.floor(lats.max())) + 1):
        for tlon in range(int(math.floor(lons.min())), int(math.floor(lons.max())) + 1):
            tid = f"{'N' if tlat >= 0 else 'S'}{abs(tlat):02d}{'E' if tlon >= 0 else 'W'}{abs(tlon):03d}"
            path = SRTM_CACHE / f"{tid}.SRTMGL1.hgt.zip"
            rows = np.where((lats >= tlat) & (lats <= tlat + 1))[0]
            cols = np.where((lons >= tlon) & (lons <= tlon + 1))[0]
            if not rows.size or not cols.size:
                continue
            h = read_hgt_zip(path).astype("float64")
            h[h == VOID] = np.nan
            tr = np.rint((tlat + 1 - lats[rows]) * 3600).astype(int)
            tc = np.rint((lons[cols] - tlon) * 3600).astype(int)
            out[np.ix_(rows, cols)] = h[np.ix_(tr, tc)]
    return out


def cudem_window(list_url: str, box):
    """Mosaic of the CUDEM tiles covering ``box`` on their shared lattice, plus its transform."""
    import rasterio

    with urllib.request.urlopen(urllib.request.Request(list_url, headers={"User-Agent": USER_AGENT}), context=_ssl(), timeout=60) as r:
        urls = [u.strip() for u in r.read().decode().splitlines() if u.strip().endswith(".tif")]
    west, south, east, north = box
    picked = []
    for u in urls:
        name = u.rsplit("/", 1)[-1]
        parts = name.split("_")
        n = float(parts[1][1:].replace("x", "."))
        w = -float(parts[2][1:].replace("x", "."))
        if w < east and w + 0.25 > west and n > south and n - 0.25 < north:
            picked.append(u)
    if not picked:
        return None
    env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")
    with env:
        with rasterio.open(picked[0]) as ref:
            res = ref.res[0]
            t0 = ref.transform
            crs = ref.crs.to_string()
        # Snap the box to the shared lattice.
        c_w = math.floor(round((west - t0.c) / res, 6)); c_e = math.ceil(round((east - t0.c) / res, 6))
        r_n = math.floor(round((t0.f - north) / res, 6)); r_s = math.ceil(round((t0.f - south) / res, 6))
        width, height = c_e - c_w, r_s - r_n
        grid_t = (res, 0.0, t0.c + c_w * res, 0.0, -res, t0.f - r_n * res)
        mosaic = np.full((height, width), np.nan)
        for u in picked:
            with rasterio.open(u) as src:
                t = src.transform
                off_c = round((t.c - grid_t[2]) / res); off_r = round((grid_t[5] - t.f) / res)
                r0, c0 = max(0, -off_r), max(0, -off_c)
                r1, c1 = min(src.height, height - off_r), min(src.width, width - off_c)
                if r1 <= r0 or c1 <= c0:
                    continue
                data = src.read(1, window=((r0, r1), (c0, c1))).astype("float64")
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan
                dst = mosaic[r0 + off_r:r1 + off_r, c0 + off_c:c1 + off_c]
                fill = np.isnan(dst)
                dst[fill] = data[fill]
    return {"values": mosaic, "transform": grid_t, "width": width, "height": height, "crs": crs,
            "tiles": [u.rsplit("/", 1)[-1] for u in picked], "resolution_deg": res}


def open_opendap(opendap_url: str, attempts: int = 5, wait_s: float = 10.0):
    """Open an OPeNDAP dataset, retrying the THREDDS server's transient 503s with backoff."""
    import netCDF4

    for attempt in range(1, attempts + 1):
        try:
            return netCDF4.Dataset(opendap_url)
        except OSError as exc:
            if attempt == attempts:
                raise
            print(f"  {opendap_url.rsplit('/', 1)[-1]}: {exc.__class__.__name__}, retry {attempt}/{attempts - 1}", flush=True)
            time.sleep(wait_s * 2 ** (attempt - 1))


def ncei_extents(ncei: dict) -> dict:
    """Lon/lat extent of each NCEI regional DEM, read once from its axes and cached."""
    cache = WORK_DIR / "ncei_extents.json"
    known = json.loads(cache.read_text()) if cache.exists() else {}
    for key, meta in ncei.items():
        if key in known:
            continue
        ds = open_opendap(meta["opendap_url"])
        try:
            lat = np.asarray(ds.variables["lat"][:], "float64")
            lon = np.asarray(ds.variables["lon"][:], "float64")
        finally:
            ds.close()
        known[key] = [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(known, indent=2) + "\n")
    return known


def overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def ncei_window(opendap_url: str, box):
    """Window of an NCEI regional NetCDF DEM over OPeNDAP, north-up, with its transform."""
    ds = open_opendap(opendap_url)
    try:
        lat = np.asarray(ds.variables["lat"][:], "float64")
        lon = np.asarray(ds.variables["lon"][:], "float64")
        var = [v for v in ds.variables.values() if v.ndim == 2][0]
        west, south, east, north = box
        ci = np.where((lon >= west) & (lon <= east))[0]
        ri = np.where((lat >= south) & (lat <= north))[0]
        if ci.size < 3 or ri.size < 3:
            return None
        data = np.asarray(var[ri.min():ri.max() + 1, ci.min():ci.max() + 1], "float64")
        fill = getattr(var, "_FillValue", None)
        if fill is not None and np.isfinite(fill):
            data[data == fill] = np.nan
        lats = lat[ri.min():ri.max() + 1]
        lons = lon[ci.min():ci.max() + 1]
    finally:
        ds.close()
    if lats[0] < lats[-1]:
        data, lats = data[::-1], lats[::-1]
    res_x, res_y = float(np.median(np.diff(lons))), float(np.median(np.abs(np.diff(lats))))
    grid_t = (res_x, 0.0, lons[0] - res_x / 2, 0.0, -res_y, lats[0] + res_y / 2)
    return {"values": data, "transform": grid_t, "width": lons.size, "height": lats.size, "crs": "EPSG:4269",  # WGS 84 per NCEI; NAD83 used alike
            "resolution_deg": res_x}


# -- per-site processing -------------------------------------------------------------

def _compare(name, dem, lidar, frac, slope, extra=None):
    keep = (frac >= MIN_VALID_FRACTION) & np.isfinite(lidar) & np.isfinite(dem)
    diff = np.where(keep, dem - lidar, np.nan)
    result = {"overall": summarize(diff), "by_slope_class_deg": by_slope_class(diff, slope)}
    if extra:
        result.update(extra)
    return result, diff[keep].astype("float32"), slope[keep].astype("float32")


def process_site(site: dict, offset_fn, ncei: dict) -> dict:
    sid = site["site_id"]
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"lidar_{sid}_", dir=WORK_DIR))
    provenance, results, arrays = [], {}, {}
    try:
        paths = {"2018": [], "d24": []}
        for part in site["lidar_2018"]:
            dest = tmp / part["url"].rsplit("/", 1)[-1]
            provenance.append({"survey": "2018", "project": part["project"], **download(part["url"], dest)})
            paths["2018"].append(dest)
        dest = tmp / site["lidar_d24"]["url"].rsplit("/", 1)[-1]
        provenance.append({"survey": "d24", "project": "PR_PuertoRicoUSVI_D24", **download(site["lidar_d24"]["url"], dest)})
        paths["d24"].append(dest)

        boxes = [lidar_geographic_box(p) for p in paths["2018"]]
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        d24_box = lidar_geographic_box(paths["d24"][0])
        box = (max(box[0], d24_box[0]), max(box[1], d24_box[1]), min(box[2], d24_box[2]), min(box[3], d24_box[3]))

        # 1 arc-second point grid: SRTMGL1, NASADEM, COP30, and D24 - 2018.
        pt, pw, ph = point_grid(*box)
        lons, lats = cell_centres(pt, pw, ph)
        l18, f18 = aggregate_lidar(paths["2018"], pt, pw, ph)
        ld, fd = aggregate_lidar(paths["d24"], pt, pw, ph)
        slope = slope_degrees(l18, lats, ARCSEC)
        off96 = offset_fn(lons, lats, "EGM96", EPOCH["2018"])
        off08 = offset_fn(lons, lats, "EGM2008", EPOCH["2018"])
        dems = {
            "nasa_srtmgl1_v003": (srtm_on_grid(lons, lats), off96),
            "nasa_nasadem_hgt_v001": (sample_on_grid(OT_CACHE / f"NASADEM_{OT_AOI}.tif", lons, lats), off96),
            "copernicus_glo30_dem": (sample_on_grid(OT_CACHE / f"COP30_{OT_AOI}.tif", lons, lats), off08),
        }
        for name, (dem, off) in dems.items():
            results[name], arrays[f"{name}__diff"], arrays[f"{name}__slope"] = _compare(
                name, dem, l18 + off, f18, slope,
                {"grid": "1 arc-second, centres on whole arc-seconds", "lidar_datum_offset_mean_m": round(float(np.nanmean(off)), 3)})
        both = (f18 >= MIN_VALID_FRACTION) & (fd >= MIN_VALID_FRACTION)
        change = np.where(both, ld - l18, np.nan)
        results["lidar_d24_minus_2018_1arcsec"] = {
            "overall": summarize(change), "by_slope_class_deg": by_slope_class(change, slope),
            "cells_beyond_1m": int(np.sum(np.abs(change[np.isfinite(change)]) > 1.0)),
        }
        arrays["lidar_d24_minus_2018_1arcsec__diff"] = change[np.isfinite(change)].astype("float32")
        arrays["lidar_d24_minus_2018_1arcsec__slope"] = slope[np.isfinite(change)].astype("float32")
        # Summit check (central cordillera only).
        r = int(np.argmin(np.abs(lats - 18.172281))); c = int(np.argmin(np.abs(lons - -66.5916862)))
        point_check = {"lon": round(float(lons[c]), 6), "lat": round(float(lats[r]), 6),
                       "lidar_2018_prvd02_m": round(float(l18[r, c]), 2), "lidar_2018_egm96_m": round(float(l18[r, c] + off96[r, c]), 2),
                       "offset_prvd02_to_egm96_m": round(float(off96[r, c]), 3), "offset_prvd02_to_egm2008_m": round(float(off08[r, c]), 3),
                       **{f"{k}_m": (round(float(v[0][r, c]), 2) if np.isfinite(v[0][r, c]) else None) for k, v in dems.items()}}

        # AW3D30 on its own (pixel-is-area) grid.
        at, aw, ah = area_grid(*box)
        alons, alats = cell_centres(at, aw, ah)
        la, fa = aggregate_lidar(paths["2018"], at, aw, ah)
        aslope = slope_degrees(la, alats, ARCSEC)
        aoff = offset_fn(alons, alats, "EGM96", EPOCH["2018"])
        aw3d = sample_on_grid(OT_CACHE / f"AW3D30_{OT_AOI}.tif", alons, alats)
        results["jaxa_aw3d30"], arrays["jaxa_aw3d30__diff"], arrays["jaxa_aw3d30__slope"] = _compare(
            "jaxa_aw3d30", aw3d, la + aoff, fa, aslope,
            {"grid": "1 arc-second, edges on whole arc-seconds", "lidar_datum_offset_mean_m": round(float(np.nanmean(aoff)), 3)})

        # CUDEM 1/9" and 1/3" (PRVD02, no conversion); D24 - 2018 again at 1/9".
        for name, url in CUDEM_LISTS.items():
            win = cudem_window(url, box)
            if win is None:
                continue
            gl, gf = aggregate_lidar(paths["2018"], win["transform"], win["width"], win["height"])
            glons, glats = cell_centres(win["transform"], win["width"], win["height"])
            gslope = slope_degrees(gl, glats, win["resolution_deg"])
            results[name], arrays[f"{name}__diff"], arrays[f"{name}__slope"] = _compare(
                name, win["values"], gl, gf, gslope, {"grid": f"CUDEM lattice, {win['resolution_deg'] * 3600:.4f} arc-seconds", "tiles": win["tiles"]})
            if name.endswith("9525"):
                low = (gslope < 5.0)
                d = np.where((gf >= MIN_VALID_FRACTION) & low & np.isfinite(win["values"]), gl - win["values"], np.nan)
                results["datum_test_lidar_2018_minus_cudem_ninth_low_slope"] = summarize(d)
                gd, gfd = aggregate_lidar(paths["d24"], win["transform"], win["width"], win["height"])
                both9 = (gf >= MIN_VALID_FRACTION) & (gfd >= MIN_VALID_FRACTION)
                ch9 = np.where(both9, gd - gl, np.nan)
                results["lidar_d24_minus_2018_ninth_arcsec"] = {
                    "overall": summarize(ch9), "by_slope_class_deg": by_slope_class(ch9, gslope),
                    "cells_beyond_1m": int(np.sum(np.abs(ch9[np.isfinite(ch9)]) > 1.0)),
                }

        # NCEI regional DEMs covering the site.
        extents = ncei_extents(ncei)
        for key, meta in ncei.items():
            if not overlaps(extents[key], box):
                continue
            win = ncei_window(meta["opendap_url"], box)
            if win is None or not np.isfinite(win["values"]).any():
                continue
            gl, gf = aggregate_lidar(paths["2018"], win["transform"], win["width"], win["height"])
            _, glats = cell_centres(win["transform"], win["width"], win["height"])
            gslope = slope_degrees(gl, glats, win["resolution_deg"])
            source_id = "ncei_" + key
            results[source_id], arrays[f"{source_id}__diff"], arrays[f"{source_id}__slope"] = _compare(
                source_id, win["values"], gl, gf, gslope,
                {"grid": f"NCEI lat/lon grid, {win['resolution_deg'] * 3600:.4f} arc-seconds", "vertical_datum": meta["vertical_datum"],
                 "datum_note": "no conversion: PRVD02 against lidar PRVD02" if "Puerto Rico" in meta["vertical_datum"]
                 else "uncorrected: Mean High Water against lidar PRVD02; the median is the MHW offset plus any bias"})
    finally:
        for p in tmp.iterdir():
            p.unlink()
        tmp.rmdir()
    record = {"site_id": sid, "box_nad83": [round(v, 6) for v in box], "provenance": provenance, "results": results}
    if sid == "central_cordillera_cerro_de_punta":
        record["summit_check"] = point_check
    np.savez_compressed(WORK_DIR / f"{sid}.npz", **arrays)
    (WORK_DIR / f"{sid}.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


# -- receipt ---------------------------------------------------------------------------

def write_receipt(config: dict, ops: dict, out_dir: Path, offset_fn=None) -> dict:
    sites = [json.loads((WORK_DIR / f"{s['site_id']}.json").read_text()) for s in config["sites"]]
    names = sorted({k for s in sites for k in s["results"] if not k.startswith(("datum_test", "lidar_d24_minus_2018_ninth"))})
    overall = {}
    for name in names:
        diffs, slopes = [], []
        for s in config["sites"]:
            path = WORK_DIR / f"{s['site_id']}.npz"
            with np.load(path) as z:
                if f"{name}__diff" in z:
                    diffs.append(z[f"{name}__diff"]); slopes.append(z[f"{name}__slope"])
        if diffs:
            d, sl = np.concatenate(diffs), np.concatenate(slopes)
            overall[name] = {"overall": summarize(d), "by_slope_class_deg": by_slope_class(d, sl),
                             "sites": [s["site_id"] for s in sites if name in s["results"]]}
    datum_test = {s["site_id"]: s["results"].get("datum_test_lidar_2018_minus_cudem_ninth_low_slope") for s in sites}
    receipt = {
        "generated": time.strftime("%Y-%m-%d"),
        "method": {
            "reference": "3DEP 1 m lidar, 2018 collection (TNM projects PR_PRVI_A-H_2018), averaged from its 1 m pixels onto each DEM's own grid; cells need at least 90% valid lidar pixels",
            "difference": "DEM minus lidar, with the lidar moved to the DEM's vertical datum",
            "lidar_vertical_datum_assumed": "PRVD02 (tile metadata says NAVD88, USGS's programme wording; tested against CUDEM)",
            "lidar_horizontal": "NAD83(2011) geographic; DEM grids are WGS 84 / ITRF. The 1-2 m horizontal difference is under a tenth of a 30 m cell and is not corrected.",
            "datum_chain": ops,
            "epochs": EPOCH,
            "slope_classes_deg": [f"{lo:g}-{hi:g}" for lo, hi in SLOPE_CLASSES],
        },
        "overall": overall,
        "datum_test_lidar_2018_minus_cudem_ninth_low_slope": datum_test,
        "sites": [{"site_id": s["site_id"], "box_nad83": s["box_nad83"], "results": s["results"], **({"summit_check": s["summit_check"]} if "summit_check" in s else {})} for s in sites],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (out_dir / "tiles_provenance.json").write_text(json.dumps({s["site_id"]: s["provenance"] for s in sites}, indent=2) + "\n")
    if offset_fn is not None:
        (out_dir / "datum_chain.json").write_text(json.dumps(datum_chain_record(config, ops, offset_fn), indent=2) + "\n")
    return receipt


def datum_chain_record(config: dict, ops: dict, offset_fn) -> dict:
    """The PROJ operations, the epochs, and the PRVD02-to-geoid offset at each site centre."""
    rows = []
    for site in config["sites"]:
        lon, lat = site["centre_lon_lat"]
        row = {"site_id": site["site_id"], "lon": lon, "lat": lat}
        for survey, epoch in EPOCH.items():
            for model in ("EGM96", "EGM2008"):
                off = offset_fn(np.array([lon]), np.array([lat]), model, epoch)
                row[f"offset_prvd02_to_{model.lower()}_m_{survey}"] = round(float(off[0, 0]), 3)
        rows.append(row)
    return {
        "operations": ops,
        "epochs": EPOCH,
        "sign": "height on the geoid model = PRVD02 height + offset",
        "avoided": "PROJ's default NAD83(2011) to WGS 84 (1) is a null transform (0 m, stated accuracy 2 m)",
        "site_centres": rows,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--site", action="append", help="site_id to process (repeatable); default all")
    p.add_argument("--force", action="store_true", help="reprocess sites that already have results")
    p.add_argument("--receipt-only", action="store_true")
    p.add_argument("--receipt-dir", default=str(REPO_ROOT / "evidence" / "dem_sources" / "lidar_comparison_2026-11-24"))
    args = p.parse_args(argv)
    config = json.loads(CONFIG_PATH.read_text())
    offset_fn, ops = datum_chain()
    manifest = json.loads(NCEI_MANIFEST.read_text())
    ncei = {d["dataset_key"]: d for d in manifest["datasets"] if d.get("opendap_url")}
    if not args.receipt_only:
        for site in config["sites"]:
            if args.site and site["site_id"] not in args.site:
                continue
            if (WORK_DIR / f"{site['site_id']}.json").exists() and not args.force:
                print(f"{site['site_id']}: done earlier, skipping", flush=True)
                continue
            t0 = time.time()
            rec = process_site(site, offset_fn, ncei)
            print(f"{site['site_id']}: {len(rec['results'])} comparisons in {time.time() - t0:.0f}s", flush=True)
    missing = [s["site_id"] for s in config["sites"] if not (WORK_DIR / f"{s['site_id']}.json").exists()]
    if missing:
        print(f"not writing the receipt yet; sites missing: {', '.join(missing)}", flush=True)
        return 0
    write_receipt(config, ops, Path(args.receipt_dir), offset_fn)
    print(f"receipt -> {args.receipt_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
