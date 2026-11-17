"""Print both surveys' elevations in a 300 m window around a point.

Usage: python3 spot_check.py <workdir> <lat> <lon>
"""

import json
import os
import sys

import numpy as np
import rasterio
from rasterio.warp import transform as wt
from rasterio.windows import Window

S, lat, lon = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
items = json.load(open(f"{S}/island/tiles.json"))
ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CURL_CA_BUNDLE=os.environ.get("CURL_CA_BUNDLE", ""),
)
with rasterio.Env(**ENV):
    for i in items:
        b = i["boundingBox"]
        if not (b["minX"] < lon < b["maxX"] and b["minY"] < lat < b["maxY"]):
            continue
        with rasterio.open("/vsicurl/" + i["downloadURL"]) as ds:
            x, y = wt("EPSG:4326", ds.crs, [lon], [lat])
            r, c = ds.index(x[0], y[0])
            a = ds.read(1, window=Window(c - 150, r - 150, 300, 300)).astype(float)
            a[a == ds.nodata] = np.nan
            print(
                i["downloadURL"].split("/")[-1],
                "centre 40x40 m: min %.1f med %.1f max %.1f | "
                "ring (150 m out): med %.1f min %.1f max %.1f | nodata cells %d"
                % (
                    np.nanmin(a[130:170, 130:170]),
                    np.nanmedian(a[130:170, 130:170]),
                    np.nanmax(a[130:170, 130:170]),
                    np.nanmedian(np.r_[a[:20].ravel(), a[-20:].ravel()]),
                    np.nanmin(a),
                    np.nanmax(a),
                    int(np.isnan(a).sum()),
                ),
            )
            np.save(
                f"{S}/island/spot_{'D24' if 'D24' in i['downloadURL'] else '2018'}.npy",
                a,
            )
