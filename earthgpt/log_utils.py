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


def get_structured_logger(session_id: str = None) -> "logging.Logger":
    """Return a logger emitting structured JSON with session_id."""
    import logging, json

    class JsonFormatter(logging.Formatter):
        def __init__(self, sid: str) -> None:
            super().__init__()
            self.sid = sid

        def format(self, record: logging.LogRecord) -> str:
            return json.dumps({
                "level": record.levelname,
                "message": record.getMessage(),
                "session_id": self.sid,
                "logger": record.name,
                "timestamp": self.formatTime(record),
            })

    logger = logging.getLogger(f"earthgpt.{session_id or 'default'}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter(session_id))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
