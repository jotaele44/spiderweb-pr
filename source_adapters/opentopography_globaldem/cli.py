"""CLI for the OpenTopography global DEM adapter.

``plan`` prints the requests that would be made, key redacted. ``fetch``
downloads one GeoTIFF per demtype into an operator-local cache and requires
``--acknowledge-no-commit``.

Exit codes: 0 success, 2 usage, refusal or missing key, 3 key refused, 4 other
request failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..cache_provenance import merge_rows, previous_rows
from .client import (
    REDACTED,
    OpenTopographyAuthError,
    OpenTopographyKeyMissing,
    OpenTopographyRequestError,
    api_key,
    build_request_url,
    demtypes,
    fetch,
    load_config,
    redact,
)

DEFAULT_CACHE_DIR = Path("data/opentopography/cache")


def _bbox(args: argparse.Namespace, config: dict) -> list[float]:
    return list(args.bbox) if args.bbox else list(config["aoi"]["bbox_wsen"])


def _selected(args: argparse.Namespace, config: dict) -> list[str]:
    return args.demtype or list(demtypes(config))


def plan(args: argparse.Namespace) -> int:
    config = load_config()
    bbox = _bbox(args, config)
    rows = [
        {"demtype": d, "catalog_source_id": demtypes(config)[d]["catalog_source_id"],
         "request_url": redact(build_request_url(config, d, bbox, REDACTED))}
        for d in _selected(args, config)
    ]
    print(json.dumps({"key_present": api_key(config) is not None, "requests": rows}, indent=2))
    return 0


def run_fetch(args: argparse.Namespace) -> int:
    if not args.acknowledge_no_commit:
        print("refusing to fetch: pass --acknowledge-no-commit (rasters stay local and uncommitted)", file=sys.stderr)
        return 2
    config = load_config()
    key = api_key(config)
    bbox = _bbox(args, config)
    cache = Path(args.cache_dir)
    rows = []
    for demtype in _selected(args, config):
        dest = cache / f"{demtype}_{'_'.join(f'{v:g}' for v in bbox)}.tif"
        try:
            row = fetch(config, demtype, bbox, dest, key=key)
        except OpenTopographyKeyMissing as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except OpenTopographyAuthError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        except OpenTopographyRequestError as exc:
            print(str(exc), file=sys.stderr)
            return 4
        rows.append(row)
        print(f"{demtype:8s} {row['file_size_bytes']:>12,d} B  sha256 {row['sha256'][:16]}…  -> {dest}")
    out = cache / "provenance.json"
    rows = merge_rows(previous_rows(out), rows, cache)
    out.write_text(json.dumps({"adapter": "opentopography_globaldem", "files": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"provenance -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m source_adapters.opentopography_globaldem.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("plan", plan), ("fetch", run_fetch)):
        p = sub.add_parser(name)
        p.add_argument("--demtype", action="append", help="SRTMGL1, NASADEM, COP30 or AW3D30 (repeatable; default all)")
        p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), help="defaults to the config AOI")
        p.set_defaults(func=func)
        if name == "fetch":
            p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
            p.add_argument("--acknowledge-no-commit", action="store_true")
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
