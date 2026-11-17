"""Merge tile results, dedupe across tile overlaps, apply CRITERIA.md tests 1-3.

Usage: python3 aggregate.py <workdir>  (reads island/tiles/*.json and island/ref/)
"""

import glob
import json
import math
import statistics as st
import sys
from collections import defaultdict

S = sys.argv[1]
P = []
land = 0
tiles = 0
noise = []
for f in sorted(glob.glob(f"{S}/island/tiles/*.json")):
    r = json.load(open(f))
    tiles += 1
    land += r["land_km2"]
    if "p05" in r:
        noise.append((r["p05"], r["p95"], r["offset"]))
    for p in r["patches"]:
        p["tile"] = r["tile"]
        P.append(p)
kx = 111.195 * math.cos(math.radians(18.2))
ky = 111.195


def d(a, b):
    return math.hypot((a["lat"] - b["lat"]) * ky, (a["lon"] - b["lon"]) * kx)


P.sort(key=lambda p: -abs(p["vol_m3"]))
# grid index for dedupe + neighbour search

G = defaultdict(list)
out = []
for p in P:
    k = (int(p["lat"] * 100), int(p["lon"] * 100))
    dup = False
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for q in G[(k[0] + i, k[1] + j)]:
                if (
                    q["kind"] == p["kind"]
                    and q["tile"] != p["tile"]
                    and d(p, q) < max(0.03, 0.0003 * q["area_m2"] ** 0.5)
                    and 0.5 < p["vol_m3"] / q["vol_m3"] < 2
                ):
                    dup = True
    if not dup:
        G[k].append(p)
        out.append(p)
P = out
echo = json.load(open(f"{S}/island/ref/echo_ref.json"))
mrds = json.load(open(f"{S}/island/ref/mrds_ref.json"))


def near(p, ref, r=0.5):
    best = None
    for q in ref:
        la = q.get("lat")
        lo = q.get("lon")
        if la is None:
            continue
        x = math.hypot((p["lat"] - float(la)) * ky, (p["lon"] - float(lo)) * kx)
        if x <= r and (best is None or x < best[0]):
            best = (round(x, 2), q.get("name"), q.get("cls") or q.get("dev"))
    return best


L = [p for p in P if abs(p["vol_m3"]) >= 20000]
cuts = [p for p in P if p["kind"] == "cut"]
for p in L:
    p["steep"] = p["slope"] > 25
    p["echo"] = near(p, echo)
    p["mrds"] = near(p, mrds)
    if p["kind"] == "fill":
        cv = -sum(
            c["vol_m3"]
            for c in cuts
            if abs(c["lat"] - p["lat"]) < 0.012 and d(c, p) <= 1.0
        )
        p["cut1km"] = cv
        p["bal"] = cv >= 0.5 * p["vol_m3"]
    p["resid"] = not (p["echo"] or p["mrds"] or p.get("bal"))
fills = [p for p in L if p["kind"] == "fill"]
print(
    "tiles",
    tiles,
    "land km2",
    round(land),
    "patches",
    len(P),
    "fill",
    sum(p["kind"] == "fill" for p in P),
    "cut",
    len(cuts),
)
print(
    "vol fill Mm3",
    round(sum(p["vol_m3"] for p in P if p["kind"] == "fill") / 1e6, 2),
    "cut",
    round(sum(p["vol_m3"] for p in cuts) / 1e6, 2),
)

print(
    "noise median p05/p95",
    st.median(n[0] for n in noise),
    st.median(n[1] for n in noise),
    "offset range",
    min(n[2] for n in noise),
    max(n[2] for n in noise),
)
print(
    "LARGE", len(L), "fills", len(fills), "steep fills", sum(p["steep"] for p in fills)
)
ns = [p for p in fills if not p["steep"]]
print(
    "non-steep LARGE fills",
    len(ns),
    "echo",
    sum(bool(p["echo"]) for p in ns),
    "mrds",
    sum(bool(p["mrds"]) for p in ns),
    "bal",
    sum(p["bal"] for p in ns),
    "resid",
    sum(p["resid"] for p in ns),
)
print(
    "steep resid",
    sum(p["resid"] for p in fills if p["steep"]),
    "LARGE cuts",
    len(L) - len(fills),
    "resid cuts",
    sum(p["resid"] for p in L if p["kind"] == "cut"),
)
json.dump(L, open(f"{S}/island/large.json", "w"))
json.dump(P, open(f"{S}/island/patches_all.json", "w"))
for p in sorted(
    [p for p in fills if p["resid"]], key=lambda p: (p["steep"], -p["vol_m3"])
):
    print(
        p["tile"],
        p["lat"],
        p["lon"],
        "vol",
        p["vol_m3"],
        "area",
        p["area_m2"],
        "max",
        p["max_m"],
        "slope",
        p["slope"],
        "elev",
        p["elev"],
        "cut1km",
        p["cut1km"],
        "STEEP" if p["steep"] else "",
    )
