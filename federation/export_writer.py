"""Write a spiderweb-pr federation export package.

A package is a directory containing one ``<stream>.jsonl`` file per record
stream plus a ``manifest.json`` sidecar. Each JSONL line is one evidence
envelope. Streams: airspace_events, observations, tracks, sources.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from .envelope import EvidenceEnvelope, entity_ref
from .namespace import PREFIX, PRODUCER, namespaced_id

SCHEMA_VERSION = "0.1"

# stream filename stem -> envelope record_type
STREAM_RECORD_TYPES = {
    "airspace_events": "airspace_event",
    "observations": "observation",
    "tracks": "track",
    "sources": "source",
}

# Minimal name normalizer mirroring the contract used by the funding producer,
# so operator/org names join across producers on ``normalized_name``.
_LEGAL_SUFFIXES = frozenset(
    {
        "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LLC",
        "LTD", "LP", "LLP", "PSC", "PC", "SA", "SE", "GMBH", "PLC", "LIMITED",
        "INTL", "INTERNATIONAL",
    }
)
_AMP = re.compile(r"\s*&\s*")
_DOTTED = re.compile(r"\b(?:[A-Z]\.){2,}")
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")
_SPACE = re.compile(r"\s+")


def normalize_name(name: Optional[str]) -> str:
    """Canonical alphanumeric-uppercase form for cross-producer entity joins."""
    if not name:
        return ""
    s = str(name).upper()
    s = _AMP.sub(" AND ", s)
    s = _DOTTED.sub(lambda m: m.group(0).replace(".", ""), s)
    s = _NON_ALNUM.sub(" ", s)
    s = _SPACE.sub(" ", s).strip()
    tokens = [t for t in s.split(" ") if t and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce(record: Union[EvidenceEnvelope, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(record, EvidenceEnvelope):
        return record.to_dict()
    if isinstance(record, dict):
        return record
    raise TypeError(f"record must be EvidenceEnvelope or dict, got {type(record)!r}")


def write_stream(path: Union[str, Path], records: Iterable) -> int:
    """Write records as one JSON object per line. Returns the count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(_coerce(record), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def write_package(
    out_dir: Union[str, Path],
    streams: Mapping[str, Iterable],
    *,
    synthetic: bool = False,
    producer: str = PRODUCER,
    prefix: str = PREFIX,
    record_types: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Write every stream + a manifest.json. Returns the manifest dict.

    ``record_types`` overrides the stream-stem -> record_type map for the
    manifest (used by hub tests that emit a different producer's package).
    ``prefix`` is the ID namespace recorded in the manifest.
    """
    type_map = dict(STREAM_RECORD_TYPES)
    if record_types:
        type_map.update(record_types)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []
    for name, records in streams.items():
        filename = f"{name}.jsonl"
        count = write_stream(out / filename, records)
        files.append(
            {
                "filename": filename,
                "record_type": type_map.get(name, name),
                "record_count": count,
                "sha256": _sha256(out / filename),
            }
        )
    manifest = {
        "producer": producer,
        "prefix": prefix,
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "synthetic": bool(synthetic),
        "files": files,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


# --------------------------------------------------------------------------
# Envelope builders
# --------------------------------------------------------------------------


def _point(lat: Optional[float], lon: Optional[float]) -> Optional[Dict[str, Any]]:
    if lat is None or lon is None:
        return None
    return {"type": "Point", "coordinates": [lon, lat]}


def org_entity_ref(raw_entity_id: str, name: str) -> Dict[str, str]:
    """Build an entities[] member for an operator/org observed in airspace."""
    return entity_ref(namespaced_id(raw_entity_id), name, normalize_name(name))


def build_airspace_event(
    raw_event_id: str,
    *,
    source_id: str,
    event_time: Optional[str],
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    entities: Optional[List[Dict[str, Any]]] = None,
    confidence_score: float = 0.82,
    synthetic: bool = False,
    lineage: Optional[List[Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        producer=PRODUCER,
        record_type="airspace_event",
        record_id=namespaced_id(raw_event_id),
        source_id=namespaced_id(source_id),
        timestamp=event_time,
        geo=_point(lat, lon),
        entities=list(entities or []),
        confidence={"score": confidence_score, "method": "producer_contract"},
        lineage=list(lineage or [{"stage": "intake"}]),
        payload=dict(payload or {}),
        synthetic=synthetic,
    )
