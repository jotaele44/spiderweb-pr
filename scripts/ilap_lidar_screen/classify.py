"""Classify LARGE fills per CRITERIA.md (tests 1-3 plus amendments A1, A2).

Run after aggregate.py and flatness.py. Usage: python3 classify.py <workdir>
"""

import json
import sys
from collections import Counter

S = sys.argv[1]
L = json.load(open(f"{S}/island/large.json"))


def cls(p):
    if (p.get("med") or 0) > 50:
        return "artifact_spike"
    if (p.get("flat") or 0) >= 0.6:
        return "water_level"
    if p["echo"]:
        return "landfill_or_registered_site"
    if p["mrds"]:
        return "quarry_or_mine"
    if p.get("bal"):
        return "cut_fill_balance"
    return "steep_unexplained" if p["steep"] else "RESIDUAL"


F = [p for p in L if p["kind"] == "fill"]

for p in F:
    p["cls"] = cls(p)
c = Counter(p["cls"] for p in F)
v = Counter()
for p in F:
    v[p["cls"]] += p["vol_m3"]
tot = sum(v.values())
for k in c:
    print(k, c[k], round(v[k] / 1e6, 2), "Mm3", round(100 * v[k] / tot, 1), "%")
print("LARGE fills", len(F), "vol", round(tot / 1e6, 1))
R = sorted(
    [p for p in F if p["cls"] in ("RESIDUAL", "steep_unexplained")],
    key=lambda p: (p["cls"] != "RESIDUAL", -p["vol_m3"]),
)
for i, p in enumerate(R):
    p["id"] = i + 1
json.dump(R, open(f"{S}/island/residuals.json", "w"), indent=0)
json.dump(F, open(f"{S}/island/large_fills_classified.json", "w"))
print(len(R))
for p in R:
    print(
        p["id"],
        p["cls"][:5],
        p["tile"],
        p["lat"],
        p["lon"],
        p["vol_m3"],
        p["area_m2"],
        p["max_m"],
        "sl",
        p["slope"],
        "el",
        p["elev"],
        "flat",
        p.get("flat"),
        "cut1km",
        p["cut1km"],
    )
