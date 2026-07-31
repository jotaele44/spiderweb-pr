#!/usr/bin/env python3
"""Generate server/frontend/src/lib/snapshot.json for the offline export.

The standalone `file://` build (VITE_OFFLINE=1) cannot fetch, so
server/frontend/src/lib/api.ts resolves each endpoint from an embedded snapshot
keyed by request path (query string stripped). This script builds a fresh,
ISOLATED synthetic demo database in a temp dir, points the backend at it, and
dumps the static endpoints — so `npm run build:export` always ships obviously-
synthetic demo data.

Isolation is deliberate: the runtime DB (server/priis.db) may contain real
ingested contracts/sites/flights (server/ingestion/ingest_data.py uses that same
path). Snapshotting it would leak real records into an export presented as a
demo, so we never read it here.

Calling the async endpoint functions directly (via asyncio) avoids the FastAPI
TestClient, which would pull in a test-only httpx dependency.

Usage (from repo root):
    python3 scripts/gen_snapshot.py
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # allow `import server...` regardless of CWD

from server.ingestion import seed_demo  # noqa: E402

OUT = _ROOT / "server" / "frontend" / "src" / "lib" / "snapshot.json"

# Static reads only — pipeline/RAG endpoints are POST/SSE and not part of the
# offline snapshot. Geo layers are skipped: catalog layers are status="deferred".
ENDPOINT_NAMES = [
    ("/health", "health"),
    ("/sites", "list_sites"),
    ("/contracts", "list_contracts"),
    ("/events", "list_events"),
    ("/anomalies", "list_anomalies"),
    ("/sources", "list_sources"),
    ("/catalog", "layer_catalog"),
]


def main() -> None:
    # The refresh needs the backend Python stack (aiosqlite, fastapi, ...), which
    # a frontend-only checkout won't have. Degrade gracefully: if it's missing,
    # keep the committed snapshot.json so `npm run build:export` still produces an
    # export (with the last-generated synthetic data) instead of failing.
    try:
        from server.backend import main as backend  # noqa: E402
    except ImportError as exc:
        print(
            f"[gen_snapshot] backend deps unavailable ({exc}); "
            f"keeping committed {OUT.name}. Install `pip install -e \".[server]\"` "
            f"from the repo root to refresh it.",
            file=sys.stderr,
        )
        return

    tmp_dir = Path(tempfile.mkdtemp(prefix="priis-demo-snapshot-"))
    demo_db = tmp_dir / "priis_demo.db"
    try:
        # Seed a fresh synthetic DB in isolation — never the runtime server/priis.db.
        seed_demo.main(demo_db)
        backend.DB_PATH = demo_db  # endpoint _rows()/health read this module global
        snapshot = {
            path: asyncio.run(getattr(backend, fn)()) for path, fn in ENDPOINT_NAMES
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    counts = {p: (len(v) if isinstance(v, list) else 1) for p, v in snapshot.items()}
    print(f"wrote {OUT.relative_to(_ROOT)}  {counts}")


if __name__ == "__main__":
    main()
