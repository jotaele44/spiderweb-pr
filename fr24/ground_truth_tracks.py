"""
Ground-truth flight track loader for the FR24 pipeline.

The FR24 screenshot pipeline produces an OCR-derived `aircraft_observations`
table but leaves `flight_track_features` empty and has no `track_points` — the
on-screen path geometry was never recoverable from a single screenshot
(see fr24/rlsm_flight_track.py, which ships a 0.3-confidence heuristic).

This module ingests *real* FR24 CSV track exports (the "Download CSV" files,
header: Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction) — both the
historical bundles under the GPT Data folder and freshly fetched flights — and
produces:

  * track_points          — one row per (flight, timestamp) with lat/lon/alt/spd/hdg
  * flight_track_features  — one row per flight with MEASURED path geometry
                             (path_shape, has_hover, has_loop/orbit, length, etc.)
                             confidence = 1.0 ('measured'), replacing the heuristic.

Flights are keyed by FR24 flight id (the hex filename stem, e.g. 3d1e6025),
which is exactly the join key the rest of the pipeline already uses. The
registration comes from the CSV Callsign column (falling back to a REG_ prefix
in the filename), so these rows link straight onto `aircraft_observations`.

Usage:
    python -m fr24.ground_truth_tracks \
        --inputs "/path/to/GPT Data" \
        --db data/ground_truth/ground_truth.sqlite \
        --summary data/ground_truth/summary.csv
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sqlite3
import sys
import zipfile
from io import TextIOWrapper
from pathlib import Path
from collections import defaultdict

FR24_HEADER = ["Timestamp", "UTC", "Callsign", "Position", "Altitude", "Speed", "Direction"]
HEX_RE = re.compile(r"([0-9a-f]{6,9})")
REG_RE = re.compile(r"\b(N[0-9][0-9A-Z]{1,5}|N2JJ)\b", re.I)


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def _haversine_km(a, b):
    R = 6371.0088
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _ang_diff(h1, h2):
    d = abs((h2 - h1 + 180) % 360 - 180)
    return d


def parse_fr24_csv(handle, source_name):
    """Yield dict points from an FR24 CSV file handle. Returns (flight_id, reg, points)."""
    reader = csv.reader(handle)
    try:
        header = next(reader)
    except StopIteration:
        return None
    if [h.strip() for h in header[:7]] != FR24_HEADER:
        return None
    pts = []
    reg = None
    for row in reader:
        if len(row) < 7:
            continue
        try:
            ts = int(row[0])
        except ValueError:
            continue
        cs = (row[2] or "").strip()
        if cs and reg is None:
            reg = cs
        pos = (row[3] or "").strip().strip('"')
        if "," not in pos:
            continue
        try:
            lat, lon = (float(x) for x in pos.split(",")[:2])
        except ValueError:
            continue
        def num(v):
            try:
                return float(str(v).replace(",", ""))
            except ValueError:
                return None
        pts.append({
            "ts": ts, "utc": row[1].strip(), "lat": lat, "lon": lon,
            "alt_ft": num(row[4]), "speed_kt": num(row[5]), "heading_deg": num(row[6]),
        })
    if not pts:
        return None
    pts.sort(key=lambda p: p["ts"])
    m = HEX_RE.search(Path(source_name).stem.lower())
    flight_id = m.group(1) if m else Path(source_name).stem
    if reg is None:
        rm = REG_RE.search(Path(source_name).stem)
        reg = rm.group(1).upper() if rm else "UNKNOWN"
    return flight_id, reg.upper(), pts


# --------------------------------------------------------------------------- #
# measured feature extraction  (the replacement for the 0.3 heuristic)
# --------------------------------------------------------------------------- #
def compute_features(pts):
    n = len(pts)
    coords = [(p["lat"], p["lon"]) for p in pts]
    path_km = sum(_haversine_km(coords[i], coords[i + 1]) for i in range(n - 1))
    straight_km = _haversine_km(coords[0], coords[-1])
    sinuosity = path_km / straight_km if straight_km > 0.05 else float("inf")
    duration_s = pts[-1]["ts"] - pts[0]["ts"]

    speeds = [p["speed_kt"] for p in pts if p["speed_kt"] is not None]
    alts = [p["alt_ft"] for p in pts if p["alt_ft"] is not None]
    hov_frac = (sum(1 for s in speeds if s < 5) / len(speeds)) if speeds else 0.0
    has_hover = hov_frac > 0.12

    # cumulative turning + heading reversals (parallel-leg / survey signal)
    hdgs = [p["heading_deg"] for p in pts if p["heading_deg"] is not None]
    total_turn = sum(_ang_diff(hdgs[i], hdgs[i + 1]) for i in range(len(hdgs) - 1))
    reversals = sum(1 for i in range(len(hdgs) - 1) if _ang_diff(hdgs[i], hdgs[i + 1]) > 150)

    returns = straight_km < 1.0 and path_km > 3.0
    has_loop = returns and total_turn > 360
    has_orbit = returns and total_turn > 540 and path_km < 20

    if has_hover and path_km < 2.0:
        shape = "hover"
    elif has_orbit:
        shape = "orbit"
    elif has_loop:
        shape = "loop"
    elif reversals >= 4 and sinuosity > 1.6:
        shape = "survey_grid"
    elif sinuosity != float("inf") and sinuosity < 1.3:
        shape = "linear"
    else:
        shape = "complex"

    lats = [c[0] for c in coords]; lons = [c[1] for c in coords]
    return {
        "point_count": n,
        "duration_s": duration_s,
        "track_length_km": round(path_km, 3),
        "straight_dist_km": round(straight_km, 3),
        "sinuosity": round(sinuosity, 3) if sinuosity != float("inf") else None,
        "total_turn_deg": round(total_turn, 1),
        "heading_reversals": reversals,
        "alt_min_ft": min(alts) if alts else None,
        "alt_max_ft": max(alts) if alts else None,
        "speed_mean_kt": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "speed_max_kt": max(speeds) if speeds else None,
        "has_hover": int(has_hover),
        "has_loop": int(has_loop),
        "has_orbit": int(has_orbit),
        "path_shape": shape,
        "bbox_min_lat": round(min(lats), 5), "bbox_max_lat": round(max(lats), 5),
        "bbox_min_lon": round(min(lons), 5), "bbox_max_lon": round(max(lons), 5),
        "start_utc": pts[0]["utc"], "end_utc": pts[-1]["utc"],
        "confidence": 1.0, "source": "measured_fr24_csv",
    }


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def discover_csvs(roots):
    """Yield (source_name, file_handle_factory) for every FR24 CSV under roots,
    including those inside .zip bundles. Skips __MACOSX noise."""
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for p in root.rglob("*.csv"):
            if "__MACOSX" in str(p) or p.name.startswith("._") or p.name.startswith("_manifest"):
                continue
            yield str(p), (lambda pp=p: open(pp, "r", encoding="utf-8", errors="replace"))
        for z in root.rglob("*.zip"):
            try:
                zf = zipfile.ZipFile(z)
            except Exception:
                continue
            for name in zf.namelist():
                if not name.lower().endswith(".csv") or "__MACOSX" in name:
                    continue
                yield f"{z.name}:{name}", (lambda zf=zf, name=name: TextIOWrapper(zf.open(name), encoding="utf-8", errors="replace"))


# --------------------------------------------------------------------------- #
# db
# --------------------------------------------------------------------------- #
def build_db(db_path, flights):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    c = con.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS track_points;
        DROP TABLE IF EXISTS flight_track_features;
        CREATE TABLE track_points(
            flight_id TEXT, registration TEXT, seq INTEGER, ts INTEGER, utc TEXT,
            lat REAL, lon REAL, alt_ft REAL, speed_kt REAL, heading_deg REAL,
            source_file TEXT
        );
        CREATE TABLE flight_track_features(
            flight_id TEXT PRIMARY KEY, registration TEXT, point_count INTEGER,
            duration_s INTEGER, track_length_km REAL, straight_dist_km REAL,
            sinuosity REAL, total_turn_deg REAL, heading_reversals INTEGER,
            alt_min_ft REAL, alt_max_ft REAL, speed_mean_kt REAL, speed_max_kt REAL,
            has_hover INTEGER, has_loop INTEGER, has_orbit INTEGER, path_shape TEXT,
            bbox_min_lat REAL, bbox_max_lat REAL, bbox_min_lon REAL, bbox_max_lon REAL,
            start_utc TEXT, end_utc TEXT, confidence REAL, source TEXT, source_file TEXT
        );
        CREATE INDEX idx_tp_flight ON track_points(flight_id);
        CREATE INDEX idx_tp_reg ON track_points(registration);
        CREATE INDEX idx_ftf_reg ON flight_track_features(registration);
    """)
    for fid, (reg, pts, feats, src) in flights.items():
        c.executemany(
            "INSERT INTO track_points VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(fid, reg, i, p["ts"], p["utc"], p["lat"], p["lon"], p["alt_ft"],
              p["speed_kt"], p["heading_deg"], src) for i, p in enumerate(pts)],
        )
        c.execute(
            "INSERT INTO flight_track_features VALUES (" + ",".join("?" * 26) + ")",
            (fid, reg, feats["point_count"], feats["duration_s"], feats["track_length_km"],
             feats["straight_dist_km"], feats["sinuosity"], feats["total_turn_deg"],
             feats["heading_reversals"], feats["alt_min_ft"], feats["alt_max_ft"],
             feats["speed_mean_kt"], feats["speed_max_kt"], feats["has_hover"],
             feats["has_loop"], feats["has_orbit"], feats["path_shape"],
             feats["bbox_min_lat"], feats["bbox_max_lat"], feats["bbox_min_lon"],
             feats["bbox_max_lon"], feats["start_utc"], feats["end_utc"],
             feats["confidence"], feats["source"], src),
        )
    con.commit()
    con.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Load ground-truth FR24 tracks into track_points + flight_track_features")
    ap.add_argument("--inputs", nargs="+", required=True, help="root folders to scan (recursively) for FR24 CSVs/zips")
    ap.add_argument("--db", default="data/ground_truth/ground_truth.sqlite")
    ap.add_argument("--summary", default="data/ground_truth/summary.csv")
    args = ap.parse_args(argv)

    flights = {}   # flight_id -> (reg, pts, feats, source)
    seen_sources = 0
    for src, opener in discover_csvs(args.inputs):
        try:
            with opener() as fh:
                parsed = parse_fr24_csv(fh, src)
        except Exception:
            continue
        if not parsed:
            continue
        seen_sources += 1
        fid, reg, pts = parsed
        # dedupe by flight id: keep the richest copy
        if fid in flights and len(flights[fid][1]) >= len(pts):
            continue
        flights[fid] = (reg, pts, compute_features(pts), src)

    if not flights:
        print("No FR24 CSV tracks found under:", args.inputs, file=sys.stderr)
        return 1

    build_db(args.db, flights)

    # summary
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    rows = []
    by_reg = defaultdict(int); by_shape = defaultdict(int); total_pts = 0
    for fid, (reg, pts, f, src) in sorted(flights.items()):
        by_reg[reg] += 1; by_shape[f["path_shape"]] += 1; total_pts += f["point_count"]
        rows.append([fid, reg, f["point_count"], f["track_length_km"], f["duration_s"],
                     f["path_shape"], f["has_hover"], f["has_loop"], f["has_orbit"],
                     f["alt_max_ft"], f["speed_max_kt"]])
    with open(args.summary, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["flight_id", "registration", "points", "track_km", "duration_s",
                    "path_shape", "has_hover", "has_loop", "has_orbit", "alt_max_ft", "speed_max_kt"])
        w.writerows(rows)

    print(f"Parsed {seen_sources} CSV sources -> {len(flights)} unique flights, {total_pts:,} track points")
    print(f"DB:      {args.db}")
    print(f"Summary: {args.summary}")
    print("\nFlights per registration:")
    for r, n in sorted(by_reg.items(), key=lambda x: -x[1]):
        print(f"  {r:10} {n:3}")
    print("\nMeasured path_shape distribution (replaces the 0.3 heuristic):")
    for s, n in sorted(by_shape.items(), key=lambda x: -x[1]):
        print(f"  {s:12} {n:3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
