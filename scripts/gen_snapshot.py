#!/usr/bin/env python3
"""Generate server/frontend/src/lib/snapshot.json for the offline export.

The standalone `file://` build (VITE_OFFLINE=1) cannot fetch, so
server/frontend/src/lib/api.ts resolves each endpoint from an embedded snapshot
keyed by request path (query string stripped). This script seeds the demo DB if
needed, then calls the backend's endpoint functions directly and dumps those
paths, so `npm run build:export` ships a workbench with data baked in instead of
empty fallbacks. Calling the async functions directly (via asyncio) avoids the
FastAPI TestClient, which would pull in a test-only httpx dependency.

Usage (from repo root):
    python3 scripts/gen_snapshot.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # allow `import server...` regardless of CWD

from server.ingestion import seed_demo  # noqa: E402

# Ensure there is data to snapshot before importing the backend (which reads DB_PATH).
if not seed_demo.DB_PATH.exists():
    seed_demo.main()

from server.backend import main as backend  # noqa: E402

# Map each snapshot key (the query-string-stripped path api.ts looks up) to the
# backend endpoint coroutine that produces it. Static reads only — the pipeline
# and RAG endpoints are POST/SSE and are not part of the offline snapshot. Geo
# layers are skipped: catalog layers are status="deferred" (not consumed yet).
ENDPOINTS = {
    "/health": backend.health,
    "/sites": backend.list_sites,
    "/contracts": backend.list_contracts,
    "/events": backend.list_events,
    "/anomalies": backend.list_anomalies,
    "/sources": backend.list_sources,
    "/catalog": backend.layer_catalog,
}

OUT = _ROOT / "server" / "frontend" / "src" / "lib" / "snapshot.json"


def main() -> None:
    snapshot = {path: asyncio.run(fn()) for path, fn in ENDPOINTS.items()}
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    counts = {
        p: (len(v) if isinstance(v, list) else 1) for p, v in snapshot.items()
    }
    print(f"wrote {OUT.relative_to(_ROOT)}  {counts}")


if __name__ == "__main__":
    main()
