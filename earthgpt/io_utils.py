"""
EarthGPT iOS — I/O utilities for JSONL reading and writing.

All pipeline stages consume and produce JSONL files.
These helpers ensure safe, resumable, and tolerant I/O.
"""

import json
import os
from pathlib import Path
from typing import Generator, List, Optional


def iter_jsonl(path: str | Path) -> Generator[dict, None, None]:
    """Yield parsed rows from a JSONL file. Skips malformed lines silently."""
    path = Path(path)
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def read_jsonl(path: str | Path) -> List[dict]:
    """Read all rows from a JSONL file into a list."""
    return list(iter_jsonl(path))


def write_jsonl(path: str | Path, rows: List[dict], mode: str = "w") -> None:
    """Write rows to a JSONL file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: str | Path, row: dict) -> None:
    """Append a single row to a JSONL file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_done_ids(path: str | Path, id_field: str = "node_id") -> set:
    """Return the set of already-processed node IDs from an output JSONL."""
    done = set()
    for row in iter_jsonl(path):
        val = row.get(id_field)
        if val is not None:
            done.add(val)
    return done


def count_jsonl(path: str | Path) -> tuple[int, int]:
    """Return (valid_count, invalid_count) for a JSONL file."""
    valid, invalid = 0, 0
    path = Path(path)
    if not path.exists():
        return 0, 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
                valid += 1
            except json.JSONDecodeError:
                invalid += 1
    return valid, invalid
