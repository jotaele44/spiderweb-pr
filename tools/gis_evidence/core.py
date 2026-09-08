"""Strict byte/identity helpers shared by parsers, metrics and benchmarks."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def write_new(path: Path, value: Any) -> None:
    """Idempotent only for identical bytes; never overwrite a different receipt."""
    data = canonical_json(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"OUTPUT_ALREADY_EXISTS_DIFFERENT:{path}")
        return
    with path.open("xb") as stream:
        stream.write(data)


def checked_bytes(path: Path, expected_sha256: str, expected_size: int | None = None) -> bytes:
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("INVALID_SHA256_CONTRACT")
    if not path.is_file():
        raise FileNotFoundError(f"FROZEN_ARTIFACT_UNAVAILABLE:{path}")
    data = path.read_bytes()
    if expected_size is not None and len(data) != expected_size:
        raise ValueError(f"BYTE_COUNT_MISMATCH:{len(data)}:{expected_size}")
    if digest(data) != expected_sha256:
        raise ValueError("SOURCE_SHA256_MISMATCH")
    return data


def id_index(rows: list[dict], field: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for n, row in enumerate(rows):
        key = row.get(field)
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"INVALID_STABLE_ID:{field}:row={n}")
        if key in result:
            raise ValueError(f"DUPLICATE_STABLE_ID:{key}")
        result[key] = row
    return result


def set_receipt(a: set[str], b: set[str]) -> dict:
    parts = {"intersection": a & b, "a_only": a - b, "b_only": b - a, "union": a | b, "symmetric_difference": a ^ b}
    return {"counts": {k: len(v) for k, v in parts.items()}, "ids": {k: sorted(v) for k, v in parts.items()}}


def load_geojson(path: Path, expected_sha256: str, stable_id: str) -> tuple[dict, dict[str, dict]]:
    obj = json.loads(checked_bytes(path, expected_sha256))
    if not isinstance(obj, dict) or obj.get("type") != "FeatureCollection" or not isinstance(obj.get("features"), list):
        raise ValueError("EXPECTED_FEATURECOLLECTION")
    rows = obj["features"]
    if not rows:
        raise ValueError("EMPTY_FEATURE_DENOMINATOR")
    props = []
    for n, f in enumerate(rows):
        if not isinstance(f, dict) or f.get("type") != "Feature" or not isinstance(f.get("properties"), dict):
            raise ValueError(f"INVALID_FEATURE:{n}")
        props.append(f["properties"])
    indexed = id_index(props, stable_id)
    return obj, {key: rows[n] for n, key in enumerate(indexed)}


def positive_finite(value: Any, name: str, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"NONFINITE_OR_NONNUMERIC:{name}")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"NONPOSITIVE:{name}")
    return float(value)
