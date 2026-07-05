"""Load a producer export package (manifest + JSONL streams) from disk.

Fail-closed: a missing manifest or a missing/declared-but-absent stream file is
recorded as an error and yields empty rows rather than raising. Downstream
validation turns any error into a producer-level FAIL.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Union

from ..namespace import prefix_for_producer


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_package(package_dir: Union[str, Path]) -> Dict[str, Any]:
    """Load a package directory.

    Returns a dict with:
        dir       : str path
        producer  : manifest producer label or None
        prefix    : expected ID prefix (from manifest or derived) or None
        synthetic : manifest synthetic flag (bool)
        manifest  : the parsed manifest or None
        streams   : {stream_stem: [row, ...]}
        records   : flat list of all rows
        errors    : list of load-time error strings (empty == clean load)
    """
    out_dir = Path(package_dir)
    result: Dict[str, Any] = {
        "dir": str(out_dir),
        "producer": None,
        "prefix": None,
        "synthetic": False,
        "manifest": None,
        "streams": {},
        "records": [],
        "errors": [],
    }

    manifest_path = out_dir / "manifest.json"
    if not manifest_path.is_file():
        result["errors"].append(f"missing manifest.json in {out_dir}")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result["errors"].append(f"unreadable manifest.json: {exc}")
        return result

    result["manifest"] = manifest
    result["producer"] = manifest.get("producer")
    result["synthetic"] = bool(manifest.get("synthetic", False))
    result["prefix"] = manifest.get("prefix") or prefix_for_producer(manifest.get("producer", ""))

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        result["errors"].append("manifest declares no files")
        return result

    streams: Dict[str, List[Dict[str, Any]]] = {}
    records: List[Dict[str, Any]] = []
    for spec in files:
        filename = spec.get("filename") if isinstance(spec, dict) else None
        if not filename:
            result["errors"].append("manifest file entry missing 'filename'")
            continue
        path = out_dir / filename
        if not path.is_file():
            result["errors"].append(f"declared file missing on disk: {filename}")
            continue
        try:
            rows = _read_jsonl(path)
        except (json.JSONDecodeError, OSError) as exc:
            result["errors"].append(f"unreadable stream {filename}: {exc}")
            continue
        stem = filename[:-6] if filename.endswith(".jsonl") else filename
        streams[stem] = rows
        records.extend(rows)

    result["streams"] = streams
    result["records"] = records
    return result
