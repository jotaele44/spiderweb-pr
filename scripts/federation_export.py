#!/usr/bin/env python3
"""Project spiderweb's evidence-envelope streams into PRII canonical streams.

spiderweb's native producer export is a domain envelope (events / observations /
tracks / sources with spiderweb_* schemas). This adapter re-projects those stream
files onto the Hub's canonical contract so the Hub can aggregate spiderweb
alongside the other producers:

  * each source record       -> one `sources` row + a `sensor_source` entity
  * each event/observation/track -> one `entities` row (airspace_event/observation/track)
  * each subject (aircraft callsign) -> one `entities` row (entity_type=aircraft)
  * record -[reported_by]-> source
  * record -[observed]-> aircraft  (when subject_id / callsign present)

Reads a package dir (defaults to exports/samples, accepting `<name>.jsonl` or
`<name>.sample.jsonl`) and writes `exports/federation/{sources,entities,
relationships}.jsonl` + a Hub-conformant manifest. Deterministic ids. Stdlib only.

NOTE (Z2): the canonical entity schema now carries an optional `location`
{lat, lon}; record entities (observations/events/tracks) project a representative
WGS84 point from their GeoJSON geometry/path so the query-hub's correlate_spatial
can join them against other producers' entities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCER = "spiderweb-pr"
CONTRACT_VERSION = "1.0.0"
PRODUCER_SCRIPT = "scripts/federation_export.py"
STREAM_SCHEMA = {
    "sources": "federation_source.schema.json",
    "entities": "federation_entity.schema.json",
    "relationships": "federation_relationship.schema.json",
}
# spiderweb stream file -> canonical entity_type for its records
RECORD_STREAMS = {
    "airspace_events": "airspace_event",
    "observations": "airspace_observation",
    "tracks": "airspace_track",
}


def _fid(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{hashlib.sha256('|'.join(str(p) for p in parts).encode()).hexdigest()[:32]}"


def _norm(name: str) -> str:
    return " ".join(str(name).strip().upper().split())


def _score(conf: Any) -> float:
    if isinstance(conf, dict):
        return float(conf.get("score", 0.5))
    try:
        return float(conf)
    except (TypeError, ValueError):
        return 0.5


def _lineage(phase: str) -> dict[str, Any]:
    return {
        "producer_script": PRODUCER_SCRIPT,
        "producer_phase": phase,
        "source_inputs": ["exports/<package>/{sources,observations,airspace_events,tracks}.jsonl"],
        "extraction_method": "deterministic_envelope_projection",
    }


def _aircraft(record: dict[str, Any]) -> str | None:
    return record.get("subject_id") or (record.get("attributes") or {}).get("callsign")


def _point(record: dict[str, Any]) -> dict[str, float] | None:
    """Representative WGS84 {lat, lon} from a record's GeoJSON Point geometry or
    LineString path (first vertex). GeoJSON order is [lon, lat]. Returns None when
    absent or out of range (Z2)."""
    coords = None
    geom = record.get("geometry")
    if isinstance(geom, dict) and geom.get("type") == "Point":
        c = geom.get("coordinates")
        if isinstance(c, list) and len(c) >= 2:
            coords = c
    if coords is None:
        path = record.get("path")
        if isinstance(path, dict) and path.get("type") == "LineString":
            cc = path.get("coordinates")
            if isinstance(cc, list) and cc and isinstance(cc[0], list) and len(cc[0]) >= 2:
                coords = cc[0]
    if coords is None:
        return None
    lon, lat = coords[0], coords[1]
    if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return {"lat": round(float(lat), 6), "lon": round(float(lon), 6)}


def build_streams(sources_in: list[dict], records_by_stream: dict[str, list[dict]], now: str) -> dict[str, list[dict]]:
    sources: dict[str, dict] = {}
    src_entity: dict[str, str] = {}
    entities: dict[str, dict] = {}
    relationships: dict[str, dict] = {}

    for s in sources_in:
        raw = s.get("source_id") or s.get("id")
        synthetic = bool(s.get("is_synthetic"))
        score = _score(s.get("confidence"))
        sid = _fid("src", raw)
        sources[sid] = {
            "source_id": sid, "source_type": s.get("kind") or "unknown",
            "source_name": raw, "source_ref": raw, "confidence": score,
            "lineage": _lineage("SOURCE_REGISTRY"), "synthetic": synthetic,
            "created_at": s.get("first_seen_at") or now, "extracted_at": now,
        }
        ent_id = _fid("ent", "source", raw)
        src_entity[raw] = ent_id
        entities[ent_id] = {
            "entity_id": ent_id, "source_id": sid, "name": raw,
            "normalized_name": _norm(raw), "entity_type": "sensor_source",
            "jurisdiction": "PR", "confidence": score, "lineage": _lineage("SOURCE_ENTITY"),
            "synthetic": synthetic, "created_at": s.get("first_seen_at") or now, "extracted_at": now,
        }

    for stream, etype in RECORD_STREAMS.items():
        for r in records_by_stream.get(stream, []):
            raw_src = r.get("source_id")
            sid = sources.get(_fid("src", raw_src), {}).get("source_id") or _fid("src", raw_src)
            synthetic = bool(r.get("is_synthetic"))
            score = _score(r.get("confidence"))
            when = r.get("observed_at") or r.get("event_time") or now
            rid = r.get("id")
            ent_id = _fid("ent", stream, rid)
            entities[ent_id] = {
                "entity_id": ent_id, "source_id": sid,
                "name": f"{etype} {rid[:8]}", "normalized_name": _norm(f"{etype} {rid[:8]}"),
                "entity_type": etype, "jurisdiction": "PR", "confidence": score,
                "lineage": _lineage("RECORD_ENTITY"), "synthetic": synthetic,
                "created_at": when, "extracted_at": now,
            }
            # Z2: project a representative point so correlate_spatial can join this
            loc = _point(r)
            if loc:
                entities[ent_id]["location"] = loc
            # reported_by -> source entity
            tgt = src_entity.get(raw_src) or _fid("ent", "source", raw_src)
            relationships.update(_rel(ent_id, "reported_by", tgt, sid, score, synthetic, when, now))
            # observed -> aircraft
            ac = _aircraft(r)
            if ac:
                ac_id = _fid("ent", "aircraft", _norm(ac))
                entities.setdefault(ac_id, {
                    "entity_id": ac_id, "source_id": sid, "name": ac,
                    "normalized_name": _norm(ac), "entity_type": "aircraft",
                    "jurisdiction": "PR", "confidence": score, "lineage": _lineage("AIRCRAFT_ENTITY"),
                    "synthetic": synthetic, "created_at": when, "extracted_at": now,
                })
                relationships.update(_rel(ent_id, "observed", ac_id, sid, score, synthetic, when, now))

    return {"sources": list(sources.values()),
            "entities": list(entities.values()),
            "relationships": list(relationships.values())}


def _rel(src_ent, rtype, tgt_ent, sid, score, synthetic, created, now):
    rid = _fid("rel", src_ent, rtype, tgt_ent)
    return {rid: {
        "relationship_id": rid, "source_id": sid, "source_entity_id": src_ent,
        "target_entity_id": tgt_ent, "relationship_type": rtype, "evidence_source_id": sid,
        "confidence": score, "lineage": _lineage("RELATIONSHIP"),
        "synthetic": synthetic, "created_at": created, "extracted_at": now,
    }}


# Primary-key field per canonical stream (used by the diff mode).
_ID_FIELD = {
    "sources": "source_id",
    "entities": "entity_id",
    "relationships": "relationship_id",
}


def _load_existing_streams(prev_dir: Path) -> dict[str, list[dict]]:
    """Load {sources,entities,relationships}.jsonl from a previous export dir."""
    out: dict[str, list[dict]] = {}
    for stream in ("sources", "entities", "relationships"):
        fp = prev_dir / f"{stream}.jsonl"
        out[stream] = (
            [json.loads(ln) for ln in fp.read_text().splitlines() if ln.strip()]
            if fp.exists() else []
        )
    return out


def diff_streams(new_streams: dict[str, list[dict]],
                 prev_streams: dict[str, list[dict]]) -> dict[str, Any]:
    """Per-stream added/removed/changed record diff keyed on the stream's id."""
    report: dict[str, Any] = {}
    for stream in ("sources", "entities", "relationships"):
        idf = _ID_FIELD[stream]
        new_by = {r[idf]: r for r in new_streams.get(stream, [])}
        old_by = {r[idf]: r for r in prev_streams.get(stream, [])}
        added = sorted(set(new_by) - set(old_by))
        removed = sorted(set(old_by) - set(new_by))
        changed = sorted(
            k for k in (set(new_by) & set(old_by))
            if json.dumps(new_by[k], sort_keys=True)
            != json.dumps(old_by[k], sort_keys=True)
        )
        report[stream] = {
            "added": len(added), "removed": len(removed), "changed": len(changed),
            "added_ids": added, "removed_ids": removed, "changed_ids": changed,
        }
    return report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_stream(pkg: Path, name: str) -> list[dict]:
    for candidate in (pkg / f"{name}.jsonl", pkg / f"{name}.sample.jsonl"):
        if candidate.exists():
            return [json.loads(line) for line in candidate.read_text().splitlines() if line.strip()]
    return []


