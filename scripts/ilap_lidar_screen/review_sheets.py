"""Review sheets for residual fills: dz chip, 2024 hillshade, USGS imagery.

Usage: python3 review_sheets.py <workdir>  (writes island/rev/sheet_NN.png)
"""

import io
import json
import os
import re
import subprocess
import sys

import matplotlib
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform as wt
from rasterio.windows import from_bounds

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

S = sys.argv[1]
R = json.load(open(f"{S}/island/residuals.json"))
os.makedirs(f"{S}/island/rev", exist_ok=True)
items = {}

for i in json.load(open(f"{S}/island/tiles.json")):
    if "D24" in i["downloadURL"]:
        items[re.search(r"(\d\d)_(x\d+y\d+)", i["downloadURL"]).group(0)] = i[
            "downloadURL"
        ]
ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CURL_CA_BUNDLE=os.environ.get("CURL_CA_BUNDLE", ""),
    GDAL_HTTP_MAX_RETRY="4",
    GDAL_HTTP_RETRY_DELAY="2",
)
N = 4
for s0 in range(0, len(R), N):
    grp = R[s0 : s0 + N]
    fig, ax = plt.subplots(len(grp), 3, figsize=(15, 5 * len(grp)), squeeze=False)
    for k, p in enumerate(grp):
        z = np.load(f"{S}/island/tiles/{p['tile']}_dz.npz")
        dz = z["dz"].astype("float32") / 10
        tr = Affine(*z["tr"])
        crs = str(z["crs"])
        r0, r1, c0, c1 = p.get("bbox") or [
            int(p["px"][0]) - 60,
            int(p["px"][0]) + 60,
            int(p["px"][1]) - 60,
            int(p["px"][1]) + 60,
        ]
        half = max(r1 - r0, c1 - c0) // 2 + 100
        rc, cc = (r0 + r1) // 2, (c0 + c1) // 2
        r0, r1, c0, c1 = (
            max(rc - half, 0),
            min(rc + half, dz.shape[0]),
            max(cc - half, 0),
            min(cc + half, dz.shape[1]),
        )
        x0, y1 = tr * (c0, r0)
        x1, y0 = tr * (c1, r1)
        ax[k, 0].imshow(
            dz[r0:r1, c0:c1], cmap="RdBu_r", vmin=-6, vmax=6, extent=(x0, x1, y0, y1)
        )
        ax[k, 0].set_title(
            f"#{p['id']} {p['cls'][:5]} {p['lat']},{p['lon']} "
            f"vol {p['vol_m3'] / 1e3:.0f}k m3 max {p['max_m']} m "
            f"slope {p['slope']} | {(x1 - x0):.0f} m wide",
            fontsize=9,
        )
        try:
            with (
                rasterio.Env(**ENV),
                rasterio.open("/vsicurl/" + items[p["tile"]]) as ds,
            ):
                w = from_bounds(x0, y0, x1, y1, ds.transform)
                f = max(1, int((x1 - x0) / 900))
                e = ds.read(
                    1,
                    window=w,
                    out_shape=(int(w.height / f), int(w.width / f)),
                    resampling=Resampling.average,
                ).astype("float32")
            gy, gx = np.gradient(e, f)
            hs = (gx - gy) / np.sqrt(gx**2 + gy**2 + 1) / 1.414
            ax[k, 1].imshow(
                hs, cmap="gray", vmin=-0.6, vmax=0.6, extent=(x0, x1, y0, y1)
            )
            ax[k, 1].set_title("2024 lidar hillshade", fontsize=9)
        except Exception as ex:
            ax[k, 1].set_title("hs fail " + repr(ex)[:60], fontsize=7)
        try:
            lo, la = wt(crs, "EPSG:4326", [x0, x1], [y0, y1])
            url = f"https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export?bbox={lo[0]},{la[0]},{lo[1]},{la[1]}&bboxSR=4326&imageSR=4326&size=700,700&format=jpg&f=image"
            b = subprocess.run(
                ["curl", "-sS", "-m", "60", url], capture_output=True
            ).stdout
            ax[k, 2].imshow(Image.open(io.BytesIO(b)), extent=(x0, x1, y0, y1))
            ax[k, 2].set_title("USGS imagery (undated)", fontsize=9)
        except Exception as ex:
            ax[k, 2].set_title("img fail " + repr(ex)[:60], fontsize=7)
        for a in ax[k]:
            a.set_xticks([])
            a.set_yticks([])
    plt.tight_layout()
    fn = f"{S}/island/rev/sheet_{s0 // N + 1:02d}.png"
    plt.savefig(fn, dpi=70)
    plt.close()
    print(fn, flush=True)
