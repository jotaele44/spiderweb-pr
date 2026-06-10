"""Deterministic cross-repo federation query.

``query_federation`` validates both producer packages (fail-closed), loads and
indexes their records, then resolves shared anchors into matched records plus
cross-producer evidence links. Four correlation strategies are available and
exposed as standalone helpers:

* A — temporal proximity   (:func:`correlate_temporal`)
* B — entity correlation   (:func:`correlate_entities`)
* C — source / confidence  (:func:`filter_by_confidence`)
* D — evidence bundle       (entity + date + confidence filters combined)

``mode`` gates synthetic data: ``"test"`` keeps synthetic rows; any other value
(e.g. ``"production"``) rejects them at validation time.
"""
from __future__ import annotations

import calendar
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .index import (
    FederationIndex,
    parse_timestamp,
    record_external_ids,
    record_normalized_names,
    record_point,
)
from .package_loader import load_package
from .normalize import normalize_package

_MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.upper(): i for i, m in enumerate(calendar.month_abbr) if m})

_STOPWORDS = frozenset(
    {"THE", "AND", "FOR", "WITH", "FROM", "THAT", "THIS", "RECORDS", "RELATED", "BETWEEN"}
)
_CONF_RE = re.compile(r"(?:under|below|less than|<)\s*(\d*\.\d+|\d+(?:\.\d+)?)", re.IGNORECASE)
_MONTH_YEAR_RE = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{4})\b")
_YEAR_RE = re.compile(r"\b(\d{4})\b")


def _score(record: Dict[str, Any]) -> Optional[float]:
    conf = record.get("confidence")
    if isinstance(conf, dict) and isinstance(conf.get("score"), (int, float)):
        return float(conf["score"])
    return None


def _ordered(a: str, b: str):
    return (a, b) if a <= b else (b, a)


# --------------------------------------------------------------------------
# Correlation strategies
# --------------------------------------------------------------------------


def correlate_temporal(records: List[Dict[str, Any]], window_days: int = 7) -> List[Dict[str, Any]]:
    """Mode A: link cross-producer records whose timestamps fall within window."""
    timed = []
    for rec in records:
        ts = parse_timestamp(rec.get("timestamp"))
        if ts is not None:
            timed.append((rec, ts))

    links: List[Dict[str, Any]] = []
    for i in range(len(timed)):
        for j in range(i + 1, len(timed)):
            ra, ta = timed[i]
            rb, tb = timed[j]
            if ra.get("producer") == rb.get("producer"):
                continue
            delta_days = abs((ta - tb).total_seconds()) / 86400.0
            if delta_days > window_days:
                continue
            src, tgt = _ordered(ra.get("record_id"), rb.get("record_id"))
            confidence = round(max(0.0, 1.0 - 0.5 * (delta_days / window_days)), 3)
            links.append(
                {
                    "source_record_id": src,
                    "target_record_id": tgt,
                    "link_type": "temporal_proximity",
                    "confidence": confidence,
                    "explanation": f"Records occur within {round(delta_days, 1)} day(s).",
                }
            )
    return links


