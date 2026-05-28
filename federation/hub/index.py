"""In-memory indexes over normalized federation records.

Records are plain envelope dicts. Indexes are built fresh per query (temporary)
and discarded afterwards.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def record_normalized_names(record: Dict[str, Any]) -> List[str]:
    """All non-empty normalized entity names referenced by a record."""
    names = []
    for ent in record.get("entities") or []:
        if isinstance(ent, dict):
            norm = ent.get("normalized_name")
            if isinstance(norm, str) and norm:
                names.append(norm)
    return names


class FederationIndex:
    """Bundles the records plus lookup structures used by the query modes."""

    def __init__(self, records: List[Dict[str, Any]]):
        self.records: List[Dict[str, Any]] = list(records)
        self.by_normalized_name: Dict[str, List[Dict[str, Any]]] = {}
        self.by_source: Dict[str, List[Dict[str, Any]]] = {}
        self.timed: List[Dict[str, Any]] = []  # records with a parseable timestamp

        for rec in self.records:
            for norm in record_normalized_names(rec):
                self.by_normalized_name.setdefault(norm, []).append(rec)
            src = rec.get("source_id")
            if isinstance(src, str):
                self.by_source.setdefault(src, []).append(rec)
            if parse_timestamp(rec.get("timestamp")) is not None:
                self.timed.append(rec)

    def normalized_names(self) -> List[str]:
        return list(self.by_normalized_name.keys())
