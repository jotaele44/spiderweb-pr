"""
EarthGPT iOS — Lightweight logging utilities.

Designed for minimal overhead and readable terminal output on iOS / a-Shell.
"""

import sys
import time


def log(msg: str, prefix: str = "INFO") -> None:
    """Print a timestamped log line to stdout."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{prefix}] {msg}", flush=True)


def warn(msg: str) -> None:
    log(msg, prefix="WARN")


def error(msg: str) -> None:
    log(msg, prefix="ERR ")


def progress(done: int, total: int, interval: int = 10, label: str = "nodes") -> None:
    """Print progress at regular intervals."""
    if total == 0:
        return
    if done % interval == 0 or done == total:
        pct = 100.0 * done / total
        log(f"{done}/{total} {label} ({pct:.1f}%)", prefix="PROG")
