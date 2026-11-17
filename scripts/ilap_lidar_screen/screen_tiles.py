"""Island-wide lidar change screen, one D24 tile per unit. See CRITERIA.md.

Usage: python3 screen_tiles.py <workdir> all | <tile id> [<tile id> ...]
"""

import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as wt
from scipy import ndimage as ndi

S = sys.argv[1]
OUT = os.path.join(S, "island", "tiles")
os.makedirs(OUT, exist_ok=True)
items = json.load(open(os.path.join(S, "island", "tiles.json")))
D24 = [i for i in items if "D24" in i["downloadURL"]]
OLD = [i for i in items if "D24" not in i["downloadURL"]]
ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CURL_CA_BUNDLE=os.environ.get("CURL_CA_BUNDLE", ""),
    GDAL_HTTP_MAX_RETRY="5",
    GDAL_HTTP_RETRY_DELAY="3",
)
F = 2  # decimation -> 2 m


def overlap(a, b, pad=0.0005):
    return not (
        a["maxX"] < b["minX"] - pad
        or a["minX"] > b["maxX"] + pad
        or a["maxY"] < b["minY"] - pad
        or a["minY"] > b["maxY"] + pad
    )


def tid(i):
    return re.search(r"(\d\d)_(x\d+y\d+)", i["downloadURL"]).group(0)


def run(i):
    name = tid(i)
    fn = os.path.join(OUT, name + ".json")
    if os.path.exists(fn):
        return name, "cached"
    t0 = time.time()
    try:
        with rasterio.Env(**ENV):
            with rasterio.open("/vsicurl/" + i["downloadURL"]) as ds:
                h, w = ds.height // F, ds.width // F
                b = ds.read(1, out_shape=(h, w), resampling=Resampling.average).astype(
                    "float32"
                )
                nd = ds.nodata
                tr = ds.transform * Affine.scale(ds.width / w, ds.height / h)
                crs = ds.crs
            if nd is not None:
                b[b == nd] = np.nan
            b[(b < -50) | (b > 1500)] = np.nan
            a = np.full((h, w), np.nan, "float32")
            srcs = [o for o in OLD if overlap(o["boundingBox"], i["boundingBox"])]
            for o in srcs:
                with rasterio.open("/vsicurl/" + o["downloadURL"]) as so:
                    with WarpedVRT(
                        so,
                        crs=crs,
                        transform=tr,
                        width=w,
                        height=h,
                        resampling=Resampling.bilinear,
                        src_nodata=so.nodata,
                        nodata=-9999.0,
                    ) as v:
                        x = v.read(1).astype("float32")
                x[(x <= -9998) | (x < -50) | (x > 1500)] = np.nan
                m = np.isnan(a) & ~np.isnan(x)
                a[m] = x[m]
        land = ~np.isnan(a) & ~np.isnan(b) & (a > 0.5) & (b > 0.5)
        rec = dict(
            tile=name,
            land_km2=round(float(land.sum()) * 4 / 1e6, 2),
            n_old=len(srcs),
            patches=[],
        )
        if land.sum() > 2500:
            az = np.where(land, a, np.nan)
            gy, gx = np.gradient(az, 2.0)
            slope = np.degrees(np.arctan(np.hypot(gx, gy)))
            d = b - a
            flat = land & (slope < 3)
            off = (
                float(np.nanmedian(d[flat]))
                if flat.sum() > 500
                else float(np.nanmedian(d[land]))
            )
            dz = np.where(land, d - off, 0.0)
            rec.update(
                offset=round(off, 3),
                flat_cells=int(flat.sum()),
                p05=round(float(np.percentile(dz[land], 5)), 2),
                p95=round(float(np.percentile(dz[land], 95)), 2),
            )
            for sign, kind in ((1, "fill"), (-1, "cut")):
                m = ndi.binary_opening(land & (sign * dz > 1.0), iterations=1)
                lab, n = ndi.label(m)
                if not n:
                    continue
                idx = np.arange(1, n + 1)
                sz = np.asarray(ndi.sum(m, lab, idx))
                keep = idx[sz * 4 >= 500]
                if not len(keep):
                    continue
                vol = np.asarray(ndi.sum(dz, lab, keep)) * 4
                mx = np.asarray(ndi.maximum(sign * dz, lab, keep))
                sl = np.asarray(ndi.mean(np.nan_to_num(slope), lab, keep))
                el = np.asarray(ndi.mean(np.nan_to_num(a), lab, keep))
                cm = ndi.center_of_mass(m, lab, keep)
                xs = [tr * (c + 0.5, r + 0.5) for r, c in cm]
                lo, la = wt(crs, "EPSG:4326", [p[0] for p in xs], [p[1] for p in xs])
                for j in range(len(keep)):
                    rec["patches"].append(
                        dict(
                            kind=kind,
                            area_m2=int(sz[keep[j] - 1] * 4),
                            vol_m3=int(vol[j]),
                            max_m=round(float(mx[j]), 1),
                            slope=round(float(sl[j]), 1),
                            elev=round(float(el[j]), 1),
                            lat=round(la[j], 5),
                            lon=round(lo[j], 5),
                        )
                    )
            np.savez_compressed(
                os.path.join(OUT, name + "_dz.npz"),
                dz=np.clip(np.round(dz * 10), -32000, 32000).astype("int16"),
                tr=np.array(tr)[:6],
                crs=crs.to_string(),
            )
        rec["sec"] = round(time.time() - t0, 1)
        json.dump(rec, open(fn, "w"))
        return (
            name,
            f"ok {rec['land_km2']} km2 {len(rec['patches'])} patches {rec['sec']}s",
        )
    except Exception as e:
        return name, "ERR " + repr(e)[:200] + " " + traceback.format_exc()[
            -200:
        ].replace("\n", " ")


if __name__ == "__main__":
    sel = D24
    if len(sys.argv) > 2 and sys.argv[2] != "all":
        sel = [i for i in D24 if tid(i) in sys.argv[2:]]
    with ThreadPoolExecutor(3) as ex:
        for name, msg in ex.map(run, sel):
            print(name, msg, flush=True)