def write_package(streams, out_dir: Path, mode: str, now: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for stream in ("sources", "entities", "relationships"):
        rows = streams[stream]
        if not rows:
            continue
        fpath = out_dir / f"{stream}.jsonl"
        fpath.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        files.append({"filename": f"{stream}.jsonl", "stream": stream, "record_count": len(rows),
                      "sha256": _sha256(fpath), "schema_id": STREAM_SCHEMA[stream]})
    digest = hashlib.sha256(
        ("|".join(f"{f['filename']}:{f['sha256']}" for f in files) + f"|{mode}").encode()
    ).hexdigest()[:32]
    manifest = {"package_id": f"pkg_{digest}", "producer": PRODUCER,
                "export_contract_version": CONTRACT_VERSION, "mode": mode,
                "created_at": now, "extracted_at": now,
                "federation": {"producer_repo": PRODUCER, "hub_parent": "thehub-pr"},
                "files": files}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return out_dir / "manifest.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Project spiderweb envelope streams to PRII canonical streams.")
    ap.add_argument("--package", default=str(REPO_ROOT / "exports/samples"))
    ap.add_argument("--out", default=str(REPO_ROOT / "exports/federation"))
    ap.add_argument("--mode", default="test", choices=["test", "production"])
    ap.add_argument("--dry-run", action="store_true",
                    help="Build streams and report counts without writing any files.")
    ap.add_argument("--diff-from", default=None,
                    help="Compare the would-be export against a previous export dir.")
    args = ap.parse_args()

    pkg = Path(args.package)
    sources_in = _read_stream(pkg, "sources")
    records = {name: _read_stream(pkg, name) for name in RECORD_STREAMS}
    if not sources_in and not any(records.values()):
        print(f"no envelope streams found in {pkg} — nothing to export")
        return 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    streams = build_streams(sources_in, records, now)

    if args.mode == "production":
        synthetic = [r for s in streams.values() for r in s if r.get("synthetic")]
        if synthetic:
            print(f"FAIL — {len(synthetic)} synthetic rows are not allowed in production mode")
            return 1

    counts = {k: len(v) for k, v in streams.items()}

    if args.diff_from:
        prev = _load_existing_streams(Path(args.diff_from))
        diff = diff_streams(streams, prev)
        print(json.dumps({"diff_from": args.diff_from, "diff": diff}, indent=2))

    if args.dry_run:
        print(json.dumps({"dry_run": True, "out": args.out, "counts": counts,
                          "would_write": [f"{s}.jsonl" for s, n in counts.items() if n]
                          + ["manifest.json"]}, indent=2))
        return 0

    manifest_path = write_package(streams, Path(args.out), args.mode, now)
    print(f"wrote {manifest_path} — {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
