#!/usr/bin/env python3
"""Check that Spiderweb's HTTP surface has an explicit GUI disposition.

The check is intentionally small and dependency-free: FastAPI decorators are
the backend source of truth, while the shipped TypeScript client and spatial
module are the GUI evidence. Endpoints that are deliberately operator/internal
are listed explicitly so an accidental new route cannot silently bypass review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROUTE_RE = re.compile(
    r"@\s*(?:app|router)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*[\"']([^\"']+)"
)
CLIENT_PATH_RE = re.compile(r"""["'`]([^"'`]*\/(?:health|agencies|vendors|sites|contracts|events|anomalies|sources|investigations|alerts|pipeline|geo|catalog|spatial|rag)[^"'`]*)["'`]""")
INTERNAL_ROUTES = {
    # Liveness and registry metadata are consumed by the desktop shell and
    # deployment health checks; they are not user workflows in the web app.
    ("GET", "/health"),
    ("GET", "/health/martin-delivery"),
    ("GET", "/catalog"),
    ("GET", "/spatial/capabilities"),
    ("GET", "/spatial/scene"),
    ("GET", "/spatial/layers"),
    ("GET", "/spatial/boundaries/{boundary_id}.geojson"),
    ("POST", "/rag/index"),
}


def _routes(root: Path) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in (root / "server/backend").rglob("*.py"):
        for match in ROUTE_RE.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            found.add((match.group(1).upper(), match.group(2)))
    return found


def _gui_text(root: Path) -> str:
    files = list((root / "server/frontend/src").rglob("*.ts"))
    files += list((root / "server/frontend/src").rglob("*.tsx"))
    return "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in files)


def _wired(route: tuple[str, str], gui_text: str) -> bool:
    method, path = route
    if path in gui_text:
        return True
    # Dynamic paths are represented by template strings such as /geo/${key}.
    prefix = path.split("{", 1)[0]
    return bool(prefix and prefix in gui_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    routes = _routes(root)
    gui_text = _gui_text(root)
    gaps = [
        {"method": method, "path": path}
        for method, path in sorted(routes)
        if (method, path) not in INTERNAL_ROUTES and not _wired((method, path), gui_text)
    ]
    report = {
        "schema_version": "spiderweb.gui-parity-report/v1",
        "passed": not gaps,
        "summary": {
            "backend_routes": len(routes),
            "gui_wired": len(routes) - len(gaps),
            "internal": len(routes & INTERNAL_ROUTES),
            "new_gaps": len(gaps),
            "manifest_issues": 0,
        },
        "gaps": gaps,
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if gaps:
        for gap in gaps:
            print(f"BACKEND_NOT_GUI_SURFACED: {gap['method']} {gap['path']}", file=sys.stderr)
        return 1
    print(
        f"PASS gui-parity spiderweb-pr routes={len(routes)} "
        f"wired={report['summary']['gui_wired']} internal={len(routes & INTERNAL_ROUTES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
