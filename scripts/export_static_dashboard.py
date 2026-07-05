#!/usr/bin/env python3
"""Build a portable static dashboard bundle.

This command makes the dashboard usable without hosting the FastAPI server:

    python scripts/export_static_dashboard.py --dist dist/static-dashboard

It copies the browser dashboard assets, rewrites output paths to be bundle-relative,
and stages dashboard JSON/GeoJSON outputs under ``dist/static-dashboard/outputs``.
If ``dashboard_data.json`` is missing and ``--db`` is supplied, it generates the
snapshot through ``run_all.export_json``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REQUIRED_OUTPUTS = ("dashboard_data.json",)
OPTIONAL_OUTPUTS = (
    "fr24_dashboard_review_queue.json",
    "contract_finance_layer_report.json",
    "contract_finance_scored_overlay.geojson",
)
DASHBOARD_ASSETS = (
    "dashboard.jsx",
    "dashboard_contract_finance.jsx",
)


class StaticDashboardExportError(RuntimeError):
    """Raised when the static dashboard bundle cannot be created safely."""


def repo_root_from(start: Path | None = None) -> Path:
    """Resolve the repository root from this script path or a supplied start path."""
    start = (start or Path(__file__)).resolve()
    return start.parents[1] if start.name == "export_static_dashboard.py" else start


def _copy_required_asset(src: Path, dst: Path) -> None:
    if not src.exists():
        raise StaticDashboardExportError(f"required asset missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_outputs(source_outputs: Path, staged_outputs: Path, names: Iterable[str]) -> dict[str, str]:
    staged_outputs.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for name in names:
        src = source_outputs / name
        if src.exists():
            dst = staged_outputs / name
            shutil.copy2(src, dst)
            copied[name] = str(dst)
        else:
            copied[name] = "missing"
    return copied


def _generate_dashboard_json(db_path: Path, dashboard_json: Path) -> None:
    if not db_path.exists():
        raise StaticDashboardExportError(f"database not found: {db_path}")
    dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    # Direct execution (``python scripts/export_static_dashboard.py``) puts
    # ``scripts/`` on sys.path, not the repo root, so ``run_all`` in the parent
    # directory is not importable. Add the root before importing, matching the
    # pattern used across scripts/ (e.g. parse_adsb_archive.py, cascade_refine.py).
    root = repo_root_from()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from run_all import export_json  # noqa: E402

    export_json(str(db_path), str(dashboard_json))


def _rewrite_dashboard_html(raw_html: str) -> str:
    """Convert repo-local dashboard paths into bundle-local paths."""
    rewritten = raw_html.replace('url: "../outputs/', 'url: "./outputs/')
    rewritten = rewritten.replace("url: '../outputs/", "url: './outputs/")
    rewritten = rewritten.replace('fetchJson("../outputs/', 'fetchJson("./outputs/')
    rewritten = rewritten.replace("fetchJson('../outputs/", "fetchJson('./outputs/")
    rewritten = rewritten.replace(
        "Open this file in a browser:",
        "Open index.html through a local static file server or GitHub Pages:",
    )
    rewritten = rewritten.replace(
        "python -m http.server 8080",
        "python -m http.server 8080  # from this bundle directory",
    )
    return rewritten


def bundle_static_dashboard(
    *,
    repo_root: Path,
    dist_dir: Path,
    source_outputs: Path,
    db_path: Path | None = None,
    clean: bool = True,
) -> dict[str, object]:
    """Create a portable dashboard bundle and return manifest metadata."""
    repo_root = repo_root.resolve()
    dist_dir = dist_dir.resolve()
    source_outputs = source_outputs.resolve()
    db_path = db_path.resolve() if db_path else None

    dashboard_dir = repo_root / "dashboard"
    dashboard_html = dashboard_dir / "dashboard.html"
    staged_outputs = dist_dir / "outputs"

    if clean and dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    for asset in DASHBOARD_ASSETS:
        _copy_required_asset(dashboard_dir / asset, dist_dir / asset)

    if not dashboard_html.exists():
        raise StaticDashboardExportError(f"required asset missing: {dashboard_html}")
    (dist_dir / "index.html").write_text(
        _rewrite_dashboard_html(dashboard_html.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    dashboard_json = source_outputs / "dashboard_data.json"
    if not dashboard_json.exists() and db_path is not None:
        _generate_dashboard_json(db_path, dashboard_json)

    missing_required = [name for name in REQUIRED_OUTPUTS if not (source_outputs / name).exists()]
    if missing_required:
        raise StaticDashboardExportError(
            "missing required dashboard output(s): "
            + ", ".join(missing_required)
            + "; run `python run_all.py --export-json outputs/dashboard_data.json` "
            + "or pass --db to generate it."
        )

    required = _copy_outputs(source_outputs, staged_outputs, REQUIRED_OUTPUTS)
    optional = _copy_outputs(source_outputs, staged_outputs, OPTIONAL_OUTPUTS)

    manifest: dict[str, object] = {
        "mode": "static-dashboard",
        "server_required": False,
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "dist_dir": str(dist_dir),
        "source_outputs": str(source_outputs),
        "entrypoint": "index.html",
        "load_contract": {
            "required_outputs": list(REQUIRED_OUTPUTS),
            "optional_outputs": list(OPTIONAL_OUTPUTS),
            "required_dashboard_arrays": ["flights", "aircraft_profiles", "alerts", "anomalies"],
            "degraded_optional_outputs_allowed": True,
        },
        "required_outputs": required,
        "optional_outputs": optional,
        "dashboard_assets": {asset: str(dist_dir / asset) for asset in DASHBOARD_ASSETS},
        "run_hint": "cd {dist} && python -m http.server 8080".format(dist=dist_dir),
    }
    (dist_dir / "static_dashboard_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a serverless/static dashboard bundle from repo outputs."
    )
    parser.add_argument(
        "--dist",
        default="dist/static-dashboard",
        help="Directory to write the portable static dashboard bundle.",
    )
    parser.add_argument(
        "--outputs",
        default="outputs",
        help="Source outputs directory containing dashboard_data.json and optional overlays.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional SQLite DB path. Generates dashboard_data.json when missing.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete the destination bundle before writing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = repo_root_from()
    try:
        manifest = bundle_static_dashboard(
            repo_root=root,
            dist_dir=Path(args.dist),
            source_outputs=Path(args.outputs),
            db_path=Path(args.db) if args.db else None,
            clean=not args.no_clean,
        )
    except StaticDashboardExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("\n  STATIC DASHBOARD EXPORT")
    print("  " + "─" * 50)
    print(f"  Entrypoint: {Path(manifest['dist_dir']) / manifest['entrypoint']}")
    print(f"  Server required: {manifest['server_required']}")
    print(f"  Manifest: {Path(manifest['dist_dir']) / 'static_dashboard_manifest.json'}")
    print(f"  Run: {manifest['run_hint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
