#!/usr/bin/env python3
"""RLSM location normalization helpers.

Registry loader for airport/place/LZ/hangar/corridor alias resolution.
The module preserves raw text and returns explicit unresolved records instead of guessing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

import yaml

VALID_VISIBILITY = {"V0", "V1", "V2", "V3", "V4"}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = text.replace("ñ", "n")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _record_identity(record: Dict[str, Any]) -> str:
    for field in ("airport_id", "canonical_id", "lz_id", "hangar_id", "corridor_id", "project_location_id"):
        if record.get(field):
            return str(record[field])
    return str(record.get("canonical_name", ""))


def load_simple_yaml(path: Path) -> Dict[str, Any]:
    """Load a registry/config YAML file as a top-level mapping."""
    if not path.exists():
        raise FileNotFoundError(path)
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Top-level YAML content must be a mapping: {path}")
    return parsed


class AliasIndex:
    def __init__(self) -> None:
        self.alias_to_record: Dict[str, Dict[str, Any]] = {}
        self.collisions: Dict[str, List[Dict[str, Any]]] = {}

    def add(self, alias: str, record: Dict[str, Any]) -> None:
        key = _norm(alias)
        if not key:
            return
        if key in self.alias_to_record:
            existing = self.alias_to_record[key]
            same_identity = _record_identity(existing) == _record_identity(record)
            same_name = _norm(existing.get("canonical_name")) == _norm(record.get("canonical_name"))
            if same_identity or same_name:
                return
            self.collisions.setdefault(key, [existing]).append(record)
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
        ("airport_registry.yaml", "airports"),
        ("place_aliases.yaml", "places"),
        ("lz_registry.yaml", "known_lz_candidates"),
        ("hangar_registry.yaml", "known_hangar_candidates"),
        # corridor_aliases.yaml is the ontology alias source; corridor_registry.yaml
        # is the separate observed-corridor catalog (canonical_id / flights_logged).
        ("corridor_aliases.yaml", "corridors"),
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
