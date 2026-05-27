#!/usr/bin/env python3
"""RLSM location normalization helpers.

Pure-stdlib registry loader for airport/place/LZ/hangar/POI alias resolution.
The module preserves raw text and returns explicit unresolved records instead of guessing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

VALID_VISIBILITY = {"V0", "V1", "V2", "V3", "V4"}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = text.replace("ñ", "n")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if raw in {"null", "None", ""}:
        return None
    if raw in {"true", "false"}:
        return raw == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _parse_inline_list(raw: str) -> List[str]:
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return [raw]
    inner = raw[1:-1].strip()
    if not inner:
        return []
    return [part.strip().strip('"').strip("'") for part in inner.split(",")]


def load_simple_yaml(path: Path) -> Dict[str, Any]:
    """Load the small YAML subset used by configs without external dependencies."""
    if not path.exists():
        raise FileNotFoundError(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    root: Dict[str, Any] = {}
    stack: List[tuple[int, Any]] = [(-1, root)]

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if text.startswith("- "):
            item_text = text[2:]
            if not isinstance(parent, list):
                continue
            if ":" in item_text:
                key, value = item_text.split(":", 1)
                item: Dict[str, Any] = {key.strip(): _parse_scalar(value) if value.strip() else None}
                parent.append(item)
                stack.append((indent, item))
            else:
                parent.append(_parse_scalar(item_text))
            continue

        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            # Look ahead: default to list for plural registry keys, otherwise dict.
            container: Any = [] if key.endswith("s") or key in {"places", "airports", "corridors"} else {}
            parent[key] = container
            stack.append((indent, container))
        elif value.startswith("[") and value.endswith("]"):
            parent[key] = _parse_inline_list(value)
        else:
            parent[key] = _parse_scalar(value)
    return root


class AliasIndex:
    def __init__(self) -> None:
        self.alias_to_record: Dict[str, Dict[str, Any]] = {}
        self.collisions: Dict[str, List[Dict[str, Any]]] = {}

    def add(self, alias: str, record: Dict[str, Any]) -> None:
        key = _norm(alias)
        if not key:
            return
        if key in self.alias_to_record:
            self.collisions.setdefault(key, [self.alias_to_record[key]]).append(record)
            return
        self.alias_to_record[key] = record

    def resolve(self, raw_text: str, namespace: str = "location") -> Dict[str, Any]:
        key = _norm(raw_text)
        if key in self.collisions:
            return {
                "raw_text": raw_text,
                "normalized_id": None,
                "canonical_name": None,
                "namespace": namespace,
                "resolution_status": "collision_review_required",
                "visibility": "V2",
                "candidate_count": len(self.collisions[key]),
            }
        record = self.alias_to_record.get(key)
        if record:
            return {
                "raw_text": raw_text,
                "normalized_id": record.get("canonical_id") or record.get("airport_id") or record.get("lz_id") or record.get("hangar_id") or record.get("corridor_id"),
                "canonical_name": record.get("canonical_name"),
                "namespace": namespace,
                "resolution_status": "resolved",
                "visibility": record.get("visibility", "V3"),
                "record": record,
            }
        return {
            "raw_text": raw_text,
            "normalized_id": None,
            "canonical_name": None,
            "namespace": namespace,
            "resolution_status": "unresolved",
            "visibility": "V0",
        }


def build_location_index(config_dir: Path = Path("configs")) -> AliasIndex:
    index = AliasIndex()
    for filename, collection_key in [
        ("place_aliases.yaml", "places"),
        ("airport_registry.yaml", "airports"),
        ("lz_registry.yaml", "known_lz_candidates"),
        ("hangar_registry.yaml", "known_hangar_candidates"),
        ("corridor_registry.yaml", "corridors"),
    ]:
        path = config_dir / filename
        if not path.exists():
            continue
        data = load_simple_yaml(path)
        for record in data.get(collection_key, []) or []:
            for field in ("canonical_name", "iata", "icao"):
                if record.get(field):
                    index.add(str(record[field]), record)
            for alias in record.get("aliases", []) or []:
                index.add(alias, record)
    return index


def normalize_location(raw_text: str, config_dir: Path = Path("configs"), namespace: str = "location") -> Dict[str, Any]:
    return build_location_index(config_dir).resolve(raw_text, namespace=namespace)


def normalize_flight_locations(event: Dict[str, Any], config_dir: Path = Path("configs")) -> Dict[str, Any]:
    result = dict(event)
    for raw_field, normalized_field in [
        ("origin_raw", "origin_normalized"),
        ("destination_raw", "destination_normalized"),
        ("origin_airport", "origin_airport_normalized"),
        ("destination_airport", "destination_airport_normalized"),
    ]:
        if raw_field in event and event.get(raw_field):
            result[normalized_field] = normalize_location(str(event[raw_field]), config_dir=config_dir)
    result["raw_text_preserved"] = True
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_text")
    parser.add_argument("--config-dir", default="configs")
    args = parser.parse_args()
    print(json.dumps(normalize_location(args.raw_text, Path(args.config_dir)), indent=2, ensure_ascii=False))