def correlate_entities(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mode B: link cross-producer records sharing a normalized entity name."""
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        for norm in record_normalized_names(rec):
            by_name.setdefault(norm, []).append(rec)

    links: List[Dict[str, Any]] = []
    for norm, recs in by_name.items():
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                ra, rb = recs[i], recs[j]
                if ra.get("producer") == rb.get("producer"):
                    continue
                if ra.get("record_id") == rb.get("record_id"):
                    continue
                src, tgt = _ordered(ra.get("record_id"), rb.get("record_id"))
                scores = [s for s in (_score(ra), _score(rb)) if s is not None]
                confidence = round(min(scores), 3) if scores else 0.0
                links.append(
                    {
                        "source_record_id": src,
                        "target_record_id": tgt,
                        "link_type": "entity_correlation",
                        "match_basis": "normalized_name",
                        "confidence": confidence,
                        "explanation": f"Shared normalized entity name '{norm}'.",
                    }
                )
    return links


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def correlate_spatial(records: List[Dict[str, Any]], threshold_km: float = 1.0) -> List[Dict[str, Any]]:
    """Mode D: link cross-producer records whose locations fall within threshold_km."""
    pts = [(rec, record_point(rec)) for rec in records]
    pts = [(rec, pt) for rec, pt in pts if pt is not None]

    links: List[Dict[str, Any]] = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            ra, pa = pts[i]
            rb, pb = pts[j]
            if ra.get("producer") == rb.get("producer"):
                continue
            dist = _haversine_km(pa[0], pa[1], pb[0], pb[1])
            if dist > threshold_km:
                continue
            src, tgt = _ordered(ra.get("record_id"), rb.get("record_id"))
            confidence = round(max(0.0, 1.0 - dist / threshold_km), 3)
            links.append(
                {
                    "source_record_id": src,
                    "target_record_id": tgt,
                    "link_type": "spatial_proximity",
                    "match_basis": "location",
                    "confidence": confidence,
                    "explanation": f"Records within {round(dist, 2)} km.",
                }
            )
    return links


def correlate_by_external_id(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mode E: link cross-producer records sharing an external id (uei/duns/...)."""
    by_xid: Dict[tuple, List[Dict[str, Any]]] = {}
    for rec in records:
        for key, val in record_external_ids(rec):
            by_xid.setdefault((key, val), []).append(rec)

    links: List[Dict[str, Any]] = []
    for (key, val), recs in by_xid.items():
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                ra, rb = recs[i], recs[j]
                if ra.get("producer") == rb.get("producer"):
                    continue
                if ra.get("record_id") == rb.get("record_id"):
                    continue
                src, tgt = _ordered(ra.get("record_id"), rb.get("record_id"))
                scores = [s for s in (_score(ra), _score(rb)) if s is not None]
                confidence = round(min(scores), 3) if scores else 0.9
                links.append(
                    {
                        "source_record_id": src,
                        "target_record_id": tgt,
                        "link_type": "entity_correlation",
                        "match_basis": f"external_id:{key}",
                        "confidence": confidence,
                        "explanation": f"Shared external id {key}={val}.",
                    }
                )
    return links


def filter_by_confidence(records: List[Dict[str, Any]], threshold: float) -> List[Dict[str, Any]]:
    """Mode C helper: records whose confidence score is below ``threshold``."""
    out = []
    for rec in records:
        score = _score(rec)
        if score is not None and score < threshold:
            out.append(rec)
    return out


def _dedupe_links(links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Any, Dict[str, Any]] = {}
    for link in links:
        key = (
            frozenset((link["source_record_id"], link["target_record_id"])),
            link["link_type"],
        )
        if key not in best or link["confidence"] > best[key]["confidence"]:
            best[key] = link
    return sorted(
        best.values(),
        key=lambda l: (l["link_type"], l["source_record_id"], l["target_record_id"]),
    )


# --------------------------------------------------------------------------
# Lightweight deterministic query parser
# --------------------------------------------------------------------------


def parse_query(query_text: str, index: FederationIndex) -> Dict[str, Any]:
    """Best-effort extraction of entity / date-range / confidence threshold.

    Anything not found is None. Explicit kwargs to ``query_federation`` override
    whatever is parsed here.
    """
    parsed: Dict[str, Any] = {"entity": None, "start": None, "end": None, "max_confidence": None}
    if not query_text:
        return parsed
    upper = query_text.upper()

    # entity: match a salient token from a known normalized name.
    for norm in index.normalized_names():
        for token in norm.split():
            if len(token) >= 4 and token not in _STOPWORDS and re.search(rf"\b{re.escape(token)}\b", upper):
                parsed["entity"] = token
                break
        if parsed["entity"]:
            break

    # date range: "<Month> <Year>" first, else a bare year.
    m = _MONTH_YEAR_RE.search(query_text)
    if m and m.group(1).upper() in _MONTHS:
        month = _MONTHS[m.group(1).upper()]
        year = int(m.group(2))
        last = calendar.monthrange(year, month)[1]
        parsed["start"] = f"{year:04d}-{month:02d}-01"
        parsed["end"] = f"{year:04d}-{month:02d}-{last:02d}"
    else:
        y = _YEAR_RE.search(query_text)
        if y:
            year = int(y.group(1))
            parsed["start"] = f"{year:04d}-01-01"
            parsed["end"] = f"{year:04d}-12-31"

    c = _CONF_RE.search(query_text)
    if c:
        try:
            parsed["max_confidence"] = float(c.group(1))
        except ValueError:
            pass
    return parsed


def _matches_entity(record: Dict[str, Any], entity: str) -> bool:
    needle = entity.upper().strip()
    for norm in record_normalized_names(record):
        if needle == norm or needle in norm.split() or needle in norm:
            return True
    return False


def _in_range(ts: datetime, start: Optional[str], end: Optional[str]) -> bool:
    day = ts.date()
    if start:
        sd = parse_timestamp(start)
        if sd is not None and day < sd.date():
            return False
    if end:
        ed = parse_timestamp(end)
        if ed is not None and day > ed.date():
            return False
    return True


def _record_view(record: Dict[str, Any], matched_on: List[str]) -> Dict[str, Any]:
    return {
        "producer": record.get("producer"),
        "record_type": record.get("record_type"),
        "record_id": record.get("record_id"),
        "timestamp": record.get("timestamp"),
        "confidence": _score(record),
        "matched_on": matched_on,
        "lineage_count": len(record.get("lineage") or []),
    }


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def query_federation(
    query_text: str,
    packages: List[Union[str, Path]],
    mode: str = "test",
    *,
    window_days: int = 7,
    entity: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """Run a deterministic cross-repo query over validated export packages."""
    reject_synthetic = mode != "test"

    normalized = [
        normalize_package(load_package(pkg), reject_synthetic=reject_synthetic)
        for pkg in packages
    ]
    validation = {n["producer"]: n["status"] for n in normalized}

    if any(n["status"] != "PASS" for n in normalized):
        return {
            "query": query_text,
            "mode": mode,
            "records": [],
            "links": [],
            "validation": validation,
            "errors": {n["producer"]: n["errors"] for n in normalized if n["errors"]},
        }

    all_records: List[Dict[str, Any]] = []
    for n in normalized:
        all_records.extend(n["records"])

    index = FederationIndex(all_records)
    parsed = parse_query(query_text, index)
    entity = entity if entity is not None else parsed["entity"]
    start = start if start is not None else parsed["start"]
    end = end if end is not None else parsed["end"]
    max_confidence = max_confidence if max_confidence is not None else parsed["max_confidence"]

    has_filter = bool(entity or start or end or (max_confidence is not None))

    selected: List[tuple] = []
    if not has_filter:
        selected = [(rec, []) for rec in all_records]
    else:
        for rec in all_records:
            reasons: List[str] = []
            ok = True
            if entity:
                if _matches_entity(rec, entity):
                    reasons.append("entity")
                else:
                    ok = False
            if ok and (start or end):
                ts = parse_timestamp(rec.get("timestamp"))
                if ts is not None and _in_range(ts, start, end):
                    reasons.append("time_window")
                else:
                    ok = False
            if ok and max_confidence is not None:
                score = _score(rec)
                if score is not None and score < max_confidence:
                    reasons.append("confidence")
                else:
                    ok = False
            if ok:
                selected.append((rec, reasons))

    selected_records = [rec for rec, _ in selected]
    links = _dedupe_links(
        correlate_temporal(selected_records, window_days=window_days)
        + correlate_entities(selected_records)
        + correlate_spatial(selected_records)
        + correlate_by_external_id(selected_records)
    )

    return {
        "query": query_text,
        "mode": mode,
        "records": [_record_view(rec, reasons) for rec, reasons in selected],
        "links": links,
        "validation": validation,
    }
