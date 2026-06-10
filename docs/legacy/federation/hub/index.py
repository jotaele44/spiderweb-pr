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


def _coerce_latlon(lat: Any, lon: Any) -> Optional[tuple]:
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        if -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180:
            return (float(lat), float(lon))
    return None


def record_point(record: Dict[str, Any]) -> Optional[tuple]:
    """Best-effort (lat, lon) for a record, from ``location`` or a GeoJSON Point.

    Accepts ``location.{lat|latitude}/{lon|longitude}`` or a ``geometry``/``geo``
    GeoJSON Point (``coordinates`` are ``[lon, lat]``). Returns None if absent.
    """
    loc = record.get("location")
    if isinstance(loc, dict):
        pt = _coerce_latlon(loc.get("lat", loc.get("latitude")),
                            loc.get("lon", loc.get("longitude")))
        if pt:
            return pt
    for key in ("geometry", "geo"):
        geom = record.get(key)
        if isinstance(geom, dict) and geom.get("type") == "Point":
            coords = geom.get("coordinates")
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                pt = _coerce_latlon(coords[1], coords[0])  # GeoJSON is [lon, lat]
                if pt:
                    return pt
    return None


def record_external_ids(record: Dict[str, Any]) -> List[tuple]:
    """All (key, value) external identifiers carried by a record's entities."""
    out: List[tuple] = []
    for ent in record.get("entities") or []:
        if isinstance(ent, dict):
            xids = ent.get("external_ids")
            if isinstance(xids, dict):
                for key, val in xids.items():
                    if isinstance(val, str) and val.strip():
                        out.append((str(key), val.strip()))
    return out


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
