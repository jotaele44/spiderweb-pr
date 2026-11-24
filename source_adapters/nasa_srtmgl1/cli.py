"""CLI for the NASA SRTMGL1 adapter.

``discover`` is metadata-only. ``fetch`` downloads tiles into an operator-local
cache and requires ``--acknowledge-no-commit``. ``composition`` reads cached
SRTMGL1N files and reports which platform supplied each tile's heights.

Exit codes: 0 success, 2 usage or refusal, 3 Earthdata login required.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..cache_provenance import merge_rows, previous_rows
from .composition import composition
from .fetch import EarthdataLoginRequired, download, token_from_env, utc_now
from .fetch_plan import DEFAULT_CACHE_DIR, build_fetch_plan, select_tiles
from .hgt import height_stats, read_hgt_zip, read_num_zip
from .provenance import build_provenance, cached_row
from .registry import DEFAULT_MANIFEST_PATH, load_manifest, load_tiles

PROVENANCE_NAME = "provenance.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _selection(args: argparse.Namespace):
    tiles = load_tiles(args.manifest)
    if args.tile:
        return select_tiles(tiles, tile_ids=args.tile)
    bbox = args.bbox or load_manifest(args.manifest)["aoi"]["bbox_wsen"]
    return select_tiles(tiles, bbox_wsen=bbox)


def discover(args: argparse.Namespace) -> int:
    plan = build_fetch_plan(_selection(args), metadata_only=True)
    out = Path(args.out)
    write_json(out / "fetch_plan.json", plan)
    print(f"metadata-only plan for {len(plan['selected_tiles'])} tiles -> {out / 'fetch_plan.json'}")
    return 0


def fetch(args: argparse.Namespace) -> int:
    if not args.acknowledge_no_commit:
        print("refusing to fetch: pass --acknowledge-no-commit (raw tiles stay local and uncommitted)", file=sys.stderr)
        return 2
    selected = _selection(args)
    cache = Path(args.cache_dir)
    plan = build_fetch_plan(
        selected,
        include_hgt=not args.num_only,
        include_num=not args.hgt_only,
        metadata_only=False,
        cache_dir=cache,
    )
    token = token_from_env()
    rows = []
    for task in plan["tasks"]:
        dest = Path(task["local_cache_path"])
        if dest.exists() and not args.force:
            row = cached_row(dest, task["source_url"])
        else:
            try:
                row = download(task["source_url"], dest, token=token)
            except EarthdataLoginRequired as exc:
                print(str(exc), file=sys.stderr)
                return 3
            row["review_status"] = "downloaded_local"
        row.update({"product": task["product"], "tile_id": task["tile_id"]})
        rows.append(row)
        print(f"{task['product']:9s} {task['tile_id']}  {row['file_size_bytes']:>10,d} B  sha256 {row['sha256'][:16]}…")
    rows = merge_rows(previous_rows(cache / PROVENANCE_NAME), rows, cache)
    write_json(cache / PROVENANCE_NAME, build_provenance(rows, generated_at=utc_now()))
    print(f"provenance -> {cache / PROVENANCE_NAME}")
    return 0


def composition_report(args: argparse.Namespace) -> int:
    cache = Path(args.cache_dir)
    tiles = load_tiles(args.manifest)
    report_tiles = []
    for tile in tiles:
        num_path = cache / tile.num_zip_name
        if not num_path.exists():
            continue
        entry = {"tile_id": tile.tile_id, "num_file": num_path.name, **composition(read_num_zip(num_path))}
        hgt_path = cache / tile.hgt_zip_name
        if hgt_path.exists():
            entry["heights"] = height_stats(read_hgt_zip(hgt_path))
        report_tiles.append(entry)
    if not report_tiles:
        print(f"no SRTMGL1N files in {cache}; run fetch first", file=sys.stderr)
        return 2
    report = {
        "adapter": "nasa_srtmgl1",
        "generated_at": utc_now(),
        "basis": "SRTMGL1N v003 NUM values classified by SRTM User Guide V3, Table 2",
        "tiles": report_tiles,
    }
    out = Path(args.out) if args.out else cache / "composition.json"
    write_json(out, report)
    for entry in report_tiles:
        shares = ", ".join(f"{k} {v}%" for k, v in entry["platform_share_percent"].items() if v)
        print(f"{entry['tile_id']}: land {entry['land_samples']:,d} samples; {shares or 'no land'}")
    print(f"report -> {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m source_adapters.nasa_srtmgl1.cli")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    def selection(p: argparse.ArgumentParser) -> None:
        p.add_argument("--tile", action="append", help="tile id such as N18W067 (repeatable)")
        p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), help="defaults to the manifest AOI")

    p_discover = sub.add_parser("discover", help="write a metadata-only fetch plan")
    selection(p_discover)
    p_discover.add_argument("--out", default="outputs/nasa_srtmgl1/review")
    p_discover.set_defaults(func=discover)

    p_fetch = sub.add_parser("fetch", help="download tiles into a local cache")
    selection(p_fetch)
    p_fetch.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    p_fetch.add_argument("--acknowledge-no-commit", action="store_true")
    p_fetch.add_argument("--force", action="store_true", help="download again even if cached")
    only = p_fetch.add_mutually_exclusive_group()
    only.add_argument("--hgt-only", action="store_true")
    only.add_argument("--num-only", action="store_true")
    p_fetch.set_defaults(func=fetch)

    p_comp = sub.add_parser("composition", help="report per-tile source composition from cached NUM files")
    p_comp.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    p_comp.add_argument("--out")
    p_comp.set_defaults(func=composition_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
