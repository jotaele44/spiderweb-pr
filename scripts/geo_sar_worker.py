#!/usr/bin/env python3
"""Run operations from the geographic job ledger in a process of its own.

The worker owns nothing: every fact about a job is in the ledger file.  Stop
it at any point and start another; the new one releases expired leases and
continues.  Neither the API server nor the frontend starts or supervises it.

    python scripts/geo_sar_worker.py --db outputs/geo_sar/jobs.sqlite \
        --artifact-root outputs/geo_sar/artifacts --until-idle

Exit status: 0 when it stopped with nothing left to do, 2 on a usage error.
A failed job is reported in the ledger, not by the worker's exit status.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.geo_sar.handlers import HANDLERS, Context, HandlerError  # noqa: E402
from spiderweb.geo_sar.jobs import JobLedger, StaleLease  # noqa: E402


def run(
    ledger: JobLedger,
    *,
    worker_id: str,
    artifact_root: Path,
    lease_seconds: float,
    poll_seconds: float,
    until_idle: bool,
    max_operations: int | None = None,
) -> int:
    done = 0
    while max_operations is None or done < max_operations:
        claim = ledger.claim(worker_id, lease_seconds=lease_seconds)
        if claim is None:
            if until_idle and not ledger.has_work():
                break
            time.sleep(poll_seconds)
            continue
        done += 1
        handler = HANDLERS.get(claim.kind)
        try:
            if handler is None:
                ledger.fail(
                    claim, f"no handler for kind {claim.kind!r}", retryable=False
                )
                continue
            result = handler(
                Context(
                    ledger=ledger,
                    claim=claim,
                    artifact_root=artifact_root,
                    lease_seconds=lease_seconds,
                )
            )
            ledger.complete(claim, result)
        except StaleLease:
            # Another worker holds the operation now.  Write nothing.
            continue
        except HandlerError as error:
            try:
                ledger.fail(claim, str(error), retryable=error.retryable)
            except StaleLease:
                continue
        except Exception as error:  # noqa: BLE001 - reported, never swallowed
            try:
                ledger.fail(claim, f"{type(error).__name__}: {error}", retryable=True)
            except StaleLease:
                continue
    return done


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}:{os.getpid()}")
    parser.add_argument("--lease-seconds", type=float, default=60.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument(
        "--until-idle",
        action="store_true",
        help="exit when no operation is pending or running",
    )
    args = parser.parse_args(argv)
    if args.lease_seconds <= 0 or args.poll_seconds <= 0:
        parser.error("--lease-seconds and --poll-seconds must be positive")
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    with JobLedger(args.db) as ledger:
        run(
            ledger,
            worker_id=args.worker_id,
            artifact_root=args.artifact_root,
            lease_seconds=args.lease_seconds,
            poll_seconds=args.poll_seconds,
            until_idle=args.until_idle,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
