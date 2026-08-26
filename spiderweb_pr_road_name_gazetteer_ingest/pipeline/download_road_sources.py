#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
import hashlib
import sys
from pathlib import Path
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parents[1]

def download(url: str, dest: Path, overwrite: bool = False) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        print(f"SKIP exists {dest}")
        return True
    print(f"GET {url}")
    req = Request(url, headers={'User-Agent':'spiderweb-pr-road-gazetteer/0.1'})
    try:
        with urlopen(req, timeout=90) as r, dest.open('wb') as f:
            while True:
                chunk = r.read(1024*1024)
                if not chunk:
                    break
                f.write(chunk)
        print(f"OK {dest} {dest.stat().st_size} bytes")
        return True
    except Exception as e:
        print(f"ERR {url}: {e}", file=sys.stderr)
        return False

def read_queue(path: Path):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tiger', action='store_true')
    ap.add_argument('--osm', action='store_true')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()
    if not (args.tiger or args.osm or args.all):
        ap.error('Use --tiger, --osm, or --all')
    base = ROOT
    ok = True
    if args.tiger or args.all:
        rows = read_queue(base / 'data/reference/roads/source_queue/tiger_pr_2025_county_roads.csv')
        for r in rows:
            ok = download(r['download_url'], base / r['local_expected_path'], args.overwrite) and ok
    if args.osm or args.all:
        rows = read_queue(base / 'data/reference/roads/source_queue/osm_geofabrik_pr_latest.csv')
        # Download preferred GPKG only by default, not both alternates.
        for r in rows:
            if r.get('status') == 'alternate':
                continue
            ok = download(r['download_url'], base / r['local_expected_path'], args.overwrite) and ok
    raise SystemExit(0 if ok else 2)

if __name__ == '__main__':
    main()
