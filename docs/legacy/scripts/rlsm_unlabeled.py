#!/usr/bin/env python3
"""Parallel runner for unlabeled RLSM screenshots (T4-24).

Mirrors ``scripts/ocr_parallel.py``'s mini-batch ``ThreadPoolExecutor`` pattern,
but the extraction **worker is injected** (anything with ``process(path) -> data
| None``), so the parallelism harness — discovery, dedup, the time-boxed batch
loop, and the thread-safe write path — is unit-testable without pytesseract or
opencv. ``--workers`` controls concurrency.

The default worker (built lazily in ``main`` via ``_build_default_worker``)
wraps the existing FlightAnalyzer OCR engine — constructed once and reused across
every image — so the runner is real when the OCR stack is installed; only that
heavy path is exercised outside CI. ``main`` pins ``OMP_THREAD_LIMIT=1`` before
importing that stack so the worker threads don't oversubscribe the CPU.

Usage:
  python3 scripts/rlsm_unlabeled.py --image-dir DIR --db DB [--workers 4]
  python3 scripts/rlsm_unlabeled.py --status --db DB
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
DEFAULT_WORKERS = 4
DEFAULT_TIME_BUDGET = 0.0  # seconds; 0 disables the time-box (process everything)

_db_lock = threading.Lock()


def discover_images(image_dir: str | Path) -> list[str]:
    """Sorted list of supported image paths under *image_dir* (recursive)."""
    root = Path(image_dir)
    if not root.exists():
        return []
    return sorted(str(p) for p in root.rglob("*") if p.suffix.lower() in SUPPORTED)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _already_processed(db_path_str: str, sha256: str) -> bool:
    """Dedup check against the screenshots table (read-only; thread-safe)."""
    conn = sqlite3.connect(db_path_str, check_same_thread=False)
    try:
        row = conn.execute(
            "SELECT 1 FROM screenshots WHERE screenshot_id = ?", (sha256,)
        ).fetchone()
    except sqlite3.OperationalError:
        row = None  # no screenshots table yet → nothing is a duplicate
    finally:
        conn.close()
    return row is not None


def process_one(path_str: str, db_path_str: str, worker: Any) -> dict:
    """Hash, dedup-check, extract. Runs in a worker thread (read-only DB access).

    Returns a result dict with ``status`` in {ok, skip, err}. A worker that
    returns ``None`` (no extraction) counts as ``skip``; a worker exception is
    isolated to this image as ``err``.
    """
    path = Path(path_str)
    try:
        sha256 = _sha256(path)
    except OSError as exc:
        return {"status": "err", "path": path_str, "err": str(exc)}
    if _already_processed(db_path_str, sha256):
        return {"status": "skip", "path": path_str, "sha256": sha256}
    try:
        data = worker.process(path_str)
    except Exception as exc:  # noqa: BLE001 - isolate a bad image, keep the batch going
        return {"status": "err", "path": path_str, "sha256": sha256, "err": str(exc)}
    if data is None:
        return {"status": "skip", "path": path_str, "sha256": sha256}
    return {"status": "ok", "path": path_str, "sha256": sha256, "data": data}


def run_batch(
    paths: Iterable[str],
    db_path: str,
    worker: Any,
    *,
    workers: int = DEFAULT_WORKERS,
    time_budget: float = DEFAULT_TIME_BUDGET,
    store: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Process *paths* across *workers* threads. Returns {ok, skip, err, processed}.

    Submits in mini-batches of *workers* (mirrors ocr_parallel) so *time_budget*,
    when set, stops dispatching new work after the budget elapses. ``store(result)``
    persists an ``ok`` result and is called under a lock, so a plain sqlite writer
    is thread-safe. ``store`` is injectable for tests.
    """
    paths = list(paths)
    stats = {"ok": 0, "skip": 0, "err": 0, "processed": 0}
    batch = max(1, workers)
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=batch) as executor:
        i = 0
        while i < len(paths):
            if time_budget and (time.time() - t_start) >= time_budget:
                break
            chunk = paths[i:i + batch]
            futures = {executor.submit(process_one, p, db_path, worker): p for p in chunk}
            for future in as_completed(futures):
                result = future.result()
                stats["processed"] += 1
                stats[result["status"]] += 1
                if result["status"] == "ok" and store is not None:
                    with _db_lock:
                        store(result)
            i += batch
    return stats


class _OCRWorker:
    """Adapter wrapping a FlightAnalyzer OCR engine as an injectable worker."""

    def __init__(self, ocr: Any) -> None:
        self._ocr = ocr

    def process(self, path_str: str) -> Any:
        return self._ocr.extract_from_image(path_str)


def _build_default_worker(image_dir: str, db_path: str):
    """Construct the real OCR-backed worker + a DB store callable.

    Lazily imports FlightAnalyzer so the heavy OCR stack (pytesseract/opencv) is
    only required for real processing — not for importing this module or for the
    unit-tested harness above.
    """
    from pipeline.flight_analyzer import FlightAnalyzer

    fa = FlightAnalyzer(Path(image_dir), Path(db_path))

    def store(result: dict) -> None:
        fa.db.store_screenshot(result["sha256"], result["path"], result["data"])

    return _OCRWorker(fa.ocr), store


def _print_status(db_path: str) -> None:
    shots = 0
    if Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        try:
            shots = conn.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
        except sqlite3.OperationalError:
            shots = 0
        finally:
            conn.close()
    print(f"  RLSM unlabeled — screenshots processed: {shots:,}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Parallel runner for unlabeled RLSM screenshots.")
    parser.add_argument("--image-dir", default=None, help="Directory of screenshots to process.")
    parser.add_argument("--db", required=True, help="SQLite flight database path.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Worker threads.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N images.")
    parser.add_argument("--time-budget", type=float, default=DEFAULT_TIME_BUDGET,
                        help="Stop dispatching new work after this many seconds (0 = no limit).")
    parser.add_argument("--status", action="store_true", help="Show counts without processing.")
    args = parser.parse_args(argv)

    if args.status:
        _print_status(args.db)
        return 0

    if not args.image_dir:
        parser.error("--image-dir is required unless --status is given")

    paths = discover_images(args.image_dir)
    if args.limit is not None:
        paths = paths[:args.limit]
    if not paths:
        print(f"  no images found under {args.image_dir}")
        return 0

    # Pin OpenMP to one thread per worker *before* the OCR stack is imported
    # (FlightAnalyzer → pytesseract, lazily inside _build_default_worker). This
    # mirrors scripts/ocr_parallel.py and is the real throughput lever: without
    # it each of the N tesseract workers spawns its own OMP pool and they
    # oversubscribe the CPU. setdefault leaves an operator override intact.
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    worker, store = _build_default_worker(args.image_dir, args.db)
    stats = run_batch(paths, args.db, worker, workers=args.workers,
                      time_budget=args.time_budget, store=store)
    print(f"  processed {stats['processed']}/{len(paths)}  "
          f"ok:{stats['ok']} skip:{stats['skip']} err:{stats['err']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
