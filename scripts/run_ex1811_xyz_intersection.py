#!/usr/bin/env python3
"""Acquire EX1811 100 m XYZ product and test overlap with the selected W00247 BAG.

EX1811 is an independent multibeam acquisition root.  Its archived XYZ product
can establish spatially overlapping sensor-derived bathymetry, but NCEI's
collection metadata reports the vertical datum as unknown; this script therefore
never subtracts EX1811 z values from W00247 MLLW depths.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://data.ngdc.noaa.gov/platforms/ocean/ships/okeanos_explorer/EX1811/multibeam/data/version1/products/EX1811_MB_FNL_100m_WGS84.xyz.gz"
BBOX = (-65.9833772516194, 17.723098751773474, -65.82659038887648, 17.873293497881694)


def _download(url: str, path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    req = Request(url, headers={"User-Agent": "spiderweb-pr/0.1 marine-evidence"})
    with urlopen(req, timeout=180) as response, path.open("wb") as out:
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status}")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _parse_triplet(line: str) -> tuple[float, float, float] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", ">")):
        return None
    parts = stripped.replace(",", " ").split()
    if len(parts) < 3:
        return None
    try:
        values = tuple(float(value) for value in parts[:3])
    except ValueError:
        return None
    return values[0], values[1], values[2]


def main() -> int:
    out = Path("evidence/marine/ex1811_xyz_w00247_v0_1")
    out.mkdir(parents=True, exist_ok=True)
    archive = out / "EX1811_MB_FNL_100m_WGS84.xyz.gz"
    sha256, size = _download(URL, archive)

    min_lon, min_lat, max_lon, max_lat = BBOX
    selected: list[tuple[float, float, float]] = []
    total_numeric = 0
    malformed = 0
    global_min_x = math.inf
    global_max_x = -math.inf
    global_min_y = math.inf
    global_max_y = -math.inf
    with gzip.open(archive, "rt", encoding="utf-8", errors="strict") as stream:
        for line in stream:
            value = _parse_triplet(line)
            if value is None:
                if line.strip() and not line.lstrip().startswith(("#", ">")):
                    malformed += 1
                continue
            x, y, z = value
            total_numeric += 1
            global_min_x = min(global_min_x, x)
            global_max_x = max(global_max_x, x)
            global_min_y = min(global_min_y, y)
            global_max_y = max(global_max_y, y)
            if min_lon <= x <= max_lon and min_lat <= y <= max_lat:
                selected.append((x, y, z))

    if total_numeric == 0:
        raise ValueError("EX1811 XYZ contained no numeric triples")
    if not (-180 <= global_min_x <= 180 and -180 <= global_max_x <= 180 and -90 <= global_min_y <= 90 and -90 <= global_max_y <= 90):
        raise ValueError("first two XYZ columns are not plausible WGS84 longitude/latitude")

    selected_path = out / "EX1811_W00247_bbox_points.csv"
    with selected_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["lon", "lat", "z_source_units"])
        writer.writerows(selected)
    selected_sha = hashlib.sha256(selected_path.read_bytes()).hexdigest()

    z_values = [row[2] for row in selected]
    manifest = {
        "receipt_version": "0.1",
        "source_survey": "EX1811",
        "source_sensor": "Kongsberg EM302 multibeam",
        "source_url": URL,
        "source_product": "EX1811_MB_FNL_100m_WGS84.xyz.gz",
        "source_product_sha256": sha256,
        "source_product_size_bytes": size,
        "selected_w00247_bbox_wgs84": list(BBOX),
        "total_numeric_xyz_rows": total_numeric,
        "malformed_noncomment_rows": malformed,
        "source_xy_envelope": [global_min_x, global_min_y, global_max_x, global_max_y],
        "intersecting_xyz_rows": len(selected),
        "selected_csv_sha256": selected_sha,
        "selected_z": ({
            "minimum": min(z_values),
            "maximum": max(z_values),
            "mean": sum(z_values) / len(z_values),
        } if z_values else None),
        "horizontal_reference": "WGS84 as declared by product filename and NCEI cruise product description",
        "vertical_reference": "UNKNOWN",
        "state": "OVERLAP_CONFIRMED_VERTICAL_BLOCKED" if selected else "NO_XYZ_POINT_OVERLAP",
        "epistemic_binding": {
            "FACT": "EX1811 is an independent multibeam acquisition root from W00247.",
            "COMPUTED": "Point overlap is computed directly from byte-frozen EX1811 XYZ coordinates and the byte-frozen W00247 BAG raster envelope.",
            "BLOCKED": "Numerical EX1811-vs-W00247 depth subtraction is prohibited because EX1811 collection metadata declares vertical datum unknown while W00247 is MLLW depth EPSG:5866."
        },
        "certification_boundary": "Spatially overlapping independent sensor-derived bathymetry only; no vertical equivalence, screenshot registration, feature equivalence, or origin classification is certified."
    }
    (out / "ex1811_xyz_w00247_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    # Do not retain the ~56 MB full-source duplicate in the artifact after its hash
    # and selected subset have been frozen; NCEI remains the immutable source URI.
    archive.unlink()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
