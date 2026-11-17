"""Water-level test for LARGE patches.

Share of a patch whose dz sits within 0.15 m of the patch median (hydro-flattened
surfaces). Also stores each patch's pixel bbox for review_sheets.py.
Usage: python3 flatness.py <workdir>
"""

import json
import sys

import numpy as np
from rasterio.transform import Affine
from rasterio.warp import transform as wt
from scipy import ndimage as ndi

S = sys.argv[1]
L = json.load(open(f"{S}/island/large.json"))
by = {}
for p in L:
    by.setdefault(p["tile"], []).append(p)
for t, ps in by.items():
    z = np.load(f"{S}/island/tiles/{t}_dz.npz")
    dz = z["dz"].astype("float32") / 10
    tr = Affine(*z["tr"])
    crs = str(z["crs"])
    xs, ys = wt("EPSG:4326", crs, [p["lon"] for p in ps], [p["lat"] for p in ps])
    for p, x, y in zip(ps, xs, ys):
        c, r = ~tr * (x, y)
        p["px"] = [float(r), float(c)]
    for sign, kind in ((1, "fill"), (-1, "cut")):
        q = [p for p in ps if p["kind"] == kind]
        if not q:
            continue
        m = ndi.binary_opening(sign * dz >= 1.0, iterations=1)
        lab, n = ndi.label(m)
        idx = np.arange(1, n + 1)
        sz = np.asarray(ndi.sum(m, lab, idx)) * 4
        big = idx[sz >= 400]
        cm = np.array(ndi.center_of_mass(m, lab, big))
        sl = ndi.find_objects(lab)
        for p in q:
            dd = np.hypot(cm[:, 0] - p["px"][0], cm[:, 1] - p["px"][1])
            ok = np.where(
                (dd < 40)
                & (np.abs(sz[big - 1] - p["area_m2"]) < 0.25 * p["area_m2"] + 400)
            )[0]
            if not len(ok):
                p["flat"] = None
                continue
            k = big[ok[np.argmin(dd[ok])]]
            s = sl[k - 1]
            v = dz[s][lab[s] == k]
            med = np.median(v)
            p["flat"] = round(float(np.mean(np.abs(v - med) <= 0.15)), 2)
            p["med"] = round(float(med), 2)
            p["bbox"] = [
                int(s[0].start),
                int(s[0].stop),
                int(s[1].start),
                int(s[1].stop),
            ]
json.dump(L, open(f"{S}/island/large.json", "w"))
r = [p for p in L if p["kind"] == "fill" and p["resid"]]
print("unmatched", sum(p.get("flat") is None for p in L), "of", len(L))
for p in sorted(r, key=lambda p: -p["vol_m3"]):
    print(
        p["tile"],
        p["lat"],
        p["lon"],
        p["vol_m3"],
        "flat",
        p.get("flat"),
        "med",
        p.get("med"),
        "slope",
        p["slope"],
        "S" if p["steep"] else "",
    )
